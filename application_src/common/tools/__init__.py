"""
Tools factory for GenAI-In-A-Box agent.
This module provides a factory for creating tools.
"""

import os
import json
import time
from typing import List, Dict, Any
from config import Config
from strands_tools import http_request
from .mcp import get_mcp_tools

# Global in-memory storage for MCP connection info
_mcp_connections = {}  # Dictionary keyed by agent_name containing connection info

def get_mcp_connection_info(agent_name=None):
    """Get MCP connection info with fallback logic for common agent names."""
    global _mcp_connections
    if not agent_name:
        # Fallback to common agent names in priority order
        for common_name in ["qa_agent_2", "qa_agent", "agent"]:
            if common_name in _mcp_connections:
                agent_name = common_name
                break
    
    if agent_name and agent_name in _mcp_connections:
        return _mcp_connections[agent_name]
    return None

def auto_connect_mcp_servers(mcp_client, tool_config: Dict[str, Any], agent_name: str) -> List:
    """
    Automatically connect to configured MCP servers and load their tools.
    
    This function:
    1. Extracts MCP server configuration from tool config
    2. Connects to the MCP server using mcp_client
    3. Lists available tools from the server
    4. Stores connection info in memory for later use
    
    Args:
        mcp_client: The mcp_client tool/module
        tool_config: Configuration from SSM parameter store
        agent_name: Name of the agent (for connection naming)
    
    Returns:
        List containing the mcp_client tool (for backwards compatibility)
    """
    global _mcp_connections
    
    try:
        print(f"🔄 Auto-connecting MCP servers for {agent_name}...")
        
        # Extract configuration
        transport = tool_config.get("default_transport", "streamable_http") 
        server_url = tool_config.get("server_url")
        headers = tool_config.get("default_headers")
        
        if not server_url:
            print("❌ No server_url configured for MCP client")
            return [mcp_client]
            
        print(f"📡 Connecting to MCP server: {server_url}")
        print(f"🚀 Transport: {transport}")
        
        # Parse headers if they're a string
        if isinstance(headers, str):
            if headers.strip():  # Only parse if not empty
                try:
                    headers = json.loads(headers)
                except json.JSONDecodeError as e:
                    print(f"⚠️ Invalid JSON in default_headers: {e}")
                    headers = {}
            else:
                headers = {}
        elif not headers:
            headers = {}
            
        # Generate unique connection ID
        connection_id = f"{agent_name}_auto_{int(time.time())}"
        
        # Connect to MCP server - handle both function and module cases
        try:
            # Try calling it as a function first
            connect_result = mcp_client(
                action="connect",
                connection_id=connection_id,
                transport=transport,
                server_url=server_url,
                headers=headers,
                timeout=30.0
            )
        except TypeError as e:
            # If it's a module, we need to find the actual function
            print(f"🔧 mcp_client is a module, looking for the function...")
            if hasattr(mcp_client, 'mcp_client'):
                # Try calling the function inside the module
                connect_result = mcp_client.mcp_client(
                    action="connect",
                    connection_id=connection_id,
                    transport=transport,
                    server_url=server_url,
                    headers=headers,
                    timeout=30.0
                )
            else:
                print(f"🚨 Cannot find mcp_client function in module: {e}")
                return [mcp_client]
        
        # Check for success using the actual MCP client response format
        connection_success = (
            connect_result.get("status") == "success" or
            connect_result.get("status") == "connected" or
            connect_result.get("success", False) or
            "connection_id" in connect_result
        )
        
        if not connection_success:
            error_msg = "Unknown error"
            if connect_result.get("status") == "error":
                content = connect_result.get("content", [])
                if content and isinstance(content, list) and len(content) > 0:
                    error_msg = content[0].get("text", "Unknown error")
            else:
                error_msg = connect_result.get("error", "Unknown error")
                
            print(f"❌ Failed to connect to MCP server: {error_msg}")
            print(f"🔍 Full connect_result: {connect_result}")
            print(f"🔍 Connect_result type: {type(connect_result)}")
            print(f"🔍 Connect_result keys: {list(connect_result.keys()) if isinstance(connect_result, dict) else 'Not a dict'}")
            return [mcp_client]
            
        print("✅ Connected to MCP server successfully")
        
        # List available tools - handle both function and module cases
        try:
            # Try calling it as a function first
            list_result = mcp_client(
                action="list_tools",
                connection_id=connection_id
            )
        except TypeError as e:
            # If it's a module, we need to find the actual function
            print(f"🔧 mcp_client is a module for list_tools, using function...")
            if hasattr(mcp_client, 'mcp_client'):
                # Try calling the function inside the module
                list_result = mcp_client.mcp_client(
                    action="list_tools",
                    connection_id=connection_id
                )
            else:
                print(f"🚨 Cannot find mcp_client function in module for list_tools: {e}")
                return [mcp_client]
        
        # Check for success using the actual MCP client response format  
        list_success = (
            list_result.get("status") == "success" or
            list_result.get("status") == "completed" or
            list_result.get("success", False) or
            "tools" in list_result or
            ("content" in list_result and len(list_result["content"]) > 1 and 
             "json" in list_result["content"][1] and 
             "tools" in list_result["content"][1]["json"])
        )
        
        if not list_success:
            error_msg = "Unknown error"
            if list_result.get("status") == "error":
                content = list_result.get("content", [])
                if content and isinstance(content, list) and len(content) > 0:
                    error_msg = content[0].get("text", "Unknown error")
            else:
                error_msg = list_result.get("error", "Unknown error")
                
            print(f"❌ Failed to list tools from MCP server: {error_msg}")
            print(f"🔍 Full list_result: {list_result}")
            print(f"🔍 List_result type: {type(list_result)}")
            print(f"🔍 List_result keys: {list(list_result.keys()) if isinstance(list_result, dict) else 'Not a dict'}")
            return [mcp_client]
            
        # Parse tools from the actual response format used by GitHub Copilot MCP server
        tools = []
        if "content" in list_result and len(list_result["content"]) > 1:
            # GitHub Copilot format: content[1].json.tools
            json_content = list_result["content"][1].get("json", {})
            tools = json_content.get("tools", [])
            print(f"🔍 Found tools in GitHub Copilot format: content[1].json.tools")
        else:
            # Fallback to direct tools location for other MCP servers
            tools = list_result.get("tools", [])
            print(f"🔍 Found tools in standard format: root.tools")
            
        print(f"🔍 Found {len(tools)} tools available on MCP server:")
        for tool in tools[:3]:  # Show first 3 tools
            tool_name = tool.get("name", "Unknown")
            tool_desc = tool.get("description", "No description")
            print(f"  - {tool_name}: {tool_desc}")
        if len(tools) > 3:
            print(f"  ... and {len(tools) - 3} more tools")
            
        # Store connection info in memory
        mcp_info = {
            "connection_id": connection_id,
            "available_tools": tools,
            "server_url": server_url,
            "transport": transport,
            "headers": headers,
            "connected_at": time.time()
        }
        
        _mcp_connections[agent_name] = mcp_info
        print(f"🛠️ Stored MCP connection info in memory for {agent_name}")
        print("✅ MCP server connection established.")
        
        return [mcp_client]
        
    except Exception as e:
        print(f"❌ Error in auto_connect_mcp_servers: {e}")
        import traceback
        traceback.print_exc()
        return [mcp_client]

