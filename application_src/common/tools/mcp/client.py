"""
MCP Client implementation for GenAI-In-A-Box agents.
This module provides MCP client tools for remote MCP server integration.
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import httpx
from functools import lru_cache

logger = logging.getLogger(__name__)

@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    url: str
    description: str = ""
    auth_type: str = "none"  # none, bearer, basic, api_key
    auth_token: Optional[str] = None
    auth_header: str = "Authorization"  # For custom auth headers
    timeout: int = 30
    enabled: bool = True
    retry_attempts: int = 3
    cache_ttl: int = 300  # 5 minutes

@dataclass
class MCPTool:
    """Represents an MCP tool from a remote server."""
    name: str
    description: str
    server_name: str
    server_url: str
    input_schema: Dict[str, Any]
    
class MCPServerCache:
    """Cache for MCP server capabilities and responses."""
    
    def __init__(self, ttl_seconds: int = 300):
        self.ttl = ttl_seconds
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_time: Dict[str, float] = {}
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached value if still valid."""
        if key in self.cache and time.time() - self.cache_time[key] < self.ttl:
            return self.cache[key]
        return None
    
    def set(self, key: str, value: Dict[str, Any]) -> None:
        """Set cached value with timestamp."""
        self.cache[key] = value
        self.cache_time[key] = time.time()
    
    def clear(self) -> None:
        """Clear all cached values."""
        self.cache.clear()
        self.cache_time.clear()

