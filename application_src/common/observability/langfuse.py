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
            
            print(f"🔍 Langfuse provider config: {provider_config}")
            
            # Get Langfuse configuration
            public_key = provider_config.get("public_key", "")
            secret_key = provider_config.get("secret_key", "")
            host = provider_config.get("host", "https://us.cloud.langfuse.com")
            
            # Use secure logging to prevent clear text exposure of sensitive credentials
            secure_logger = SecureLogger()
            print(f"🔑 Langfuse credentials check:")
            print(f"   Public Key: {'✅ Present' if public_key else '❌ Missing'}")
            print(f"   Secret Key: {'✅ Present' if secret_key else '❌ Missing'}")
            print(f"   Host: {secure_logger.hash_sensitive_value(host)}")
            
            if not public_key or not secret_key:
                print("❌ Error: Langfuse public key and secret key are required")
                return {}
            
            # Set up environment variables for Langfuse (CRITICAL for Strands integration)
            os.environ["LANGFUSE_PUBLIC_KEY"] = public_key
            os.environ["LANGFUSE_SECRET_KEY"] = secret_key
            os.environ["LANGFUSE_HOST"] = host
            
            print(f"✅ Langfuse environment variables set:")
            print(f"   LANGFUSE_PUBLIC_KEY: {'✅ Set' if os.environ.get('LANGFUSE_PUBLIC_KEY') else '❌ Not set'}")
            print(f"   LANGFUSE_SECRET_KEY: {'✅ Set' if os.environ.get('LANGFUSE_SECRET_KEY') else '❌ Not set'}")
            # Use secure logging for environment variable values that might contain sensitive info
            secure_logger = SecureLogger()
            print(f"   LANGFUSE_HOST: {secure_logger.hash_sensitive_value(os.environ.get('LANGFUSE_HOST', 'NOT SET'))}")
            
            # CRITICAL: Initialize OpenTelemetry for Langfuse (this was missing!)
            try:
                self._initialize_opentelemetry(public_key, secret_key, host)
                print("🚀 OpenTelemetry initialized successfully for Langfuse")
            except Exception as otel_error:
                print(f"⚠️ OpenTelemetry initialization failed: {otel_error}")
                print("   Traces will not be sent to Langfuse")
                # Don't return empty dict - still provide trace attributes for debugging
            
            # Set up trace attributes with configurable project name
            project_name = os.environ.get('PROJECT_NAME', 'genai-box')
            self.trace_attributes = {
                "session.id": f"{project_name}-session",
                "user.id": f"{project_name}-user",
                "langfuse.tags": [
                    project_name,
                    "Strands-Agent",
                    "Production"
                ]
            }
            
            print(f"✅ Langfuse observability provider initialized successfully")
            print(f"📊 Trace attributes: {self.trace_attributes}")
            return self.trace_attributes
            
        except Exception as e:
            print(f"❌ Error initializing Langfuse observability provider: {str(e)}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _initialize_opentelemetry(self, public_key: str, secret_key: str, host: str):
        """Initialize OpenTelemetry using common base class method."""
        # Build auth header
        auth_string = f"{public_key}:{secret_key}"
        auth_header = base64.b64encode(auth_string.encode()).decode()
        
        # Use common initialization with Langfuse-specific config
        otlp_config = {
            "endpoint": f"{host}/api/public/otel/v1/traces",
            "headers": {"Authorization": f"Basic {auth_header}"},
            "resource_attributes": {
                "service.name": "genai-in-a-box",
                "service.version": "1.0.0",
                "deployment.environment": "production"
            }
        }
        
        print(f"📡 OTLP Endpoint: {otlp_config['endpoint']}")
        print(f"🔑 Auth Header: ✅ Configured")
        
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
            
            return self._build_standard_tracer_config(service_name, environment, endpoint, headers)
            
        except Exception as e:
            print(f"⚠️ Error getting Strands tracer config for Langfuse: {e}")
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