def get_default_tools(agent_name="qa_agent") -> List:
    """Get default tools for use with Strands Agent."""
    tools = []
    
    # Create config instance with the correct agent name
    agent_config_instance = Config(agent_name)
    
    # Get tools configuration from SSM parameter store
    agent_config_instance.load_config(force_refresh=True)  # Force refresh to get latest config
    agent_config = agent_config_instance.config  # Access the config directly
    tools_config = agent_config.get("tools", [])
    
    print(f"Found {len(tools_config)} tools in SSM parameter store configuration")
    
    # Process each tool in the configuration
    for tool_config in tools_config:
        tool_name = tool_config.get("name", "").lower()
        tool_config_details = tool_config.get("config", {})
        
        # Check if the tool is enabled
        is_enabled = str(tool_config_details.get("enabled", "")).lower() in ["yes", "true"]
        
        print(f"Tool: {tool_name}, Enabled: {is_enabled}")
        
        if is_enabled:
            # Initialize and register the tool based on its name
            tool_instances = initialize_tool(tool_name, tool_config_details)
            if tool_instances:
                tools.extend(tool_instances)
                print(f"Successfully registered tool: {tool_name}")
            else:
                print(f"Failed to register tool: {tool_name}")
    
    # Add MCP tools if enabled
    try:
        mcp_tools = get_mcp_tools(agent_config)
        if mcp_tools:
            tools.extend(mcp_tools)
            print(f"Successfully registered {len(mcp_tools)} MCP tools")
        else:
            print("No MCP tools configured or MCP disabled")
    except Exception as e:
        print(f"Failed to load MCP tools: {e}")
    
    # NOTE: We're removing this section to avoid duplicate tools
    # The retrieve tool should be added by the knowledge base provider, not here
    # This ensures that only the tools from the selected provider are added
    
    # No fallback tools - if no tools were registered, return empty list
    print(f"Total registered tools: {len(tools)}")
    return tools

