"""
AWS Cognito identity provider implementation.

This module implements the IdentityProvider interface for AWS Cognito,
providing authentication services using Cognito User Pools.
"""

import logging
import json
import base64
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

import boto3
import jwt
from jwt.algorithms import RSAAlgorithm
from botocore.exceptions import ClientError
import httpx

from .base_provider import BaseIdentityProvider
from ..types import (
    AuthConfig,
    AuthenticationResult,
    AuthenticationError,
    TokenValidationError,
    UserInfo,
    IdentityProviderType
)

logger = logging.getLogger(__name__)


class CognitoProvider(BaseIdentityProvider):
    """
    AWS Cognito identity provider implementation.
    
    This class provides authentication services using AWS Cognito User Pools,
    including token validation, user authentication, and JWKS management.
    """
    
    def __init__(self, config: AuthConfig):
        super().__init__(config)
        self.cognito_client = None
        self.region = config.region
        self.user_pool_id = config.user_pool_id
        self.jwks_uri = None
        
    async def initialize(self) -> bool:
        """
        Initialize Cognito provider with AWS client and JWKS URI.
        
        Returns:
            bool: True if initialization successful
        """
        try:
            await self._validate_config()
            
            # Initialize Cognito client
            self.cognito_client = boto3.client(
                'cognito-idp',
                region_name=self.region
            )
            
            # Set up JWKS URI
            if self.user_pool_id and self.region:
                self.jwks_uri = (
                    f"https://cognito-idp.{self.region}.amazonaws.com/"
                    f"{self.user_pool_id}/.well-known/jwks.json"
                )
            
            self.is_initialized = True
            logger.info(f"Cognito provider initialized for region {self.region}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize Cognito provider: {str(e)}")
            return False
    
    async def authenticate(self, username: str, password: str) -> AuthenticationResult:
        """
        Authenticate user with Cognito using username and password.
        
        Args:
            username: User's username or email
            password: User's password
            
        Returns:
            AuthenticationResult: Authentication result with tokens
        """
        if not self.is_initialized:
            await self.initialize()
            
        try:
            # Use AdminInitiateAuth for server-side authentication
            response = self.cognito_client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.config.client_id,
                AuthFlow='ADMIN_NO_SRP_AUTH',
                AuthParameters={
                    'USERNAME': username,
                    'PASSWORD': password
                }
            )
            
            # Handle different auth challenge states
            if 'ChallengeName' in response:
                return self._handle_auth_challenge(response)
            
            # Extract tokens from successful authentication
            auth_result = response.get('AuthenticationResult', {})
            access_token = auth_result.get('AccessToken')
            refresh_token = auth_result.get('RefreshToken')
            id_token = auth_result.get('IdToken')
            expires_in = auth_result.get('ExpiresIn')
            
            if not access_token:
                return AuthenticationResult(
                    success=False,
                    error="NO_TOKENS",
                    error_description="No tokens returned from authentication"
                )
            
            # Get user info from access token
            user_info = await self.get_user_info(access_token)
            
            return AuthenticationResult(
                success=True,
                user_info=user_info,
                access_token=access_token,
                refresh_token=refresh_token,
                id_token=id_token,
                expires_in=expires_in,
                token_type="Bearer"
            )
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'UNKNOWN_ERROR')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            logger.error(f"Cognito authentication failed: {error_code} - {error_message}")
            
            return AuthenticationResult(
                success=False,
                error=error_code,
                error_description=error_message
            )
        except Exception as e:
            return self._handle_authentication_error(e, "during Cognito authentication")
    
    async def validate_token(self, token: str, token_type: str = "access") -> UserInfo:
        """
        Validate Cognito JWT token and extract user information.
        
        Args:
            token: JWT token to validate
            token_type: Type of token ('access', 'id')
            
        Returns:
            UserInfo: Validated user information
            
        Raises:
            TokenValidationError: If token is invalid
        """
        if not self.is_initialized:
            await self.initialize()
            
        try:
            # Get JWKS for token validation
            jwks = await self.get_jwks()
            
            # Decode token header to get key ID
            unverified_header = jwt.get_unverified_header(token)
            key_id = unverified_header.get('kid')
            
            if not key_id:
                raise TokenValidationError("Token missing key ID in header")
            
            # Find the correct key in JWKS
            public_key = None
            for key in jwks.get('keys', []):
                if key.get('kid') == key_id:
                    public_key = RSAAlgorithm.from_jwk(json.dumps(key))
                    break
            
            if not public_key:
                raise TokenValidationError(f"Unable to find key {key_id} in JWKS")
            
            # Validate and decode token (Cognito access tokens don't have 'aud' claim)
            try:
                # First decode without audience validation for Cognito access tokens
                payload = jwt.decode(
                    token,
                    public_key,
                    algorithms=['RS256'],
                    options={"verify_aud": False},
                    issuer=f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
                )
                
                # Manually validate Cognito-specific claims
                token_use = payload.get('token_use')
                client_id = payload.get('client_id')
                
                if token_type == "access" and token_use != "access":
                    raise TokenValidationError(f"Expected access token but got {token_use}")
                
                if token_type == "id" and token_use != "id":
                    raise TokenValidationError(f"Expected ID token but got {token_use}")
                
                # Validate client_id matches our configuration
                if client_id != self.config.client_id:
                    raise TokenValidationError("Token client_id does not match expected client_id")
                    
            except jwt.ExpiredSignatureError:
                raise TokenValidationError("Token has expired")
            except jwt.InvalidTokenError as e:
                raise TokenValidationError(f"Token validation failed: {str(e)}")
            
            # Create user info from validated token
            return self._create_user_info_from_token(payload, token)
            
        except TokenValidationError:
            raise
        except Exception as e:
            raise TokenValidationError(f"Token validation error: {str(e)}")
    
    async def refresh_token(self, refresh_token: str) -> AuthenticationResult:
        """
        Refresh Cognito access token using refresh token.
        
        Args:
            refresh_token: Valid Cognito refresh token
            
        Returns:
            AuthenticationResult: New authentication tokens
        """
        if not self.is_initialized:
            await self.initialize()
            
        try:
            response = self.cognito_client.admin_initiate_auth(
                UserPoolId=self.user_pool_id,
                ClientId=self.config.client_id,
                AuthFlow='REFRESH_TOKEN_AUTH',
                AuthParameters={
                    'REFRESH_TOKEN': refresh_token
                }
            )
            
            auth_result = response.get('AuthenticationResult', {})
            access_token = auth_result.get('AccessToken')
            new_refresh_token = auth_result.get('RefreshToken', refresh_token)
            id_token = auth_result.get('IdToken')
            expires_in = auth_result.get('ExpiresIn')
            
            if not access_token:
                return AuthenticationResult(
                    success=False,
                    error="NO_ACCESS_TOKEN",
                    error_description="No access token returned from refresh"
                )
            
            # Get user info from new access token
            user_info = await self.get_user_info(access_token)
            
            return AuthenticationResult(
                success=True,
                user_info=user_info,
                access_token=access_token,
                refresh_token=new_refresh_token,
                id_token=id_token,
                expires_in=expires_in,
                token_type="Bearer"
            )
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'REFRESH_FAILED')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            return AuthenticationResult(
                success=False,
                error=error_code,
                error_description=error_message
            )
        except Exception as e:
            return self._handle_authentication_error(e, "during token refresh")
    
    async def logout(self, access_token: str, refresh_token: Optional[str] = None) -> bool:
        """
        Logout user from Cognito (global sign out).
        
        Args:
            access_token: User's access token
            refresh_token: Optional refresh token (not used in Cognito global signout)
            
        Returns:
            bool: True if logout successful
        """
        if not self.is_initialized:
            await self.initialize()
            
        try:
            # Global sign out invalidates all tokens for the user
            self.cognito_client.admin_user_global_sign_out(
                UserPoolId=self.user_pool_id,
                AccessToken=access_token
            )
            
            logger.info("User successfully logged out from Cognito")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'LOGOUT_FAILED')
            logger.error(f"Cognito logout failed: {error_code}")
            # Return True even if logout fails - client should clear tokens
            return True
        except Exception as e:
            logger.error(f"Logout error: {str(e)}")
            return True
    
    async def get_user_info(self, access_token: str) -> UserInfo:
        """
        Get user information from Cognito access token.
        
        Args:
            access_token: Valid Cognito access token
            
        Returns:
            UserInfo: User information
        """
        if not self.is_initialized:
            await self.initialize()
            
        try:
            # Validate token and extract user info
            user_info = await self.validate_token(access_token, "access")
            return user_info
            
        except Exception as e:
            logger.error(f"Failed to get user info: {str(e)}")
            raise AuthenticationError(f"Unable to get user information: {str(e)}")
    
    async def get_jwks(self) -> Dict[str, Any]:
        """
        Get Cognito JWKS for token validation.
        
        Returns:
            Dict[str, Any]: JWKS data
        """
        # Check if we have valid cached JWKS
        if self._is_jwks_cache_valid():
            return self._jwks_cache
        
        try:
            if not self.jwks_uri:
                raise AuthenticationError("JWKS URI not configured")
            
            async with httpx.AsyncClient() as client:
                response = await client.get(self.jwks_uri)
                response.raise_for_status()
                
                jwks_data = response.json()
                self._cache_jwks(jwks_data)
                
                return jwks_data
                
        except Exception as e:
            logger.error(f"Failed to fetch JWKS: {str(e)}")
            raise AuthenticationError(f"Unable to fetch JWKS: {str(e)}")
    
    def _handle_auth_challenge(self, response: Dict[str, Any]) -> AuthenticationResult:
        """
        Handle Cognito authentication challenges.
        
        Args:
            response: Cognito authentication response with challenge
            
        Returns:
            AuthenticationResult: Challenge result
        """
        challenge_name = response.get('ChallengeName')
        
        if challenge_name == 'NEW_PASSWORD_REQUIRED':
            return AuthenticationResult(
                success=False,
                error="NEW_PASSWORD_REQUIRED",
                error_description="User must set a new password"
            )
        elif challenge_name == 'MFA_REQUIRED':
            return AuthenticationResult(
                success=False,
                error="MFA_REQUIRED", 
                error_description="Multi-factor authentication required"
            )
        else:
            return AuthenticationResult(
                success=False,
                error="CHALLENGE_REQUIRED",
                error_description=f"Authentication challenge required: {challenge_name}"
            )
    
    @property
    def provider_name(self) -> str:
        """Get the name of the Cognito provider."""
        return "AWS Cognito"
    
    @property
    def is_configured(self) -> bool:
        """
        Check if Cognito provider is properly configured.
        
        Returns:
            bool: True if provider has required configuration
        """
        return (
            super().is_configured and
            self.user_pool_id is not None and
            self.region is not None and
            len(self.user_pool_id.strip()) > 0 and
            len(self.region.strip()) > 0
        )
    
    async def _validate_config(self) -> bool:
        """
        Validate Cognito-specific configuration.
        
        Returns:
            bool: True if configuration is valid
            
        Raises:
            AuthenticationError: If configuration is invalid
        """
        await super()._validate_config()
        
        if not self.user_pool_id:
            raise AuthenticationError(
                "User Pool ID is required for Cognito provider",
                error_code="INVALID_CONFIG"
            )
            
        if not self.region:
            raise AuthenticationError(
                "AWS region is required for Cognito provider",
                error_code="INVALID_CONFIG"
            )
        
        return True


