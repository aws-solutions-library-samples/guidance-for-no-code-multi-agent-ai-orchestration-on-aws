"""
Observability provider factory for GenAI-In-A-Box agent.
This module provides a factory for creating observability providers.
"""

from config import Config
from .base import BaseObservabilityProvider
from .langfuse import LangfuseObservabilityProvider
from .dynatrace import DynatraceObservabilityProvider

class ObservabilityFactory:
    """Factory for creating observability providers."""
    
    @staticmethod
    def create(agent_name="qa_agent"):
        """Create an observability provider based on configuration."""
        print(f"🏭 ObservabilityFactory.create() called for agent: {agent_name}")
        
        # Create a config instance with the specified agent_name
        agent_config = Config(agent_name)
        obs_config = agent_config.get_observability_config()
        
        print(f"📋 Observability config for {agent_name}: {obs_config}")
        
        if not obs_config["enabled"]:
            print("❌ Observability is disabled")
            return None
        
        provider = obs_config.get("provider")
        
        if not provider:
            print("❌ No observability provider specified, disabling observability")
            return None
        
        provider = provider.lower()
        print(f"🔧 Creating observability provider: {provider}")
        
        if provider == "langfuse":
            print("✅ Creating Langfuse observability provider")
            return LangfuseObservabilityProvider(obs_config)
        elif provider == "dynatrace":
            print("✅ Creating Dynatrace observability provider")
            return DynatraceObservabilityProvider(obs_config)
        else:
            print(f"❌ Unknown observability provider: {provider}")
            return None

def get_trace_attributes(agent_name="qa_agent"):
    """Get trace attributes for use with Strands Agent."""
    print(f"🔍 Getting trace attributes for agent: {agent_name}...")
    obs_provider = ObservabilityFactory.create(agent_name)
    if obs_provider:
        trace_attrs = obs_provider.get_trace_attributes()
        print(f"✅ Trace attributes retrieved: {trace_attrs}")
        return trace_attrs
    else:
        print("❌ No observability provider available")
        return {}
