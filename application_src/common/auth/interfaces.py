"""
Abstract interfaces for the authentication and authorization system.

This module defines the contracts that all authentication components must implement,
ensuring consistency and extensibility across different identity providers and services.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from .types import (
    AuthenticationResult,
    UserInfo,
    JWTToken,
    Role,
    Permission,
    AuthConfig,
    IdentityProviderType
)


class IdentityProvider(ABC):
    """
    Abstract base class for identity providers.
    
    This interface defines the contract that all identity providers (Cognito, Okta, Ping, Auth0)
    must implement to provide consistent authentication capabilities.
    """
    
    def __init__(self, config: AuthConfig):
        self.config = config
        self.provider_type = config.provider_type
    
    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the identity provider with configuration.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def authenticate(self, username: str, password: str) -> AuthenticationResult:
        """
        Authenticate user with username and password.
        
        Args:
            username: User's username or email
            password: User's password
            
        Returns:
            AuthenticationResult: Result containing tokens and user info
        """
        pass
    
    @abstractmethod
    async def validate_token(self, token: str, token_type: str = "access") -> UserInfo:
        """
        Validate and decode an authentication token.
        
        Args:
            token: JWT token to validate
            token_type: Type of token ('access', 'id', 'refresh')
            
        Returns:
            UserInfo: Decoded user information from token
            
        Raises:
            TokenValidationError: If token is invalid or expired
        """
        pass
    
    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> AuthenticationResult:
        """
        Refresh access token using refresh token.
        
        Args:
            refresh_token: Valid refresh token
            
        Returns:
            AuthenticationResult: New tokens and user info
        """
        pass
    
    @abstractmethod
    async def logout(self, access_token: str, refresh_token: Optional[str] = None) -> bool:
        """
        Logout user and invalidate tokens.
        
        Args:
            access_token: User's access token
            refresh_token: Optional refresh token to invalidate
            
        Returns:
            bool: True if logout successful
        """
        pass
    
    @abstractmethod
    async def get_user_info(self, access_token: str) -> UserInfo:
        """
        Get user information from access token.
        
        Args:
            access_token: Valid access token
            
        Returns:
            UserInfo: User information
        """
        pass
    
    @abstractmethod
    async def get_jwks(self) -> Dict[str, Any]:
        """
        Get JSON Web Key Set for token validation.
        
        Returns:
            Dict[str, Any]: JWKS data
        """
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the name of the identity provider."""
        pass
    
    @property 
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider is properly configured."""
        pass


class TokenValidator(ABC):
    """
    Abstract base class for JWT token validators.
    
    This interface defines how JWT tokens should be validated, parsed, and verified
    across different identity providers.
    """
    
    @abstractmethod
    async def validate_token(self, token: str, audience: Optional[str] = None) -> JWTToken:
        """
        Validate JWT token structure, signature, and claims.
        
        Args:
            token: Raw JWT token string
            audience: Expected audience claim
            
        Returns:
            JWTToken: Parsed and validated token object
            
        Raises:
            TokenValidationError: If token is invalid
        """
        pass
    
    @abstractmethod
    async def decode_token(self, token: str, verify_signature: bool = True) -> JWTToken:
        """
        Decode JWT token without full validation.
        
        Args:
            token: Raw JWT token string  
            verify_signature: Whether to verify token signature
            
        Returns:
            JWTToken: Decoded token object
        """
        pass
    
    @abstractmethod
    async def verify_signature(self, token: str, jwks: Dict[str, Any]) -> bool:
        """
        Verify JWT token signature against JWKS.
        
        Args:
            token: Raw JWT token string
            jwks: JSON Web Key Set
            
        Returns:
            bool: True if signature is valid
        """
        pass
    
    @abstractmethod
    def extract_claims(self, token: JWTToken) -> Dict[str, Any]:
        """
        Extract standard and custom claims from JWT token.
        
        Args:
            token: Parsed JWT token
            
        Returns:
            Dict[str, Any]: Token claims
        """
        pass
    
    @abstractmethod
    def is_token_expired(self, token: JWTToken) -> bool:
        """
        Check if JWT token is expired.
        
        Args:
            token: Parsed JWT token
            
        Returns:
            bool: True if token is expired
        """
        pass


class RoleManager(ABC):
    """
    Abstract base class for role-based access control management.
    
    This interface defines how roles and permissions are managed, validated,
    and enforced throughout the application.
    """
    
    @abstractmethod
    async def initialize_roles(self) -> bool:
        """
        Initialize role management system with default roles and permissions.
        
        Returns:
            bool: True if initialization successful
        """
        pass
    
    @abstractmethod
    async def get_user_roles(self, user_id: str) -> List[Role]:
        """
        Get all roles assigned to a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List[Role]: List of user's roles
        """
        pass
    
    @abstractmethod
    async def get_user_permissions(self, user_id: str) -> List[Permission]:
        """
        Get all permissions for a user (from all their roles).
        
        Args:
            user_id: User identifier
            
        Returns:
            List[Permission]: List of user's permissions
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    async def assign_role(self, user_id: str, role_name: str) -> bool:
        """
        Assign role to user.
        
        Args:
            user_id: User identifier
            role_name: Name of role to assign
            
        Returns:
            bool: True if assignment successful
        """
        pass
    
    @abstractmethod
    async def remove_role(self, user_id: str, role_name: str) -> bool:
        """
        Remove role from user.
        
        Args:
            user_id: User identifier
            role_name: Name of role to remove
            
        Returns:
            bool: True if removal successful
        """
        pass
    
    @abstractmethod
    async def create_role(self, role: Role) -> bool:
        """
        Create new role in the system.
        
        Args:
            role: Role definition
            
        Returns:
            bool: True if creation successful
        """
        pass
    
    @abstractmethod
    async def update_role(self, role_name: str, role: Role) -> bool:
        """
        Update existing role.
        
        Args:
            role_name: Current role name
            role: Updated role definition
            
        Returns:
            bool: True if update successful
        """
        pass
    
    @abstractmethod
    async def delete_role(self, role_name: str) -> bool:
        """
        Delete role from system.
        
        Args:
            role_name: Name of role to delete
            
        Returns:
            bool: True if deletion successful
        """
        pass
    
    @abstractmethod
    async def get_role(self, role_name: str) -> Optional[Role]:
        """
        Get role definition by name.
        
        Args:
            role_name: Name of role
            
        Returns:
            Optional[Role]: Role definition if found
        """
        pass
    
    @abstractmethod
    async def list_roles(self) -> List[Role]:
        """
        List all available roles.
        
        Returns:
            List[Role]: All roles in system
        """
        pass
    
    @abstractmethod
    async def create_agent_group(self, agent_id: str, agent_type: str) -> bool:
        """
        Create role group for a specific agent.
        
        This enables agent-specific access control where users can be granted
        access to specific agents based on their role membership.
        
        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent (generic, supervisor, etc.)
            
        Returns:
            bool: True if group creation successful
        """
        pass
    
    @abstractmethod
    async def delete_agent_group(self, agent_id: str) -> bool:
        """
        Delete role group for a specific agent.
        
        Args:
            agent_id: Unique agent identifier
            
        Returns:
            bool: True if group deletion successful
        """
        pass


