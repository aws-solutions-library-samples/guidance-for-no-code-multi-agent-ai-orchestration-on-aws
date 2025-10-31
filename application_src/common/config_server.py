"""
Standalone configuration server that runs alongside agents.
Provides configuration endpoints without interfering with the main agent server.
"""

import asyncio
import logging
import uvicorn
from datetime import datetime
from typing import Optional, Dict, Any
from secure_logging_utils import log_exception_safely
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pathlib import Path
import sys
import importlib.util

logger = logging.getLogger(__name__)

class ConfigServer:
    """
    Standalone configuration server that runs on a separate port.
    """
    
    def __init__(self, agent_name: str, config_port: int, agent_port: int, agent_instance_getter=None):
        """
        Initialize configuration server.
        
        Args:
            agent_name: Name of the agent (e.g., 'qa_agent', 'supervisor_agent')
            config_port: Port for the configuration server (e.g., 9101 for agent-1)
            agent_port: Port of the main agent server (e.g., 9001 for agent-1)
            agent_instance_getter: Callable to get the agent instance
        """
        self.agent_name = agent_name
        self.config_port = config_port
        self.agent_port = agent_port
        self.agent_instance_getter = agent_instance_getter
        self.config_instance = None
        self.creation_time = datetime.now()
        self.app = FastAPI(title=f"{agent_name} Configuration API")
        
        # Import Config class
        self._load_config_class()
        
        # Add endpoints
        self._add_endpoints()
    
    def _load_config_class(self):
        """Load the Config class from the common directory."""
        try:
            current_file_dir = Path(__file__).parent
            config_file = current_file_dir / "config.py"
            
            spec = importlib.util.spec_from_file_location("config", config_file)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            self.Config = config_module.Config
            logger.info(f"Successfully loaded Config class for {self.agent_name}")
        except Exception as e:
            logger.error(f"Failed to load Config class: {e}")
            # Fallback - try direct import
            try:
                from config import Config
                self.Config = Config
            except ImportError as ie:
                logger.error(f"Fallback import also failed: {ie}")
                self.Config = None
    
    def _add_endpoints(self):
        """Add configuration endpoints to the FastAPI app."""
        
        @self.app.get("/config/status")
        async def get_agent_config_status():  # nosemgrep: useless-inner-function
            """Get current agent configuration status and runtime details."""
            try:
                if not self.Config:
                    raise Exception("Config class not available")
                
                # Create a fresh config instance to get current SSM values
                if self.config_instance is None:
                    self.config_instance = self.Config(self.agent_name)
                
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
                    "server_port": self.agent_port,
                    "server_host": "0.0.0.0",  # nosec: B104 # Container networking requires binding to all interfaces
                    "config_server_port": self.config_port,
                    "hosted_dns": None,
                    "http_url": "unknown"
                }
                
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
        
        @self.app.get("/config/refresh")
        async def refresh_agent_config():  # nosemgrep: useless-inner-function
            """Force refresh of agent configuration from SSM Parameter Store."""
            try:
                if not self.Config:
                    raise Exception("Config class not available")
                
                self.config_instance = self.Config(self.agent_name)
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
        
        @self.app.get("/config/health")
        async def get_agent_health():  # nosemgrep: useless-inner-function
            """Get basic health status of the agent."""
            try:
                uptime = (datetime.now() - self.creation_time).total_seconds()
                
                # Get agent instance if getter is available
                agent_instance = None
                if self.agent_instance_getter:
                    try:
                        agent_instance = await self.agent_instance_getter() if callable(self.agent_instance_getter) else self.agent_instance_getter
                    except:
                        pass
                
                return {
                    "agent_name": self.agent_name,
                    "status": "healthy",
                    "uptime_seconds": uptime,
                    "server_port": self.agent_port,
                    "config_server_port": self.config_port,
                    "streaming_enabled": getattr(agent_instance, 'streaming', True),
                    "timestamp": datetime.now().isoformat()
                }
                
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
        
        @self.app.get("/")
        async def root():  # nosemgrep: useless-inner-function
            """Root endpoint with service information."""
            return {
                "service": f"{self.agent_name} Configuration API",
                "agent_port": self.agent_port,
                "config_port": self.config_port,
                "endpoints": {
                    "/config/status": "GET - Agent configuration and runtime status",
                    "/config/refresh": "GET - Force refresh configuration from SSM",
                    "/config/health": "GET - Basic health check"
                },
                "timestamp": datetime.now().isoformat()
            }
        
        logger.info(f"✅ Configuration endpoints ready for {self.agent_name}")
    
    async def _get_agent_info(self) -> Dict[str, Any]:
        """Get agent runtime information."""
        agent_instance = None
        if self.agent_instance_getter:
            try:
                agent_instance = await self.agent_instance_getter() if callable(self.agent_instance_getter) else self.agent_instance_getter
            except:
                pass
        
        agent_info = {
            "name": getattr(agent_instance, 'name', self.agent_name) if agent_instance else self.agent_name,
            "description": getattr(agent_instance, 'description', 'Unknown') if agent_instance else f'{self.agent_name} agent',
            "streaming_enabled": getattr(agent_instance, 'streaming', False) if agent_instance else True,
            "tools_count": len(getattr(agent_instance, 'tools', [])) if agent_instance else 0,
            "creation_time": self.creation_time.isoformat(),
            "uptime_seconds": (datetime.now() - self.creation_time).total_seconds()
        }
        
        return agent_info
    
    async def _get_tool_names(self) -> list:
        """Get list of tool names from agent instance."""
        tool_names = []
        
        if self.agent_instance_getter:
            try:
                agent_instance = await self.agent_instance_getter() if callable(self.agent_instance_getter) else self.agent_instance_getter
                
                if agent_instance and hasattr(agent_instance, 'tools') and agent_instance.tools:
                    for tool in agent_instance.tools:
                        tool_name = getattr(tool, 'name', getattr(tool, '__name__', str(tool)))
                        tool_names.append(tool_name)
            except:
                pass
        
        return tool_names
    
    def start(self, background=True):
        """Start the configuration server."""
        if background:
            # Run in background thread
            import threading
            
            def run_server():
                try:
                    # Use configurable host with secure default
                    host = os.environ.get('HOST', '127.0.0.1')
                    uvicorn.run(self.app, host=host, port=self.config_port, log_level="info")
                except Exception as e:
                    logger.error(f"Configuration server failed to start: {e}")
            
            thread = threading.Thread(target=run_server, daemon=True)
            thread.start()
            logger.info(f"🚀 Configuration server started for {self.agent_name} on port {self.config_port}")
        else:
            # Run in main thread (blocking)
            host = os.environ.get('HOST', '127.0.0.1')
            uvicorn.run(self.app, host=host, port=self.config_port, log_level="info")


def start_config_server(agent_name: str, config_port: int, agent_port: int, agent_instance_getter=None):
    """
    Convenience function to start a configuration server.
    
    Args:
        agent_name: Name of the agent
        config_port: Port for configuration server (e.g., 9101, 9102, 9103)
        agent_port: Port of main agent server (e.g., 9001, 9002, 9003)
        agent_instance_getter: Callable to get agent instance
    """
    server = ConfigServer(agent_name, config_port, agent_port, agent_instance_getter)
    server.start(background=True)
    return server
