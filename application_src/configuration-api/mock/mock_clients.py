"""
Mock AWS clients for Configuration API testing.

This module provides mock implementations of AWS services (SSM, VPC Lattice)
that return predefined responses from mock_data.yaml instead of making actual AWS API calls.
"""

import json
import yaml
import os
from typing import Any, Dict, List, Optional
from datetime import datetime
from botocore.exceptions import ClientError


class MockSSMClient:
    """Mock implementation of AWS SSM client."""
    
    def __init__(self, region_name: str = 'us-east-1'):
        self.region_name = region_name
        self._load_mock_data()
    
    def _load_mock_data(self):
        """Load mock data from YAML file."""
        mock_data_path = os.path.join(os.path.dirname(__file__), 'mock_data.yaml')
        try:
            with open(mock_data_path, 'r', encoding='utf-8') as f:
                self.mock_data = yaml.safe_load(f)
            print(f"[MOCK SSM] Loaded mock data from {mock_data_path}")
        except Exception as e:
            print(f"[MOCK SSM] Error loading mock data: {e}")
            self.mock_data = {'ssm_parameters': {}}
    
    def get_parameter(self, Name: str) -> Dict[str, Any]:
        """Mock get_parameter implementation."""
        print(f"[MOCK SSM] get_parameter called with Name: {Name}")
        
        parameters = self.mock_data.get('ssm_parameters', {})
        
        if Name in parameters:
            value = parameters[Name]
            
            # If value is a dict, convert to JSON string
            if isinstance(value, dict):
                value_str = json.dumps(value)
            else:
                value_str = str(value)
            
            response = {
                'Parameter': {
                    'Name': Name,
                    'Type': 'String',
                    'Value': value_str,
                    'Version': 1,
                    'LastModifiedDate': datetime.now(),
                    'ARN': f'arn:aws:ssm:{self.region_name}:123456789012:parameter{Name}',
                    'DataType': 'text'
                }
            }
            print(f"[MOCK SSM] Returning parameter: {Name}")
            return response
        else:
            print(f"[MOCK SSM] Parameter not found: {Name}")
            # Raise the same exception as real SSM
            error_response = {
                'Error': {
                    'Code': 'ParameterNotFound',
                    'Message': f'Parameter {Name} not found.'
                }
            }
            raise ClientError(error_response, 'GetParameter')
    
    def put_parameter(self, Name: str, Value: str, Type: str = 'String', 
                     Overwrite: bool = True, Description: str = '') -> Dict[str, Any]:
        """Mock put_parameter implementation."""
        print(f"[MOCK SSM] put_parameter called with Name: {Name}")
        
        # In a real mock, we might want to persist this data
        # For now, we'll just log it and return success
        parameters = self.mock_data.get('ssm_parameters', {})
        
        # Try to parse JSON if it looks like JSON
        try:
            parsed_value = json.loads(Value)
            parameters[Name] = parsed_value
        except (json.JSONDecodeError, TypeError):
            parameters[Name] = Value
        
        response = {
            'Version': 1,
            'Tier': 'Standard'
        }
        print(f"[MOCK SSM] Parameter stored: {Name}")
        return response
    
    def describe_parameters(self, ParameterFilters: Optional[List[Dict[str, Any]]] = None,
                          MaxResults: int = 50) -> Dict[str, Any]:
        """Mock describe_parameters implementation."""
        print(f"[MOCK SSM] describe_parameters called with filters: {ParameterFilters}")
        
        parameters = self.mock_data.get('ssm_parameters', {})
        matching_params = []
        
        for param_name, param_value in parameters.items():
            # Apply filters if provided
            if ParameterFilters:
                matches_filter = False
                for param_filter in ParameterFilters:
                    key = param_filter.get('Key')
                    option = param_filter.get('Option')
                    values = param_filter.get('Values', [])
                    
                    if key == 'Name' and option == 'BeginsWith':
                        for value in values:
                            if param_name.startswith(value):
                                matches_filter = True
                                break
                    # Add more filter types as needed
                
                if not matches_filter:
                    continue
            
            # Create parameter metadata
            param_metadata = {
                'Name': param_name,
                'Type': 'String',
                'LastModifiedDate': datetime.now(),
                'Description': f'Mock parameter {param_name}'
            }
            matching_params.append(param_metadata)
        
        # Limit results
        matching_params = matching_params[:MaxResults]
        
        response = {
            'Parameters': matching_params
        }
        
        print(f"[MOCK SSM] Returning {len(matching_params)} parameters")
        return response
    
    def get_paginator(self, operation_name: str):
        """Mock paginator for describe_parameters."""
        if operation_name == 'describe_parameters':
            return MockSSMPaginator(self)
        else:
            raise NotImplementedError(f"Paginator for {operation_name} not implemented")


class MockSSMPaginator:
    """Mock paginator for SSM operations."""
    
    def __init__(self, ssm_client: MockSSMClient):
        self.ssm_client = ssm_client
    
    def paginate(self, **kwargs):
        """Mock paginate method."""
        # For simplicity, just return one page with all results
        result = self.ssm_client.describe_parameters(**kwargs)
        yield result


class MockVPCLatticeClient:
    """Mock implementation of AWS VPC Lattice client."""
    
    def __init__(self, region_name: str = 'us-east-1'):
        self.region_name = region_name
        self._load_mock_data()
    
    def _load_mock_data(self):
        """Load mock data from YAML file."""
        mock_data_path = os.path.join(os.path.dirname(__file__), 'mock_data.yaml')
        try:
            with open(mock_data_path, 'r', encoding='utf-8') as f:
                self.mock_data = yaml.safe_load(f)
            print(f"[MOCK VPC Lattice] Loaded mock data from {mock_data_path}")
        except Exception as e:
            print(f"[MOCK VPC Lattice] Error loading mock data: {e}")
            self.mock_data = {'vpc_lattice': {}}
    
    def list_service_network_service_associations(self, serviceNetworkIdentifier: str) -> Dict[str, Any]:
        """Mock list_service_network_service_associations implementation."""
        print(f"[MOCK VPC Lattice] list_service_network_service_associations called with serviceNetworkIdentifier: {serviceNetworkIdentifier}")
        
        vpc_lattice_data = self.mock_data.get('vpc_lattice', {})
        service_associations = vpc_lattice_data.get('service_associations', [])
        
        response = {
            'items': service_associations
        }
        
        print(f"[MOCK VPC Lattice] Returning {len(service_associations)} service associations")
        return response


def mock_boto3_client(service_name: str, region_name: str = 'us-east-1', **kwargs):
    """Mock boto3.client() function."""
    print(f"[MOCK] Creating mock client for service: {service_name}, region: {region_name}")
    
    if service_name == 'ssm':
        return MockSSMClient(region_name=region_name)
    elif service_name == 'vpc-lattice':
        return MockVPCLatticeClient(region_name=region_name)
    else:
        raise NotImplementedError(f"Mock client for service '{service_name}' not implemented")


def patch_boto3():
    """Patch boto3 to use mock clients."""
    import boto3
    
    # Store original client function
    if not hasattr(boto3, '_original_client'):
        boto3._original_client = boto3.client
    
    # Replace with mock
    boto3.client = mock_boto3_client
    print("[MOCK] boto3.client patched with mock implementation")


def unpatch_boto3():
    """Restore original boto3 client."""
    import boto3
    
    if hasattr(boto3, '_original_client'):
        boto3.client = boto3._original_client
        delattr(boto3, '_original_client')
        print("[MOCK] boto3.client restored to original implementation")
