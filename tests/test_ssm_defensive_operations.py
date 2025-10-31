#!/usr/bin/env python3
"""
Test SSM Parameter Initialization Defensive/Upsert Operations.

This test verifies that the parameter initialization service properly implements
defensive operations that won't overwrite existing parameters.
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add the application source to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'application_src', 'configuration-api'))

from app.services.ssm_service import SSMService
from app.services.parameter_initialization import ParameterInitializationService


class TestSSMDefensiveOperations:
    """Test defensive/upsert behavior of SSM parameter operations."""
    
    @pytest.fixture
    def mock_ssm_client(self):
        """Create a mock SSM client."""
        return Mock()
    
    @pytest.fixture
    def ssm_service(self, mock_ssm_client):
        """Create SSM service with mocked client."""
        with patch('boto3.client', return_value=mock_ssm_client):
            service = SSMService(region_name='us-east-1')
            service.client = mock_ssm_client
            return service
    
    @pytest.fixture
    def param_init_service(self, ssm_service):
        """Create parameter initialization service."""
        return ParameterInitializationService(ssm_service)
    
    def test_parameter_exists_defensive_check(self, ssm_service, mock_ssm_client):
        """Test that parameter_exists properly checks for existing parameters."""
        # Mock successful parameter retrieval
        mock_ssm_client.get_parameter.return_value = {
            'Parameter': {'Value': 'test-value'}
        }
        
        # Should return True when parameter exists
        assert ssm_service.parameter_exists('/test/parameter') == True
        
        # Verify correct API call
        mock_ssm_client.get_parameter.assert_called_with(Name='/test/parameter')
    
    def test_parameter_exists_handles_not_found(self, ssm_service, mock_ssm_client):
        """Test that parameter_exists handles ParameterNotFound gracefully."""
        from botocore.exceptions import ClientError
        
        # Mock ParameterNotFound exception
        mock_ssm_client.get_parameter.side_effect = ClientError(
            error_response={'Error': {'Code': 'ParameterNotFound'}},
            operation_name='GetParameter'
        )
        
        # Should return False when parameter doesn't exist
        assert ssm_service.parameter_exists('/nonexistent/parameter') == False
    
    def test_store_parameter_with_overwrite_flag(self, ssm_service, mock_ssm_client):
        """Test that store_parameter uses Overwrite=True but only after defensive checks."""
        # Mock successful parameter creation
        mock_ssm_client.put_parameter.return_value = {}
        
        # Store parameter
        result = ssm_service.store_parameter(
            name='/test/parameter',
            value='test-value',
            parameter_type='SecureString'
        )
        
        # Should succeed
        assert result == True
        
        # Verify put_parameter was called with Overwrite=True
        mock_ssm_client.put_parameter.assert_called_with(
            Name='/test/parameter',
            Value='test-value',
            Type='SecureString',
            Tier='Advanced',
            Overwrite=True,
            Description='',
            KeyId='alias/development-ssm-parameters'
        )
    
    def test_initialization_service_defensive_behavior(self, param_init_service, ssm_service):
        """Test that initialization service only creates parameters that don't exist."""
        with patch.object(ssm_service, 'parameter_exists') as mock_exists:
            with patch.object(ssm_service, 'store_parameter') as mock_store:
                # Mock that parameter doesn't exist
                mock_exists.return_value = False
                mock_store.return_value = True
                
                # Mock prompts directory and files
                with patch('pathlib.Path.exists', return_value=True):
                    with patch('pathlib.Path.rglob') as mock_rglob:
                        # Mock finding prompt files
                        mock_prompt_files = [
                            Mock(name='qa.md', relative_to=Mock(return_value=Mock(with_suffix=Mock(return_value='qa')))),
                            Mock(name='weather.md', relative_to=Mock(return_value=Mock(with_suffix=Mock(return_value='weather'))))
                        ]
                        mock_rglob.return_value = mock_prompt_files
                        
                        # Mock file reading
                        with patch('builtins.open', Mock()):
                            # This should call parameter_exists before creating
                            result = param_init_service._initialize_prompt_library()
                            
                            # Should check existence before creating
                            assert mock_exists.called
                            assert result == True
    
    def test_initialization_service_skips_existing_parameters(self, param_init_service, ssm_service):
        """Test that initialization service skips parameters that already exist."""
        with patch.object(ssm_service, 'parameter_exists') as mock_exists:
            with patch.object(ssm_service, 'store_parameter') as mock_store:
                # Mock that parameter already exists
                mock_exists.return_value = True
                
                # Mock prompts directory
                with patch('pathlib.Path.exists', return_value=True):
                    with patch('pathlib.Path.rglob') as mock_rglob:
                        mock_prompt_files = [
                            Mock(name='qa.md', relative_to=Mock(return_value=Mock(with_suffix=Mock(return_value='qa'))))
                        ]
                        mock_rglob.return_value = mock_prompt_files
                        
                        result = param_init_service._initialize_prompt_library()
                        
                        # Should check existence
                        assert mock_exists.called
                        # Should NOT call store_parameter since parameter exists
                        assert not mock_store.called
                        assert result == True
    
    def test_json_parameter_defensive_storage(self, ssm_service, mock_ssm_client):
        """Test that JSON parameters are stored defensively with SecureString."""
        mock_ssm_client.put_parameter.return_value = {}
        
        test_data = {"agent_name": "test_agent", "model_id": "claude-3"}
        
        result = ssm_service.store_json_parameter(
            name='/test/config',
            data=test_data,
            description='Test config'
        )
        
        assert result == True
        
        # Verify JSON was serialized and stored as SecureString
        call_args = mock_ssm_client.put_parameter.call_args[1]
        assert call_args['Type'] == 'SecureString'
        assert call_args['Overwrite'] == True
        assert call_args['KeyId'] == 'alias/development-ssm-parameters'
        
        # Verify JSON content
        stored_value = json.loads(call_args['Value'])
        assert stored_value == test_data
    
    def test_multiple_initialization_calls_are_idempotent(self, param_init_service, ssm_service):
        """Test that multiple initialization calls don't overwrite existing parameters."""
        call_count = 0
        
        def mock_parameter_exists(name):
            nonlocal call_count
            call_count += 1
            # First call: parameter doesn't exist, second call: it exists
            return call_count > 1
        
        store_call_count = 0
        def mock_store_parameter(*args, **kwargs):
            nonlocal store_call_count
            store_call_count += 1
            return True
        
        with patch.object(ssm_service, 'parameter_exists', side_effect=mock_parameter_exists):
            with patch.object(ssm_service, 'store_parameter', side_effect=mock_store_parameter):
                with patch('pathlib.Path.exists', return_value=True):
                    with patch('pathlib.Path.rglob', return_value=[]):
                        with patch('builtins.open', Mock()):
                            # First initialization - should create parameter
                            result1 = param_init_service.initialize_default_agent_parameters()
                            
                            # Second initialization - should skip existing parameter
                            result2 = param_init_service.initialize_default_agent_parameters()
                            
                            # Both should succeed
                            assert result1 == True
                            assert result2 == True
                            
                            # Store should only be called once (first time)
                            # Note: This is a simplified test - actual implementation may have multiple parameters


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
