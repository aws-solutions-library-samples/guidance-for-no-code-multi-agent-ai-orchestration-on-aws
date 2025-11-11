"""
Observability provider factory for GenAI-In-A-Box agent.
This module provides a factory for creating observability providers.
"""

import logging

from config import Config
from .base import BaseObservabilityProvider
from .langfuse import LangfuseObservabilityProvider
from .dynatrace import DynatraceObservabilityProvider
from .elastic import ElasticObservabilityProvider

logger = logging.getLogger(__name__)


class ObservabilityFactory:
    """Factory for creating observability providers."""
    
    @staticmethod
    def create(agent_name="qa_agent"):
        """Create an observability provider based on configuration."""
        logger.debug(f"ObservabilityFactory.create() called for agent: {agent_name}")
        
        # Create a config instance with the specified agent_name
        agent_config = Config(agent_name)
        obs_config = agent_config.get_observability_config()
        
        logger.debug(f"Observability config for {agent_name}: enabled={obs_config.get('enabled')}, provider={obs_config.get('provider')}")
        
        if not obs_config["enabled"]:
            logger.info("Observability is disabled")
            return None
        
        provider = obs_config.get("provider")
        
        if not provider:
            logger.warning("No observability provider specified, disabling observability")
            return None
        
        provider = provider.lower()
        logger.info(f"Creating observability provider: {provider}")
        
        if provider == "langfuse":
            logger.debug("Creating Langfuse observability provider")
            return LangfuseObservabilityProvider(obs_config)
        elif provider == "dynatrace":
            logger.debug("Creating Dynatrace observability provider")
            return DynatraceObservabilityProvider(obs_config)
        elif provider == "elastic":
            logger.debug("Creating Elastic observability provider")
            return ElasticObservabilityProvider(obs_config)
        else:
            logger.error(f"Unknown observability provider: {provider}")
            return None


def get_trace_attributes(agent_name="qa_agent"):
    """Get trace attributes for use with Strands Agent."""
    logger.debug(f"Getting trace attributes for agent: {agent_name}")
    obs_provider = ObservabilityFactory.create(agent_name)
    if obs_provider:
        trace_attrs = obs_provider.get_trace_attributes()
        logger.debug(f"Trace attributes retrieved: {trace_attrs}")
        return trace_attrs
    else:
        logger.warning("No observability provider available")
        return {}