class AuthMiddleware(ABC):
    """
    Abstract base class for authentication middleware.
    
    This interface defines how authentication middleware should be implemented
    for different web frameworks (FastAPI, Flask, etc.).
    """
    
    @abstractmethod
    async def authenticate_request(self, request: Any) -> Optional[UserInfo]:
        """
        Authenticate incoming request.
        
        Args:
            request: HTTP request object
            
        Returns:
            Optional[UserInfo]: User info if authenticated, None otherwise
        """
        pass
    
    @abstractmethod
    async def authorize_request(self, request: Any, required_permissions: List[str]) -> bool:
        """
        Authorize request based on required permissions.
        
        Args:
            request: HTTP request object
            required_permissions: List of required permissions
            
        Returns:
            bool: True if authorized
        """
        pass
    
    @abstractmethod
    def extract_token(self, request: Any) -> Optional[str]:
        """
        Extract authentication token from request.
        
        Args:
            request: HTTP request object
            
        Returns:
            Optional[str]: Token if found
        """
        pass


class AgentCoreIdentityProvider(ABC):
    """
    Abstract base class for Bedrock AgentCore Identity integration.
    
    This interface defines how agents authenticate with each other using
    Bedrock AgentCore Identity in standalone mode.
    """
    
    @abstractmethod
    async def initialize_workload_identity(self, agent_id: str) -> bool:
        """
        Initialize workload identity for agent.
        
        Args:
            agent_id: Unique agent identifier
            
        Returns:
            bool: True if initialization successful
        """
        pass
    
    @abstractmethod
    async def get_agent_credentials(self, agent_id: str) -> Dict[str, str]:
        """
        Get credentials for agent-to-agent communication.
        
        Args:
            agent_id: Unique agent identifier
            
        Returns:
            Dict[str, str]: Agent credentials
        """
        pass
    
    @abstractmethod
    async def validate_agent_request(self, request: Any) -> bool:
        """
        Validate incoming request from another agent.
        
        Args:
            request: HTTP request from agent
            
        Returns:
            bool: True if request is valid
        """
        pass
