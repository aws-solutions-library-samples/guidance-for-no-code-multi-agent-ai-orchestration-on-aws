"""
Configuration loader for GenAI-In-A-Box agent.
This module loads configuration from SSM parameter store.
"""

import json
try:
    from .ssm_client import ssm
except ImportError:
    # Fallback for when running as standalone module
    from ssm_client import ssm

class Config:
    """Configuration loader for GenAI-In-A-Box agent."""
    
    def __init__(self, agent_name="qa_agent"):
        """Initialize the configuration loader."""
        self.agent_name = agent_name
        self.config_path = f"/agent/{agent_name}/config"
        self.config = {}
        self.last_loaded = 0
        self.cache_ttl = 30  # Cache for 30 seconds to reduce SSM calls
        self.load_config()
    
    def load_config(self, force_refresh=False):
        """Load configuration from SSM parameter store with caching."""
        import time
        current_time = time.time()
        
        # Use cached config if still valid and not forcing refresh
        if not force_refresh and (current_time - self.last_loaded) < self.cache_ttl and self.config:
            return
        
        try:
            self.config = ssm.get_json_parameter(self.config_path, {}, force_refresh=force_refresh)
            self.last_loaded = current_time
            # Only log on initialization or forced refresh to reduce log spam
            if force_refresh or not hasattr(self, '_initialized'):
                print(f"CONFIG: Loaded configuration for {self.agent_name}")
                self._initialized = True
        except Exception as e:
            print(f"CONFIG ERROR: Failed to load configuration for {self.agent_name}: {str(e)}")
    
    def get_model_config(self):
        """Get model configuration with environment variable override support."""
        import os
        
        # Reload config to get latest changes
        self.load_config(force_refresh=True)
        
        # Environment variables take precedence over SSM parameters
        # This allows for flexible deployment scenarios:
        # 1. Local development: docker-compose.yml sets environment variables
        # 2. ECS deployment: CDK stack injects environment variables from config files
        # 3. UI agent creation: Configuration API sets environment variables
        
        model_id = (
            os.environ.get(f"{self.agent_name.upper()}_MODEL_ID") or  # Agent-specific env var
            os.environ.get("MODEL_ID") or  # Global env var
            self.config.get("model_id", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")  # SSM fallback
        )
        
        judge_model_id = (
            os.environ.get(f"{self.agent_name.upper()}_JUDGE_MODEL_ID") or  # Agent-specific env var
            os.environ.get("JUDGE_MODEL_ID") or  # Global env var
            self.config.get("judge_model_id", "")  # SSM fallback
        )
        
        embedding_model_id = (
            os.environ.get(f"{self.agent_name.upper()}_EMBEDDING_MODEL_ID") or  # Agent-specific env var
            os.environ.get("EMBEDDING_MODEL_ID") or  # Global env var
            self.config.get("embedding_model_id", "amazon.titan-embed-text-v2:0")  # SSM fallback
        )
        
        temperature = float(
            os.environ.get(f"{self.agent_name.upper()}_TEMPERATURE") or
            os.environ.get("TEMPERATURE") or
            str(self.config.get("temperature", 0.3))
        )
        
        top_p = float(
            os.environ.get(f"{self.agent_name.upper()}_TOP_P") or
            os.environ.get("TOP_P") or
            str(self.config.get("top_p", 0.8))
        )
        
        streaming_env = (
            os.environ.get(f"{self.agent_name.upper()}_STREAMING") or
            os.environ.get("STREAMING") or
            str(self.config.get("streaming", "True"))
        )
        streaming = streaming_env.lower() in ["true", "yes", "1"]
        
        print(f"CONFIG: Model configuration for {self.agent_name}:")
        print(f"  - model_id: {model_id} {'(from env)' if os.environ.get(f'{self.agent_name.upper()}_MODEL_ID') or os.environ.get('MODEL_ID') else '(from SSM)'}")
        print(f"  - judge_model_id: {judge_model_id}")
        print(f"  - embedding_model_id: {embedding_model_id}")
        print(f"  - temperature: {temperature}")
        print(f"  - top_p: {top_p}")
        print(f"  - streaming: {streaming}")
        
        return {
            "model_id": model_id,
            "judge_model_id": judge_model_id,
            "temperature": temperature,
            "top_p": top_p,
            "streaming": streaming,
            "embedding_model_id": embedding_model_id
        }
    
    def get_memory_config(self):
        """Get memory configuration."""
        # Reload config to get latest changes
        self.load_config(force_refresh=True)
        return {
            "enabled": self.config.get("memory", "True") == "True",
            "provider": self.config.get("memory_provider", "mem0"),
            "provider_details": self.config.get("memory_provider_details", [])
        }
    
    def get_knowledge_base_config(self):
        """Get knowledge base configuration."""
        # Reload config to get latest changes
        self.load_config(force_refresh=True)
        kb_config = {
            "enabled": self.config.get("knowledge_base", "True") == "True",
            "provider": self.config.get("knowledge_base_provider", "Elastic"),
            "knowledge_base_provider_type": self.config.get("knowledge_base_provider_type", "custom"),
            "provider_details": self.config.get("knowledge_base_details", [])
        }
        # Only log on force refresh to reduce spam
        if hasattr(self, '_kb_logged') and not self._kb_logged:
            print(f"CONFIG: Knowledge base configured for {self.agent_name} with provider: {kb_config['provider']}")
            self._kb_logged = True
        return kb_config
    
    def get_observability_config(self):
        """Get observability configuration."""
        # Reload config to get latest changes
        self.load_config(force_refresh=True)
        
        # Check if observability is enabled (Yes/True) or disabled (No/False or any other value)
        observability_value = str(self.config.get("observability", "No")).lower()
        is_enabled = observability_value in ["yes", "true"]
        
        # Get the provider name, defaulting to None if not specified
        provider = self.config.get("observability_provider", None)
        
        print(f"Observability config: value='{observability_value}', enabled={is_enabled}, provider='{provider}'")
        
        # If observability is enabled but no provider is specified, disable it
        if is_enabled and not provider:
            print("Warning: Observability is enabled but no provider is specified. Disabling observability.")
            is_enabled = False
        
        return {
            "enabled": is_enabled,
            "provider": provider,
            "provider_details": self.config.get("observability_provider_details", [])
        }
    
    def get_guardrail_config(self):
        """Get guardrail configuration."""
        # Reload config to get latest changes
        self.load_config(force_refresh=True)
        return {
            "enabled": self.config.get("guardrail", "No") == "Yes",
            "provider": self.config.get("guardrail_provider", "Bedrock GuardRails"),
            "provider_details": self.config.get("guardrail_provider_details", [])
        }
    
    def get_tools_config(self):
        """Get tools configuration."""
        # Reload config to get latest changes
        self.load_config(force_refresh=True)
        return {
            "tools": self.config.get("tools", [])
        }
    
    def get_mcp_config(self):
        """Get MCP configuration."""
        # Reload config to get latest changes
        self.load_config(force_refresh=True)
        return {
            "mcp_enabled": self.config.get("mcp_enabled", False),
            "mcp_servers": self.config.get("mcp_servers", ""),
            "mcp_discovery_timeout": self.config.get("mcp_discovery_timeout", 10),
            "mcp_request_timeout": self.config.get("mcp_request_timeout", 30),
            "mcp_retry_attempts": self.config.get("mcp_retry_attempts", 3),
            "mcp_cache_ttl": self.config.get("mcp_cache_ttl", 5)
        }
    
    def get_system_prompt_name(self):
        """Get system prompt name."""
        # Reload config to get latest changes
        self.load_config(force_refresh=True)
        return self.config.get("system_prompt_name", "ElasticsearchSystemPrompt")

# No singleton instance - each agent should create its own Config instance
# with the appropriate agent_name parameter
