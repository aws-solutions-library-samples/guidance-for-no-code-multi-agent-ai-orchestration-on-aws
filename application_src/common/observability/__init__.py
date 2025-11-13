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
from .datadog import DatadogObservabilityProvider

logger = logging.getLogger(__name__)


class ObservabilityFactory:
    """Factory for creating observability providers with proper transition handling."""
    
    # Supported observability provider mappings
    _SUPPORTED_PROVIDERS = {
        "langfuse": LangfuseObservabilityProvider,
        "dynatrace": DynatraceObservabilityProvider,
        "elastic": ElasticObservabilityProvider,
        "datadog": DatadogObservabilityProvider,
    }
    
    # Track active provider for proper cleanup during transitions
    _active_provider = None
    _active_provider_name = None
    
    @classmethod
    def get_supported_providers(cls) -> list[str]:
        """Get list of supported observability providers."""
        return list(cls._SUPPORTED_PROVIDERS.keys())
    
    @classmethod
    def cleanup_previous_provider(cls):
        """Clean up the previously active provider to prevent conflicts."""
        if cls._active_provider and hasattr(cls._active_provider, 'cleanup'):
            try:
                logger.info(f"Cleaning up previous observability provider: {cls._active_provider_name}")
                cls._active_provider.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up previous provider {cls._active_provider_name}: {e}")
        
        cls._active_provider = None
        cls._active_provider_name = None
    
    @classmethod
    def is_provider_active(cls, provider_name: str) -> bool:
        """Check if a specific provider is currently the active provider."""
        return cls._active_provider_name == provider_name.lower()
    
    @classmethod
    def get_active_provider_name(cls) -> str | None:
        """Get the name of the currently active provider."""
        return cls._active_provider_name
    
    @classmethod
    def force_cleanup_all_providers(cls):
        """Force cleanup of all provider environment variables and global state."""
        logger.info("Forcing cleanup of all observability provider configurations")
        
        # Clean up all known provider environment variables
        import os
        all_provider_env_vars = [
            # Datadog variables
            "DD_API_KEY", "DD_SITE", "DD_ENV", "DD_SERVICE", "DD_VERSION",
            "DD_TRACE_AGENT_URL", "DD_TRACE_API_VERSION", "DD_AGENT_HOST",
            "DD_DOGSTATSD_PORT", "DD_APM_DD_URL", "DD_LLMOBS_INTAKE_URL",
            "DD_LOGS_INJECTION", "DD_LLMOBS_ENABLED", "DD_LLMOBS_ML_APP",
            "DD_LLMOBS_AGENTLESS_ENABLED", "DD_TRACE_TLS_CERT_FILE",
            "DD_TRACE_TLS_CA_CERT", "DD_TRACE_TLS_VERIFY", "DD_LLMOBS_TLS_VERIFY",
            "DD_TRACE_WRITER_BUFFER_SIZE_BYTES", "DD_TRACE_WRITER_MAX_PAYLOAD_SIZE",
            "DD_TRACE_WRITER_INTERVAL_SECONDS", "DATADOG_METRICS_ENABLED",
            "DATADOG_SERVICE_NAME", "DATADOG_ENVIRONMENT",
            
            # Langfuse variables
            "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST",
            
            # Elastic variables
            "ELASTIC_API_KEY", "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_HEADERS",
            
            # Dynatrace variables
            "DT_TOKEN", "OTLP_ENDPOINT",
            
            # Common variables
            "PROJECT_NAME"
        ]
        
        removed_count = 0
        for env_var in all_provider_env_vars:
            if env_var in os.environ:
                del os.environ[env_var]
                removed_count += 1
        
        logger.info(f"Removed {removed_count} provider environment variables")
        
        # Reset OpenTelemetry to clean state
        try:
            from opentelemetry import trace
            trace.set_tracer_provider(trace.NoOpTracerProvider())
            logger.debug("Reset OpenTelemetry tracer provider")
        except ImportError:
            pass
        
        cls._active_provider = None
        cls._active_provider_name = None
    
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
        
        # Check if we're switching providers and need cleanup
        if (ObservabilityFactory._active_provider_name and 
            ObservabilityFactory._active_provider_name != provider):
            logger.info(f"Provider transition detected: {ObservabilityFactory._active_provider_name} → {provider}")
            ObservabilityFactory.cleanup_previous_provider()
        
        logger.info(f"Creating observability provider: {provider}")
        
        provider_class = ObservabilityFactory._SUPPORTED_PROVIDERS.get(provider)
        if provider_class:
            logger.debug(f"Creating {provider.title()} observability provider")
            new_provider = provider_class(obs_config)
            
            # Track the new active provider
            ObservabilityFactory._active_provider = new_provider
            ObservabilityFactory._active_provider_name = provider
            
            return new_provider
        else:
            supported_providers = ", ".join(ObservabilityFactory._SUPPORTED_PROVIDERS.keys())
            logger.error(f"Unknown observability provider: {provider}. Supported providers: {supported_providers}")
            return None


def get_trace_attributes(agent_name="qa_agent"):
    """Get trace attributes for use with Strands Agent - validates current configuration."""
    logger.debug(f"Getting trace attributes for agent: {agent_name}")
    
    # CRITICAL: Always validate against current configuration, not cached provider
    agent_config = Config(agent_name)
    obs_config = agent_config.get_observability_config()
    
    # Strict validation - only proceed if observability is enabled and provider is specified
    if not obs_config.get("enabled", False):
        logger.debug("Observability is disabled in configuration")
        return {}
    
    current_provider = obs_config.get("provider")
    if not current_provider:
        logger.warning("No observability provider specified in current configuration")
        return {}
    
    current_provider = current_provider.lower()
    
    # Additional safeguard: check if cached provider matches current config
    if (ObservabilityFactory._active_provider_name and 
        ObservabilityFactory._active_provider_name != current_provider):
        logger.warning(f"Active provider ({ObservabilityFactory._active_provider_name}) doesn't match current config ({current_provider})")
        ObservabilityFactory.force_cleanup_all_providers()
    
    # Create provider only if configuration is valid and enabled
    obs_provider = ObservabilityFactory.create(agent_name)
    if obs_provider:
        trace_attrs = obs_provider.get_trace_attributes()
        logger.debug(f"Trace attributes retrieved for {current_provider}: {trace_attrs}")
        return trace_attrs
    else:
        logger.warning("No observability provider available")
        return {}
