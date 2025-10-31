"""Validation utilities for CDK stacks."""

import re
from typing import Any, Dict, List, Optional, Union

from aws_cdk import aws_ec2 as ec2

from .exceptions import ValidationError


class ConfigValidator:
    """Utility class for validating configuration parameters."""
    
    @staticmethod
    def validate_required_config(config: Dict[str, Any], 
                                required_keys: List[str]) -> None:
        """
        Validate that all required configuration keys are present.
        
        Args:
            config: Configuration dictionary to validate
            required_keys: List of required configuration keys
            
        Raises:
            ValidationError: If any required key is missing
        """
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            raise ValidationError(
                f"Missing required configuration keys: {', '.join(missing_keys)}",
                parameter_name="config",
                provided_value=str(list(config.keys()))
            )
    
    @staticmethod
    def validate_port_range(port: int) -> None:
        """
        Validate that port number is within valid range.
        
        Args:
            port: Port number to validate
            
        Raises:
            ValidationError: If port is outside valid range
        """
        if not 1 <= port <= 65535:
            raise ValidationError(
                f"Port must be between 1 and 65535, got {port}",
                parameter_name="port",
                provided_value=str(port)
            )
    
    @staticmethod
    def validate_cidr_block(cidr: str) -> None:
        """
        Validate CIDR block format.
        
        Args:
            cidr: CIDR block to validate
            
        Raises:
            ValidationError: If CIDR format is invalid
        """
        cidr_pattern = re.compile(
            r'^([0-9]{1,3}\.){3}[0-9]{1,3}(/([0-9]|[1-2][0-9]|3[0-2]))?$'
        )
        if not cidr_pattern.match(cidr):
            raise ValidationError(
                f"Invalid CIDR block format: {cidr}",
                parameter_name="cidr",
                provided_value=cidr
            )
    
    @staticmethod
    def validate_resource_name(name: str, max_length: int = 63) -> None:
        """
        Validate AWS resource name format.
        
        Args:
            name: Resource name to validate
            max_length: Maximum allowed length
            
        Raises:
            ValidationError: If name format is invalid
        """
        # Skip validation for CDK tokens (CloudFormation references)
        if isinstance(name, str) and ('${Token[' in name or '${' in name):
            return
        
        if not name:
            raise ValidationError(
                "Resource name cannot be empty",
                parameter_name="name",
                provided_value=name
            )
        
        if len(name) > max_length:
            raise ValidationError(
                f"Resource name too long (max {max_length}): {name}",
                parameter_name="name",
                provided_value=name
            )
        
        # AWS resource names should contain only alphanumeric chars, hyphens, and underscores
        if not re.match(r'^[a-zA-Z0-9-_]+$', name):
            raise ValidationError(
                f"Invalid resource name format: {name}. "
                f"Only alphanumeric characters, hyphens, and underscores allowed",
                parameter_name="name",
                provided_value=name
            )
    
    @staticmethod
    def validate_environment_vars(env_vars: Optional[Dict[str, str]]) -> None:
        """
        Validate environment variables dictionary.
        
        Args:
            env_vars: Environment variables to validate
            
        Raises:
            ValidationError: If environment variables are invalid
        """
        if env_vars is None:
            return
        
        if not isinstance(env_vars, dict):
            raise ValidationError(
                "Environment variables must be a dictionary",
                parameter_name="environment_vars",
                provided_value=str(type(env_vars))
            )
        
        for key, value in env_vars.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise ValidationError(
                    f"Environment variable key and value must be strings: {key}={value}",
                    parameter_name="environment_vars",
                    provided_value=f"{key}={value}"
                )


class AWSResourceValidator:
    """Utility class for validating AWS resource parameters."""
    
    @staticmethod
    def validate_vpc(vpc: ec2.IVpc) -> None:
        """
        Validate VPC resource.
        
        Args:
            vpc: VPC to validate (can be Vpc or imported via IVpc)
            
        Raises:
            ValidationError: If VPC is invalid
        """
        # Check if VPC has required attributes instead of using isinstance
        # since IVpc is a Protocol and can't be used with isinstance()
        if not hasattr(vpc, 'vpc_id'):
            raise ValidationError(
                f"Expected VPC instance with vpc_id attribute, got {type(vpc)}",
                parameter_name="vpc",
                provided_value=str(type(vpc))
            )
    
    @staticmethod
    def validate_subnets(subnets: List[ec2.ISubnet], 
                        min_count: int = 1) -> None:
        """
        Validate subnet list.
        
        Args:
            subnets: List of subnets to validate
            min_count: Minimum number of subnets required
            
        Raises:
            ValidationError: If subnets are invalid
        """
        if not subnets:
            raise ValidationError(
                "At least one subnet is required",
                parameter_name="subnets",
                provided_value="[]"
            )
        
        if len(subnets) < min_count:
            raise ValidationError(
                f"At least {min_count} subnets required, got {len(subnets)}",
                parameter_name="subnets",
                provided_value=str(len(subnets))
            )
    
    @staticmethod
    def validate_arn(arn: str, service: Optional[str] = None) -> None:
        """
        Validate AWS ARN format.
        
        Args:
            arn: ARN to validate
            service: Expected AWS service (optional)
            
        Raises:
            ValidationError: If ARN format is invalid
        """
        # Skip validation for CDK tokens (CloudFormation references)
        if arn.startswith('${Token[') or '${' in arn:
            return
        
        arn_pattern = re.compile(
            r'^arn:aws[a-zA-Z0-9-]*:[a-zA-Z0-9-]+:'
            r'[a-zA-Z0-9-]*:[0-9]*:[a-zA-Z0-9-/._]+$'
        )
        
        if not arn_pattern.match(arn):
            raise ValidationError(
                f"Invalid ARN format: {arn}",
                parameter_name="arn",
                provided_value=arn
            )
        
        if service and ':' in arn and not arn.split(':')[2] == service:
            expected_service = arn.split(':')[2]
            raise ValidationError(
                f"Expected {service} service ARN, got {expected_service}",
                parameter_name="arn",
                provided_value=arn
            )
