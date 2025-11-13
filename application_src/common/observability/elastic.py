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
            
            # Simple credential validation with minimal logging
            if not api_key or not otlp_endpoint:
                logging.error("Elastic api_key and otlp_endpoint required but not provided")
                return {}
            
            logging.info("Elastic credentials validated")
            
            # Set up environment variables for Elastic (CRITICAL for Strands integration)
            os.environ["ELASTIC_API_KEY"] = api_key
            os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = otlp_endpoint
            os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=ApiKey {api_key}"
            
            # Log environment variable setup securely
            logging.info("✅ Elastic environment variables configured:")
            logging.info("   ELASTIC_API_KEY: ✅ Set")
            self._log_endpoint_securely("OTEL_EXPORTER_OTLP_ENDPOINT", otlp_endpoint)
            logging.info("   OTEL_EXPORTER_OTLP_HEADERS: ✅ Set")
            
            # CRITICAL: Initialize OpenTelemetry for Elastic
            try:
                self._initialize_opentelemetry(otlp_endpoint, api_key)
                logging.info("🚀 OpenTelemetry initialized successfully for Elastic")
            except Exception as otel_error:
                from secure_logging_utils import log_exception_safely
                log_exception_safely(logger, "Elastic OpenTelemetry initialization", otel_error)
                logging.warning("   Traces will not be sent to Elastic")
                # Don't return empty dict - still provide trace attributes for debugging
            
            # Use DRY helper to create standard trace attributes with Elastic-specific additions
            dataset = provider_config.get("dataset", "generic.otel")
            namespace = provider_config.get("namespace", "default")
            
            self.trace_attributes = self._create_standard_trace_attributes()
            # Add Elastic-specific attributes
            self.trace_attributes.update({
                "data_stream.dataset": dataset,
                "data_stream.namespace": namespace
            })
            
            logging.info("✅ Elastic observability provider initialized successfully")
            logging.debug("📊 Trace attributes configured")
            return self.trace_attributes
            
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Elastic provider initialization", e)
            return {}
    
    def _initialize_opentelemetry(self, otlp_endpoint: str, api_key: str):
        """Initialize OpenTelemetry using common base class method."""
        # Get dataset and namespace from config
        provider_config = self.get_provider_config()
        dataset = provider_config.get("dataset", "generic.otel")
        namespace = provider_config.get("namespace", "default")
        
        # Use DRY helper for service info
        service_name, service_version = self._get_service_info()
        
        # Normalize endpoint and log securely
        normalized_endpoint = self._normalize_otlp_endpoint(otlp_endpoint, '/v1/traces')
        self._log_endpoint_securely("Elastic OTLP endpoint", normalized_endpoint)
        logging.debug("🔑 Auth Header: ✅ Configured (not logged)")
        
        # Use common initialization with Elastic-specific config
        otlp_config = {
            "endpoint": normalized_endpoint,
            "headers": {"Authorization": f"ApiKey {api_key}"},
            "resource_attributes": {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": os.environ.get('ENVIRONMENT', 'production'),
                "data_stream.dataset": dataset,
                "data_stream.namespace": namespace
            }
        }
        
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
            
            # Use DRY helper to normalize endpoint and build config
            normalized_endpoint = self._normalize_otlp_endpoint(otlp_endpoint, "/v1/traces")
            headers = {"Authorization": f"ApiKey {api_key}"}
            additional_attributes = {
                "data_stream.dataset": provider_config.get("dataset", "generic.otel"),
                "data_stream.namespace": provider_config.get("namespace", "default")
            }
            
            # Log endpoint securely
            self._log_endpoint_securely("Elastic tracer endpoint", normalized_endpoint)
            
            return self._build_standard_tracer_config(service_name, environment, normalized_endpoint, headers, additional_attributes)
            
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Elastic tracer config generation", e)
            return {}
    
    def _cleanup_environment_variables(self):
        """Clean up Elastic-specific environment variables."""
        elastic_env_vars = [
            "ELASTIC_API_KEY", "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_HEADERS"
        ]
        
        removed_count = self._cleanup_environment_variables_by_list(elastic_env_vars)
        logging.debug(f"Removed {removed_count} Elastic environment variables")
    
    def _provider_specific_cleanup(self):
        """Elastic-specific cleanup for provider transitions."""
        try:
            # Elastic uses standard OpenTelemetry, so minimal specific cleanup needed
            logging.info("Elastic-specific cleanup completed")
            
        except Exception as e:
            logging.warning(f"Error in Elastic-specific cleanup: {e}")
