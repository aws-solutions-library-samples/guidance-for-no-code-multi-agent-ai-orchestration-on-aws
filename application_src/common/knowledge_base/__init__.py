"""
Knowledge base provider factory for GenAI-In-A-Box agent.
This module provides a factory for creating knowledge base providers.
"""

try:
    from ..config import Config
except ImportError:
    from config import Config
from .base import BaseKnowledgeBaseProvider

# Global variable to store the provider instance
_kb_provider_instance = None
_kb_provider_agent_name = None

class KnowledgeBaseFactory:
    """Factory for creating knowledge base providers."""
    
    @staticmethod
    def create(agent_name="qa_agent"):
        """Create a knowledge base provider based on configuration."""
        global _kb_provider_instance, _kb_provider_agent_name
        
        print(f"DEBUG KB FACTORY CREATE: Called with agent_name: {agent_name}")
        print(f"DEBUG KB FACTORY CREATE: Current _kb_provider_agent_name: {_kb_provider_agent_name}")
        
        # Check if we need to reset the provider instance due to agent name change
        if _kb_provider_instance is not None and _kb_provider_agent_name != agent_name:
            print(f"KB Factory: Agent name changed from {_kb_provider_agent_name} to {agent_name}, resetting instance")
            reset_knowledge_base_provider()
            # Force a new instance to be created
            _kb_provider_instance = None
            _kb_provider_agent_name = agent_name
        
        # Create a config instance with the specified agent_name
        agent_config = Config(agent_name)
        
        # Force refresh to get the latest configuration
        kb_config = agent_config.get_knowledge_base_config()
        
        print(f"DEBUG KB FACTORY: Creating KB provider for agent_name: {agent_name}, config: {kb_config}")
        
        if not kb_config["enabled"]:
            print("Knowledge base is disabled")
            return None
        
        provider = kb_config["provider"].lower()
        provider_type = kb_config.get("knowledge_base_provider_type", "custom").lower()
        
        print(f"KB Factory: Requested provider={provider}, type={provider_type}, agent_name={agent_name}")
        
        # Check if we need to reset the provider instance due to configuration change
        if _kb_provider_instance is not None:
            current_provider = getattr(_kb_provider_instance, 'provider_name', '').lower()
            print(f"KB Factory: Current provider={current_provider}, requested provider={provider}")
            
            if current_provider != provider:
                print(f"KB Factory: Provider changed from {current_provider} to {provider}, resetting instance")
                reset_knowledge_base_provider()
            else:
                print(f"KB Factory: Provider unchanged ({current_provider}), using existing instance")
        else:
            print("KB Factory: No existing provider instance")
        
        # If we already have a provider instance, return it
        if _kb_provider_instance is not None:
            print(f"KB Factory: Using existing knowledge base provider instance: {_kb_provider_instance.provider_name} for agent: {_kb_provider_agent_name}")
            # Double check that we're using the right agent
            if _kb_provider_agent_name != agent_name:
                print(f"WARNING: Provider agent name mismatch! Expected {agent_name}, got {_kb_provider_agent_name}")
                # Force reset and recreate
                reset_knowledge_base_provider()
                # Continue with creation below
            else:
                return _kb_provider_instance
        
        print(f"KB Factory: Initializing knowledge base provider: {provider} with type: {provider_type}")
        print(f"KB Factory: Full KB config: {kb_config}")
        
        # Store the current agent name
        _kb_provider_agent_name = agent_name
        print(f"DEBUG KB FACTORY: Set _kb_provider_agent_name to: {_kb_provider_agent_name}")
        
        # Provider mapping for different knowledge base types
        if provider == "elastic" or provider == "elasticsearch":
            print(f"KB Factory: Creating Elasticsearch provider with type: {provider_type} for agent: {agent_name}")
            _kb_provider_instance = KnowledgeBaseFactory._create_elastic_provider(kb_config, provider_type)
        elif provider == "bedrock knowledge base" or provider == "bedrock_kb":
            print(f"KB Factory: Creating Bedrock Knowledge Base provider with type: {provider_type} for agent: {agent_name}")
            _kb_provider_instance = KnowledgeBaseFactory._create_bedrock_provider(kb_config, provider_type)
        elif provider == "snowflake":
            print(f"KB Factory: Creating Snowflake provider with type: {provider_type} for agent: {agent_name}")
            _kb_provider_instance = KnowledgeBaseFactory._create_snowflake_provider(kb_config, provider_type)
        elif provider == "aurora":
            print(f"KB Factory: Creating Aurora provider with type: {provider_type} for agent: {agent_name}")
            _kb_provider_instance = KnowledgeBaseFactory._create_aurora_provider(kb_config, provider_type)
        else:
            print(f"KB Factory: Unknown knowledge base provider: {provider}")
            return None
        
        if _kb_provider_instance is not None:
            print(f"KB Factory: Successfully created provider instance: {_kb_provider_instance.provider_name}")
        else:
            print(f"KB Factory: Failed to create provider instance for {provider}")
        
        return _kb_provider_instance
    
    @staticmethod
    def _create_elastic_provider(kb_config, provider_type):
        """Create Elasticsearch provider based on type."""
        if provider_type == "custom":
            print("Using custom direct Elasticsearch client")
            from .custom.elastic import ElasticKnowledgeBaseProvider
            return ElasticKnowledgeBaseProvider(kb_config)
        elif provider_type == "mcp":
            print("Using MCP Elasticsearch client")
            from .mcp.elastic import ElasticKnowledgeBaseProvider
            return ElasticKnowledgeBaseProvider(kb_config)
        else:
            print(f"Unknown Elasticsearch provider type: {provider_type}, defaulting to custom")
            from .custom.elastic import ElasticKnowledgeBaseProvider
            return ElasticKnowledgeBaseProvider(kb_config)
    
    @staticmethod
    def _create_bedrock_provider(kb_config, provider_type):
        """Create Bedrock Knowledge Base provider based on type."""
        if provider_type == "custom":
            print("Using custom direct Bedrock Knowledge Base client")
            try:
                from .custom.bedrock_kb import BedrockKnowledgeBaseProvider
                return BedrockKnowledgeBaseProvider(kb_config)
            except ImportError:
                print("Custom Bedrock KB provider not implemented, falling back to default")
                from .bedrock_kb import BedrockKnowledgeBaseProvider
                return BedrockKnowledgeBaseProvider(kb_config)
        elif provider_type == "mcp":
            print("Using MCP Bedrock Knowledge Base client")
            try:
                from .mcp.bedrock_kb import BedrockKnowledgeBaseProvider
                return BedrockKnowledgeBaseProvider(kb_config)
            except ImportError:
                print("MCP Bedrock KB provider not implemented, falling back to default")
                from .bedrock_kb import BedrockKnowledgeBaseProvider
                return BedrockKnowledgeBaseProvider(kb_config)
        else:
            print(f"Unknown Bedrock KB provider type: {provider_type}, using default")
            from .bedrock_kb import BedrockKnowledgeBaseProvider
            return BedrockKnowledgeBaseProvider(kb_config)
    
    @staticmethod
    def _create_snowflake_provider(kb_config, provider_type):
        """Create Snowflake provider based on type."""
        if provider_type == "custom":
            print("Using custom direct Snowflake client")
            try:
                from .custom.snowflake import SnowflakeKnowledgeBaseProvider
                return SnowflakeKnowledgeBaseProvider(kb_config)
            except ImportError:
                print("Custom Snowflake provider not implemented yet")
                return None
        elif provider_type == "mcp":
            print("Using MCP Snowflake client")
            try:
                from .mcp.snowflake import SnowflakeKnowledgeBaseProvider
                return SnowflakeKnowledgeBaseProvider(kb_config)
            except ImportError:
                print("MCP Snowflake provider not implemented yet")
                return None
        else:
            print(f"Unknown Snowflake provider type: {provider_type}")
            return None
    
    @staticmethod
    def _create_aurora_provider(kb_config, provider_type):
        """Create Aurora provider based on type."""
        if provider_type == "custom":
            print("Using custom Aurora PostgreSQL Data API client")
            try:
                from .custom.aurora import AuroraKnowledgeBaseProvider
                return AuroraKnowledgeBaseProvider(kb_config)
            except ImportError:
                print("Custom Aurora provider not implemented yet")
                return None
        elif provider_type == "mcp":
            print("Using MCP Aurora client")
            try:
                from .mcp.aurora import AuroraKnowledgeBaseProvider
                return AuroraKnowledgeBaseProvider(kb_config)
            except ImportError:
                print("MCP Aurora provider not implemented yet")
                return None
        else:
            print(f"Unknown Aurora provider type: {provider_type}")
            return None

