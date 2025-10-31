"""
Authentication API routes for the Configuration API.

This module provides endpoints for token validation, user information,
and authentication status checking.
"""

import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

from common.auth import (
    get_auth_service,
    AuthService,
    UserInfo,
    AuthenticationError,
    TokenValidationError
)
from ..middleware.auth_middleware import security, get_current_user, get_current_user_optional

logger = logging.getLogger(__name__)

# Create router for authentication endpoints
router = APIRouter(prefix="/api/auth", tags=["authentication"])


# Response models
class TokenValidationResponse(BaseModel):
    """Response model for token validation."""
    valid: bool
    user_info: Optional[Dict[str, Any]] = None
    expires_in: Optional[int] = None
    error: Optional[str] = None
    error_description: Optional[str] = None


class UserInfoResponse(BaseModel):
    """Response model for user information."""
    user_id: str
    username: str
    email: str
    roles: list[str]
    permissions: list[str]
    groups: list[str]
    authenticated: bool = True


class AuthStatusResponse(BaseModel):
    """Response model for authentication status."""
    authenticated: bool
    provider: str
    provider_type: str
    ready: bool


class HealthResponse(BaseModel):
    """Response model for authentication health check."""
    status: str
    provider: str
    ready: bool
    timestamp: str


@router.get("/health", response_model=HealthResponse)
async def auth_health():
    """
    Health check endpoint for authentication service.
    
    Returns:
        HealthResponse: Authentication service health status
    """
    auth_service = get_auth_service()
    
    return HealthResponse(
        status="healthy" if auth_service.is_ready() else "not_ready",
        provider=auth_service.get_provider_name(),
        ready=auth_service.is_ready(),
        timestamp=datetime.utcnow().isoformat()
    )


@router.post("/validate-token", response_model=TokenValidationResponse)
async def validate_token(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Validate JWT token and return user information.
    
    Args:
        credentials: HTTP authorization credentials containing Bearer token
        
    Returns:
        TokenValidationResponse: Token validation result
    """
    if not credentials:
        return TokenValidationResponse(
            valid=False,
            error="missing_token",
            error_description="Authorization header with Bearer token is required"
        )
    
    auth_service = get_auth_service()
    
    try:
        user_info = await auth_service.validate_token(credentials.credentials)
        
        return TokenValidationResponse(
            valid=True,
            user_info={
                "user_id": user_info.user_id,
                "username": user_info.username,
                "email": user_info.email,
                "roles": user_info.roles,
                "permissions": user_info.permissions,
                "groups": user_info.groups
            },
            expires_in=int((user_info.token_expires_at - datetime.utcnow()).total_seconds())
        )
        
    except TokenValidationError as e:
        return TokenValidationResponse(
            valid=False,
            error="invalid_token",
            error_description=str(e)
        )
    except AuthenticationError as e:
        return TokenValidationResponse(
            valid=False,
            error="authentication_failed",
            error_description=str(e)
        )
    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        return TokenValidationResponse(
            valid=False,
            error="validation_error",
            error_description="Internal validation error"
        )


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Get current authenticated user information.
    
    Args:
        current_user: Current authenticated user from dependency
        
    Returns:
        UserInfoResponse: Current user information
    """
    return UserInfoResponse(
        user_id=current_user.user_id,
        username=current_user.username,
        email=current_user.email,
        roles=current_user.roles,
        permissions=current_user.permissions,
        groups=current_user.groups,
        authenticated=True
    )


@router.get("/status", response_model=AuthStatusResponse)
async def get_auth_status(
    current_user: Optional[UserInfo] = Depends(get_current_user_optional)
):
    """
    Get authentication status for current request.
    
    Args:
        current_user: Optional current user information
        
    Returns:
        AuthStatusResponse: Authentication status
    """
    auth_service = get_auth_service()
    
    return AuthStatusResponse(
        authenticated=current_user is not None,
        provider=auth_service.get_provider_name(),
        provider_type=auth_service.get_provider_type().value if auth_service.get_provider_type() else "none",
        ready=auth_service.is_ready()
    )


@router.get("/permissions")
async def get_user_permissions(
    current_user: UserInfo = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get detailed permissions for current user.
    
    Args:
        current_user: Current authenticated user
        
    Returns:
        Dict[str, Any]: User permissions and role details
    """
    auth_service = get_auth_service()
    
    try:
        # Get detailed role information if role manager is available
        detailed_permissions = []
        if auth_service.role_manager:
            permissions = await auth_service.role_manager.get_user_permissions(current_user.user_id)
            for perm in permissions:
                detailed_permissions.append({
                    "name": perm.name,
                    "description": perm.description,
                    "resource": perm.resource,
                    "action": perm.action,
                    "conditions": perm.conditions
                })
        
        return {
            "user_id": current_user.user_id,
            "roles": current_user.roles,
            "permissions": current_user.permissions,
            "detailed_permissions": detailed_permissions,
            "groups": current_user.groups
        }
        
    except Exception as e:
        logger.error(f"Error getting user permissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to retrieve user permissions"
        )


@router.post("/check-permission")
async def check_permission(
    permission_request: Dict[str, str],
    current_user: UserInfo = Depends(get_current_user)
) -> Dict[str, bool]:
    """
    Check if current user has specific permission.
    
    Args:
        permission_request: Dict with 'resource' and 'action' keys
        current_user: Current authenticated user
        
    Returns:
        Dict[str, bool]: Permission check result
    """
    resource = permission_request.get('resource')
    action = permission_request.get('action')
    
    if not resource or not action:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both 'resource' and 'action' are required"
        )
    
    auth_service = get_auth_service()
    
    try:
        has_permission = await auth_service.check_permission(
            current_user.user_id, resource, action
        )
        
        return {
            "user_id": current_user.user_id,
            "resource": resource,
            "action": action,
            "has_permission": has_permission
        }
        
    except Exception as e:
        logger.error(f"Error checking permission: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to check permission"
        )


# Import datetime for health endpoint
from datetime import datetime
