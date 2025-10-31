import boto3
import json
import time
import logging
import os
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SSMClient:
    def __init__(self):
        # Get region from environment variable with fallback
        region = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
        self.client = boto3.client('ssm', region_name=region)
        self.region = region
        self.cache_ttl = 10  # Reduce cache TTL to 10 seconds
        self.last_refresh = {}  # Track last refresh time for each parameter
        self.cache = {}  # Simple cache for parameter values
        self.parameter_metadata = {}  # Cache parameter metadata including type
        
    def get_parameter(self, name, default=None, force_refresh=False):
        """Get a single parameter value with minimal caching"""
        current_time = time.time()
        
        # Check if we need to refresh this parameter
        if force_refresh or name not in self.last_refresh or (current_time - self.last_refresh[name]) > self.cache_ttl:
            try:
                response = self.client.get_parameter(Name=name, WithDecryption=True)
                value = response['Parameter']['Value']
                self.last_refresh[name] = current_time
                self.cache[name] = value
                return value
            except Exception as e:
                print(f"Error getting parameter {name}: {str(e)}")
                return default
        else:
            # Use cached value
            return self.cache.get(name, default)
    
    def get_json_parameter(self, name: str, default: Optional[Dict[str, Any]] = None, force_refresh: bool = False) -> Dict[str, Any]:
        """Get a parameter and parse it as JSON"""
        value = self.get_parameter(name, None, force_refresh)
        if value is not None:
            try:
                return json.loads(value)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse parameter {name} as JSON: {str(e)}")
                pass
        return default if default is not None else {}
    
    def get_parameter_metadata(self, name: str, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get parameter metadata including type, description, and last modified date.
        
        Args:
            name: Parameter name
            force_refresh: Force refresh from SSM
            
        Returns:
            Dictionary with parameter metadata or None if not found
        """
        current_time = time.time()
        
        # Check cache first
        if not force_refresh and name in self.parameter_metadata:
            cached_time = self.parameter_metadata[name].get('cached_time', 0)
            if (current_time - cached_time) <= self.cache_ttl:
                return self.parameter_metadata[name]['metadata']
        
        try:
            response = self.client.describe_parameters(
                ParameterFilters=[
                    {
                        'Key': 'Name',
                        'Values': [name]
                    }
                ]
            )
            
            if response['Parameters']:
                metadata = response['Parameters'][0]
                self.parameter_metadata[name] = {
                    'metadata': metadata,
                    'cached_time': current_time
                }
                
                # Log if parameter is SecureString for monitoring
                if metadata.get('Type') == 'SecureString':
                    logger.info(f"Accessing SecureString parameter: {name}")
                    
                return metadata
                
        except Exception as e:
            logger.error(f"Error getting metadata for parameter {name}: {str(e)}")
        
        return None
    
    def get_parameters_by_path(self, path: str, recursive: bool = True, force_refresh: bool = False) -> Dict[str, str]:
        """
        Get multiple parameters by path with SecureString support.
        
        Args:
            path: Parameter path prefix
            recursive: Whether to retrieve parameters recursively
            force_refresh: Force refresh from SSM
            
        Returns:
            Dictionary mapping parameter names to values
        """
        current_time = time.time()
        cache_key = f"path:{path}:recursive:{recursive}"
        
        # Check cache first
        if not force_refresh and cache_key in self.cache:
            cached_time = self.last_refresh.get(cache_key, 0)
            if (current_time - cached_time) <= self.cache_ttl:
                return self.cache[cache_key]
        
        try:
            parameters = {}
            paginator = self.client.get_paginator('get_parameters_by_path')
            
            page_iterator = paginator.paginate(
                Path=path,
                Recursive=recursive,
                WithDecryption=True  # Always decrypt SecureString parameters
            )
            
            for page in page_iterator:
                for parameter in page['Parameters']:
                    parameters[parameter['Name']] = parameter['Value']
                    
                    # Cache individual parameters too
                    param_name = parameter['Name']
                    self.cache[param_name] = parameter['Value']
                    self.last_refresh[param_name] = current_time
            
            # Cache the path result
            self.cache[cache_key] = parameters
            self.last_refresh[cache_key] = current_time
            
            logger.info(f"Retrieved {len(parameters)} parameters from path {path} (recursive: {recursive})")
            return parameters
            
        except Exception as e:
            logger.error(f"Error getting parameters by path {path}: {str(e)}")
            return {}
    
    def validate_parameter_access(self, name: str) -> bool:
        """
        Validate that the current IAM role has access to decrypt the parameter.
        
        Args:
            name: Parameter name to validate
            
        Returns:
            True if parameter can be accessed, False otherwise
        """
        try:
            # Attempt to retrieve parameter without caching
            response = self.client.get_parameter(Name=name, WithDecryption=True)
            
            # Check if it's a SecureString
            if response['Parameter'].get('Type') == 'SecureString':
                logger.info(f"Successfully validated SecureString parameter access: {name}")
            
            return True
            
        except self.client.exceptions.ParameterNotFound:
            logger.warning(f"Parameter not found: {name}")
            return False
        except self.client.exceptions.AccessDeniedException:
            logger.error(f"Access denied to parameter: {name} - Check IAM permissions and KMS key access")
            return False
        except Exception as e:
            logger.error(f"Error validating parameter access {name}: {str(e)}")
            return False
    
    def clear_cache(self) -> None:
        """Clear all cached parameters."""
        self.cache.clear()
        self.last_refresh.clear()
        self.parameter_metadata.clear()
        logger.info("SSM parameter cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for monitoring."""
        return {
            'cached_parameters': len(self.cache),
            'metadata_cached': len(self.parameter_metadata),
            'cache_ttl_seconds': self.cache_ttl,
            'last_refresh_times': dict(self.last_refresh)
        }

# Create a singleton instance
ssm = SSMClient()
