"""
Elastic observability provider for GenAI-In-A-Box agent.
This module provides an observability provider for Elastic with proper OpenTelemetry initialization.
"""

import logging
import os
import uuid
from typing import Dict, Any
from .base import BaseObservabilityProvider

logger = logging.getLogger(__name__)


class ElasticObservabilityProvider(BaseObservabilityProvider):
    """Observability provider for Elastic."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Elastic observability provider."""
        super().__init__(config)
        self.provider_name = "elastic"
    
    def initialize(self) -> Dict[str, Any]:
        """Initialize the Elastic observability provider and get the trace attributes."""
        try:
            provider_config = self.get_provider_config()
            
            # Get Elastic configuration
            api_key = provider_config.get("api_key", "")
            otlp_endpoint = provider_config.get("otlp_endpoint", "")
            
            logger.debug("Elastic credentials check:")
            logger.debug(f"   API Key: {'Present' if api_key else 'Missing'}")
            logger.debug(f"   OTLP Endpoint: {'Configured' if otlp_endpoint else 'Missing'}")
            
            if not api_key:
                logger.error("Elastic API key (api_key) is required")
                return {}
                
            if not otlp_endpoint:
                logger.error("Elastic OTLP endpoint (otlp_endpoint) is required")
                return {}
            
            # Set up environment variables for Elastic (CRITICAL for Strands integration)
            os.environ["ELASTIC_API_KEY"] = api_key
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp_endpoint
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=ApiKey {api_key}"
            
            logger.info("Elastic environment variables configured successfully")
            
            # CRITICAL: Initialize OpenTelemetry for Elastic
            try:
                self._initialize_opentelemetry(otlp_endpoint, api_key)
                logger.info("OpenTelemetry initialized successfully for Elastic")
            except Exception as otel_error:
                logger.warning(f"OpenTelemetry initialization failed: {otel_error}")
                logger.warning("Traces will not be sent to Elastic")
                # Don't return empty dict - still provide trace attributes for debugging
            
            # Get service name from config or environment
            # Priority: agent_name from config > AGENT_NAME env var > SERVICE_NAME env var > default
            service_name = (
                self.config.get("agent_name") or 
                os.environ.get('AGENT_NAME') or 
                os.environ.get('SERVICE_NAME') or 
                'genai-in-a-box'
            )
            
            # Get service version from config or environment
            service_version = (
                self.config.get("agent_version") or 
                os.environ.get('SERVICE_VERSION') or 
                '1.0.0'
            )
            
            # Get optional dataset routing configuration
            dataset = provider_config.get("dataset", "generic.otel")
            namespace = provider_config.get("namespace", "default")
            
            self.trace_attributes = {
                "session.id": f"{service_name}-session-{uuid.uuid4()}",
                "user.id": f"{service_name}-user",
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": os.environ.get('ENVIRONMENT', 'production'),
                "data_stream.dataset": dataset,
                "data_stream.namespace": namespace
            }
            
            logger.info("Elastic observability provider initialized successfully")
            logger.debug(f"Trace attributes: {self.trace_attributes}")
            return self.trace_attributes
            
        except Exception as e:
            logger.exception("Error initializing Elastic observability provider")
            return {}
    
    def _initialize_opentelemetry(self, otlp_endpoint: str, api_key: str):
        """Initialize OpenTelemetry using common base class method."""
        # Get dataset and namespace from config
        provider_config = self.get_provider_config()
        dataset = provider_config.get("dataset", "generic.otel")
        namespace = provider_config.get("namespace", "default")
        
        # Get service name and version
        service_name = self.config.get("agent_name", "genai-in-a-box")
        service_version = self.config.get("agent_version", "1.0.0")
        
        # Ensure correct endpoint path
        if not otlp_endpoint.endswith('/v1/traces'):
            if otlp_endpoint.endswith('/'):
                otlp_endpoint = otlp_endpoint + 'v1/traces'
            else:
                otlp_endpoint = otlp_endpoint + '/v1/traces'
        
        # Use common initialization with Elastic-specific config
        otlp_config = {
            "endpoint": otlp_endpoint,
            "headers": {"Authorization": f"ApiKey {api_key}"},
            "resource_attributes": {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": os.environ.get('ENVIRONMENT', 'production'),
                "data_stream.dataset": dataset,
                "data_stream.namespace": namespace
            }
        }
        
        logger.debug(f"   Final OTLP traces endpoint: {otlp_endpoint}")
        logger.debug("   Headers: Authorization=ApiKey [REDACTED]")
        
        self._initialize_opentelemetry_common(otlp_config)
    
    def _get_metrics_client_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get Elastic metrics client configuration."""
        provider_config = self.get_provider_config()
        return {
            "type": "elastic_otlp_metrics",
            "api_key": provider_config.get("api_key", ""),
            "otlp_endpoint": provider_config.get("otlp_endpoint", "").replace('/v1/traces', '/v1/metrics'),
            "tags": {"service": service_name, "env": environment}
        }
    
    def _get_log_client_config(self) -> Dict[str, Any]:
        """Get Elastic log client configuration."""
        return {"type": "elastic_otlp_spans"}
    
    def _send_metrics_with_client(self, metrics_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Send metrics using Elastic OTLP - minimal implementation."""
        from opentelemetry import metrics as otel_metrics
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        
        # Create OTLP metric exporter
        exporter = OTLPMetricExporter(
            endpoint=client_config["otlp_endpoint"],
            headers={"Authorization": f"ApiKey {client_config['api_key']}"}
        )
        reader = PeriodicExportingMetricReader(exporter, export_interval_millis=5000)
        meter = MeterProvider(metric_readers=[reader]).get_meter("strands")
        
        # Send metrics
        if metrics_data["tokens"]:
            counter = meter.create_counter("tokens_total")
            counter.add(metrics_data["tokens"]["total"], client_config["tags"])
            print(f"✅ Sent {metrics_data['tokens']['total']} tokens to Elastic")
    
    def _emit_log_with_client(self, log_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Emit log using Elastic OTLP spans - minimal implementation."""
        from opentelemetry import trace
        tracer = trace.get_tracer("strands-logs")
        with tracer.start_as_current_span("strands_log") as span:
            span.set_attribute("log.message", log_data["message"])
            span.set_attribute("log.level", log_data["level"])
    
    def get_strands_tracer_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get configuration for Strands get_tracer() to send traces to Elastic."""
        # CRITICAL: Only return config if this provider is currently active
        if not self._validate_provider_is_active():
            logging.debug(f"Skipping tracer config for inactive {self.provider_name} provider")
            return {}
            
        try:
            provider_config = self.get_provider_config()
            api_key = provider_config.get("api_key", "")
            otlp_endpoint = provider_config.get("otlp_endpoint", "")
            
            # Ensure endpoint is for traces
            if not otlp_endpoint.endswith('/v1/traces'):
                if otlp_endpoint.endswith('/'):
                    otlp_endpoint = otlp_endpoint + 'v1/traces'
                else:
                    otlp_endpoint = otlp_endpoint + '/v1/traces'
            
            # Return Elastic OTLP configuration for Strands tracer
            return {
                "service_name": service_name,
                "otlp_endpoint": otlp_endpoint,
                "headers": {"Authorization": f"ApiKey {api_key}"},
                "enable_console_export": False,
                "resource_attributes": {
                    "service.name": service_name,
                    "service.version": "1.0.0",
                    "deployment.environment": environment,
                    "data_stream.dataset": provider_config.get("dataset", "generic.otel"),
                    "data_stream.namespace": provider_config.get("namespace", "default")
                }
            }
            
        except Exception as e:
            print(f"⚠️ Error getting Strands tracer config for Elastic: {e}")
            return {}
    
    def _cleanup_environment_variables(self):
        """Clean up Elastic-specific environment variables."""
        import os
        elastic_env_vars = [
            "ELASTIC_API_KEY", "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_HEADERS"
        ]
        
        removed_count = 0
        for env_var in elastic_env_vars:
            if env_var in os.environ:
                del os.environ[env_var]
                removed_count += 1
        
        logging.debug(f"Removed {removed_count} Elastic environment variables")
    
    def _provider_specific_cleanup(self):
        """Elastic-specific cleanup for provider transitions."""
        try:
            # Elastic uses standard OpenTelemetry, so minimal specific cleanup needed
            logging.info("Elastic-specific cleanup completed")
            
        except Exception as e:
            logging.warning(f"Error in Elastic-specific cleanup: {e}")
