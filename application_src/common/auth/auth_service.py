"""
Main authentication service that orchestrates all authentication components.

This service provides a unified interface for authentication and authorization,
using pluggable identity providers and comprehensive role management.
"""

import logging
from typing import Dict, List, Optional, Any
import os

from .interfaces import IdentityProvider, RoleManager
from .providers import create_provider, create_cognito_provider_from_secret
from .jwt_handler import JWTHandler, create_jwt_handler
from .role_manager import create_role_manager
from .types import (
    AuthConfig,
    AuthenticationResult,
    AuthenticationError,
    UserInfo,
    IdentityProviderType,
    SystemRoles
)

logger = logging.getLogger(__name__)


class AuthService:
    """
    Main authentication service that orchestrates all authentication components.
    
    This service provides:
    - Pluggable identity provider management
    - JWT token validation and handling
    - Role-based access control
    - Unified authentication interface
    """
    
    def __init__(self):
        self.identity_provider: Optional[IdentityProvider] = None
        self.jwt_handler: Optional[JWTHandler] = None
        self.role_manager: Optional[RoleManager] = None
        self.is_initialized = False
        self._current_provider_type: Optional[IdentityProviderType] = None
        
    async def initialize(
        self,
        provider_config: Optional[AuthConfig] = None,
        secret_arn: Optional[str] = None,
        region: Optional[str] = None
    ) -> bool:
        """
        Initialize authentication service with identity provider.
        
        Args:
            provider_config: Direct provider configuration
            secret_arn: AWS Secrets Manager secret ARN for configuration
            region: AWS region
            
        Returns:
            bool: True if initialization successful
        """
        try:
            # Initialize from environment or parameters
            region = region or os.environ.get('AWS_REGION', 'us-west-2')
            
            if provider_config:
                # Use direct configuration
                self.identity_provider = create_provider(
                    provider_config.provider_type.value, 
                    provider_config
                )
                await self.identity_provider.initialize()
                
                # Initialize role manager if using Cognito (with timeout protection)
                if provider_config.provider_type == IdentityProviderType.COGNITO:
                    try:
                        import asyncio
                        self.role_manager = await asyncio.wait_for(
                            create_role_manager(provider_config.user_pool_id, region),
                            timeout=30.0  # 30 second timeout
                        )
                        logger.info("✅ Role manager initialized successfully")
                    except asyncio.TimeoutError:
                        logger.warning("⚠️ Role manager initialization timed out - will create on first use")
                        self.role_manager = None
                    except Exception as e:
                        logger.warning(f"⚠️ Role manager initialization failed: {str(e)} - will create on first use")
                        self.role_manager = None
                
                self._current_provider_type = provider_config.provider_type
                
            elif secret_arn:
                # Initialize Cognito from Secrets Manager ARN
                self.identity_provider = await create_cognito_provider_from_secret(
                    secret_arn, 
                    region
                )
                
                # Initialize role manager with Cognito config
                self.role_manager = await create_role_manager(
                    self.identity_provider.config.user_pool_id,
                    region
                )
                
                self._current_provider_type = IdentityProviderType.COGNITO
                
            else:
                # Try to initialize from environment variables
                secret_arn = os.environ.get('SECRETS_MANAGER_ARN')
                if secret_arn:
                    return await self.initialize(secret_arn=secret_arn, region=region)
                else:
                    raise AuthenticationError(
                        "No authentication configuration provided - set SECRETS_MANAGER_ARN",
                        error_code="NO_CONFIG"
                    )
            
            # Initialize JWT handler with provider's client ID as audience
            self.jwt_handler = create_jwt_handler(
                audience=self.identity_provider.config.client_id
            )
            
            self.is_initialized = True
            logger.info(f"AuthService initialized with {self._current_provider_type.value} provider")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize AuthService: {str(e)}")
            return False
    
    async def authenticate(self, username: str, password: str) -> AuthenticationResult:
        """
        Authenticate user using configured identity provider.
        
        Args:
            username: User's username or email
            password: User's password
            
        Returns:
            AuthenticationResult: Authentication result with tokens and user info
        """
        if not self.is_initialized or not self.identity_provider:
            raise AuthenticationError("AuthService not initialized")
        
        try:
            result = await self.identity_provider.authenticate(username, password)
            
            # Enhance user info with role information
            if result.success and result.user_info and self.role_manager:
                enhanced_user_info = await self._enhance_user_info_with_roles(result.user_info)
                result.user_info = enhanced_user_info
            
            return result
            
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            return AuthenticationResult(
                success=False,
                error="AUTHENTICATION_FAILED",
                error_description=str(e)
            )
    
    async def validate_token(self, token: str) -> UserInfo:
        """
        Validate JWT token and return user information with roles.
        
        Args:
            token: JWT token to validate
            
        Returns:
            UserInfo: Validated user information with roles and permissions
        """
        if not self.is_initialized or not self.identity_provider:
            raise AuthenticationError("AuthService not initialized")
        
        try:
            # Validate token with identity provider
            user_info = await self.identity_provider.validate_token(token)
            
            # Enhance with role information
            if self.role_manager:
                enhanced_user_info = await self._enhance_user_info_with_roles(user_info)
                return enhanced_user_info
            
            return user_info
            
        except Exception as e:
            logger.error(f"Token validation failed: {str(e)}")
            raise AuthenticationError(f"Invalid token: {str(e)}")
    
    async def refresh_token(self, refresh_token: str) -> AuthenticationResult:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            AuthenticationResult: New authentication tokens
        """
        if not self.is_initialized or not self.identity_provider:
            raise AuthenticationError("AuthService not initialized")
        
        return await self.identity_provider.refresh_token(refresh_token)
    
    async def logout(self, access_token: str, refresh_token: Optional[str] = None) -> bool:
        """
        Logout user and invalidate tokens.
        
        Args:
            access_token: User's access token
            refresh_token: Optional refresh token
            
        Returns:
            bool: True if logout successful
        """
        if not self.is_initialized or not self.identity_provider:
            return False
        
        return await self.identity_provider.logout(access_token, refresh_token)
    
    async def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        """
        Check if user has specific permission.
        
        Args:
            user_id: User identifier
            resource: Resource being accessed
            action: Action being performed
            
        Returns:
            bool: True if user has permission
        """
        if not self.role_manager:
            logger.warning("No role manager available for permission check")
            return False
        
        return await self.role_manager.check_permission(user_id, resource, action)
    
    async def assign_user_role(self, user_id: str, role_name: str) -> bool:
        """
        Assign role to user.
        
        Args:
            user_id: User identifier
            role_name: Role to assign
            
        Returns:
            bool: True if assignment successful
        """
        if not self.role_manager:
            logger.error("No role manager available for role assignment")
            return False
        
        return await self.role_manager.assign_role(user_id, role_name)
    
    async def remove_user_role(self, user_id: str, role_name: str) -> bool:
        """
        Remove role from user.
        
        Args:
            user_id: User identifier
            role_name: Role to remove
            
        Returns:
            bool: True if removal successful
        """
        if not self.role_manager:
            logger.error("No role manager available for role removal")
            return False
        
        return await self.role_manager.remove_role(user_id, role_name)
    
    async def create_agent_access_group(self, agent_id: str, agent_type: str) -> bool:
        """
        Create access group for specific agent during deployment.
        
        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent
            
        Returns:
            bool: True if group creation successful
        """
        if not self.role_manager:
            logger.error("No role manager available for agent group creation")
            return False
        
        return await self.role_manager.create_agent_group(agent_id, agent_type)
    
    async def delete_agent_access_group(self, agent_id: str) -> bool:
        """
        Delete access group for specific agent during cleanup.
        
        Args:
            agent_id: Unique agent identifier
            
        Returns:
            bool: True if group deletion successful
        """
        if not self.role_manager:
            logger.error("No role manager available for agent group deletion")
            return False
        
        return await self.role_manager.delete_agent_group(agent_id)
    
    async def get_user_info(self, access_token: str) -> UserInfo:
        """
        Get comprehensive user information including roles and permissions.
        
        Args:
            access_token: Valid access token
            
        Returns:
            UserInfo: Complete user information
        """
        if not self.is_initialized or not self.identity_provider:
            raise AuthenticationError("AuthService not initialized")
        
        user_info = await self.identity_provider.get_user_info(access_token)
        
        # Enhance with role information
        if self.role_manager:
            enhanced_user_info = await self._enhance_user_info_with_roles(user_info)
            return enhanced_user_info
        
        return user_info
    
    async def _enhance_user_info_with_roles(self, user_info: UserInfo) -> UserInfo:
        """
        Enhance user info with role and permission data from role manager.
        
        Args:
            user_info: Basic user information
            
        Returns:
            UserInfo: Enhanced user information
        """
        if not self.role_manager:
            return user_info
        
        try:
            # Get roles from role manager
            roles = await self.role_manager.get_user_roles(user_info.user_id)
            role_names = [role.name for role in roles]
            
            # Get permissions from role manager
            permissions = await self.role_manager.get_user_permissions(user_info.user_id)
            permission_names = [str(perm) for perm in permissions]
            
            # Create enhanced user info
            return UserInfo(
                user_id=user_info.user_id,
                username=user_info.username,
                email=user_info.email,
                groups=user_info.groups,  # Keep original groups from token
                roles=role_names,  # Updated with actual role definitions
                permissions=permission_names,  # Updated with actual permissions
                attributes=user_info.attributes,
                token_issued_at=user_info.token_issued_at,
                token_expires_at=user_info.token_expires_at
            )
            
        except Exception as e:
            logger.error(f"Failed to enhance user info with roles: {str(e)}")
            return user_info
    
    def get_provider_type(self) -> Optional[IdentityProviderType]:
        """Get current identity provider type."""
        return self._current_provider_type
    
    def get_provider_name(self) -> str:
        """Get current identity provider name."""
        if self.identity_provider:
            return self.identity_provider.provider_name
        return "Not configured"
    
    def is_ready(self) -> bool:
        """Check if service is ready for use."""
        return (
            self.is_initialized and
            self.identity_provider is not None and
            self.identity_provider.is_configured
        )


# Global instance for singleton pattern
_auth_service_instance: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """
    Get global AuthService instance (singleton pattern).
    
    Returns:
        AuthService: Global authentication service instance
    """
    global _auth_service_instance
    if _auth_service_instance is None:
        _auth_service_instance = AuthService()
    return _auth_service_instance


async def initialize_auth_service(
    provider_config: Optional[AuthConfig] = None,
    secret_arn: Optional[str] = None,
    region: Optional[str] = None
) -> AuthService:
    """
    Initialize global authentication service.
    
    Args:
        provider_config: Direct provider configuration
        secret_arn: AWS Secrets Manager secret ARN
        region: AWS region
        
    Returns:
        AuthService: Initialized authentication service
    """
    auth_service = get_auth_service()
    await auth_service.initialize(provider_config, secret_arn, region)
    return auth_service


# Convenience functions for common operations
async def authenticate_user(username: str, password: str) -> AuthenticationResult:
    """Authenticate user with global auth service."""
    auth_service = get_auth_service()
    return await auth_service.authenticate(username, password)


async def validate_user_token(token: str) -> UserInfo:
    """Validate token with global auth service."""
    auth_service = get_auth_service()
    return await auth_service.validate_token(token)


async def check_user_permission(user_id: str, resource: str, action: str) -> bool:
    """Check user permission with global auth service."""
    auth_service = get_auth_service()
    return await auth_service.check_permission(user_id, resource, action)
