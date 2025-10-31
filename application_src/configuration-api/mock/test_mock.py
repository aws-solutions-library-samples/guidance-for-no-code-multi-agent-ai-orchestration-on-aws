"""
Test script for Configuration API Mock Server.

This script tests all the endpoints of the mock server to ensure
it responds with the expected mock data.
"""

import requests
import json
import time
from typing import Dict, Any


class ConfigAPITester:
    """Test class for Configuration API Mock Server."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
    
    def test_endpoint(self, method: str, endpoint: str, data: Dict[Any, Any] = None, 
                     expected_status: int = 200, test_name: str = "") -> bool:
        """Test a single endpoint."""
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == "GET":
                response = self.session.get(url)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = response.status_code == expected_status
            
            result = {
                "test_name": test_name or f"{method} {endpoint}",
                "method": method,
                "endpoint": endpoint,
                "expected_status": expected_status,
                "actual_status": response.status_code,
                "success": success,
                "response_data": None,
                "error": None
            }
            
            if success:
                try:
                    result["response_data"] = response.json()
                except:
                    result["response_data"] = response.text
            else:
                result["error"] = f"Expected {expected_status}, got {response.status_code}"
                try:
                    result["response_data"] = response.json()
                except:
                    result["response_data"] = response.text
            
            self.test_results.append(result)
            return success
            
        except Exception as e:
            result = {
                "test_name": test_name or f"{method} {endpoint}",
                "method": method,
                "endpoint": endpoint,
                "expected_status": expected_status,
                "actual_status": None,
                "success": False,
                "response_data": None,
                "error": str(e)
            }
            self.test_results.append(result)
            return False
    
    def run_all_tests(self):
        """Run all test cases."""
        print("🧪 Starting Configuration API Mock Server Tests")
        print("=" * 60)
        
        # Test 1: Health check
        self.test_endpoint("GET", "/health", test_name="Health Check")
        
        # Test 2: Discover DNS entries
        self.test_endpoint("GET", "/discover", test_name="Discover DNS Entries")
        
        # Test 3: Load existing agent config (qa_agent)
        load_data = {"agent_name": "qa_agent"}
        self.test_endpoint("POST", "/config/load", data=load_data, test_name="Load QA Agent Config")
        
        # Test 4: Load existing agent config (chat_agent)
        load_data = {"agent_name": "chat_agent"}
        self.test_endpoint("POST", "/config/load", data=load_data, test_name="Load Chat Agent Config")
        
        # Test 5: Try to load non-existent agent
        load_data = {"agent_name": "non_existent_agent"}
        self.test_endpoint("POST", "/config/load", data=load_data, 
                          expected_status=404, test_name="Load Non-existent Agent")
        
        # Test 6: Save a new agent config
        save_data = {
            "agent_name": "test_agent",
            "agent_description": "Test Agent for mock server testing",
            "system_prompt_name": "test_prompt",
            "system_prompt": "You are a test assistant for validating mock responses.",
            "model_id": "anthropic.claude-3-haiku-20240307-v1:0",
            "judge_model_id": "anthropic.claude-3-haiku-20240307-v1:0",
            "embedding_model_id": "amazon.titan-embed-text-v2:0",
            "region_name": "us-east-1",
            "temperature": 0.5,
            "top_p": 0.8,
            "streaming": "false",
            "cache_prompt": "false",
            "cache_tools": "false",
            "thinking": {
                "type": "budget",
                "budget_tokens": 500
            },
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
        self.test_endpoint("POST", "/config/save", data=save_data, test_name="Save New Agent Config")
        
        # Test 7: List all agent configurations
        self.test_endpoint("GET", "/config/list", test_name="List Agent Configurations")
        
        # Test 8: Test SSM connection
        self.test_endpoint("GET", "/config/test-ssm", test_name="Test SSM Connection")
        
        # Test 9: Debug agent config
        self.test_endpoint("GET", "/config/debug/qa_agent", test_name="Debug QA Agent Config")
        
        self._print_results()
    
    def _print_results(self):
        """Print test results summary."""
        print("\n" + "=" * 60)
        print("📊 Test Results Summary")
        print("=" * 60)
        
        passed = sum(1 for result in self.test_results if result["success"])
        total = len(self.test_results)
        
        for result in self.test_results:
            status_icon = "✅" if result["success"] else "❌"
            print(f"{status_icon} {result['test_name']}")
            
            if not result["success"]:
                print(f"   Error: {result['error']}")
                if result["response_data"]:
                    print(f"   Response: {result['response_data']}")
            elif result["success"] and isinstance(result["response_data"], dict):
                # Print a brief summary of successful responses
                if "status" in result["response_data"]:
                    print(f"   Status: {result['response_data']['status']}")
                elif "agent_name" in result["response_data"]:
                    print(f"   Agent: {result['response_data']['agent_name']}")
                elif isinstance(result["response_data"], list):
                    print(f"   Items returned: {len(result['response_data'])}")
            
            print()
        
        print(f"📈 Results: {passed}/{total} tests passed ({passed/total*100:.1f}%)")
        
        if passed == total:
            print("🎉 All tests passed! Mock server is working correctly.")
        else:
            print("⚠️  Some tests failed. Check the mock server setup.")


def wait_for_server(url: str, timeout: int = 30) -> bool:
    """Wait for the server to be available."""
    print(f"⏳ Waiting for server at {url} to be ready...")
    
    start_time = time.time()
    wait_time = 0.1  # Start with 100ms
    max_wait = 2.0   # Maximum 2 seconds between attempts
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{url}/health", timeout=5)
            if response.status_code == 200:
                print(f"✅ Server is ready at {url}")
                return True
        except:
            pass
        
        # Exponential backoff for server polling - more efficient than fixed 1-second sleep
        time.sleep(wait_time)  # nosemgrep: arbitrary-sleep
        wait_time = min(wait_time * 1.5, max_wait)
    
    print(f"❌ Server at {url} is not responding after {timeout} seconds")
    return False


def main():
    """Main function to run tests."""
    base_url = "http://localhost:8000"
    
    print("🔍 Configuration API Mock Server Test Suite")
    print("=" * 60)
    
    # Wait for server to be available
    if not wait_for_server(base_url):
        print("❌ Cannot connect to mock server. Make sure it's running:")
        print("   cd application_src/configuration-api/mock")
        print("   ./start_mock_server.sh")
        return
    
    # Run tests
    tester = ConfigAPITester(base_url)
    tester.run_all_tests()


if __name__ == "__main__":
    main()
