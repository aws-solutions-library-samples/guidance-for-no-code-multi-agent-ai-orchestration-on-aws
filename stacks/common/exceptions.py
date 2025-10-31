"""Custom exceptions for CDK stacks."""

from typing import Optional


class StackConfigurationError(Exception):
    """
    Exception raised when stack configuration is invalid.
    
    Attributes:
        message: Human-readable error description
        config_key: The configuration key that caused the error
    """
    
    def __init__(self, message: str, config_key: Optional[str] = None) -> None:
        """
        Initialize the exception.
        
        Args:
            message: Human-readable error description
            config_key: The configuration key that caused the error
        """
        self.message = message
        self.config_key = config_key
        super().__init__(self.message)


class ResourceCreationError(Exception):
    """
    Exception raised when AWS resource creation fails.
    
    Attributes:
        message: Human-readable error description
        resource_type: The AWS resource type that failed to create
    """
    
    def __init__(self, message: str, resource_type: Optional[str] = None) -> None:
        """
        Initialize the exception.
        
        Args:
            message: Human-readable error description
            resource_type: The AWS resource type that failed to create
        """
        self.message = message
        self.resource_type = resource_type
        super().__init__(self.message)


class ValidationError(Exception):
    """
    Exception raised when parameter validation fails.
    
    Attributes:
        message: Human-readable error description
        parameter_name: The parameter that failed validation
        provided_value: The value that was provided
    """
    
    def __init__(
        self, 
        message: str, 
        parameter_name: Optional[str] = None,
        provided_value: Optional[str] = None
    ) -> None:
        """
        Initialize the exception.
        
        Args:
            message: Human-readable error description
            parameter_name: The parameter that failed validation
            provided_value: The value that was provided
        """
        self.message = message
        self.parameter_name = parameter_name
        self.provided_value = provided_value
        super().__init__(self.message)
