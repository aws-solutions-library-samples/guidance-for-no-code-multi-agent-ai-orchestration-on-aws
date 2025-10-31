"""
Example client for Configuration API Mock Server.

This demonstrates how other projects can use the mock server
for local development and testing.
"""

import requests
import json
import os
from typing import Dict, Any, Optional


class ConfigurationAPIClient:
    """Client for Configuration API that can work with both real and mock servers."""
    
    def __init__(self, base_url: str = None, timeout: int = 30):
        """
        Initialize the client.
        
        Args:
            base_url: Base URL of the Configuration API
            timeout: Request timeout in seconds
        """
        # Determine base URL based on environment
        if base_url is None:
            if os.getenv('ENVIRONMENT') == 'local':
                self.base_url = "http://localhost:8000"
                print("🔧 Using mock server for local development")
            else:
                # In production, you would use your real API URL
                self.base_url = "https://your-production-api.com"
                print("🌐 Using production API")
        else:
            self.base_url = base_url
        
        self.timeout = timeout
        self.session = requests.Session()
        
        print(f"📡 Configuration API Client initialized: {self.base_url}")
    
    def health_check(self) -> Dict[str, Any]:
        """Check if the API is healthy."""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Health check failed: {str(e)}")
    
    def discover_services(self) -> list:
        """Discover available services via VPC Lattice."""
        try:
            response = self.session.get(f"{self.base_url}/discover", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Service discovery failed: {str(e)}")
    
    def load_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """Load configuration for a specific agent."""
        try:
            data = {"agent_name": agent_name}
            response = self.session.post(
                f"{self.base_url}/config/load",
                json=data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise Exception(f"Agent '{agent_name}' not found")
            else:
                raise Exception(f"Failed to load agent config: {str(e)}")
        except Exception as e:
            raise Exception(f"Failed to load agent config: {str(e)}")
    
    def save_agent_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save configuration for an agent."""
        try:
            response = self.session.post(
                f"{self.base_url}/config/save",
                json=config_data,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Failed to save agent config: {str(e)}")
    
    def list_agents(self) -> Dict[str, Any]:
        """List all available agent configurations."""
        try:
            response = self.session.get(f"{self.base_url}/config/list", timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise Exception(f"Failed to list agents: {str(e)}")


def example_usage():
    """Example usage of the Configuration API Client."""
    
    print("🚀 Configuration API Client Example")
    print("=" * 50)
    
    try:
        # Initialize client (will use mock server if ENVIRONMENT=local)
        client = ConfigurationAPIClient()
        
        # Test 1: Health check
        print("\n1️⃣ Testing health check...")
        health = client.health_check()
        print(f"✅ API is healthy: {health}")
        
        # Test 2: Discover services
        print("\n2️⃣ Discovering services...")
        services = client.discover_services()
        print(f"✅ Found {len(services)} services:")
        for service in services:
            print(f"   - {service}")
        
        # Test 3: List all agents
        print("\n3️⃣ Listing all agents...")
        agents_list = client.list_agents()
        print(f"✅ Found {agents_list.get('count', 0)} agents:")
        for agent in agents_list.get('agents', []):
            print(f"   - {agent}")
        
        # Test 4: Load specific agent configurations
        test_agents = ['qa_agent', 'chat_agent']
        for agent_name in test_agents:
            print(f"\n4️⃣ Loading config for {agent_name}...")
            try:
                config = client.load_agent_config(agent_name)
                print(f"✅ Loaded config for {agent_name}:")
                print(f"   - Description: {config.get('agent_description', 'N/A')}")
                print(f"   - Model: {config.get('model_id', 'N/A')}")
                print(f"   - Temperature: {config.get('temperature', 'N/A')}")
                print(f"   - Knowledge Base: {config.get('knowledge_base', 'N/A')}")
                print(f"   - Tools: {len(config.get('tools', []))}")
            except Exception as e:
                print(f"❌ Failed to load {agent_name}: {str(e)}")
        
        # Test 5: Try to load non-existent agent
        print("\n5️⃣ Testing error handling with non-existent agent...")
        try:
            client.load_agent_config('non_existent_agent')
        except Exception as e:
            print(f"✅ Expected error handled correctly: {str(e)}")
        
        print("\n🎉 All tests completed successfully!")
        print("\n💡 Your dependent projects can use this client pattern to work with both")
        print("   the mock server (local development) and the real API (production).")
        
    except Exception as e:
        print(f"❌ Example failed: {str(e)}")
        print("\n🔧 Make sure the mock server is running:")
        print("   cd application_src/configuration-api/mock")
        print("   ./start_mock_server.sh")


def integration_example():
    """Example of how to integrate this into your project."""
    
    print("\n" + "=" * 50)
    print("📋 Integration Example")
    print("=" * 50)
    
    print("""
# Example integration in your project:

import os
from config_api_client import ConfigurationAPIClient

# Set environment variable for local development
# export ENVIRONMENT=local

class MyApplication:
    def __init__(self):
        # Client will automatically use mock server if ENVIRONMENT=local
        self.config_client = ConfigurationAPIClient()
    
    def initialize_agent(self, agent_name: str):
        try:
            # Load agent configuration
            config = self.config_client.load_agent_config(agent_name)
            
            # Use the configuration in your application
            self.model_id = config['model_id']
            self.temperature = config['temperature']
            self.system_prompt = config['system_prompt']
            
            print(f"Agent {agent_name} initialized successfully")
            
        except Exception as e:
            print(f"Failed to initialize agent: {e}")
    
    def discover_available_services(self):
        # Discover services for inter-service communication
        services = self.config_client.discover_services()
        return services

# Usage example:
# app = MyApplication()
# app.initialize_agent('qa_agent')
# services = app.discover_available_services()
""")


if __name__ == "__main__":
    example_usage()
    integration_example()
