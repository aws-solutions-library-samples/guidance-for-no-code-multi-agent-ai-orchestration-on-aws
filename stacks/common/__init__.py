"""
Common CDK stack components and utilities.

This module provides reusable components following Python best practices:
- Modular design with single responsibility
- Comprehensive error handling
- Type safety and validation
- Clear documentation and examples
"""

# Import base classes
from .base import BaseStack, FargateServiceStack

# Import mixins
from .mixins import (
    IAMPolicyMixin,
    SecurityGroupMixin,
    VpcLatticeServiceMixin,
    CognitoMixin,
    CognitoConfiguration,
    CognitoResources,
    LoadBalancerLoggingMixin
)

# Import exceptions
from .exceptions import (
    StackConfigurationError,
    ResourceCreationError,
    ValidationError
)

# Import validators
from .validators import (
    ConfigValidator,
    AWSResourceValidator
)

# Import constants
from .constants import *

__all__ = [
    # Base classes
    "BaseStack",
    "FargateServiceStack",
    
    # Mixins
    "IAMPolicyMixin",
    "SecurityGroupMixin",
    "VpcLatticeServiceMixin",
    "CognitoMixin",
    "CognitoConfiguration",
    "CognitoResources",
    "LoadBalancerLoggingMixin",
    
    # Exceptions
    "StackConfigurationError",
    "ResourceCreationError", 
    "ValidationError",
    
    # Validators
    "ConfigValidator",
    "AWSResourceValidator",
    
    # Constants (imported from constants module)
]
