"""
Authentication and authorization module for GenAI-in-the-Box platform.

This module provides an extensible authentication system that supports multiple
identity providers through an abstract interface, enabling OAuth 2.0 bearer token
authentication, role-based access control, and Bedrock AgentCore Identity integration.

Key Components:
- Abstract IDP Interface: Extensible identity provider interface supporting Cognito, Okta, Ping, Auth0
- OAuth Bearer Token Authentication: JWT-based API security for Configuration API endpoints
- Role-Based Access Control: Dynamic permission system for admin, agent-creator, and agent-specific roles
- JWT Token Management: Token validation, parsing, signature verification, and refresh
- Bedrock AgentCore Identity: Secure agent-to-agent authentication for standalone mode
"""

from .types import (
    AuthenticationResult,
    AuthenticationError,
    TokenValidationError,
    IdentityProviderType,
    UserInfo,
    JWTToken,
    Role,
    Permission,
    AuthConfig
)

from .interfaces import (
    IdentityProvider,
    TokenValidator,
    RoleManager
)

from .providers import (
    CognitoProvider,
    BaseIdentityProvider,
    create_provider,
    create_cognito_provider_from_secret
)

from .jwt_handler import JWTHandler
from .role_manager import RoleManagerService
from .auth_service import AuthService, get_auth_service, initialize_auth_service

__all__ = [
    # Types
    'AuthenticationResult',
    'AuthenticationError', 
    'TokenValidationError',
    'IdentityProviderType',
    'UserInfo',
    'JWTToken',
    'Role',
    'Permission',
    'AuthConfig',
    
    # Interfaces
    'IdentityProvider',
    'TokenValidator',
    'RoleManager',
    
    # Providers
    'CognitoProvider',
    'BaseIdentityProvider',
    'create_provider',
    'create_cognito_provider_from_secret',
    
    # Services
    'JWTHandler',
    'RoleManagerService',
    'AuthService',
    'get_auth_service',
    'initialize_auth_service'
]
