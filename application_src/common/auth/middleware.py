"""
Common OAuth 2.0 Bearer token authentication middleware for FastAPI services.

This module provides reusable authentication middleware that can be used
across all services (Configuration API, Supervisor Agent, etc.) with
service-specific configuration options.
"""

import logging
from typing import Optional, List, Callable, Any
from functools import wraps

from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .auth_service import get_auth_service
from .types import UserInfo, AuthenticationError, TokenValidationError

logger = logging.getLogger(__name__)

# Global security scheme for FastAPI
security = HTTPBearer(auto_error=False)


def log_exception_safely(logger_instance: logging.Logger, message: str, exception: Exception) -> None:
    """
    Safely log exceptions without exposing sensitive information.
    
    Args:
        logger_instance: Logger instance to use
        message: Message to log
        exception: Exception to log
    """
    try:
        logger_instance.error(f"{message}: {type(exception).__name__}")
        logger_instance.debug(f"{message}: {str(exception)}", exc_info=True)
    except Exception as log_error:
        # Fallback if logging itself fails
        logger_instance.error(f"Failed to log exception: {type(log_error).__name__}")


class CommonOAuth2BearerMiddleware(BaseHTTPMiddleware):
    """
    Common FastAPI middleware for OAuth 2.0 Bearer token authentication.
    
    This middleware can be used by any service (Configuration API, Supervisor Agent, etc.)
    with service-specific configuration.
    """
    
    def __init__(
        self, 
        app, 
        service_name: str = "unknown_service",
        excluded_paths: Optional[List[str]] = None,
        store_token_callback: Optional[Callable[[str], None]] = None
    ):
        super().__init__(app)
        self.service_name = service_name
        self.store_token_callback = store_token_callback
        
        # Default excluded paths that work for all services
        default_excluded = [
            '/health',
            '/metrics', 
            '/docs',
            '/redoc',
            '/openapi.json',
            '/',  # Root endpoint for service info
            '/.well-known/agent-card.json'  # Agent discovery endpoint
        ]
        
        # Service-specific excluded paths
        if excluded_paths:
            self.excluded_paths = default_excluded + excluded_paths
        else:
            self.excluded_paths = default_excluded
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request through authentication middleware.
        
        Args:
            request: FastAPI request object
            call_next: Next middleware or endpoint
            
        Returns:
            Response: HTTP response
        """
        # Skip authentication for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)
        
        try:
            # Extract bearer token from Authorization header
            auth_header = request.headers.get('Authorization')
            token = self._extract_bearer_token(auth_header)
            
            if not token:
                logger.warning(f"[{self.service_name}] Missing authorization token for {request.url.path}")
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        'error': 'missing_token',
                        'error_description': 'Authorization header with Bearer token is required'
                    }
                )
            
            # Validate token and get user info
            try:
                auth_service = get_auth_service()
                user_info = await auth_service.validate_token(token)
                
                # Add user info and token to request state
                request.state.user = user_info
                request.state.auth_token = token
                request.state.authenticated = True
                
                # Call service-specific token storage callback if provided
                if self.store_token_callback:
                    self.store_token_callback(token)
                
                logger.debug(f"[{self.service_name}] Authenticated user: {user_info.username}")
                
            except TokenValidationError as e:
                log_exception_safely(logger, f"[{self.service_name}] Token validation failed", e)
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        'error': 'invalid_token',
                        'error_description': 'Token validation failed'
                    }
                )
            except AuthenticationError as e:
                log_exception_safely(logger, f"[{self.service_name}] Authentication failed", e)
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={
                        'error': 'authentication_failed',
                        'error_description': 'Authentication failed'
                    }
                )
            
            # Continue with request
            return await call_next(request)
            
        except Exception as e:
            log_exception_safely(logger, f"[{self.service_name}] Authentication middleware error", e)
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    'error': 'authentication_error',
                    'error_description': 'Internal authentication error'
                }
            )
    
    def _extract_bearer_token(self, auth_header: Optional[str]) -> Optional[str]:
        """
        Extract bearer token from Authorization header.
        
        Args:
            auth_header: Authorization header value
            
        Returns:
            Optional[str]: Bearer token if found
        """
        if not auth_header:
            return None
        
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return None
        
        return parts[1]


# Common FastAPI dependency for getting current user
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> UserInfo:
    """
    FastAPI dependency to get current authenticated user.
    Works across all services.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        UserInfo: Current user information
        
    Raises:
        HTTPException: If user is not authenticated
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header with Bearer token is required",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    try:
        auth_service = get_auth_service()
        user_info = await auth_service.validate_token(credentials.credentials)
        return user_info
    except TokenValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed",
            headers={"WWW-Authenticate": "Bearer"}
        )


# Common FastAPI dependency for optional authentication
async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[UserInfo]:
    """
    FastAPI dependency to get current user (optional).
    Works across all services.
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        Optional[UserInfo]: User information if authenticated, None otherwise
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials)
    except HTTPException:
        return None


# Decorator for requiring authentication
def require_authentication(func: Callable) -> Callable:
    """
    Decorator to require authentication for endpoint functions.
    
    Args:
        func: Endpoint function to protect
        
    Returns:
        Callable: Protected endpoint function
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Check if user is provided in kwargs (from dependency)
        user = kwargs.get('current_user')
        if not user or not isinstance(user, UserInfo):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"}
            )
        
        return await func(*args, **kwargs)
    
    return wrapper


