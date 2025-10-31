"""
Configuration API authentication middleware (DEPRECATED - USE COMMON MODULE).

This file now imports from the common auth middleware module to avoid code duplication.
All services should use the common middleware for consistency.
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

# Import from common auth middleware module
from common.auth.middleware import (
    create_config_api_auth_middleware,
    get_current_user,
    get_current_user_optional,
    require_authentication,
    require_permission,
    require_role,
    RequirePermission,
    RequireRole,
    AuthenticationContext,
    security  # Import security scheme for backward compatibility
)

# Create Configuration API specific middleware
OAuth2BearerMiddleware = create_config_api_auth_middleware()

# Re-export security for backward compatibility with existing imports
__all__ = [
    'OAuth2BearerMiddleware',
    'get_current_user',
    'get_current_user_optional',
    'require_authentication',
    'require_permission', 
    'require_role',
    'RequirePermission',
    'RequireRole',
    'AuthenticationContext',
    'security'
]
