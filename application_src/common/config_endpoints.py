"""
Common configuration endpoints module for all agents.
Provides reusable configuration status, refresh, and health endpoints.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from secure_logging_utils import log_exception_safely
# Import Config from the common directory regardless of where this module is used
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Ensure we can import Config from common directory
current_file_dir = Path(__file__).parent
if str(current_file_dir) not in sys.path:
    sys.path.insert(0, str(current_file_dir))

# Try to import Config from the common directory
try:
    from config import Config as CommonConfig
except ImportError:
    # If that fails, try to import from the relative path
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("config", current_file_dir / "config.py")
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)
        CommonConfig = config_module.Config
    except Exception as e:
        logger.error(f"Failed to import Config class: {e}")
        raise ImportError(f"Could not import Config class from common directory: {e}")

class AgentConfigEndpoints:
    """
    Reusable configuration endpoints for agents.
    Can be added to any FastAPI app (A2A server or regular FastAPI).
    """
    
    def __init__(self, agent_name: str, port: int, agent_instance_getter=None, service_info_getter=None, agent_service=None, agent_card_provider=None, fastapi_app=None):
        """
        Initialize configuration endpoints.
        
        Args:
            agent_name: Name of the agent (e.g., 'qa_agent', 'supervisor_agent')
            port: Port number the agent is running on
            agent_instance_getter: Callable to get the agent instance (for runtime info)
            service_info_getter: Callable to get service info (for supervisor agent)
            agent_service: Reference to the agent service for reinitialization
            agent_card_provider: Reference to the A2A agent card provider for updates
            fastapi_app: Reference to the FastAPI app for updating endpoints
        """
        self.agent_name = agent_name
        self.port = port
        self.agent_instance_getter = agent_instance_getter
        self.service_info_getter = service_info_getter
        self.agent_service = agent_service
        self.agent_card_provider = agent_card_provider
        self.fastapi_app = fastapi_app
        self.config_instance: Optional[CommonConfig] = None
        self.creation_time = datetime.now()
    
    def add_endpoints(self, app: FastAPI):
        """Add configuration endpoints to a FastAPI app."""
        
        @app.get("/config/status")
        async def get_agent_config_status():  # nosemgrep: useless-inner-function
            """Get current agent configuration status and runtime details."""
            try:
                # Create a fresh config instance to get current SSM values
                if self.config_instance is None:
                    self.config_instance = CommonConfig(self.agent_name)
                
                # Get current configurations
                model_config = self.config_instance.get_model_config()
                memory_config = self.config_instance.get_memory_config()
                kb_config = self.config_instance.get_knowledge_base_config()
                observability_config = self.config_instance.get_observability_config()
                guardrail_config = self.config_instance.get_guardrail_config()
                tools_config = self.config_instance.get_tools_config()
                mcp_config = self.config_instance.get_mcp_config()
                
                # Get agent runtime information
                agent_info = await self._get_agent_info()
                
                # Get tool names if available
                tool_names = await self._get_tool_names()
                
                # Build runtime info
                runtime_info = {
                    "tools": tool_names,
                    "server_port": self.port,
                    "server_host": "0.0.0.0",  # nosec: B104 # Container networking requires binding to all interfaces
                    "hosted_dns": None,  # Will be set by individual agents if needed
                    "http_url": "unknown"
                }
                
                # Add extra runtime info if available
                if hasattr(self, '_extra_runtime_info') and self._extra_runtime_info:
                    runtime_info.update(self._extra_runtime_info)
                
                # Add supervisor-specific runtime info
                if self.service_info_getter:
                    service_info = self.service_info_getter()
                    runtime_info.update({
                        "a2a_tools": len([t for t in tool_names if 'a2a' in t.lower()]),
                        "known_agents": service_info.get('known_agents', []),
                        "configuration_api_endpoint": None  # Will be set by supervisor if available
                    })
                
                return {
                    "agent": agent_info,
                    "configuration": {
                        "model": model_config,
                        "memory": memory_config,
                        "knowledge_base": kb_config,
                        "observability": observability_config,
                        "guardrail": guardrail_config,
                        "tools": tools_config,
                        "mcp": mcp_config
                    },
                    "runtime": runtime_info,
                    "timestamp": datetime.now().isoformat(),
                    "status": "active"
                }
                
            except Exception as e:
                log_exception_safely(logger, "Error getting agent configuration status", e)
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Internal server error occurred while retrieving configuration",
                        "agent_name": self.agent_name,
                        "timestamp": datetime.now().isoformat(),
                        "status": "error"
                    }
                )
        
        @app.get("/config/refresh")
        async def refresh_agent_config():  # nosemgrep: useless-inner-function
            """Force refresh of agent configuration from SSM Parameter Store."""
            try:
                self.config_instance = CommonConfig(self.agent_name)
                # Force reload of configuration
                self.config_instance.load_config(force_refresh=True)
                
                return {
                    "message": "Configuration refreshed successfully",
                    "agent_name": self.agent_name,
                    "timestamp": datetime.now().isoformat(),
                    "status": "success"
                }
                
            except Exception as e:
                log_exception_safely(logger, "Error refreshing agent configuration", e)
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Failed to refresh configuration from parameter store",
                        "agent_name": self.agent_name, 
                        "timestamp": datetime.now().isoformat(),
                        "status": "error"
                    }
                )
        
        @app.post("/config/load")
        async def load_specific_config(config_request: dict):  # nosemgrep: useless-inner-function
            """
            Load a specific configuration from SSM Parameter Store.
            
            Expected request body:
            {
                "config_name": "specific_config_name"
            }
            """
            try:
                config_name = config_request.get("config_name")
                if not config_name:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "config_name is required in request body",
                            "agent_name": self.agent_name,
                            "timestamp": datetime.now().isoformat(),
                            "status": "error"
                        }
                    )
                
                # Store the original agent name and config path for logging
                original_agent_name = self.agent_name
                original_config_path = f"/agent/{self.agent_name}/config"
                
                # Verify the configuration exists in SSM before proceeding
                config_path = f"/agent/{config_name}/config"
                logger.info(f"Validating configuration '{config_name}' exists in SSM at path '{config_path}'")
                
                # First, check if the SSM parameter exists without creating a config instance
                try:
                    from ssm_client import ssm
                    # Try to get the parameter to verify it exists
                    test_param = ssm.get_parameter(config_path, force_refresh=True)
                    if test_param is None:
                        logger.error(f"SSM parameter not found: {config_path}")
                        return JSONResponse(
                            status_code=404,
                            content={
                                "error": f"Configuration '{config_name}' not found in SSM Parameter Store at path '{config_path}'",
                                "config_name": config_name,
                                "config_path": config_path,
                                "agent_name": self.agent_name,
                                "timestamp": datetime.now().isoformat(),
                                "status": "error"
                            }
                        )
                    logger.info(f"✅ SSM parameter found at {config_path}")
                except Exception as ssm_error:
                    log_exception_safely(logger, f"SSM parameter validation failed for '{config_path}'", ssm_error)
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": f"Configuration '{config_name}' not found in SSM Parameter Store",
                            "config_name": config_name,
                            "config_path": config_path,
                            "agent_name": self.agent_name,
                            "timestamp": datetime.now().isoformat(),
                            "status": "error"
                        }
                    )
                
                # Now create and validate the config instance
                logger.info(f"Creating configuration instance for '{config_name}'")
                try:
                    new_config_instance = CommonConfig(config_name)
                    # Force load and validate the configuration
                    new_config_instance.load_config(force_refresh=True)
                    # Test that we can get basic config sections to ensure it's valid JSON
                    new_config_instance.get_model_config()
                    logger.info(f"✅ Configuration '{config_name}' loaded and validated successfully")
                except Exception as config_error:
                    log_exception_safely(logger, f"Configuration validation failed for '{config_name}'", config_error)
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": f"Configuration '{config_name}' is invalid or malformed",
                            "config_name": config_name,
                            "config_path": config_path,
                            "agent_name": self.agent_name,
                            "timestamp": datetime.now().isoformat(),
                            "status": "error"
                        }
                    )
                
                # Replace the current config instance with the new one
                self.config_instance = new_config_instance
                
                # Log the configuration change
                logger.info(f"Successfully loaded configuration '{config_name}' for agent '{original_agent_name}'")
                logger.info(f"Configuration path changed from '{original_config_path}' to '/agent/{config_name}/config'")
                
                # Reinitialize the agent with the new configuration
                reinit_success = await self._reinitialize_agent_with_new_config(config_name)
                if not reinit_success:
                    logger.warning(f"Agent reinitialization failed or not supported for '{config_name}'")
                
                # Get current configuration details for response
                model_config = self.config_instance.get_model_config()
                memory_config = self.config_instance.get_memory_config()
                kb_config = self.config_instance.get_knowledge_base_config()
                
                return {
                    "message": f"Configuration '{config_name}' loaded successfully",
                    "config_name": config_name,
                    "config_path": f"/agent/{config_name}/config",
                    "agent_name": original_agent_name,
                    "loaded_configuration": {
                        "model": model_config,
                        "memory": memory_config,
                        "knowledge_base": kb_config
                    },
                    "timestamp": datetime.now().isoformat(),
                    "status": "success"
                }
                
            except Exception as e:
                log_exception_safely(logger, "Error loading specific configuration", e)
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Failed to load the requested configuration",
                        "agent_name": self.agent_name,
                        "timestamp": datetime.now().isoformat(),
                        "status": "error"
                    }
                )
        
        @app.get("/config/health")
        async def get_agent_health():  # nosemgrep: useless-inner-function
            """Get basic health status of the agent."""
            try:
                uptime = (datetime.now() - self.creation_time).total_seconds()
                
                # Get agent instance if getter is available
                agent_instance = None
                if self.agent_instance_getter:
                    if callable(self.agent_instance_getter):
                        # Check if it's an async function
                        import asyncio
                        if asyncio.iscoroutinefunction(self.agent_instance_getter):
                            agent_instance = await self.agent_instance_getter()
                        else:
                            agent_instance = self.agent_instance_getter()
                    else:
                        agent_instance = self.agent_instance_getter
                
                # Build basic health response
                health_response = {
                    "agent_name": self.agent_name,
                    "status": "healthy",
                    "uptime_seconds": uptime,
                    "server_port": self.port,
                    "streaming_enabled": getattr(agent_instance, 'streaming', True),
                    "timestamp": datetime.now().isoformat()
                }
                
                # Add supervisor-specific health info
                if self.service_info_getter and hasattr(self.service_info_getter, '_initialization_complete'):
                    health_response["initialization_complete"] = getattr(self.service_info_getter, '_initialization_complete', False)
                    if not agent_instance:
                        health_response["status"] = "initializing"
                
                return health_response
                
            except Exception as e:
                log_exception_safely(logger, "Error getting agent health", e)
                return JSONResponse(
                    status_code=503,
                    content={
                        "agent_name": self.agent_name,
                        "status": "unhealthy", 
                        "error": "Health check failed",
                        "timestamp": datetime.now().isoformat()
                    }
                )
        
        logger.info(f"✅ Configuration endpoints added to {self.agent_name}")
    
    async def _get_agent_info(self) -> Dict[str, Any]:
        """Get agent runtime information."""
        agent_instance = None
        if self.agent_instance_getter:
            if callable(self.agent_instance_getter):
                # Check if it's an async function
                import asyncio
                if asyncio.iscoroutinefunction(self.agent_instance_getter):
                    agent_instance = await self.agent_instance_getter()
                else:
                    agent_instance = self.agent_instance_getter()
            else:
                agent_instance = self.agent_instance_getter
        
        agent_info = {
            "name": getattr(agent_instance, 'name', self.agent_name) if agent_instance else self.agent_name,
            "description": getattr(agent_instance, 'description', 'Unknown') if agent_instance else f'{self.agent_name} not initialized',
            "streaming_enabled": getattr(agent_instance, 'streaming', False) if agent_instance else True,
            "tools_count": len(getattr(agent_instance, 'tools', [])) if agent_instance else 0,
            "creation_time": self.creation_time.isoformat(),
            "uptime_seconds": (datetime.now() - self.creation_time).total_seconds()
        }
        
        # Add supervisor-specific agent info
        if self.service_info_getter:
            if hasattr(self.service_info_getter, '_initialization_complete'):
                agent_info["initialization_complete"] = getattr(self.service_info_getter, '_initialization_complete', False)
        
        return agent_info
    
    async def _get_tool_names(self) -> list:
        """Get list of tool names from agent instance."""
        tool_names = []
        
        if self.agent_instance_getter:
            if callable(self.agent_instance_getter):
                # Check if it's an async function
                import asyncio
                if asyncio.iscoroutinefunction(self.agent_instance_getter):
                    agent_instance = await self.agent_instance_getter()
                else:
                    agent_instance = self.agent_instance_getter()
            else:
                agent_instance = self.agent_instance_getter
                
            if agent_instance and hasattr(agent_instance, 'tools') and agent_instance.tools:
                for tool in agent_instance.tools:
                    tool_name = getattr(tool, 'name', getattr(tool, '__name__', str(tool)))
                    tool_names.append(tool_name)
        
        return tool_names
    
    async def _reinitialize_agent_with_new_config(self, config_name: str) -> bool:
        """
        Reinitialize the agent with the new configuration.
        This includes updating agent name, description, behavior, and agent card.
        
        Args:
            config_name: The name of the new configuration
            
        Returns:
            bool: True if reinitialization was successful, False otherwise
        """
        try:
            if self.agent_service is None:
                logger.warning("Agent service not available for reinitialization")
                return False
            
            # Get the new configuration details
            new_config = self.config_instance
            if not new_config:
                logger.error("New configuration instance not available")
                return False
            
            # Check if the configuration has agent name and description overrides
            agent_name_override = new_config.config.get("agent_name")
            agent_description_override = new_config.config.get("agent_description")
            
            # Use overrides if available, otherwise use the config name as agent name
            new_agent_name = agent_name_override if agent_name_override else config_name
            new_agent_description = agent_description_override if agent_description_override else f"Agent using {config_name} configuration"
            
            logger.info(f"Reinitializing agent with new name: '{new_agent_name}', description: '{new_agent_description}'")
            
            # Update the agent service with the new name and description
            old_agent_name = self.agent_service.agent_name
            old_agent_description = self.agent_service.agent_description
            
            self.agent_service.agent_name = new_agent_name
            self.agent_service.agent_description = new_agent_description
            
            # Reinitialize the agent with the new configuration
            try:
                # Import here to avoid circular imports
                from agent_template import create_agent
                
                # Create a new agent instance with the new configuration
                new_agent = create_agent(
                    agent_name=new_agent_name,
                    agent_description=new_agent_description
                )
                
                if new_agent is None:
                    logger.error(f"Failed to create new agent with config '{config_name}'")
                    # Restore original settings
                    self.agent_service.agent_name = old_agent_name
                    self.agent_service.agent_description = old_agent_description
                    return False
                
                # Replace the old agent with the new one
                self.agent_service.agent = new_agent
                self.agent_service.initialization_complete = True
                
                # Update our own agent name reference for future operations
                self.agent_name = new_agent_name
                
                # Update the agent card provider if available
                if self.agent_card_provider:
                    try:
                        # Recreate the agent card provider with new name and description
                        from a2a_agent_card import create_a2a_agent_card_provider
                        updated_card_provider = create_a2a_agent_card_provider(new_agent_name, new_agent_description, self.port)
                        # Replace the old provider with the new one
                        self.agent_card_provider = updated_card_provider
                        logger.info(f"✅ Agent card provider updated for '{new_agent_name}'")
                    except Exception as card_error:
                        logger.warning(f"Failed to update agent card provider: {str(card_error)}")
                
                # Update FastAPI app title if available
                if self.fastapi_app:
                    try:
                        self.fastapi_app.title = f"{new_agent_name.replace('_', ' ').title()}"
                        self.fastapi_app.description = new_agent_description
                        logger.info(f"✅ FastAPI app title updated to '{self.fastapi_app.title}'")
                    except Exception as app_error:
                        logger.warning(f"Failed to update FastAPI app title: {str(app_error)}")
                
                logger.info(f"✅ Agent successfully reinitialized with configuration '{config_name}'")
                logger.info(f"   - New agent name: '{new_agent_name}'")
                logger.info(f"   - New agent description: '{new_agent_description}'")
                logger.info(f"   - Tool count: {len(new_agent.tools) if hasattr(new_agent, 'tools') and new_agent.tools else 0}")
                
                return True
                
            except Exception as agent_error:
                logger.error(f"Failed to reinitialize agent: {str(agent_error)}")
                # Restore original settings
                self.agent_service.agent_name = old_agent_name
                self.agent_service.agent_description = old_agent_description
                return False
                
        except Exception as e:
            log_exception_safely(logger, "Error during agent reinitialization", e)
            return False


def add_config_endpoints(app: FastAPI, agent_name: str, port: int,
                        agent_instance_getter=None, service_info_getter=None, 
                        extra_runtime_info: Optional[Dict[str, Any]] = None,
                        agent_service=None):
    """
    Convenience function to add configuration endpoints to a FastAPI app.
    
    Args:
        app: FastAPI application
        agent_name: Name of the agent
        port: Port number the agent runs on
        agent_instance_getter: Callable or object to get agent instance
        service_info_getter: Callable to get service info (for supervisor)
        extra_runtime_info: Additional runtime info to include
        agent_service: Reference to the agent service for reinitialization support
    """
    config_endpoints = AgentConfigEndpoints(agent_name, port, agent_instance_getter, service_info_getter, agent_service)
    config_endpoints.add_endpoints(app)
    
    # Store extra runtime info for later use
    if extra_runtime_info:
        config_endpoints._extra_runtime_info = extra_runtime_info
    
    return config_endpoints
