"""
Common utilities and shared modules for the GenAI In a Box platform.

This package contains reusable components that can be imported by
different services in the platform.
"""

# Version information
__version__ = "1.0.0"

# Make key modules easily accessible
__all__ = [
    'health_check_middleware',
    'logging_config',
    'data_protection_utils',
    'ssm_client',
    'base_agent_service',
    'auth'  # Authentication and authorization module
]
