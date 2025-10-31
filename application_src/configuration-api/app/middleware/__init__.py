"""
Middleware modules for the Configuration API.

This package contains middleware components for request processing,
authentication, authorization, and security.
"""

from .auth_middleware import (
    OAuth2BearerMiddleware,
    require_authentication,
    require_permission,
    get_current_user
)

# Security middleware imports will be added when modules are implemented

__all__ = [
    'OAuth2BearerMiddleware',
    'require_authentication', 
    'require_permission',
    'get_current_user',
]