# Decorator for requiring specific permissions
def require_permission(*required_permissions: str):
    """
    Decorator to require specific permissions for endpoint access.
    
    Args:
        *required_permissions: Required permission strings
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get('current_user')
            if not user or not isinstance(user, UserInfo):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Check permissions
            auth_service = get_auth_service()
            for permission in required_permissions:
                if ':' in permission:
                    resource, action = permission.split(':', 1)
                    has_permission = await auth_service.check_permission(
                        user.user_id, resource, action
                    )
                    if not has_permission:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Missing required permission: {permission}"
                        )
                else:
                    # Check if user has the permission directly
                    if permission not in user.permissions:
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail=f"Missing required permission: {permission}"
                        )
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# Decorator for requiring specific roles
def require_role(*required_roles: str):
    """
    Decorator to require specific roles for endpoint access.
    
    Args:
        *required_roles: Required role names
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            user = kwargs.get('current_user')
            if not user or not isinstance(user, UserInfo):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Check roles - user needs at least one of the required roles
            if not user.has_any_role(list(required_roles)):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required role. Required one of: {', '.join(required_roles)}"
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# FastAPI dependency for permission checking
class RequirePermission:
    """
    FastAPI dependency class for permission checking.
    
    Usage:
        @app.get("/protected")
        async def protected_endpoint(
            user: UserInfo = Depends(get_current_user),
            _: None = Depends(RequirePermission("agent:read"))
        ):
            return {"message": "Access granted"}
    """
    
    def __init__(self, permission: str):
        self.permission = permission
    
    async def __call__(self, user: UserInfo = Depends(get_current_user)):
        """
        Check if user has required permission.
        
        Args:
            user: Current authenticated user
            
        Raises:
            HTTPException: If user lacks permission
        """
        if ':' in self.permission:
            resource, action = self.permission.split(':', 1)
            auth_service = get_auth_service()
            has_permission = await auth_service.check_permission(
                user.user_id, resource, action
            )
            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {self.permission}"
                )
        else:
            if self.permission not in user.permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required permission: {self.permission}"
                )


# FastAPI dependency for role checking  
class RequireRole:
    """
    FastAPI dependency class for role checking.
    
    Usage:
        @app.get("/admin")
        async def admin_endpoint(
            user: UserInfo = Depends(get_current_user),
            _: None = Depends(RequireRole("admin"))
        ):
            return {"message": "Admin access granted"}
    """
    
    def __init__(self, *roles: str):
        self.roles = roles
    
    async def __call__(self, user: UserInfo = Depends(get_current_user)):
        """
        Check if user has required role.
        
        Args:
            user: Current authenticated user
            
        Raises:
            HTTPException: If user lacks role
        """
        if not user.has_any_role(list(self.roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required role. Required one of: {', '.join(self.roles)}"
            )


# Context manager for request authentication
class AuthenticationContext:
    """
    Context manager for handling authentication in request processing.
    """
    
    def __init__(self, request: Request):
        self.request = request
        self.user: Optional[UserInfo] = None
        self.authenticated = False
    
    async def __aenter__(self):
        """Initialize authentication context."""
        try:
            # Get user from request state (set by middleware)
            self.user = getattr(self.request.state, 'user', None)
            self.authenticated = getattr(self.request.state, 'authenticated', False)
            
            return self
            
        except Exception as e:
            log_exception_safely(logger, "Failed to initialize authentication context", e)
            self.user = None
            self.authenticated = False
            return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up authentication context."""
        pass
    
    def require_authentication(self):
        """Require user to be authenticated."""
        if not self.authenticated or not self.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
    
    def require_permission(self, permission: str):
        """Require user to have specific permission."""
        self.require_authentication()
        
        if permission not in self.user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required permission: {permission}"
            )
    
    def require_role(self, *roles: str):
        """Require user to have one of the specified roles."""
        self.require_authentication()
        
        if not self.user.has_any_role(list(roles)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required role. Required one of: {', '.join(roles)}"
            )


# Factory function to create service-specific middleware
def create_oauth_middleware(
    service_name: str,
    additional_excluded_paths: Optional[List[str]] = None,
    token_storage_callback: Optional[Callable[[str], None]] = None
):
    """
    Factory function to create OAuth middleware for a specific service.
    
    Args:
        service_name: Name of the service for logging
        additional_excluded_paths: Service-specific paths to exclude from auth
        token_storage_callback: Optional callback to store token for forwarding
        
    Returns:
        Configured middleware class
    """
    class ServiceSpecificOAuth2Middleware(CommonOAuth2BearerMiddleware):
        def __init__(self, app):
            super().__init__(
                app=app,
                service_name=service_name,
                excluded_paths=additional_excluded_paths,
                store_token_callback=token_storage_callback
            )
    
    return ServiceSpecificOAuth2Middleware


# Supervisor Agent specific middleware factory
def create_supervisor_auth_middleware(supervisor_service_instance):
    """
    Create OAuth middleware specifically for Supervisor Agent.
    
    Args:
        supervisor_service_instance: Instance to store tokens in
        
    Returns:
        Configured middleware class for supervisor agent
    """
    def store_token_in_supervisor(token: str):
        """Store token in supervisor service for Configuration API forwarding."""
        supervisor_service_instance._current_auth_token = token
    
    return create_oauth_middleware(
        service_name="supervisor_agent",
        additional_excluded_paths=[
            '/v1/message:stream',  # A2A streaming endpoint
        ],
        token_storage_callback=store_token_in_supervisor
    )


# Configuration API specific middleware factory  
def create_config_api_auth_middleware():
    """
    Create OAuth middleware specifically for Configuration API.
    
    Returns:
        Configured middleware class for configuration API
    """
    return create_oauth_middleware(
        service_name="configuration_api",
        additional_excluded_paths=[
            '/api/auth/health',
            '/api/auth/validate-token',
            '/internal/discover'  # Allow unauthenticated internal discovery for service startup
        ]
    )
