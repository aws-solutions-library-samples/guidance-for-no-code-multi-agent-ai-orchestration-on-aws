"""
AWS Systems Manager Parameter Store service.

This service handles all interactions with AWS SSM Parameter Store,
providing a clean abstraction for configuration storage and retrieval.
"""

import json
import logging
from typing import Dict, List, Optional

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../'))
from common.secure_logging_utils import log_exception_safely

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# Import SSM data models for validation (avoid circular imports)
try:
    from ..models.ssm_data_models import SSMDataValidator, SSMParameterPaths
    SSM_MODELS_AVAILABLE = True
    logger.info("SSM data models available for validation")
except ImportError:
    SSM_MODELS_AVAILABLE = False
    logger.warning("SSM data models not available - validation disabled")


class SSMService:
    """Service for AWS Systems Manager Parameter Store operations."""

    def __init__(self, region_name: str):
        """
        Initialize SSM service.
        
        Args:
            region_name: AWS region name for SSM operations
        """
        self.region_name = region_name
        self.client = boto3.client('ssm', region_name=region_name)
        
        # Get customer-managed KMS key for SecureString encryption
        # This key is created by the KMS stack and uses environment-specific naming pattern
        # Get environment from environment variable or default to development
        import os
        environment_name = os.environ.get('ENVIRONMENT', 'development')
        self.kms_key_alias = f"alias/{environment_name}-ssm-parameters"
        logger.info(f"SSMService initialized for region: {region_name} with KMS key: {self.kms_key_alias}")

    def sanitize_parameter_name(self, name: str) -> str:
        """
        Sanitize parameter name to comply with SSM naming requirements.
        
        SSM parameter names can only contain letters, numbers, and the symbols .-_
        This method replaces invalid characters with underscores.
        
        Args:
            name: Original parameter name
            
        Returns:
            Sanitized parameter name
        """
        import re
        # Replace any character that's not alphanumeric, dot, dash, or underscore with underscore
        sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', name)
        
        # Ensure it doesn't start with "ssm" (case insensitive)
        if sanitized.lower().startswith('ssm'):
            sanitized = 'param_' + sanitized
        return sanitized

    def store_parameter(
        self, 
        name: str, 
        value: str, 
        parameter_type: str = 'SecureString',  # SECURITY FIX: Default to SecureString
        description: str = "",
        tier: str = 'Advanced'
    ) -> bool:
        """
        Store a parameter in SSM Parameter Store with encryption.
        
        SECURITY: All parameters are SecureString by default with customer-managed KMS encryption.
        
        Args:
            name: Parameter name
            value: Parameter value
            parameter_type: Parameter type (SecureString is default for security)
            description: Parameter description
            tier: Parameter tier (Advanced is default for large configurations)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Build parameter request
            put_param_args = {
                'Name': name,
                'Value': value,
                'Type': parameter_type,
                'Tier': tier,
                'Overwrite': True,
                'Description': description
            }
            
            # Add KMS key for SecureString parameters
            if parameter_type == 'SecureString':
                put_param_args['KeyId'] = self.kms_key_alias
            
            self.client.put_parameter(**put_param_args)
            logger.info(f"🔐 Successfully stored SECURE parameter: {name} (type: {parameter_type}, tier: {tier})")
            return True
        except ClientError as e:
            logger.error(f"Error storing parameter {name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error storing parameter {name}: {e}")
            return False

    def get_parameter(self, name: str, with_decryption: bool = True) -> Optional[str]:
        """
        Retrieve a parameter from SSM Parameter Store.
        
        Args:
            name: Parameter name
            with_decryption: Whether to decrypt SecureString parameters
            
        Returns:
            Parameter value if found, None otherwise
        """
        try:
            response = self.client.get_parameter(
                Name=name,
                WithDecryption=with_decryption
            )
            logger.info(f"Successfully retrieved parameter: {name}")
            return response['Parameter']['Value']
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ParameterNotFound':
                logger.warning(f"Parameter not found: {name}")
                return None
            logger.error(f"Error retrieving parameter {name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error retrieving parameter {name}: {e}")
            raise

    def store_json_parameter(
        self, 
        name: str, 
        data: Dict, 
        description: str = "",
        tier: str = 'Advanced'
    ) -> bool:
        """
        Store a JSON object as an encrypted SecureString parameter.
        
        SECURITY: All JSON configurations are stored as SecureString with KMS encryption.
        
        Args:
            name: Parameter name
            data: Dictionary to store as JSON
            description: Parameter description
            tier: Parameter tier (Advanced for large agent configurations)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            json_value = json.dumps(data, indent=2)  # Pretty format for readability
            # SECURITY FIX: Always use SecureString for JSON configurations
            return self.store_parameter(name, json_value, 'SecureString', description, tier)
        except (TypeError, ValueError) as e:
            logger.error(f"Error serializing data for parameter {name}: {e}")
            return False

    def get_json_parameter(self, name: str) -> Optional[Dict]:
        """
        Retrieve and parse a JSON parameter.
        
        Args:
            name: Parameter name
            
        Returns:
            Parsed dictionary if successful, None otherwise
        """
        try:
            value = self.get_parameter(name)
            if value is None:
                return None
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON from parameter {name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error retrieving JSON parameter {name}: {e}")
            raise

    def list_parameters_by_prefix(
        self, 
        prefix: str, 
        max_results: int = 50
    ) -> List[Dict[str, str]]:
        """
        List parameters by name prefix.
        
        Args:
            prefix: Parameter name prefix to filter by
            max_results: Maximum number of results to return
            
        Returns:
            List of parameter information dictionaries
        """
        try:
            response = self.client.describe_parameters(
                ParameterFilters=[
                    {
                        'Key': 'Name',
                        'Option': 'BeginsWith',
                        'Values': [prefix]
                    }
                ],
                MaxResults=max_results
            )
            
            parameters = []
            for param in response.get('Parameters', []):
                parameters.append({
                    'name': param['Name'],
                    'type': param['Type'],
                    'last_modified': (
                        param['LastModifiedDate'].isoformat() 
                        if 'LastModifiedDate' in param else None
                    )
                })
            
            logger.info(f"Found {len(parameters)} parameters with prefix: {prefix}")
            return parameters
        except ClientError as e:
            logger.error(f"Error listing parameters with prefix {prefix}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error listing parameters with prefix {prefix}: {e}")
            raise

    def delete_parameter(self, name: str) -> bool:
        """
        Delete a parameter from SSM Parameter Store.
        
        Args:
            name: Parameter name to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.delete_parameter(Name=name)
            logger.info(f"Successfully deleted parameter: {name}")
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ParameterNotFound':
                logger.warning(f"Parameter not found for deletion: {name}")
                return False
            logger.error(f"Error deleting parameter {name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting parameter {name}: {e}")
            return False

    def parameter_exists(self, name: str) -> bool:
        """
        Check if a parameter exists.
        
        Args:
            name: Parameter name to check
            
        Returns:
            True if parameter exists, False otherwise
        """
        try:
            self.client.get_parameter(Name=name)
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ParameterNotFound':
                return False
            logger.error(f"Error checking parameter existence {name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error checking parameter existence {name}: {e}")
            raise

    def find_all_agent_parameters(self, agent_name: str) -> List[Dict[str, str]]:
        """
        Find ALL parameters containing the agent name using exhaustive search.
        
        This method uses multiple search strategies to ensure no parameters are missed:
        1. Direct prefix search for /agent/{agent_name}/
        2. Paginated search of all agent parameters with filtering
        3. Specific pattern matching for system prompts
        
        Args:
            agent_name: Name of the agent to search for
            
        Returns:
            List of all parameter information dictionaries containing the agent name
        """
        try:
            logger.info(f"Exhaustive search for ALL parameters containing agent name: {agent_name}")
            
            all_found_parameters = {}
            
            # Strategy 1: Direct prefix search - most efficient for standard patterns
            agent_prefix = f"/agent/{agent_name}/"
            try:
                prefix_parameters = self._paginated_parameter_search(agent_prefix)
                for param in prefix_parameters:
                    all_found_parameters[param['name']] = param
                logger.info(f"Strategy 1 (prefix): Found {len(prefix_parameters)} parameters")
            except Exception as e:
                logger.warning(f"Strategy 1 failed: {e}")
            
            # Strategy 2: Exhaustive search of all agent parameters - catches edge cases
            try:
                all_agent_params = self._paginated_parameter_search("/agent/")
                containing_parameters = [
                    param for param in all_agent_params 
                    if agent_name in param['name']
                ]
                for param in containing_parameters:
                    all_found_parameters[param['name']] = param
                logger.info(f"Strategy 2 (exhaustive): Found {len(containing_parameters)} additional parameters")
            except Exception as e:
                logger.warning(f"Strategy 2 failed: {e}")
            
            # Strategy 3: Direct pattern matching for known system prompt patterns
            try:
                system_prompt_patterns = [
                    f"/agent/{agent_name}/system-prompts/research",
                    f"/agent/{agent_name}/system-prompts/qa",
                    f"/agent/{agent_name}/system-prompts/weather",
                    f"/agent/{agent_name}/system-prompts/supervisor",
                    f"/agent/{agent_name}/system-prompts/elasticsearch",
                    f"/agent/{agent_name}/system-prompts/snowflake",
                    f"/agent/{agent_name}/system-prompts/aurora",
                    f"/agent/{agent_name}/system-prompts/summarization"
                ]
                
                pattern_found = 0
                for pattern in system_prompt_patterns:
                    if self.parameter_exists(pattern):
                        try:
                            response = self.client.describe_parameters(
                                Names=[pattern],
                                MaxResults=1
                            )
                            if response.get('Parameters'):
                                param = response['Parameters'][0]
                                param_info = {
                                    'name': param['Name'],
                                    'type': param['Type'],
                                    'last_modified': (
                                        param['LastModifiedDate'].isoformat() 
                                        if 'LastModifiedDate' in param else None
                                    )
                                }
                                all_found_parameters[pattern] = param_info
                                pattern_found += 1
                        except Exception as e:
                            logger.warning(f"Could not get info for pattern {pattern}: {e}")
                
                logger.info(f"Strategy 3 (patterns): Found {pattern_found} system prompt parameters")
            except Exception as e:
                logger.warning(f"Strategy 3 failed: {e}")
            
            # Convert back to list and sort for consistent output
            final_parameters = sorted(all_found_parameters.values(), key=lambda x: x['name'])
            
            logger.info(f"🔍 EXHAUSTIVE SEARCH COMPLETE: Found {len(final_parameters)} total parameters for agent '{agent_name}':")
            for param in final_parameters:
                logger.info(f"  ✅ {param['name']} ({param['type']})")
            
            return final_parameters
            
        except Exception as e:
            logger.error(f"Error in exhaustive parameter search for agent '{agent_name}': {e}")
            raise
    
    def _paginated_parameter_search(self, prefix: str) -> List[Dict[str, str]]:
        """
        Search parameters with pagination to ensure all results are captured.
        
        Args:
            prefix: Parameter name prefix to search for
            
        Returns:
            List of all parameters matching the prefix
        """
        try:
            all_parameters = []
            paginator = self.client.get_paginator('describe_parameters')
            
            page_iterator = paginator.paginate(
                ParameterFilters=[
                    {
                        'Key': 'Name',
                        'Option': 'BeginsWith',
                        'Values': [prefix]
                    }
                ]
            )
            
            for page in page_iterator:
                for param in page.get('Parameters', []):
                    all_parameters.append({
                        'name': param['Name'],
                        'type': param['Type'],
                        'last_modified': (
                            param['LastModifiedDate'].isoformat() 
                            if 'LastModifiedDate' in param else None
                        )
                    })
            
            logger.info(f"Paginated search for prefix '{prefix}' found {len(all_parameters)} parameters")
            return all_parameters
            
        except Exception as e:
            logger.error(f"Error in paginated parameter search for prefix '{prefix}': {e}")
            raise

    def get_connection_status(self) -> Dict[str, str]:
        """
        Test SSM connectivity and return status information.
        
        Returns:
            Dictionary containing connection status and region info
        """
        try:
            # Test basic connectivity by listing a small number of parameters
            self.client.describe_parameters(MaxResults=1)
            return {
                "status": "connected",
                "region": self.region_name,
                "service": "ssm"
            }
        except Exception as e:
            logger.error("SSM connectivity test failed")
            log_exception_safely(logger, e, "SSM connectivity test failed")
            # Do not include exception details in returned value!
            return {
                "status": "error",
                "region": self.region_name,
                "service": "ssm"
            }