def initialize_tool(tool_name: str, tool_config: Dict[str, Any]) -> List:
    """Initialize and register a specific tool based on its name."""
    if tool_name == "http_request":
        try:
            print("Successfully imported http_request tool")
            return [http_request]
        except Exception as e:
            print(f"Error with http_request tool: {e}")
            return []
    
    elif tool_name == "use_aws":
        try:
            from strands_tools import use_aws
            print("Successfully imported use_aws tool (includes DynamoDB support)")
            return [use_aws]
        except ImportError as e:
            print(f"Failed to import use_aws tool: {e}")
            return []
    elif tool_name == "load_tool":
        try:
            from strands_tools import load_tool
            print("Successfully imported load_tool tool ")
            return [load_tool]
        except ImportError as e:
            print(f"Failed to import use_aws tool: {e}")
            return []
    elif tool_name == "mcp_client":
        try:
            from strands_tools import mcp_client
            print("Successfully imported mcp_client tool")
            
            # Auto-connect to configured MCP servers and load their tools
            # Extract agent name from get_default_tools call stack
            import inspect
            frame = inspect.currentframe()
            agent_name = "qa_agent"  # Default fallback
            try:
                # Look through the call stack to find agent_name parameter
                while frame:
                    frame_locals = frame.f_locals
                    if 'agent_name' in frame_locals:
                        extracted_name = frame_locals['agent_name']
                        if extracted_name:  # Only use if not None/empty
                            agent_name = extracted_name
                            print(f"🔍 Extracted agent_name from call stack: {agent_name}")
                        break
                    frame = frame.f_back
            except Exception as e:
                print(f"⚠️ Failed to extract agent_name from call stack: {e}")
                pass  # Use default if extraction fails
            
            print(f"🤖 Using agent_name for MCP connection: {agent_name}")
            loaded_tools = auto_connect_mcp_servers(mcp_client, tool_config, agent_name)
            
            # Return mcp_client tool plus any loaded tools
            all_tools = []
            if loaded_tools:
                all_tools.extend(loaded_tools)
            else:
                all_tools = [mcp_client]  # Fallback to just mcp_client
                
            return all_tools
        except ImportError as e:
            print(f"Failed to import mcp_client tool: {e}")
            return []
    
    # Add more tools here as needed
    
    print(f"Unknown tool name: {tool_name}")
    return []

def get_retrieve_tool(agent_name="qa_agent"):
    """Get the retrieve tool for Bedrock Knowledge Base."""
    try:
        # Create config instance with the correct agent name
        agent_config_instance = Config(agent_name)
        agent_config_instance.load_config(force_refresh=True)
        
        # Set environment variables for Bedrock Knowledge Base
        kb_config = agent_config_instance.get_knowledge_base_config()
        print(f"Knowledge Base Config for retrieve tool: {json.dumps(kb_config, indent=2)}")
        
        if kb_config.get("enabled", False) and kb_config.get("provider", "").lower() in ["bedrock knowledge base", "bedrock_kb"]:
            # Find the provider config
            provider_config = None
            for provider in kb_config.get("provider_details", []):
                if provider.get("name", "").lower() in ["bedrock knowledge base", "bedrock_kb"]:
                    provider_config = provider.get("config", {})
                    break
            
            print(f"Provider Config for retrieve tool: {json.dumps(provider_config, indent=2) if provider_config else 'None'}")
            
            if provider_config:
                kb_id = provider_config.get("knowledge_base_id", "")
                region = provider_config.get("region", "us-east-1")
                
                print(f"Knowledge Base ID: {kb_id}")
                print(f"Region: {region}")
                
                if kb_id:
                    print(f"Setting KNOWLEDGE_BASE_ID={kb_id} for retrieve tool")
                    os.environ["KNOWLEDGE_BASE_ID"] = kb_id
                else:
                    print("Warning: No knowledge_base_id found in provider config")
                
                if region:
                    print(f"Setting AWS_REGION={region} for retrieve tool")
                    os.environ["AWS_REGION"] = region
        else:
            print(f"Bedrock Knowledge Base not enabled or not the selected provider")
            print(f"Enabled: {kb_config.get('enabled', False)}")
            print(f"Provider: {kb_config.get('provider', 'None')}")
            return []  # Return empty list if not using Bedrock KB
        
        # Print all environment variables for debugging
        print("Environment Variables for retrieve tool:")
        for key, value in os.environ.items():
            if key in ["KNOWLEDGE_BASE_ID", "AWS_REGION"]:
                print(f"  {key}={value}")
        
        # Import the retrieve tool directly
        from strands_tools import retrieve
        print(f"Successfully imported retrieve tool: {retrieve}")
        
        return [retrieve]
    except ImportError as e:
        print(f"Failed to import retrieve tool: {e}")
        import traceback
        traceback.print_exc()
        return []
