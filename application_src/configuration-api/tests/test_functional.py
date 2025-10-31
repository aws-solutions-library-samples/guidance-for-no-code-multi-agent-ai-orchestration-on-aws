"""
Functional tests for the refactored Configuration API.

This test suite validates that the refactored code works correctly
without needing a running server by testing the FastAPI app directly.
"""

import pytest
from fastapi.testclient import TestClient
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path to import the app
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.insert(0, str(parent_dir))


def create_mock_ssm_client():
    """Create a mock SSM client."""
    mock_client = MagicMock()
    
    # Mock get_parameter for qa_agent config
    qa_config = {
        "agent_name": "qa_agent",
        "agent_description": "Test Q&A Agent",
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "temperature": 0.7,
        "region_name": "us-east-1"
    }
    
    mock_client.get_parameter.return_value = {
        'Parameter': {
            'Name': '/agent/qa_agent/config',
            'Value': json.dumps(qa_config)
        }
    }
    
    # Mock describe_parameters
    mock_client.describe_parameters.return_value = {
        'Parameters': [
            {'Name': '/agent/qa_agent/config'},
            {'Name': '/agent/chat_agent/config'}
        ]
    }
    
    return mock_client


def create_mock_vpc_lattice_client():
    """Create a mock VPC Lattice client."""
    mock_client = MagicMock()
    
    mock_client.list_service_network_service_associations.return_value = {
        'items': [
            {
                'serviceName': 'test-service',
                'dnsEntry': {
                    'domainName': 'test-service.example.com'
                }
            }
        ]
    }
    
    return mock_client


@pytest.fixture
def test_client():
    """Create a test client with mocked AWS services."""
    with patch('boto3.client') as mock_boto3:
        # Configure boto3.client to return our mocks
        def mock_client_factory(service_name, region_name=None):
            if service_name == 'ssm':
                return create_mock_ssm_client()
            elif service_name == 'vpc-lattice':
                return create_mock_vpc_lattice_client()
            else:
                return MagicMock()
        
        mock_boto3.side_effect = mock_client_factory
        
        # Import the app after mocking
        from main import app
        
        client = TestClient(app)
        yield client


class TestHealthEndpoint:
    """Test health check endpoint."""
    
    def test_health_check(self, test_client):
        """Test that health endpoint returns successfully."""
        response = test_client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["service"] == "GenAI In a Box Configuration API"


class TestDiscoveryEndpoint:
    """Test service discovery endpoint."""
    
    def test_discover_services(self, test_client):
        """Test that discovery endpoint returns services."""
        response = test_client.get("/discover")
        assert response.status_code == 200
        
        data = response.json()
        assert isinstance(data, list)
        # Should contain at least one service from our mock
        assert len(data) > 0
        assert data[0]["serviceName"] == "test-service"
        assert data[0]["dnsEntry"]["domainName"] == "test-service.example.com"


class TestConfigurationEndpoints:
    """Test configuration management endpoints."""
    
    def test_load_agent_config(self, test_client):
        """Test loading agent configuration."""
        response = test_client.post(
            "/config/load",
            json={"agent_name": "qa_agent"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["agent_name"] == "qa_agent"
        assert data["agent_description"] == "Test Q&A Agent"
        assert data["model_id"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"
    
    def test_load_nonexistent_agent(self, test_client):
        """Test loading non-existent agent returns 404."""
        with patch('boto3.client') as mock_boto3:
            mock_ssm = MagicMock()
            from botocore.exceptions import ClientError
            
            # Mock ClientError for parameter not found
            mock_ssm.get_parameter.side_effect = ClientError(
                {'Error': {'Code': 'ParameterNotFound'}}, 
                'GetParameter'
            )
            
            mock_boto3.return_value = mock_ssm
            
            response = test_client.post(
                "/config/load",
                json={"agent_name": "nonexistent_agent"}
            )
            assert response.status_code == 404
    
    def test_list_agents(self, test_client):
        """Test listing all agents."""
        response = test_client.get("/config/list")
        assert response.status_code == 200
        
        data = response.json()
        assert "agents" in data
        assert "count" in data
        assert isinstance(data["agents"], list)
        assert data["count"] >= 0
    
    def test_save_agent_config(self, test_client):
        """Test saving agent configuration."""
        config_data = {
            "agent_name": "test_agent",
            "agent_description": "Test agent for validation",
            "system_prompt_name": "test_prompt",
            "system_prompt": "You are a test assistant.",
            "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
            "judge_model_id": "anthropic.claude-3-haiku-20240307-v1:0",
            "embedding_model_id": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "temperature": 0.5,
            "top_p": 0.8,
            "streaming": "false",
            "cache_prompt": "false",
            "cache_tools": "false",
            "thinking": {"type": "budget", "budget_tokens": 500},
            "memory": "false",
            "memory_provider": "none",
            "memory_provider_details": [],
            "knowledge_base": "false",
            "knowledge_base_provider": "none",
            "knowledge_base_provider_type": "none",
            "knowledge_base_details": [],
            "observability": "false",
            "observability_provider": "none",
            "observability_provider_details": [],
            "guardrail": "false",
            "guardrail_provider": "none",
            "guardrail_provider_details": [],
            "tools": []
        }
        
        response = test_client.post("/config/save", json=config_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["message"] == "Agent configuration saved successfully"
        assert data["agent_name"] == "test_agent"


class TestAPIDocumentation:
    """Test API documentation endpoints."""
    
    def test_openapi_schema(self, test_client):
        """Test that OpenAPI schema is available."""
        response = test_client.get("/openapi.json")
        assert response.status_code == 200
        
        data = response.json()
        assert data["info"]["title"] == "GenAI In a Box Configuration API"
        assert data["info"]["version"] == "1.0.0"
    
    def test_docs_endpoint(self, test_client):
        """Test that Swagger UI is available."""
        response = test_client.get("/docs")
        assert response.status_code == 200
        assert "swagger-ui" in response.text.lower()


def test_app_metadata():
    """Test basic app metadata and configuration."""
    # Import after mocking to ensure clean import
    with patch('boto3.client'):
        from main import app
        
        assert app.title == "GenAI In a Box Configuration API"
        assert app.description == "Configuration management service for AI agents with VPC Lattice discovery"
        assert app.version == "1.0.0"
        
        # Test that all expected routes are present
        route_paths = [route.path for route in app.routes]
        expected_paths = [
            "/health",
            "/discover", 
            "/config/load",
            "/config/save",
            "/config/list",
            "/config/test-ssm",
            "/config/debug/{agent_name}",
            "/config/delete/{agent_name}"
        ]
        
        for expected_path in expected_paths:
            assert expected_path in route_paths, f"Missing route: {expected_path}"


if __name__ == "__main__":
    # Run tests directly
    import subprocess
    import os
    
    # Change to the test directory
    os.chdir(Path(__file__).parent.parent)
    
    # Run the tests
    result = subprocess.run([
        "python", "-m", "pytest", "tests/test_functional.py", "-v", "--tb=short"
    ], capture_output=True, text=True)
    
    print("STDOUT:")
    print(result.stdout)
    print("STDERR:")
    print(result.stderr)
    print(f"Return code: {result.returncode}")