def reset_knowledge_base_provider():
    """Reset the knowledge base provider instance to force recreation."""
    global _kb_provider_instance, _kb_provider_agent_name
    print(f"DEBUG KB RESET: Resetting knowledge base provider. Current agent name: {_kb_provider_agent_name}")
    _kb_provider_instance = None
    _kb_provider_agent_name = None
    print("Knowledge base provider instance has been reset")

def get_knowledge_base_tools(agent_name="qa_agent"):
    """Get knowledge base tools for use with Strands Agent."""
    # Create a config instance with the specified agent_name
    agent_config = Config(agent_name)
    
    # Force refresh the configuration to check for changes
    kb_config = agent_config.get_knowledge_base_config()
    
    # Check if the provider has changed since the last time
    global _kb_provider_instance, _kb_provider_agent_name
    if _kb_provider_instance is not None:
        current_provider = getattr(_kb_provider_instance, 'provider_name', '').lower()
        requested_provider = kb_config.get("provider", "").lower()
        
        if current_provider != requested_provider or _kb_provider_agent_name != agent_name:
            print(f"KB Provider changed from {current_provider} to {requested_provider} or agent changed from {_kb_provider_agent_name} to {agent_name}, resetting instance")
            reset_knowledge_base_provider()
    
    # Create or get the knowledge base provider
    kb_provider = KnowledgeBaseFactory.create(agent_name)
    if kb_provider:
        return kb_provider.get_tools()
    return []
