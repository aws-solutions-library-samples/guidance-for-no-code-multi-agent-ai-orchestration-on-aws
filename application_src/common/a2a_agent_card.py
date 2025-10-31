"""
A2A Agent Card functionality using the official A2A framework.
Provides standardized agent metadata using a2a.types.AgentCard.
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from a2a.types import AgentCard

try:
    from a2a.types import AgentSkill
except ImportError:
    # If AgentSkill is not available, we'll use dictionaries
    AgentSkill = None

logger = logging.getLogger(__name__)

class A2AAgentCardProvider:
    """
    Agent Card provider using the official A2A framework.
    Generates standardized agent metadata for A2A discovery.
    """
    
    def __init__(self, agent_name: str, agent_description: str, port: int):
        """Initialize A2A agent card provider."""
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.port = port
        
    def create_agent_card(self, 
                         agent_instance=None,
                         base_url: Optional[str] = None,
                         extra_capabilities: Optional[Dict[str, Any]] = None,
                         extra_endpoints: Optional[List[Dict[str, Any]]] = None) -> AgentCard:
        """
        Create an A2A framework compatible AgentCard.
        
        Args:
            agent_instance: Actual agent instance for runtime information
            base_url: Base URL for the agent (auto-detected if not provided)
            extra_capabilities: Additional capabilities to include
            extra_endpoints: Additional endpoints to include
            
        Returns:
            AgentCard instance using A2A framework types
        """
        
        # Auto-detect base URL from environment if not provided
        if not base_url:
            hosted_dns = os.environ.get('HOSTED_DNS')
            http_url = os.environ.get('HTTP_URL')
            
            if hosted_dns:
                base_url = f"http://{hosted_dns}"
            elif http_url:
                base_url = http_url
            else:
                base_url = f"http://0.0.0.0:{self.port}"
        
        # Get runtime information from agent instance
        tools = []
        agent_version = "0.0.1"  # Default version to match committed version
        actual_agent_name = self.agent_name
        actual_agent_description = self.agent_description
        
        if agent_instance:
            # Try to get name and description from agent instance (from SSM config)
            if hasattr(agent_instance, 'name') and agent_instance.name:
                actual_agent_name = agent_instance.name
            
            if hasattr(agent_instance, 'description') and agent_instance.description:
                actual_agent_description = agent_instance.description
            
            # Extract tools from Strands agent instance - check Strands-specific attributes
            for tools_attr in ['tool_names', 'tool_registry', 'tools', '_tools', 'available_tools']:
                if hasattr(agent_instance, tools_attr):
                    try:
                        tools_list = getattr(agent_instance, tools_attr)
                        
                        if tools_attr == 'tool_names' and tools_list:
                            tools.extend(tools_list)
                            break
                        elif tools_attr == 'tool_registry' and tools_list:
                            if hasattr(tools_list, 'keys'):
                                tool_keys = list(tools_list.keys())
                                tools.extend(tool_keys)
                                break
                            elif hasattr(tools_list, '__iter__'):
                                for tool in tools_list:
                                    if hasattr(tool, 'name'):
                                        tools.append(tool.name)
                                    elif hasattr(tool, '__name__'):
                                        tools.append(tool.__name__)
                                    else:
                                        tools.append(str(tool))
                                break
                        elif tools_list:
                            for tool in tools_list:
                                if hasattr(tool, 'name'):
                                    tools.append(tool.name)
                                elif hasattr(tool, '__name__'):
                                    tools.append(tool.__name__)
                                else:
                                    tool_str = str(tool)
                                    tools.append(tool_str)
                            break  # Use the first successful extraction
                    except Exception as e:
                        pass  # Continue trying other tool extraction methods
            
            # Also try to get tools from the runnable interface
            if not tools and hasattr(agent_instance, 'get_available_tools'):
                try:
                    available_tools = agent_instance.get_available_tools()
                    if available_tools:
                        tools = [str(tool) for tool in available_tools]
                except Exception as e:
                    pass  # Fallback if tool extraction fails
            # Try to get version from agent
            if hasattr(agent_instance, 'version'):
                agent_version = agent_instance.version
            elif hasattr(agent_instance, '__version__'):
                agent_version = agent_instance.__version__
        
        # Build A2A capabilities based on actual agent capabilities
        # Only set streaming=true if we actually support A2A streaming protocol
        capabilities = {
            "streaming": True,  # We now support A2A streaming with message/stream endpoint
            "pushNotifications": False,  # Not implemented yet
            "stateTransitionHistory": False  # Not implemented yet
        }
        
        # Add tool-based capabilities
        if tools:
            if any('memory' in tool.lower() for tool in tools):
                capabilities["memory"] = True
            if any('retrieve' in tool.lower() or 'search' in tool.lower() for tool in tools):
                capabilities["knowledge_base"] = True
            if any('a2a' in tool.lower() for tool in tools):
                capabilities["a2a_calls"] = True
        
        # Add extra capabilities if provided
        if extra_capabilities:
            capabilities.update(extra_capabilities)
        
        # Build A2A compliant endpoints with proper transport declarations
        endpoints = [
            {"path": "/", "method": "GET", "description": "Agent information and status"},
            {"path": "/", "method": "POST", "description": "A2A JSON-RPC endpoint (message/send, message/stream)"},
            {"path": "/v1/message:stream", "method": "POST", "description": "A2A REST streaming endpoint"},
            {"path": "/chat", "method": "POST", "description": "Chat with agent (synchronous)"},
            {"path": "/health", "method": "GET", "description": "Health check endpoint"},
            {"path": "/.well-known/agent-card.json", "method": "GET", "description": "A2A agent discovery"},
        ]
        
        # Add extra endpoints if provided
        if extra_endpoints:
            endpoints.extend(extra_endpoints)
        
        # Build skills from tools - let @tool decorator provide everything
        if tools:
            skills = []
            
            # Get tool registry from agent instance
            tool_registry = None
            if agent_instance and hasattr(agent_instance, 'tool_registry'):
                tool_registry = getattr(agent_instance, 'tool_registry')
            
            for tool_name in tools:
                # Default values
                tool_description = f"Agent capability: {tool_name}"
                
                # Get description from Strands tool registry 
                if tool_registry:
                    try:
                        # Try accessing the internal registry
                        if hasattr(tool_registry, 'registry'):
                            internal_registry = tool_registry.registry
                            if tool_name in internal_registry:
                                tool_obj = internal_registry[tool_name]
                                if hasattr(tool_obj, '__doc__') and tool_obj.__doc__:
                                    tool_description = tool_obj.__doc__.strip()
                        
                        # Try get_all_tool_specs method
                        elif hasattr(tool_registry, 'get_all_tool_specs'):
                            all_specs = tool_registry.get_all_tool_specs()
                            if tool_name in all_specs:
                                spec = all_specs[tool_name]
                                if hasattr(spec, 'description'):
                                    tool_description = spec.description
                    except Exception as e:
                        pass  # Continue if tool description extraction fails
                
                skills.append({
                    "id": tool_name,
                    "name": tool_name,
                    "description": tool_description,
                    "tags": []
                })
        else:
            skills = [
                {
                    "id": f"{actual_agent_name}_general_assistance",
                    "name": "general_assistance",
                    "description": "General assistance and question answering",
                    "tags": ["general", "assistance", "qa"]
                }
            ]

        # Create A2A-compliant AgentCard following the official specification
        card_dict = {
            # A2A Protocol required fields (per specification section 5.5)
            "protocolVersion": "0.3.0",
            "name": actual_agent_name,
            "description": actual_agent_description,
            "url": base_url,
            "preferredTransport": "JSONRPC",  # Required field per spec
            "additionalInterfaces": [
                {
                    "url": base_url,
                    "transport": "JSONRPC"
                },
                {
                    "url": f"{base_url}/v1/message:stream",
                    "transport": "HTTP+JSON"
                }
            ],
            "version": agent_version,
            "capabilities": capabilities,
            "defaultInputModes": ["text/plain"],  # MIME types per A2A spec
            "defaultOutputModes": ["text/plain"], # MIME types per A2A spec
            "skills": skills,
            
            # Optional A2A fields
            "provider": {
                "organization": "Internal Development",
                "url": base_url
            },
            "supportsAuthenticatedExtendedCard": False,
            
            # Extended fields for compatibility (not part of core A2A spec)
            "agent_id": actual_agent_name,
            "port": self.port,
            "protocol": "http", 
            "endpoints": endpoints,
            "tools": tools,
            "tool_count": len(tools),
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "supports_a2a": True,
            "agent_type": "fastapi"
        }
        
        # Create AgentCard object (try to use A2A types if available, otherwise dict)
        try:
            card = AgentCard(**card_dict)
        except Exception as e:
            card = type('AgentCard', (), card_dict)()
            card.dict = lambda: card_dict
            card.__dict__.update(card_dict)
        
        return card
    
    def generate_well_known_response(self, 
                                   agent_instance=None,
                                   extra_capabilities: Optional[Dict[str, Any]] = None,
                                   extra_endpoints: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Generate the /.well-known/agent-card.json response using A2A framework.
        
        Args:
            agent_instance: Agent instance for runtime information
            extra_capabilities: Additional capabilities to include
            extra_endpoints: Additional endpoints to include
            
        Returns:
            Dictionary representation for JSON response
        """
        
        card = self.create_agent_card(
            agent_instance=agent_instance,
            extra_capabilities=extra_capabilities,
            extra_endpoints=extra_endpoints
        )
        
        # Convert AgentCard to dictionary using A2A framework method
        card_data = card.dict() if hasattr(card, 'dict') else card.__dict__.copy()
        
        # Add A2A specific metadata
        card_data.update({
            "@context": "https://schemas.agent.to.agent/v1/agent-card",
            "@type": "AgentCard",
            "well_known_endpoint": "/.well-known/agent-card.json",
            "discovery_protocol": "a2a-v1"
        })
        
        return card_data


def create_a2a_agent_card_provider(agent_name: str, agent_description: str, port: int) -> A2AAgentCardProvider:
    """
    Factory function to create an A2A agent card provider.
    
    Args:
        agent_name: Name of the agent
        agent_description: Description of the agent's purpose
        port: Port number for the agent
        
    Returns:
        A2AAgentCardProvider instance
    """
    return A2AAgentCardProvider(agent_name, agent_description, port)
