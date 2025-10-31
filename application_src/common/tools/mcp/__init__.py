"""
MCP tools for GenAI-In-A-Box agent.
This module provides MCP tools for use with Strands Agent.
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional
from functools import wraps

from .client import MCPClient, MCPServerConfig, parse_mcp_server_config, initialize_mcp_client, get_mcp_client

logger = logging.getLogger(__name__)

def create_tool_wrapper(name: str, description: str, input_schema: Dict[str, Any], conn_id: str):
    """
    Create a tool wrapper function for MCP tools with runtime execution fix.
    
    This function handles both function and module cases for mcp_client execution
    to fix "'module' object is not callable" errors discovered in production.
    """
    try:
        from strands_tools import mcp_client
    except ImportError:
        logger.error("🚨 Failed to import mcp_client from strands_tools")
        return None
    
    def mcp_tool_func(tool_input: dict) -> dict:
        """Execute MCP tool with proper error handling for both function and module cases."""
        try:
            # Prepare arguments
            final_args = tool_input if isinstance(tool_input, dict) else {}
            # Call the MCP server tool - handle both function and module cases
            try:
                # Try calling it as a function first
                result = mcp_client(
                    action="call_tool",
                    connection_id=conn_id,
                    tool_name=name,
                    arguments=final_args
                )
            except TypeError as e:
                # If it's a module, we need to find the actual function
                if hasattr(mcp_client, 'mcp_client'):
                    # Try calling the function inside the module
                    result = mcp_client.mcp_client(
                        action="call_tool",
                        connection_id=conn_id,
                        tool_name=name,
                        arguments=final_args
                    )
                else:
                    logger.error(f"🚨 Cannot find mcp_client function in module: {e}")
                    return {"error": f"MCP client module error: {e}", "success": False}
            return result
            
        except Exception as e:
            logger.error(f"🚨 Error executing MCP tool '{name}': {e}")
            return {
                "error": f"Failed to execute MCP tool '{name}': {str(e)}",
                "success": False
            }
    
    # Set function metadata for Strands Agent recognition
    mcp_tool_func.__name__ = f"mcp_{name.replace('-', '_')}"
    mcp_tool_func.__doc__ = description
    mcp_tool_func.input_schema = input_schema
    
    # Import the Strands tool decorator
    try:
        from strands import tool
        # Apply Strands @tool decorator - this is critical for recognition
        return tool(mcp_tool_func)
    except ImportError:
        logger.warning("⚠️ strands tool decorator not available, returning raw function")
        return mcp_tool_func

def create_mcp_tool_function(server_name: str, tool_name: str, tool_description: str, input_schema: Dict[str, Any]):
    """Create a Strands-compatible tool function for an MCP tool."""
    
    @wraps(create_mcp_tool_function)
    def mcp_tool_wrapper(arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        MCP tool wrapper that calls remote MCP server.
        
        Args:
            arguments: Tool arguments as provided by the agent
            
        Returns:
            Tool response from MCP server
        """
        try:
            async def call_mcp_tool():
                client = await get_mcp_client()
                if not client:
                    return {
                        "error": "MCP client not initialized",
                        "success": False
                    }
                return await client.call_tool(server_name, tool_name, arguments)
            
            # Handle event loop context
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context, run in a separate thread
                import concurrent.futures
                
                def run_in_thread():
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        return new_loop.run_until_complete(call_mcp_tool())
                    finally:
                        new_loop.close()
                
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(run_in_thread)
                    return future.result(timeout=30)
                    
            except RuntimeError:
                # No event loop is running, we can use asyncio.run
                return asyncio.run(call_mcp_tool())
            
        except Exception as e:
            logger.error(f"Error calling MCP tool {tool_name} on {server_name}: {e}")
            return {
                "error": str(e),
                "server": server_name,
                "tool": tool_name,
                "success": False
            }
    
    # Set tool metadata for Strands
    mcp_tool_wrapper.__name__ = f"mcp_{server_name}_{tool_name}"
    mcp_tool_wrapper.__doc__ = f"{tool_description}\n\nServer: {server_name}\nTool: {tool_name}"
    
    # Add input schema as function attribute for Strands
    mcp_tool_wrapper.input_schema = input_schema
    mcp_tool_wrapper.description = tool_description
    mcp_tool_wrapper.server_name = server_name
    mcp_tool_wrapper.tool_name = tool_name
    
    return mcp_tool_wrapper

