"""
Identity provider implementations for the authentication system.

This module contains concrete implementations of identity providers that support
the abstract IdentityProvider interface, enabling pluggable authentication with
different external identity services.
"""

from .cognito_provider import CognitoProvider, create_cognito_provider_from_secret
from .base_provider import BaseIdentityProvider

# Placeholder imports for future providers will be added when providers are implemented

__all__ = [
    'BaseIdentityProvider',
    'CognitoProvider',
    'create_cognito_provider_from_secret',
    'create_provider',
    'create_cognito_provider',
]


# Provider factory function
def create_provider(provider_type: str, config):
    """
    Factory function to create identity provider instances.
    
    Args:
        provider_type: Type of provider ('cognito', 'okta', 'ping', 'auth0')
        config: Provider configuration
        
    Returns:
        IdentityProvider: Configured provider instance
        
    Raises:
        ValueError: If provider type is not supported
    """
    providers = {
        'cognito': CognitoProvider,
    }
    
    provider_class = providers.get(provider_type.lower())
    if not provider_class:
        supported = ', '.join(providers.keys())
        raise ValueError(f"Unsupported provider type: {provider_type}. Supported types: {supported}")
    
    return provider_class(config)


# Convenience functions for common providers
def create_cognito_provider(config):
    """Create and return a configured Cognito provider."""
    return CognitoProvider(config)
