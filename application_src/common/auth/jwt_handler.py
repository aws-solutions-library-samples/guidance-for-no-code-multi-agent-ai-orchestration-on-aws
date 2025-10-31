"""
JWT token handler service for authentication system.

This module provides comprehensive JWT token handling including validation,
parsing, signature verification, and token refresh management.
"""

import logging
import json
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

import jwt
from jwt.algorithms import RSAAlgorithm
import httpx

from .interfaces import TokenValidator
from .types import (
    JWTToken,
    TokenValidationError,
    AuthenticationError
)

logger = logging.getLogger(__name__)


class JWTHandler(TokenValidator):
    """
    JWT token handler with validation and parsing capabilities.
    
    This service provides comprehensive JWT token management including:
    - Token structure validation
    - Signature verification against JWKS
    - Claim extraction and validation
    - Token expiration checking
    - JWKS caching for performance
    """
    
    def __init__(self, default_audience: Optional[str] = None):
        self.default_audience = default_audience
        self._jwks_cache: Dict[str, Dict[str, Any]] = {}
        self._jwks_cache_expiry: Dict[str, datetime] = {}
        
    async def validate_token(self, token: str, audience: Optional[str] = None) -> JWTToken:
        """
        Validate JWT token structure, signature, and claims.
        
        Args:
            token: Raw JWT token string
            audience: Expected audience claim (defaults to configured audience)
            
        Returns:
            JWTToken: Parsed and validated token object
            
        Raises:
            TokenValidationError: If token is invalid
        """
        try:
            # First decode without verification to get header and payload
            jwt_token = await self.decode_token(token, verify_signature=False)
            
            # Get issuer from token to fetch JWKS
            issuer = jwt_token.issuer
            if not issuer:
                raise TokenValidationError("Token missing issuer claim")
            
            # Get JWKS for the issuer
            jwks = await self._get_jwks_for_issuer(issuer)
            
            # Verify signature
            signature_valid = await self.verify_signature(token, jwks)
            if not signature_valid:
                raise TokenValidationError("Token signature verification failed")
            
            # Validate audience if provided
            expected_audience = audience or self.default_audience
            if expected_audience and jwt_token.audience != expected_audience:
                raise TokenValidationError(f"Invalid audience. Expected: {expected_audience}, Got: {jwt_token.audience}")
            
            # Check if token is expired
            if jwt_token.is_expired:
                raise TokenValidationError("Token has expired")
            
            # Mark token as valid
            jwt_token.is_valid = True
            
            return jwt_token
            
        except TokenValidationError:
            raise
        except Exception as e:
            logger.error(f"Token validation failed: {type(e).__name__}")
            raise TokenValidationError("Token validation failed due to internal error")
    
    async def decode_token(self, token: str, verify_signature: bool = True) -> JWTToken:
        """
        Decode JWT token without full validation.
        
        Args:
            token: Raw JWT token string
            verify_signature: Whether to verify token signature
            
        Returns:
            JWTToken: Decoded token object
        """
        try:
            # Decode header
            header = jwt.get_unverified_header(token)
            
            # Decode payload without verification
            payload = jwt.decode(token, options={"verify_signature": False})
            
            # Extract signature
            token_parts = token.split('.')
            if len(token_parts) != 3:
                raise TokenValidationError("Invalid token format")
            
            signature = token_parts[2]
            
            # Extract standard claims
            issued_at = datetime.fromtimestamp(
                payload.get('iat', 0), 
                tz=timezone.utc
            )
            expires_at = datetime.fromtimestamp(
                payload.get('exp', 0), 
                tz=timezone.utc
            )
            
            issuer = payload.get('iss', '')
            audience = payload.get('aud', '')
            subject = payload.get('sub', '')
            
            return JWTToken(
                raw_token=token,
                header=header,
                payload=payload,
                signature=signature,
                is_valid=False,  # Will be set to True after full validation
                issued_at=issued_at,
                expires_at=expires_at,
                issuer=issuer,
                audience=audience,
                subject=subject
            )
            
        except Exception as e:
            raise TokenValidationError(f"Failed to decode token: {str(e)}")
    
    async def verify_signature(self, token: str, jwks: Dict[str, Any]) -> bool:
        """
        Verify JWT token signature against JWKS.
        
        Args:
            token: Raw JWT token string
            jwks: JSON Web Key Set
            
        Returns:
            bool: True if signature is valid
        """
        try:
            # Get key ID from token header
            header = jwt.get_unverified_header(token)
            key_id = header.get('kid')
            
            if not key_id:
                logger.error("Token missing key ID in header")
                return False
            
            # Find the correct key in JWKS
            public_key = None
            for key in jwks.get('keys', []):
                if key.get('kid') == key_id:
                    public_key = RSAAlgorithm.from_jwk(json.dumps(key))
                    break
            
            if not public_key:
                logger.error(f"Unable to find key {key_id} in JWKS")
                return False
            
            # Verify signature
            try:
                jwt.decode(token, public_key, algorithms=['RS256'])
                return True
            except jwt.InvalidSignatureError:
                logger.error("Token signature verification failed")
                return False
            except jwt.InvalidTokenError:
                logger.error("Token validation failed")
                return False
                
        except Exception as e:
            logger.error(f"Signature verification error: {type(e).__name__}")
            return False
    
    def extract_claims(self, token: JWTToken) -> Dict[str, Any]:
        """
        Extract standard and custom claims from JWT token.
        
        Args:
            token: Parsed JWT token
            
        Returns:
            Dict[str, Any]: Token claims
        """
        claims = token.payload.copy()
        
        # Add standard claims with normalized names
        claims.update({
            'user_id': token.subject,
            'issued_at': token.issued_at.isoformat(),
            'expires_at': token.expires_at.isoformat(),
            'issuer': token.issuer,
            'audience': token.audience,
            'is_expired': self.is_token_expired(token),
            'time_until_expiry': token.time_until_expiry
        })
        
        return claims
    
    def is_token_expired(self, token: JWTToken) -> bool:
        """
        Check if JWT token is expired.
        
        Args:
            token: Parsed JWT token
            
        Returns:
            bool: True if token is expired
        """
        return token.is_expired
    
    async def _get_jwks_for_issuer(self, issuer: str) -> Dict[str, Any]:
        """
        Get JWKS data for a specific issuer.
        
        Args:
            issuer: Token issuer URL
            
        Returns:
            Dict[str, Any]: JWKS data
        """
        # Check cache first
        if self._is_jwks_cache_valid(issuer):
            return self._jwks_cache[issuer]
        
        try:
            # Construct JWKS URI from issuer
            jwks_uri = self._get_jwks_uri_from_issuer(issuer)
            
            # Fetch JWKS
            async with httpx.AsyncClient() as client:
                response = await client.get(jwks_uri, timeout=10.0)
                response.raise_for_status()
                
                jwks_data = response.json()
                
                # Cache the JWKS
                self._cache_jwks_for_issuer(issuer, jwks_data)
                
                return jwks_data
                
        except Exception as e:
            logger.error(f"Failed to fetch JWKS for issuer {issuer}: {str(e)}")
            raise TokenValidationError(f"Unable to fetch JWKS: {str(e)}")
    
    def _get_jwks_uri_from_issuer(self, issuer: str) -> str:
        """
        Construct JWKS URI from issuer URL.
        
        Args:
            issuer: Issuer URL
            
        Returns:
            str: JWKS URI
        """
        if 'cognito-idp' in issuer:
            # Cognito JWKS URI format
            return f"{issuer}/.well-known/jwks.json"
        else:
            # Standard OpenID Connect discovery
            return f"{issuer}/.well-known/jwks.json"
    
    def _is_jwks_cache_valid(self, issuer: str) -> bool:
        """
        Check if JWKS cache is valid for issuer.
        
        Args:
            issuer: Token issuer
            
        Returns:
            bool: True if cache is valid
        """
        if issuer not in self._jwks_cache or issuer not in self._jwks_cache_expiry:
            return False
            
        return datetime.now(timezone.utc) < self._jwks_cache_expiry[issuer]
    
    def _cache_jwks_for_issuer(self, issuer: str, jwks: Dict[str, Any], cache_duration_minutes: int = 60):
        """
        Cache JWKS data for specific issuer.
        
        Args:
            issuer: Token issuer
            jwks: JWKS data
            cache_duration_minutes: Cache duration in minutes
        """
        self._jwks_cache[issuer] = jwks
        self._jwks_cache_expiry[issuer] = datetime.now(timezone.utc).replace(
            minute=datetime.now(timezone.utc).minute + cache_duration_minutes
        )
    
    def parse_bearer_token(self, authorization_header: str) -> Optional[str]:
        """
        Parse bearer token from Authorization header.
        
        Args:
            authorization_header: HTTP Authorization header value
            
        Returns:
            Optional[str]: Bearer token if found
        """
        if not authorization_header:
            return None
            
        parts = authorization_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return None
            
        return parts[1]
    
    def create_token_response(self, token: JWTToken, user_info: Any = None) -> Dict[str, Any]:
        """
        Create standardized token response.
        
        Args:
            token: Validated JWT token
            user_info: Optional user information
            
        Returns:
            Dict[str, Any]: Standardized token response
        """
        response = {
            'token': token.raw_token,
            'token_type': 'Bearer',
            'expires_in': token.time_until_expiry,
            'issued_at': token.issued_at.isoformat(),
            'expires_at': token.expires_at.isoformat(),
            'claims': self.extract_claims(token)
        }
        
        if user_info:
            response['user_info'] = user_info
            
        return response