async def initialize_mcp_tools(mcp_config: Dict[str, Any]) -> List:
    """Initialize MCP tools based on configuration."""
    tools = []
    
    # Check if MCP is enabled
    if not mcp_config.get("mcp_enabled", False):
        logger.info("MCP integration is disabled")
        return tools
    
    # Parse server configurations
    servers_config = mcp_config.get("mcp_servers", "")
    if not servers_config:
        logger.warning("No MCP servers configured")
        return tools
    
    servers = parse_mcp_server_config(servers_config)
    if not servers:
        logger.warning("No valid MCP server configurations found")
        return tools
    
    # Initialize MCP client
    try:
        client = await initialize_mcp_client(servers)
        logger.info(f"MCP client initialized with {len(servers)} servers")
        
        # Discover and create tools for all servers
        for server_name in client.servers:
            try:
                mcp_tools = await client.list_tools_for_server(server_name)
                
                for mcp_tool in mcp_tools:
                    # Create Strands-compatible tool function
                    tool_func = create_mcp_tool_function(
                        server_name=mcp_tool.server_name,
                        tool_name=mcp_tool.name,
                        tool_description=mcp_tool.description,
                        input_schema=mcp_tool.input_schema
                    )
                    
                    tools.append(tool_func)
                    logger.info(f"Created MCP tool: {tool_func.__name__}")
                    
            except Exception as e:
                logger.error(f"Failed to initialize tools for server {server_name}: {e}")
                continue
        
        logger.info(f"Successfully initialized {len(tools)} MCP tools")
        return tools
        
    except Exception as e:
        logger.error(f"Failed to initialize MCP client: {e}")
        return tools

def get_mcp_tools(agent_config: Optional[Dict[str, Any]] = None) -> List:
    """Get MCP tools for use with Strands Agent."""
    if not agent_config:
        logger.info("No agent config provided, MCP tools disabled")
        return []
    
    try:
        # First, check if we have auto-connected MCP tools in memory
        from .. import get_mcp_connection_info
        
        # Try to get connection info (with fallback logic for agent names)
        connection_info = get_mcp_connection_info()
        
        if connection_info and connection_info.get("available_tools"):
            available_tools = connection_info.get("available_tools", [])
            connection_id = connection_info.get("connection_id")
            
            logger.info(f"🔍 Found {len(available_tools)} tools from auto-connect MCP system")
            logger.info(f"🔗 Using connection ID: {connection_id}")
            
            # Create tool wrappers for all discovered tools
            mcp_tools = []
            for tool_info in available_tools:
                tool_name = tool_info.get("name", "unknown")
                tool_description = tool_info.get("description", "No description available")
                input_schema = tool_info.get("inputSchema", {"type": "object", "properties": {}})
                
                # Create tool wrapper using the existing connection
                tool_wrapper = create_tool_wrapper(
                    name=tool_name,
                    description=tool_description,
                    input_schema=input_schema,
                    conn_id=connection_id
                )
                
                if tool_wrapper:
                    mcp_tools.append(tool_wrapper)
                else:
                    logger.warning(f"⚠️ Failed to create tool wrapper for: {tool_name}")
            
            logger.info(f"🛠️ Successfully created {len(mcp_tools)} MCP tool wrappers from auto-connect system")
            return mcp_tools
        
        # Fallback to the original async MCP system if no auto-connect tools found
        logger.info("🔄 No auto-connect MCP tools found, trying async MCP system...")
        
        # Check if we're already in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, so we can't use run_until_complete
            # Instead, we'll create a task and run it synchronously
            import concurrent.futures
            import threading
            
            def run_in_thread():
                # Create new event loop in a separate thread
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(initialize_mcp_tools(agent_config))
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                tools = future.result(timeout=30)  # 30 second timeout
                return tools
                
        except RuntimeError:
            # No event loop is running, we can use asyncio.run
            tools = asyncio.run(initialize_mcp_tools(agent_config))
            return tools
        
    except Exception as e:
        logger.error(f"Failed to get MCP tools: {e}")
        import traceback
        traceback.print_exc()
        return []

# Utility functions for tool management
async def list_available_mcp_servers() -> List[str]:
    """List all available MCP servers."""
    client = await get_mcp_client()
    if not client:
        return []
    return list(client.servers.keys())

async def get_server_capabilities(server_name: str) -> Dict[str, Any]:
    """Get capabilities for a specific MCP server."""
    client = await get_mcp_client()
    if not client:
        return {}
    return await client.discover_server_capabilities(server_name)

async def test_mcp_server_connection(server_name: str) -> bool:
    """Test connection to an MCP server."""
    try:
        capabilities = await get_server_capabilities(server_name)
        return "server_info" in capabilities
    except Exception as e:
        logger.error(f"Failed to test connection to {server_name}: {e}")
        return False
