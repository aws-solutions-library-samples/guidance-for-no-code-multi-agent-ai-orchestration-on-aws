"""
Elasticsearch knowledge base provider for GenAI-In-A-Box agent.
This module provides a knowledge base provider for Elasticsearch.
"""

import traceback
import socket
import requests
from typing import List, Dict, Any
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters
from ..base import BaseKnowledgeBaseProvider

class ElasticKnowledgeBaseProvider(BaseKnowledgeBaseProvider):
    """Knowledge base provider for Elasticsearch."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Elasticsearch knowledge base provider."""
        super().__init__(config)
        self.provider_name = "elasticsearch"
        self.mcp_client = None
        self.is_initialized = False
    
    def initialize(self) -> List:
        """Initialize the Elasticsearch knowledge base provider and get the tools."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses
            return self.tools
            
        try:
            provider_config = self.get_provider_config()
            
            # Get Elasticsearch credentials
            es_url = provider_config.get("es_url", "")
            es_api_key = provider_config.get("es_api_key", "")
            
            print(f"Elasticsearch URL: {es_url}")
            print(f"API Key provided: {'Yes' if es_api_key else 'No'}")
            
            if not es_url:
                print("Error: Elasticsearch URL is required")
                return []
            
            # Pre-resolve hostname to IP address for Node.js process
            import urllib.parse
            parsed_url = urllib.parse.urlparse(es_url)
            hostname = parsed_url.hostname
            port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
            
            # Check network connectivity before attempting to connect
            if not self.check_network(hostname, port):
                print(f"Network connectivity test failed for {hostname}:{port}")
                return []
            
            try:
                # Resolve hostname to IP using Python's DNS resolution (which works)
                ip_address = socket.gethostbyname(hostname)
                print(f"Resolved {hostname} to {ip_address}")
                
                # Create new URL with IP address but keep original hostname for SNI
                ip_url = f"{parsed_url.scheme}://{ip_address}:{port}{parsed_url.path or ''}"
                print(f"Using IP-based URL for MCP client: {ip_url}")
                
            except Exception as e:
                print(f"Failed to resolve hostname {hostname}: {str(e)}")
                ip_url = es_url  # Fallback to original URL
                ip_address = hostname
            
            # Set environment variables for the Node.js process
            import os
            os.environ["ES_URL"] = ip_url
            os.environ["ES_API_KEY"] = es_api_key
            os.environ["ES_ORIGINAL_HOST"] = hostname  # For SNI if needed
            
            print(f"Environment variables set: ES_URL={ip_url}, ES_API_KEY=***, Original Host={hostname}")
            
            # Test direct connection first to verify connectivity
            if not self.test_connection(ip_url, hostname):
                print("Direct connection test failed, cannot proceed with MCP client")
                return []
            
            # Create the MCP client with IP-based URL
            self.mcp_client = MCPClient(
                lambda: stdio_client(
                    StdioServerParameters(
                        command="npx",
                        args=["-y", "@elastic/mcp-server-elasticsearch"],
                        env={
                            "ES_URL": ip_url,
                            "ES_API_KEY": es_api_key,
                            "ES_ORIGINAL_HOST": hostname,
                            "NODE_OPTIONS": "--dns-result-order=ipv4first",
                            "DEBUG": "mcp:*"  # Enable MCP debugging
                        },
                        timeout=60  # Increase timeout
                    )
                )
            )
            
            # Start the client
            print("Starting MCP client...")
            self.mcp_client.__enter__()
            print("MCP client started successfully")
            
            # Get the tools
            print("Getting tools from MCP client...")
            self.tools = self.mcp_client.list_tools_sync()
            self.is_initialized = True
            
            print(f"Elasticsearch knowledge base provider initialized with {len(self.tools)} tools")
            for tool in self.tools:
                print(f"  - {tool.__name__ if hasattr(tool, '__name__') else str(tool)}")
            
            # Add fallback tool for orders search
            from strands import tool
            
            @tool
            def search_orders_fallback(query: str) -> str:
                """Fallback tool to search for orders when MCP tools fail."""
                return "The MCP Elasticsearch tools are currently available, but I can help you search for orders using natural language. Please try using the elasticsearch_search tool with your query."
            
            self.tools.append(search_orders_fallback)
            
            return self.tools
        except Exception as e:
            print(f"Error initializing Elasticsearch knowledge base provider: {str(e)}")
            traceback.print_exc()
            self.close()
            return []
    
    def check_network(self, host, port):
        """Check network connectivity to the host and port."""
        try:
            print(f"Testing network connectivity to {host}:{port}...")
            socket.create_connection((host, port), timeout=5)
            print(f"Network connectivity test successful for {host}:{port}")
            return True
        except Exception as e:
            print(f"Network connectivity issue: {str(e)}")
            return False
    
    def test_connection(self, url, hostname):
        """Test the Elasticsearch connection."""
        try:
            headers = {'Host': hostname} if hostname not in url else {}
            response = requests.get(url, headers=headers, timeout=10, verify=True)
            print(f"Direct connection test successful: {response.status_code}")
            return True
        except Exception as e:
            print(f"Direct connection test failed: {str(e)}")
            traceback.print_exc()
            return False
    
    def close(self):
        """Close the MCP client."""
        if self.mcp_client and self.is_initialized:  # nosemgrep: is-function-without-parentheses
            try:
                self.mcp_client.__exit__(None, None, None)
                self.is_initialized = False
                self.tools = []
                print("Elasticsearch MCP client closed")
            except Exception as e:
                print(f"Error closing Elasticsearch MCP client: {str(e)}")
                traceback.print_exc()
                
    def __del__(self):
        """Destructor to ensure MCP client is closed."""
        self.close()
