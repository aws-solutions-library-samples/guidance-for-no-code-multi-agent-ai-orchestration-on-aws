"""
Simplified service manager following exact Strands documentation pattern.
No complex features - just basic A2A client initialization.
"""
import logging
import asyncio
import httpx
import os
from typing import Optional
from strands import Agent
from strands.models import BedrockModel
# Import both standard and streaming A2A providers for comparison
from strands_tools.a2a_client import A2AClientToolProvider
from botocore.config import Config as BotocoreConfig

from config import CONFIGURATION_API_ENDPOINT, FALLBACK_AGENT_URLS
from health import app_health
from cache import agent_card_cache

# Import shared custom Bedrock provider from common directory
import sys
from pathlib import Path
current_dir = Path(__file__).parent
common_dir_container = Path("/app/common")
common_dir_local = current_dir.parent.parent / "common"
if common_dir_container.exists():
    sys.path.insert(0, str(common_dir_container))
else:
    sys.path.insert(0, str(common_dir_local))

from custom_bedrock_provider import ModelSwitchingBedrockProvider
from ssm_client import ssm  
from common.system_prompt import get_system_prompt
# Import enhanced A2A streaming client for true end-to-end streaming
from a2a_streaming_client import A2AStreamingGeneratorToolProvider

logger = logging.getLogger(__name__)


