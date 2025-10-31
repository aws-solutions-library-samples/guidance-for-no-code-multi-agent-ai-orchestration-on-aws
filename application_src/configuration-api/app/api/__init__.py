"""
API routes for configuration API.

This module contains all FastAPI route definitions organized by feature area.
"""

from .health import health_router
from .discovery import discovery_router
from .config import config_router
from .form_schema import form_schema_router
from .deployment import deployment_router
from .registry import registry_router

__all__ = [
    "health_router",
    "discovery_router", 
    "config_router",
    "form_schema_router",
    "deployment_router",
    "registry_router",
]
