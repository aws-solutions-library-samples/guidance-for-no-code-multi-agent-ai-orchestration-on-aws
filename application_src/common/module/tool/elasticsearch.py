"""
Elasticsearch MCP Client for Strands SDK.
This module provides a simple interface to connect to Elasticsearch via MCP.
"""

import os
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters
from typing import Optional, Dict, Any, List
from ssm_client import ssm

class ElasticsearchMCP:
    """A class to manage Elasticsearch MCP client for Strands SDK."""
    
    def __init__(self):
        """Initialize the Elasticsearch MCP client."""
        self.es_url = None
        self.es_api_key = None
        self.mcp_client = None
        self.tools = []
        
    def _get_credentials_from_ssm(self):
        """
        Get Elasticsearch credentials from SSM parameter store.
        """
        try:
            # Get the agent config from SSM
            agent_config = ssm.get_json_parameter('/agent/qa_agent/config', {})
            
            # Check if there's an elasticsearch configuration
            knowledge_bases = agent_config.get('knowledge_base', [])
            for kb in knowledge_bases:
                if kb.get('name') == 'elasticsearch':
                    config = kb.get('config', {})
                    self.es_url = config.get('host')
                    self.es_api_key = config.get('cloud_id')  # Using cloud_id as API key for now
                    
                    # If username and password are provided, use basic auth
                    username = config.get('username')
                    password = config.get('password')
                    if username and password and not self.es_api_key:
                        # For basic auth, we'll use these in the environment variables
                        os.environ['ES_USERNAME'] = username
                        os.environ['ES_PASSWORD'] = password
                    
                    break
            
            if not self.es_url:
                print("Warning: Elasticsearch URL not found in SSM parameters")
        except Exception as e:
            print(f"Error getting Elasticsearch credentials from SSM: {str(e)}")
    
    def initialize(self) -> List:
        """
        Initialize the MCP client and get the tools.
        
        Returns:
            List of Elasticsearch tools
        """
        try:
            # Get credentials from SSM
            self._get_credentials_from_ssm()
            
            if not self.es_url:
                print("Error: Elasticsearch URL is required")
                return []
            
            # Prepare environment variables
            env = {"ES_URL": self.es_url}
            
            # Add API key if available
            if self.es_api_key:
                env["ES_API_KEY"] = self.es_api_key
            
            # Create the MCP client with environment variables (no hardcoded credentials)
            self.mcp_client = MCPClient(
                lambda: stdio_client(
                    StdioServerParameters(
                        command="npx",
                        args=["-y", "@elastic/mcp-server-elasticsearch"],
                        env=env  # Use dynamically prepared environment variables
                    )
                )
            )
            
            # Start the client and get the tools
            self.mcp_client.__enter__()
            self.tools = self.mcp_client.list_tools_sync()
            
            print(f"Elasticsearch MCP initialized with {len(self.tools)} tools")
            return self.tools
        except Exception as e:
            print(f"Error initializing Elasticsearch MCP: {str(e)}")
            return []
    
    def get_tools(self) -> List:
        """
        Get the Elasticsearch tools.
        
        Returns:
            List of Elasticsearch tools
        """
        if not self.tools:
            return self.initialize()
        return self.tools
    
    def close(self):
        """Close the MCP client."""
        if self.mcp_client:
            try:
                self.mcp_client.__exit__(None, None, None)
                print("Elasticsearch MCP client closed")
            except Exception as e:
                print(f"Error closing Elasticsearch MCP client: {str(e)}")

# Create a singleton instance
elasticsearch_mcp = ElasticsearchMCP()

def get_elasticsearch_tools() -> List:
    """
    Get Elasticsearch tools for use with Strands Agent.
    
    Returns:
        List of Elasticsearch tools
    """
    global elasticsearch_mcp
    return elasticsearch_mcp.get_tools()
