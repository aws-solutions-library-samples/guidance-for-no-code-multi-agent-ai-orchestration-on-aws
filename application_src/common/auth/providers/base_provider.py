"""
Base identity provider implementation with common functionality.

This module provides common functionality that can be shared across
different identity provider implementations.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from abc import ABC

from ..interfaces import IdentityProvider
from ..types import (
    AuthConfig,
    AuthenticationResult,
    AuthenticationError,
    TokenValidationError,
    UserInfo
)

logger = logging.getLogger(__name__)


class BaseIdentityProvider(IdentityProvider, ABC):
    """
    Base implementation of IdentityProvider with common functionality.
    
    This class provides shared functionality that most identity providers
    will need, such as configuration validation, error handling, and
    common token operations.
    """
    
    def __init__(self, config: AuthConfig):
        super().__init__(config)
        self.is_initialized = False
        self._jwks_cache: Optional[Dict[str, Any]] = None
        self._jwks_cache_expiry: Optional[datetime] = None
        
    async def _validate_config(self) -> bool:
        """
        Validate provider configuration.
        
        Returns:
            bool: True if configuration is valid
            
        Raises:
            AuthenticationError: If configuration is invalid
        """
        if not self.config.client_id:
            raise AuthenticationError(
                "Client ID is required for identity provider configuration",
                error_code="INVALID_CONFIG"
            )
            
        return True
    
    def _extract_user_groups_from_token(self, token_payload: Dict[str, Any]) -> List[str]:
        """
        Extract user groups from token payload.
        
        Different providers store groups in different token claims.
        This method provides a common interface for extracting groups.
        
        Args:
            token_payload: Decoded JWT token payload
            
        Returns:
            List[str]: User groups
        """
        # Common group claim names across different providers
        group_claims = [
            'cognito:groups',
            'groups', 
            'roles',
            'memberOf',
            'groups_claim'
        ]
        
        for claim in group_claims:
            if claim in token_payload:
                groups = token_payload[claim]
                if isinstance(groups, list):
                    return [str(group) for group in groups]
                elif isinstance(groups, str):
                    return [groups]
        
        return []
    
    def _extract_user_roles_from_groups(self, groups: List[str]) -> List[str]:
        """
        Extract roles from user groups.
        
        This method maps groups to roles. By default, groups and roles
        are treated as the same, but individual providers can override
        this behavior.
        
        Args:
            groups: User groups from identity provider
            
        Returns:
            List[str]: User roles
        """
        # Default implementation: groups are roles
        return groups
    
    def _create_user_info_from_token(
        self,
        token_payload: Dict[str, Any],
        access_token: Optional[str] = None
    ) -> UserInfo:
        """
        Create UserInfo object from token payload.
        
        Args:
            token_payload: Decoded JWT token payload
            access_token: Optional access token string
            
        Returns:
            UserInfo: User information object
        """
        # Extract basic user information
        user_id = token_payload.get('sub', '')
        username = token_payload.get('cognito:username', token_payload.get('username', ''))
        email = token_payload.get('email', '')
        
        # Extract groups and roles
        groups = self._extract_user_groups_from_token(token_payload)
        roles = self._extract_user_roles_from_groups(groups)
        
        # Extract timestamps
        issued_at = datetime.fromtimestamp(
            token_payload.get('iat', 0), 
            tz=timezone.utc
        )
        expires_at = datetime.fromtimestamp(
            token_payload.get('exp', 0), 
            tz=timezone.utc
        )
        
        # For now, permissions are derived from roles
        # This will be enhanced when role manager is implemented
        permissions = []
        for role in roles:
            if role == 'admin':
                permissions.extend(['*:*'])  # Admin has all permissions
            elif role == 'agent-creator':
                permissions.extend(['agent:create', 'agent:read', 'agent:update', 'agent:delete'])
            elif 'supervisor' in role:
                permissions.extend(['supervisor:access', 'agent:read'])
        
        return UserInfo(
            user_id=user_id,
            username=username,
            email=email,
            groups=groups,
            roles=roles,
            permissions=permissions,
            attributes=token_payload,
            token_issued_at=issued_at,
            token_expires_at=expires_at
        )
    
    def _handle_authentication_error(self, error: Exception, context: str = "") -> AuthenticationResult:
        """
        Handle authentication errors consistently.
        
        Args:
            error: The original exception
            context: Additional context for debugging
            
        Returns:
            AuthenticationResult: Failed authentication result
        """
        error_message = str(error)
        error_code = getattr(error, 'error_code', 'AUTHENTICATION_FAILED')
        
        logger.error(f"Authentication failed {context}: {error_message}")
        
        return AuthenticationResult(
            success=False,
            error=error_code,
            error_description=error_message
        )
    
    def _is_jwks_cache_valid(self) -> bool:
        """
        Check if JWKS cache is still valid.
        
        Returns:
            bool: True if cache is valid
        """
        if not self._jwks_cache or not self._jwks_cache_expiry:
            return False
            
        return datetime.now(timezone.utc) < self._jwks_cache_expiry
    
    def _cache_jwks(self, jwks: Dict[str, Any], cache_duration_minutes: int = 60):
        """
        Cache JWKS data with expiration.
        
        Args:
            jwks: JWKS data to cache
            cache_duration_minutes: Cache duration in minutes
        """
        self._jwks_cache = jwks
        self._jwks_cache_expiry = datetime.now(timezone.utc) + timedelta(minutes=cache_duration_minutes)
    
    @property
    def is_configured(self) -> bool:
        """
        Check if provider has minimum required configuration.
        
        Returns:
            bool: True if provider is configured
        """
        return (
            self.config.client_id is not None and
            len(self.config.client_id.strip()) > 0
        )
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(provider_type={self.provider_type.value})"