# Factory function for creating Cognito provider from Secrets Manager
async def create_cognito_provider_from_secret(
    secret_identifier: str,
    region: str,
    client_secret: Optional[str] = None
) -> CognitoProvider:
    """
    Create Cognito provider from AWS Secrets Manager configuration.
    
    Args:
        secret_identifier: ARN or name of the secret containing Cognito config
        region: AWS region
        client_secret: Optional client secret for confidential clients
        
    Returns:
        CognitoProvider: Configured Cognito provider
        
    Raises:
        AuthenticationError: If secret cannot be retrieved or is invalid
    """
    try:
        # Get Cognito configuration from Secrets Manager using ARN or name
        secrets_client = boto3.client('secretsmanager', region_name=region)
        
        response = secrets_client.get_secret_value(SecretId=secret_identifier)
        secret_data = json.loads(response['SecretString'])
        
        # Extract configuration
        user_pool_id = secret_data.get('pool_id')
        client_id = secret_data.get('app_client_id')
        
        if not user_pool_id or not client_id:
            raise AuthenticationError(
                "Secret must contain 'pool_id' and 'app_client_id'",
                error_code="INVALID_SECRET"
            )
        
        # Create auth configuration
        config = AuthConfig(
            provider_type=IdentityProviderType.COGNITO,
            client_id=client_id,
            client_secret=client_secret,
            user_pool_id=user_pool_id,
            region=region,
            scopes=['openid', 'email', 'profile', 'aws.cognito.signin.user.admin']
        )
        
        # Create and initialize provider
        provider = CognitoProvider(config)
        await provider.initialize()
        
        return provider
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'SECRET_ACCESS_FAILED')
        raise AuthenticationError(
            f"Unable to retrieve Cognito configuration: {error_code}",
            error_code=error_code
        )
    except Exception as e:
        raise AuthenticationError(
            f"Failed to create Cognito provider from secret: {str(e)}",
            error_code="PROVIDER_CREATION_FAILED"
        )


# Cognito-specific utility functions
def extract_cognito_user_id_from_token(token: str) -> Optional[str]:
    """
    Extract user ID from Cognito token without validation.
    
    Args:
        token: Cognito JWT token
        
    Returns:
        Optional[str]: User ID if found
    """
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        return payload.get('sub')
    except Exception:
        return None


def is_cognito_token(token: str) -> bool:
    """
    Check if token is from Cognito based on issuer claim.
    
    Args:
        token: JWT token to check
        
    Returns:
        bool: True if token appears to be from Cognito
    """
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
        issuer = payload.get('iss', '')
        return 'cognito-idp' in issuer
    except Exception:
        return False
