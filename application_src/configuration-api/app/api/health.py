"""
Health check API routes.

This module provides health monitoring endpoints for load balancers and monitoring systems.
"""

from fastapi import APIRouter

health_router = APIRouter()


@health_router.get('/health')
def health_check():
    """
    Health check endpoint for the load balancer.
    
    Returns:
        Dictionary with health status
    """
    return {"status": "healthy"}
