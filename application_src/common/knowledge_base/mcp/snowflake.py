"""
MCP Snowflake knowledge base provider for GenAI-In-A-Box agent.
This module provides a knowledge base provider using MCP client for Snowflake.
"""

import traceback
import json
from typing import List, Dict, Any
from strands import tool
from ..base import BaseKnowledgeBaseProvider
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

class SnowflakeKnowledgeBaseProvider(BaseKnowledgeBaseProvider):
    """Knowledge base provider for Snowflake using MCP client."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Snowflake knowledge base provider."""
        super().__init__(config)
        self.provider_name = "snowflake"
        self.mcp_client = None
        self.is_initialized = False
    
    def initialize(self) -> List:
        """Initialize the Snowflake knowledge base provider and get the tools."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses # is_initialized is a boolean attribute, not a function
            return self.tools
            
        try:
            provider_config = self.get_provider_config()
            
            # Get Snowflake credentials
            snowflake_account = provider_config.get("snowflake_account", "")
            snowflake_username = provider_config.get("snowflake_username", "")
            snowflake_password = provider_config.get("snowflake_password", "")
            snowflake_database = provider_config.get("snowflake_database", "")
            snowflake_schema = provider_config.get("snowflake_schema", "")
            snowflake_role = provider_config.get("snowflake_role", "")
            snowflake_warehouse = provider_config.get("snowflake_warehouse", "COMPUTE_WH")
            
            # Validate required configuration
            if not snowflake_account:
                print("Error: Snowflake account is required")
                return []
                
            if not snowflake_username:
                print("Error: Snowflake username is required")
                return []
                
            if not snowflake_password:
                print("Error: Snowflake password is required")
                return []
            
            print(f"Initializing MCP Snowflake provider with account: {snowflake_account}, database: {snowflake_database}")
            
            # Initialize MCP client
            self.mcp_client = MCPClient(
                stdio_client.StdioClient(
                    StdioServerParameters(
                        server_command=["snowflake-mcp-server"],
                        server_env={
                            "SNOWFLAKE_ACCOUNT": snowflake_account,
                            "SNOWFLAKE_USER": snowflake_username,
                            "SNOWFLAKE_PASSWORD": snowflake_password,
                            "SNOWFLAKE_DATABASE": snowflake_database,
                            "SNOWFLAKE_SCHEMA": snowflake_schema,
                            "SNOWFLAKE_ROLE": snowflake_role,
                            "SNOWFLAKE_WAREHOUSE": snowflake_warehouse
                        }
                    )
                )
            )
            
            print(f"Successfully initialized MCP Snowflake client")
            
            # Create tools
            self._create_tools()
            self.is_initialized = True
            
            print(f"MCP Snowflake knowledge base provider initialized with {len(self.tools)} tools")
            for tool_func in self.tools:
                print(f"  - {tool_func.__name__ if hasattr(tool_func, '__name__') else str(tool_func)}")
            
            return self.tools
            
        except Exception as e:
            print(f"Error initializing MCP Snowflake knowledge base provider: {str(e)}")
            traceback.print_exc()
            self.close()
            return []
    
    def _create_tools(self):
        """Create Snowflake query tools using MCP."""
        
        @tool
        def retriever_snowflake_cortex_query(prompt: str) -> str:
            """
            Execute a natural language prompt over Snowflake using Cortex LLM across multiple tables.

            Args:
                prompt: Natural language instruction (e.g., "Find top 5 customers by spend and their last orders").

            Returns:
                Natural language summary or JSON result depending on prompt intent.
            """
            try:
                if not self.mcp_client:
                    return "Error: MCP Snowflake client not initialized"
                
                print(f"Executing MCP Snowflake Cortex query for: {prompt}")
                
                # Call the MCP function
                response = self.mcp_client.invoke_function(
                    "cortex_query",
                    {"prompt": prompt}
                )
                
                return response
                
            except Exception as e:
                error_msg = f"Error executing MCP Snowflake Cortex query: {str(e)}"
                print(error_msg)
                traceback.print_exc()
                return error_msg
        
        print("Creating MCP Snowflake query tools:")
        print(f"  1. retriever_snowflake_cortex_query: {retriever_snowflake_cortex_query}")
        
        self.tools = [retriever_snowflake_cortex_query]
    
    def close(self):
        """Close the MCP Snowflake client."""
        if self.is_initialized:
            try:
                if self.mcp_client:
                    self.mcp_client.close()
                self.is_initialized = False
                self.tools = []
                self.mcp_client = None
                print("MCP Snowflake client closed")
            except Exception as e:
                print(f"Error closing MCP Snowflake client: {str(e)}")
                traceback.print_exc()
