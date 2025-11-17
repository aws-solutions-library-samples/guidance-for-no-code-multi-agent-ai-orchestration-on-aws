"""
Langfuse observability provider for GenAI-In-A-Box agent.
This module provides an observability provider for Langfuse with proper OpenTelemetry initialization.
"""

import os
import base64
import logging
from typing import Dict, Any
from .base import BaseObservabilityProvider
from secure_logging_utils import SecureLogger

class LangfuseObservabilityProvider(BaseObservabilityProvider):
    """Observability provider for Langfuse."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Langfuse observability provider."""
        super().__init__(config)
        self.provider_name = "langfuse"
    
    def initialize(self) -> Dict[str, Any]:
        """Initialize the Langfuse observability provider and get the trace attributes."""
        try:
            provider_config = self.get_provider_config()
            
            logging.debug("🔍 Langfuse provider configuration validation starting")
            
            # Get Langfuse configuration
            public_key = provider_config.get("public_key", "")
            secret_key = provider_config.get("secret_key", "")
            host = provider_config.get("host", "https://us.cloud.langfuse.com")
            
            # Simple credential validation with minimal logging
            if not public_key or not secret_key:
                logging.error("Langfuse public_key and secret_key required but not provided")
                return {}
            
            logging.info("Langfuse credentials validated")
            
            # Set up environment variables for Langfuse (CRITICAL for Strands integration)
            os.environ["LANGFUSE_PUBLIC_KEY"] = public_key
            os.environ["LANGFUSE_SECRET_KEY"] = secret_key
            os.environ["LANGFUSE_HOST"] = host
            
            # Minimal logging - avoid verbose logging around sensitive operations
            logging.info("Langfuse environment variables configured")
            
            # CRITICAL: Initialize OpenTelemetry for Langfuse
            try:
                self._initialize_opentelemetry(public_key, secret_key, host)
                logging.info("🚀 OpenTelemetry initialized successfully for Langfuse")
            except Exception as otel_error:
                from secure_logging_utils import log_exception_safely
                log_exception_safely(logger, "Langfuse OpenTelemetry initialization", otel_error)
                logging.warning("   Traces will not be sent to Langfuse")
                # Don't return empty dict - still provide trace attributes for debugging
            
            # Use DRY helper to create standard trace attributes
            self.trace_attributes = self._create_standard_trace_attributes()
            
            logging.info("✅ Langfuse observability provider initialized successfully")
            logging.debug("📊 Trace attributes configured")
            return self.trace_attributes
            
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Langfuse provider initialization", e)
            return {}
    
    def _initialize_opentelemetry(self, public_key: str, secret_key: str, host: str):
        """Initialize OpenTelemetry using common base class method."""
        # Build auth header (never logged)
        auth_string = f"{public_key}:{secret_key}"
        auth_header = base64.b64encode(auth_string.encode()).decode()
        
        # Build endpoint and log securely (no clear text)
        endpoint = f"{host}/api/public/otel/v1/traces"
        self._log_endpoint_securely("Langfuse OTLP endpoint", endpoint)
        logging.debug("🔑 Auth Header: ✅ Configured (not logged)")
        
        # Use common initialization with Langfuse-specific config
        service_name, service_version = self._get_service_info()
        otlp_config = {
            "endpoint": endpoint,
            "headers": {"Authorization": f"Basic {auth_header}"},
            "resource_attributes": {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": "production"
            }
        }
        
        self._initialize_opentelemetry_common(otlp_config)
    
    def _get_metrics_client_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get Langfuse metrics client configuration."""
        return {
            "type": "langfuse_events",
            "service": service_name,
            "environment": environment
        }
    
    def _get_log_client_config(self) -> Dict[str, Any]:
        """Get Langfuse log client configuration."""
        return {"type": "langfuse_events"}
    
    def _send_metrics_with_client(self, metrics_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Send metrics using Langfuse events - minimal implementation."""
        import langfuse
        client = langfuse.Langfuse()
        
        # Send token metrics
        if metrics_data["tokens"]:
            client.event(name="strands_tokens", metadata={**metrics_data["tokens"], **client_config})
            print(f"✅ Sent {metrics_data['tokens']['total']} tokens to Langfuse")
        
        # Send performance metrics
        if metrics_data["performance"]:
            client.event(name="strands_performance", metadata={**metrics_data["performance"], **client_config})
            print(f"✅ Sent latency to Langfuse: {metrics_data['performance'].get('latency_ms', 0)}ms")
    
    def _emit_log_with_client(self, log_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Emit log using Langfuse events - minimal implementation."""
        import langfuse
        client = langfuse.Langfuse()
        client.event(name="strands_log", metadata=log_data)
    
    def get_strands_tracer_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get configuration for Strands get_tracer() to send traces to Langfuse."""
        # CRITICAL: Only return config if this provider is currently active
        if not self._validate_provider_is_active():
            logging.debug(f"Skipping tracer config for inactive {self.provider_name} provider")
            return {}
            
        try:
            provider_config = self.get_provider_config()
            public_key = provider_config.get("public_key", "")
            secret_key = provider_config.get("secret_key", "")
            host = provider_config.get("host", "https://us.cloud.langfuse.com")
            
            # Build auth header for OTLP using base64 encoding
            auth_string = f"{public_key}:{secret_key}"
            auth_header = base64.b64encode(auth_string.encode()).decode()
            
            # Use DRY helper to build standard tracer config
            endpoint = self._normalize_otlp_endpoint(f"{host}/api/public/otel", "/v1/traces")
            headers = {"Authorization": f"Basic {auth_header}"}
            
            # Log endpoint securely
            self._log_endpoint_securely("Langfuse tracer endpoint", endpoint)
            
            return self._build_standard_tracer_config(service_name, environment, endpoint, headers)
            
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Langfuse tracer config generation", e)
            return {}
    
    def _cleanup_environment_variables(self):
        """Clean up Langfuse-specific environment variables."""
        langfuse_env_vars = [
            "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "PROJECT_NAME"
        ]
        removed_count = self._cleanup_environment_variables_by_list(langfuse_env_vars)
        logging.debug(f"Removed {removed_count} Langfuse environment variables")
    
    def _provider_specific_cleanup(self):
        """Langfuse-specific cleanup for provider transitions."""
        try:
            # Langfuse doesn't have global instrumentation like Datadog's ddtrace
            # But we should clean up any lingering client instances
            try:
                import langfuse
                # Force close any existing client connections
                if hasattr(langfuse, '_client_manager'):
                    langfuse._client_manager.shutdown_all()
                logging.debug("Langfuse client connections closed")
            except (ImportError, AttributeError):
                pass
            
            logging.info("Langfuse-specific cleanup completed")
            
        except Exception as e:
            logging.warning(f"Error in Langfuse-specific cleanup: {e}")