class MCPClient:
    """Client for interacting with remote MCP servers."""
    
    def __init__(self, servers: List[MCPServerConfig], cache_ttl: int = 300):
        self.servers = {server.name: server for server in servers if server.enabled}
        self.cache = MCPServerCache(cache_ttl)
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        self._discovered_tools: Dict[str, List[MCPTool]] = {}
        logger.info(f"MCP Client initialized with {len(self.servers)} servers")
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
    
    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()
    
    def _get_auth_headers(self, server: MCPServerConfig) -> Dict[str, str]:
        """Get authentication headers for a server."""
        headers = {"Content-Type": "application/json"}
        
        if server.auth_type == "bearer" and server.auth_token:
            headers[server.auth_header] = f"Bearer {server.auth_token}"
        elif server.auth_type == "api_key" and server.auth_token:
            headers[server.auth_header] = server.auth_token
        elif server.auth_type == "basic" and server.auth_token:
            headers[server.auth_header] = f"Basic {server.auth_token}"
        
        return headers
    
    async def _make_request(self, server: MCPServerConfig, method: str, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make HTTP request to MCP server with retry logic."""
        url = f"{server.url.rstrip('/')}/{endpoint.lstrip('/')}"
        headers = self._get_auth_headers(server)
        
        for attempt in range(server.retry_attempts + 1):
            try:
                if method.upper() == "GET":
                    response = await self.http_client.get(url, headers=headers, timeout=server.timeout)
                else:
                    response = await self.http_client.post(url, headers=headers, json=data, timeout=server.timeout)
                
                response.raise_for_status()
                return response.json()
                
            except httpx.TimeoutException as e:
                logger.warning(f"Timeout for {server.name} attempt {attempt + 1}: {e}")
                if attempt < server.retry_attempts:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                raise
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error for {server.name}: {e.response.status_code} {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Request failed for {server.name} attempt {attempt + 1}: {e}")
                if attempt < server.retry_attempts:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
    
    async def discover_server_capabilities(self, server_name: str) -> Dict[str, Any]:
        """Discover capabilities of an MCP server."""
        if server_name not in self.servers:
            raise ValueError(f"Unknown server: {server_name}")
        
        server = self.servers[server_name]
        cache_key = f"capabilities_{server_name}"
        
        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            logger.info(f"Using cached capabilities for {server_name}")
            return cached
        
        logger.info(f"Discovering capabilities for MCP server: {server_name}")
        
        try:
            # Try standard MCP discovery endpoint
            capabilities = await self._make_request(server, "GET", "/mcp/capabilities")
            self.cache.set(cache_key, capabilities)
            return capabilities
            
        except Exception as e:
            logger.error(f"Failed to discover capabilities for {server_name}: {e}")
            # Return minimal capabilities structure
            fallback = {
                "tools": [],
                "resources": [],
                "server_info": {
                    "name": server_name,
                    "version": "unknown",
                    "description": server.description
                }
            }
            return fallback
    
    async def list_tools_for_server(self, server_name: str) -> List[MCPTool]:
        """List available tools for a specific server."""
        capabilities = await self.discover_server_capabilities(server_name)
        server = self.servers[server_name]
        
        tools = []
        for tool_info in capabilities.get("tools", []):
            tool = MCPTool(
                name=tool_info.get("name", "unknown"),
                description=tool_info.get("description", ""),
                server_name=server_name,
                server_url=server.url,
                input_schema=tool_info.get("inputSchema", {})
            )
            tools.append(tool)
        
        self._discovered_tools[server_name] = tools
        logger.info(f"Discovered {len(tools)} tools for server {server_name}")
        return tools
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool on a remote MCP server."""
        if server_name not in self.servers:
            raise ValueError(f"Unknown server: {server_name}")
        
        server = self.servers[server_name]
        logger.info(f"Calling tool {tool_name} on server {server_name} with args: {arguments}")
        
        request_data = {
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }
        
        try:
            response = await self._make_request(server, "POST", "/mcp/tools/call", request_data)
            logger.info(f"Tool {tool_name} response received from {server_name}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to call tool {tool_name} on {server_name}: {e}")
            return {
                "error": str(e),
                "server": server_name,
                "tool": tool_name,
                "success": False
            }
    
    async def get_all_available_tools(self) -> List[MCPTool]:
        """Get all available tools from all enabled servers."""
        all_tools = []
        
        for server_name in self.servers:
            try:
                tools = await self.list_tools_for_server(server_name)
                all_tools.extend(tools)
            except Exception as e:
                logger.warning(f"Failed to get tools from server {server_name}: {e}")
        
        logger.info(f"Total MCP tools available: {len(all_tools)}")
        return all_tools

def parse_mcp_server_config(config_data: Union[str, List[Dict]]) -> List[MCPServerConfig]:
    """Parse MCP server configuration from JSON string or dict list."""
    if isinstance(config_data, str):
        try:
            config_data = json.loads(config_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse MCP server config JSON: {e}")
            return []
    
    if not isinstance(config_data, list):
        logger.error("MCP server config must be a list of server configurations")
        return []
    
    servers = []
    for server_config in config_data:
        try:
            server = MCPServerConfig(
                name=server_config.get("name", ""),
                url=server_config.get("url", ""),
                description=server_config.get("description", ""),
                auth_type=server_config.get("auth_type", "none"),
                auth_token=server_config.get("auth_token"),
                auth_header=server_config.get("auth_header", "Authorization"),
                timeout=server_config.get("timeout", 30),
                enabled=server_config.get("enabled", True),
                retry_attempts=server_config.get("retry_attempts", 3),
                cache_ttl=server_config.get("cache_ttl", 300)
            )
            
            if not server.name or not server.url:
                logger.warning(f"Skipping incomplete MCP server config: {server_config}")
                continue
                
            servers.append(server)
            logger.info(f"Configured MCP server: {server.name} at {server.url}")
            
        except Exception as e:
            logger.error(f"Failed to parse MCP server config: {e}")
            continue
    
    return servers

# Global MCP client instance (will be initialized per agent)
_mcp_client: Optional[MCPClient] = None

async def get_mcp_client() -> Optional[MCPClient]:
    """Get the global MCP client instance."""
    return _mcp_client

async def initialize_mcp_client(servers: List[MCPServerConfig]) -> MCPClient:
    """Initialize the global MCP client."""
    global _mcp_client
    if _mcp_client:
        await _mcp_client.close()
    
    _mcp_client = MCPClient(servers)
    return _mcp_client

async def cleanup_mcp_client():
    """Cleanup the global MCP client."""
    global _mcp_client
    if _mcp_client:
        await _mcp_client.close()
        _mcp_client = None