class SupervisorService:
    """
    Simplified service manager following exact Strands documentation pattern.
    """
    
    def __init__(self):
        self.provider: Optional[A2AClientToolProvider] = None
        self.supervisor_agent: Optional[Agent] = None
        self.http_client: Optional[httpx.AsyncClient] = None
        self._initialization_complete = False
        self._supervisor_config = None
        self._supervisor_system_prompt = None
        self._current_auth_token: Optional[str] = None
    
    def _load_supervisor_config(self, force_refresh=False):
        """Load supervisor configuration from SSM parameters."""
        try:
            # Determine agent name from environment or default
            agent_name = os.environ.get('AGENT_NAME', 'supervisor_agent')
            
            # Load configuration from SSM
            config_param_name = f"/agent/{agent_name}/config"
            self._supervisor_config = ssm.get_json_parameter(
                config_param_name, 
                default={
                    "agent_name": "supervisor_agent",
                    "agent_description": "A supervisor agent that coordinates with other specialized agents",
                    "model_id": "us.anthropic.claude-opus-4-1-20250805-v1:0",
                    "model_ids": [
                        "us.anthropic.claude-opus-4-1-20250805-v1:0",
                        "us.anthropic.claude-sonnet-4-20250514-v1:0",
                        "us.anthropic.claude-opus-4-20250514-v1:0",
                        "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                        "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
                    ],
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "max_tokens": 4000
                },
                force_refresh=force_refresh
            )
            
            # Load system prompt using the common pattern (same as other agents)
            self._supervisor_system_prompt = get_system_prompt(
                streaming=False,
                user_id=None,
                agent_name=agent_name
            )
            
            logger.info(f"✅ Loaded supervisor configuration for agent: {self._supervisor_config.get('agent_name')}")
            logger.info(f"   - Model: {self._supervisor_config.get('model_id')}")
            logger.info(f"   - Available models: {len(self._supervisor_config.get('model_ids', []))}")
            logger.info(f"   - Temperature: {self._supervisor_config.get('temperature')}")
            logger.info(f"   - System prompt length: {len(self._supervisor_system_prompt)} characters")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to load supervisor configuration from SSM: {str(e)}")
            logger.warning("🔄 Using fallback configuration values")
            
            # Fallback configuration
            self._supervisor_config = {
                "agent_name": "supervisor_agent",
                "agent_description": "A supervisor agent that coordinates with other specialized agents",
                "model_id": "us.anthropic.claude-opus-4-1-20250805-v1:0",
                "model_ids": [
                    "us.anthropic.claude-opus-4-1-20250805-v1:0",
                    "us.anthropic.claude-sonnet-4-20250514-v1:0",
                    "us.anthropic.claude-opus-4-20250514-v1:0",
                    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                    "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
                ],
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 4000
            }
            
            self._supervisor_system_prompt = """You are a supervisor agent that coordinates with specialized agents to accomplish complex tasks.

Your role is to:
1. Analyze user requests and break them down into subtasks
2. Identify which specialized agents are best suited for each subtask
3. Coordinate the execution of tasks across multiple agents
4. Synthesize results from different agents into a coherent response
5. Handle any conflicts or inconsistencies between agent responses

Available agents and their capabilities will be determined dynamically through agent discovery.
Always strive to provide comprehensive and accurate responses by leveraging the collective capabilities of all available agents."""
            
            return False
    
    def get_supervisor_config(self):
        """Get current supervisor configuration."""
        if self._supervisor_config is None:
            self._load_supervisor_config()
        return self._supervisor_config
    
    def get_supervisor_system_prompt(self):
        """Get current supervisor system prompt."""
        if self._supervisor_system_prompt is None:
            self._load_supervisor_config()
        return self._supervisor_system_prompt
    
    def refresh_supervisor_config(self):
        """Force refresh supervisor configuration from SSM."""
        logger.info("🔄 Forcing refresh of supervisor configuration from SSM...")
        return self._load_supervisor_config(force_refresh=True)
    
    async def initialize(self):
        """Initialize all service components following Strands documentation."""
        try:
            # Mark as ready FIRST
            app_health.mark_ready()
            logger.info("Application marked as ready for health checks")
            
            # Load supervisor configuration from SSM
            logger.info("🔄 Loading supervisor configuration from SSM...")
            self._load_supervisor_config()
            config = self.get_supervisor_config()
            system_prompt = self.get_supervisor_system_prompt()
            
            # Initialize HTTP clients
            await self._initialize_http_clients()
            
            # Get known agent URLs
            known_agent_urls = await self._get_known_agent_urls()
            logger.info(f"🔍 Known agent URLs: {known_agent_urls}")
            
            # 🌊🔥 STREAMING UPGRADE: Use A2A Streaming Generator Tool Provider for true end-to-end streaming
            # This enables real-time streaming from worker agents to supervisor agent without buffering
            self.provider = A2AStreamingGeneratorToolProvider(known_agent_urls=known_agent_urls)
            logger.info(f"🌊🔥 A2A STREAMING GENERATOR provider initialized with {len(known_agent_urls)} agent URLs")
            logger.info("🚀 REAL-TIME STREAMING: Worker agent responses will now stream directly to supervisor agent")
            
            # Create enhanced custom Bedrock provider with tool execution support
            custom_bedrock_provider = ModelSwitchingBedrockProvider()
            custom_switching_model = custom_bedrock_provider.create_switching_model(
                initial_model_id=config.get('model_id'),
                region='us-east-1',
                max_tokens=config.get('max_tokens', 4000),
                temperature=config.get('temperature', 0.7),
                top_p=config.get('top_p', 0.9)
            )
            
            self.supervisor_agent = Agent(
                name=config.get('agent_name', 'Supervisor Agent'),
                description=config.get('agent_description', 'A supervisor agent that coordinates with other specialized agents'),
                system_prompt=system_prompt,
                tools=self.provider.tools,  # This is the key - use A2A tools directly
                model=custom_switching_model  # Use enhanced custom Bedrock provider with tool execution support
            )
            
            logger.info(f"✅ Supervisor agent using ENHANCED custom Bedrock provider with tool execution: {config.get('model_id')}")
            
            logger.info(f"✅ Supervisor agent initialized with {len(self.provider.tools)} A2A tools")
            for i, tool in enumerate(self.provider.tools):
                tool_name = getattr(tool, 'name', f'tool_{i}')
                logger.info(f"   - Tool {i}: {tool_name}")
            
            self._initialization_complete = True
            logger.info("✅ Service initialization completed following Strands docs pattern")
            
        except Exception as e:
            logger.error(f"❌ Error during service initialization: {str(e)}")
            # Continue anyway - health checks will still work
    
    async def _initialize_http_clients(self):
        """Initialize HTTP clients."""
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            http2=True,
            follow_redirects=True
        )
        logger.info("HTTP clients initialized successfully")
    
    async def _get_known_agent_urls(self, use_authenticated_endpoint: bool = False) -> list:
        """
        Get known agent URLs from discovery endpoint or fallback.
        
        Args:
            use_authenticated_endpoint: If True, use authenticated /discover endpoint
                                      If False, use internal /internal/discover endpoint
        """
        if not CONFIGURATION_API_ENDPOINT:
            logger.warning("CONFIGURATION_API_ENDPOINT not set, using fallback URLs")
            return FALLBACK_AGENT_URLS
        
        try:
            # Choose endpoint based on context
            if use_authenticated_endpoint and hasattr(self, '_current_auth_token') and self._current_auth_token:
                # UI-triggered call with user token - use authenticated endpoint
                discover_url = f"{CONFIGURATION_API_ENDPOINT}/discover"
                headers = {'Authorization': f"Bearer {self._current_auth_token}"}
                logger.debug("Using authenticated /discover endpoint with user token")
            else:
                # Startup or internal call without user token - use internal endpoint  
                discover_url = f"{CONFIGURATION_API_ENDPOINT}/internal/discover"
                headers = {}
                logger.debug("Using internal /internal/discover endpoint (no auth required)")
            
            response = await self.http_client.get(discover_url, timeout=5.0, headers=headers)
            response.raise_for_status()
            
            known_urls = response.json()
            if not isinstance(known_urls, list):
                logger.warning(f"Unexpected discover response format: {type(known_urls)}")
                return FALLBACK_AGENT_URLS
            
            logger.info(f"Retrieved {len(known_urls)} agent URLs: {known_urls}")
            return known_urls
            
        except Exception as e:
            logger.error(f"Failed to get agent URLs from {discover_url}: {str(e)}")
            return FALLBACK_AGENT_URLS
    
    async def refresh_agent_urls(self) -> dict:
        """
        Refresh agent URLs from configuration API and reinitialize A2A provider.
        
        FORCE REFRESH: Always refreshes URLs and clears cache when called explicitly,
        regardless of whether URLs have changed, since agent configurations may have 
        been updated even with the same URLs.
        
        Returns:
            dict: Status information about the refresh operation
        """
        try:
            logger.info("🔄 Starting FORCED agent URLs and cache refresh...")
            
            # Get old URLs for comparison
            old_urls = []
            if self.provider and hasattr(self.provider, '_known_agent_urls'):
                old_urls = list(self.provider._known_agent_urls)
            
            # Get fresh agent URLs from configuration API
            # Use authenticated endpoint since refresh is typically called from UI
            new_agent_urls = await self._get_known_agent_urls(use_authenticated_endpoint=True)
            logger.info(f"🔍 Refreshed agent URLs: {new_agent_urls}")
            
            # Check if URLs actually changed (for reporting purposes)
            urls_changed = set(old_urls) != set(new_agent_urls)
            
            # FORCE REFRESH: Always clear cache and reinitialize regardless of URL changes
            # This ensures agent configurations are refreshed even if URLs are the same
            cache_stats = agent_card_cache.get_stats()
            agent_card_cache.clear()
            logger.info(f"🗑️ FORCED agent card cache clear - {cache_stats['total_entries']} entries removed")
            
            # 🌊🔥 STREAMING UPGRADE: Recreate A2A Streaming Generator Tool Provider with new URLs
            self.provider = A2AStreamingGeneratorToolProvider(known_agent_urls=new_agent_urls)
            logger.info(f"🌊🔥 A2A STREAMING GENERATOR provider FORCE recreated with {len(new_agent_urls)} agent URLs")
            logger.info("🚀 REAL-TIME STREAMING: Updated provider maintains end-to-end streaming capabilities")
            
            # Recreate supervisor agent with new provider using current SSM configuration
            if self.supervisor_agent:
                # Refresh supervisor configuration from SSM
                self.refresh_supervisor_config()
                config = self.get_supervisor_config()
                system_prompt = self.get_supervisor_system_prompt()
                
                custom_bedrock_provider = ModelSwitchingBedrockProvider()
                custom_switching_model = custom_bedrock_provider.create_switching_model(
                    initial_model_id=config.get('model_id'),
                    region='us-east-1',
                    max_tokens=config.get('max_tokens', 4000),
                    temperature=config.get('temperature', 0.7),
                    top_p=config.get('top_p', 0.9)
                )
                
                self.supervisor_agent = Agent(
                    name=config.get('agent_name', 'Supervisor Agent'),
                    description=config.get('agent_description', 'A supervisor agent that coordinates with other specialized agents'),
                    system_prompt=system_prompt,
                    tools=self.provider.tools,
                    model=custom_switching_model
                )
                
                logger.info(f"✅ Supervisor agent FORCE recreated with {len(self.provider.tools)} A2A tools")
                logger.info(f"   - Using model: {config.get('model_id')}")
                logger.info(f"   - Agent name: {config.get('agent_name')}")
            
            return {
                "status": "success",
                "message": "Agent URLs and cache FORCE refreshed successfully",
                "urls_changed": urls_changed,
                "old_urls": old_urls,
                "new_urls": new_agent_urls,
                "total_agents": len(new_agent_urls),
                "cache_cleared": True,
                "cache_entries_cleared": cache_stats['total_entries'],
                "force_refresh": True
            }
                
        except Exception as e:
            logger.error(f"❌ Error refreshing agent URLs: {str(e)}")
            # Raise exception instead of returning error dict to prevent information disclosure
            raise
    
    async def get_agent(self):
        """Get the supervisor agent."""
        return self.supervisor_agent
    
    async def cleanup(self):
        """Cleanup service resources."""
        try:
            if self.http_client:
                await self.http_client.aclose()
            logger.info("Service cleanup completed")
        except Exception as e:
            logger.error(f"Error during service cleanup: {str(e)}")
    
    def get_service_info(self) -> dict:
        """Get service information for the root endpoint."""
        known_agent_list = []
        if self.provider and hasattr(self.provider, '_known_agent_urls'):
            known_agent_list = self.provider._known_agent_urls
        
        return {
            "service": "Agent Supervisor",
            "description": "Supervisor agent that coordinates with other specialized agents",
            "endpoints": {
                "/agent": "POST - Execute the supervisor agent",
                "/agent-streaming": "POST - Stream responses from the supervisor agent",
                "/direct-agent": "POST - Direct agent call with streaming",
                "/refresh-agent-urls": "POST - Refresh agent URLs from configuration API",
                "/health": "GET - Basic health check",
                "/docs": "GET - API documentation"
            },
            "known_agents": known_agent_list,
            "initialization_complete": self._initialization_complete
        }


# Global service instance
supervisor_service = SupervisorService()
