"""
CDK Stack modules for the Generative AI in the Box application.

This package provides modular, well-structured CDK stacks following Python best practices:
- PEP 8 compliance with proper formatting and naming conventions
- Modular design with single responsibility principle
- Comprehensive error handling with custom exceptions
- Type safety and input validation
- Extensive documentation with docstrings
- Reusable mixins for common functionality
- Base classes with shared patterns
"""

# Import individual stack classes
import importlib.util
import sys
from pathlib import Path

from .vpc.stack import VpcStack
from .multi_agent.stack import MultiAgentStack
from .supervisor_agent.stack import SupervisorAgentStack
from .user_interface.stack import WebAppStack
from .authentication.stack import AuthenticationStack

# Import ConfigurationApiStack from configuration-api using importlib
config_api_path = Path(__file__).parent / "configuration-api" / "stack.py"
spec = importlib.util.spec_from_file_location("configuration_api.stack", config_api_path)
config_api_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config_api_module)
ConfigurationApiStack = config_api_module.ConfigurationApiStack

# Import common components from refactored structure
from .common import (
    BaseStack,
    FargateServiceStack,
    IAMPolicyMixin,
    SecurityGroupMixin,
    VpcLatticeServiceMixin,
    CognitoMixin,
    CognitoConfiguration,
    CognitoResources,
    StackConfigurationError,
    ResourceCreationError,
    ValidationError,
    ConfigValidator,
    AWSResourceValidator
)

__all__ = [
    # Stack classes
    "VpcStack",
    "ConfigurationApiStack", 
    "MultiAgentStack",
    "SupervisorAgentStack",
    "WebAppStack",
    "AuthenticationStack",
    
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
    
    # Exceptions
    "StackConfigurationError",
    "ResourceCreationError",
    "ValidationError",
    
    # Validators
    "ConfigValidator",
    "AWSResourceValidator"
]