class TokenCache:
    """
    Simple in-memory token cache for performance optimization.
    
    This cache stores validated tokens to avoid repeated JWKS fetches
    and signature verification for frequently used tokens.
    """
    
    def __init__(self, max_size: int = 1000, default_ttl_minutes: int = 30):
        self.max_size = max_size
        self.default_ttl_minutes = default_ttl_minutes
        self._cache: Dict[str, Dict[str, Any]] = {}
        
    def get(self, token_hash: str) -> Optional[JWTToken]:
        """Get cached token if valid."""
        cache_entry = self._cache.get(token_hash)
        if not cache_entry:
            return None
            
        # Check if cache entry is expired
        if datetime.now(timezone.utc) > cache_entry['expires']:
            del self._cache[token_hash]
            return None
            
        return cache_entry['token']
    
    def put(self, token_hash: str, token: JWTToken, ttl_minutes: Optional[int] = None):
        """Cache validated token."""
        # Clean cache if at max size
        if len(self._cache) >= self.max_size:
            self._clean_expired_entries()
            
            # If still at max size, remove oldest entry
            if len(self._cache) >= self.max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k]['cached_at'])
                del self._cache[oldest_key]
        
        # Cache the token
        ttl = ttl_minutes or self.default_ttl_minutes
        self._cache[token_hash] = {
            'token': token,
            'cached_at': datetime.now(timezone.utc),
            'expires': datetime.now(timezone.utc).replace(
                minute=datetime.now(timezone.utc).minute + ttl
            )
        }
    
    def _clean_expired_entries(self):
        """Remove expired entries from cache."""
        now = datetime.now(timezone.utc)
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry['expires']
        ]
        for key in expired_keys:
            del self._cache[key]
    
    def clear(self):
        """Clear all cached tokens."""
        self._cache.clear()
    
    def size(self) -> int:
        """Get current cache size."""
        return len(self._cache)



