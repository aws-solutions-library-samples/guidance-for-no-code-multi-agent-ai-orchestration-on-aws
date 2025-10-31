"""
Type definitions for the authentication and authorization system.

This module defines all the core data structures, enums, and exceptions
used throughout the authentication system.
"""

from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class IdentityProviderType(Enum):
    """Supported identity provider types."""
    COGNITO = "cognito"
    OKTA = "okta"
    PING = "ping"
    AUTH0 = "auth0"


class AuthenticationError(Exception):
    """Base exception for authentication-related errors."""
    
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}


class TokenValidationError(AuthenticationError):
    """Exception raised when JWT token validation fails."""
    pass


class AuthorizationError(AuthenticationError):
    """Exception raised when user lacks required permissions."""
    pass


@dataclass
class UserInfo:
    """User information extracted from authentication token."""
    user_id: str
    username: str
    email: str
    groups: List[str]
    roles: List[str] 
    permissions: List[str]
    attributes: Dict[str, Any]
    token_issued_at: datetime
    token_expires_at: datetime
    
    def has_role(self, role: str) -> bool:
        """Check if user has a specific role."""
        return role in self.roles
    
    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        return permission in self.permissions
    
    def has_any_role(self, roles: List[str]) -> bool:
        """Check if user has any of the specified roles."""
        return any(role in self.roles for role in roles)
    
    def has_all_permissions(self, permissions: List[str]) -> bool:
        """Check if user has all of the specified permissions."""
        return all(permission in self.permissions for permission in permissions)


@dataclass
class JWTToken:
    """JWT token with decoded payload and metadata."""
    raw_token: str
    header: Dict[str, Any]
    payload: Dict[str, Any]
    signature: str
    is_valid: bool
    issued_at: datetime
    expires_at: datetime
    issuer: str
    audience: str
    subject: str
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.utcnow() > self.expires_at
    
    @property
    def time_until_expiry(self) -> int:
        """Get seconds until token expiry."""
        delta = self.expires_at - datetime.utcnow()
        return max(0, int(delta.total_seconds()))


@dataclass
class AuthenticationResult:
    """Result of authentication operation."""
    success: bool
    user_info: Optional[UserInfo] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    id_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: Optional[int] = None
    error: Optional[str] = None
    error_description: Optional[str] = None
    
    @property
    def is_authenticated(self) -> bool:
        """Check if authentication was successful."""
        return self.success and self.user_info is not None


@dataclass 
class Permission:
    """Permission definition with metadata."""
    name: str
    description: str
    resource: str
    action: str
    conditions: Optional[Dict[str, Any]] = None
    
    def __str__(self) -> str:
        return f"{self.resource}:{self.action}"
    
    def matches(self, resource: str, action: str) -> bool:
        """Check if permission matches resource and action."""
        return self.resource == resource and self.action == action


@dataclass
class Role:
    """Role definition with associated permissions."""
    name: str
    description: str
    permissions: List[Permission]
    is_system_role: bool = False
    metadata: Optional[Dict[str, Any]] = None
    
    def has_permission(self, resource: str, action: str) -> bool:
        """Check if role has specific permission."""
        return any(perm.matches(resource, action) for perm in self.permissions)
    
    def get_permission_names(self) -> List[str]:
        """Get list of permission names."""
        return [str(perm) for perm in self.permissions]


@dataclass
class AuthConfig:
    """Authentication configuration for identity providers."""
    provider_type: IdentityProviderType
    client_id: str
    client_secret: Optional[str] = None
    issuer_url: Optional[str] = None
    user_pool_id: Optional[str] = None
    region: Optional[str] = None
    domain: Optional[str] = None
    scopes: List[str] = None
    redirect_uri: Optional[str] = None
    logout_uri: Optional[str] = None
    additional_config: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.scopes is None:
            self.scopes = ["openid", "email", "profile"]


@dataclass
class AgentCoreIdentityConfig:
    """Configuration for Bedrock AgentCore Identity integration."""
    workload_identity_arn: str
    region: str
    agent_id: str
    agent_alias_id: Optional[str] = None
    trust_policy: Optional[Dict[str, Any]] = None
    
    
@dataclass
class OAuthFlowConfig:
    """OAuth 2.0 flow configuration."""
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None
    end_session_endpoint: Optional[str] = None
    flow_type: str = "authorization_code"
    response_type: str = "code"
    grant_type: str = "authorization_code"


# Role and Permission Constants
class SystemRoles:
    """System-defined roles."""
    ADMIN = "admin"
    AGENT_CREATOR = "agent-creator"
    SUPERVISOR_USER = "supervisor-user"
    READONLY_USER = "readonly-user"


class SystemPermissions:
    """System-defined permissions."""
    # Agent management
    AGENT_CREATE = "agent:create"
    AGENT_READ = "agent:read"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    AGENT_DEPLOY = "agent:deploy"
    
    # Configuration management
    CONFIG_READ = "config:read"
    CONFIG_UPDATE = "config:update"
    CONFIG_DELETE = "config:delete"
    
    # User management
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"
    
    # System administration
    SYSTEM_ADMIN = "system:admin"
    SYSTEM_MONITOR = "system:monitor"
    
    # Supervisor agent specific
    SUPERVISOR_ACCESS = "supervisor:access"
    SUPERVISOR_MANAGE = "supervisor:manage"


# Agent-specific role patterns
def get_supervisor_role_name(supervisor_type: str) -> str:
    """Generate role name for specific supervisor agent type."""
    return f"supervisor-{supervisor_type.lower().replace(' ', '-')}-user"


def get_supervisor_permissions(supervisor_type: str) -> List[str]:
    """Get permissions for specific supervisor agent type."""
    base_role = f"supervisor-{supervisor_type.lower().replace(' ', '-')}"
    return [
        f"{base_role}:access",
        f"{base_role}:use",
        SystemPermissions.AGENT_READ,
        SystemPermissions.CONFIG_READ
    ]
