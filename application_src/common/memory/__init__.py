"""
Memory provider factory for GenAI-In-A-Box agent.
This module provides a factory for creating memory providers.
"""

try:
    from ..config import Config
except ImportError:
    from config import Config
from .base import BaseMemoryProvider
from .mem0 import Mem0MemoryProvider
from .opensearch import OpenSearchMemoryProvider
from .bedrock_agentcore import BedrockAgentCoreMemoryProvider

class MemoryFactory:
    """Factory for creating memory providers."""
    
    @staticmethod
    def create(agent_name="qa_agent"):
        """Create a memory provider based on configuration."""
        # Create a config instance with the specified agent_name
        agent_config = Config(agent_name)
        
        memory_config = agent_config.get_memory_config()
        
        if not memory_config["enabled"]:
            print("Memory is disabled")
            return None
        
        provider = memory_config["provider"].lower()
        
        if provider == "mem0":
            return Mem0MemoryProvider(memory_config)
        elif provider == "opensearch":
            return OpenSearchMemoryProvider(memory_config)
        elif provider == "bedrock_agentcore":
            return BedrockAgentCoreMemoryProvider(memory_config)
        else:
            print(f"Unknown memory provider: {provider}")
            return None

def get_memory_tools(agent_name="qa_agent"):
    """Get memory tools for use with Strands Agent."""
    memory_provider = MemoryFactory.create(agent_name)
    if memory_provider:
        return memory_provider.get_tools()
    return []