import secrets
import time
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

class SecureTokenValidator:
    """Enhanced token validator with security best practices."""
    
    def __init__(self):
        self.rate_limiter = {}
        self.max_attempts = 5
        self.window_size = 300  # 5 minutes
        
    def validate_token_rate_limit(self, identifier: str) -> bool:
        """Implement rate limiting for token validation attempts."""
        now = time.time()
        
        # Clean old entries
        self.rate_limiter = {
            k: v for k, v in self.rate_limiter.items() 
            if now - v['first_attempt'] < self.window_size
        }
        
        if identifier not in self.rate_limiter:
            self.rate_limiter[identifier] = {
                'attempts': 1,
                'first_attempt': now
            }
            return True
            
        entry = self.rate_limiter[identifier]
        if entry['attempts'] >= self.max_attempts:
            return False
            
        entry['attempts'] += 1
        return True
    
    def secure_token_hash(self, token: str) -> str:
        """Create a secure hash of the token for logging/caching."""
        if not token:
            return ""
        
        # Use SHA-256 with salt for secure hashing
        salt = b"secure_jwt_salt_2024"
        digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
        digest.update(salt)
        digest.update(token.encode('utf-8'))
        hash_bytes = digest.finalize()
        return hash_bytes.hex()[:16]  # First 16 characters for logging

def create_secure_jwt_handler(audience: Optional[str] = None) -> JWTHandler:
    """
    Factory function to create secure JWT handler with enhanced security.
    
    Args:
        audience: Default expected audience for token validation
        
    Returns:
        JWTHandler: Configured JWT handler with security enhancements
    """
    handler = JWTHandler(default_audience=audience)
    handler.secure_validator = SecureTokenValidator()
    return handler


def create_jwt_handler(audience: Optional[str] = None) -> JWTHandler:
    """
    Factory function to create JWT handler.
    
    Args:
        audience: Default expected audience for token validation
        
    Returns:
        JWTHandler: Configured JWT handler
    """
    return JWTHandler(default_audience=audience)


def hash_token_for_cache(token: str) -> str:
    """
    Create a hash of the token for cache key.
    
    Args:
        token: JWT token string
        
    Returns:
        str: Token hash for caching
    """
    import hashlib
    # Use cryptographically secure hashing
    salt = b"jwt_cache_salt_2024"
    digest = hashes.Hash(hashes.SHA256(), backend=default_backend())
    digest.update(salt)
    digest.update(token.encode('utf-8'))
    hash_bytes = digest.finalize()
    return hash_bytes.hex()[:16]