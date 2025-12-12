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
        """Initialize the Elastic observability provider using ADOT programmatic activation."""
        try:
            provider_config = self.get_provider_config()
            
            # Get Elastic configuration
            api_key = provider_config.get("api_key", "")
            otlp_endpoint = provider_config.get("otlp_endpoint", "")
            dataset = provider_config.get("dataset", "generic.otel")
            namespace = provider_config.get("namespace", "default")
            
            # Simple credential validation with minimal logging
            if not api_key or not otlp_endpoint:
                logging.error("Elastic api_key and otlp_endpoint required but not provided")
                return {}
            
            logging.info("✅ Elastic credentials validated")
            
            # Prepare ADOT configuration for all 3 pillars (traces, metrics, logs)
            provider_endpoints = {
                "traces": self._normalize_otlp_endpoint(otlp_endpoint, "/v1/traces"),
                "metrics": self._normalize_otlp_endpoint(otlp_endpoint, "/v1/metrics"),
                "logs": self._normalize_otlp_endpoint(otlp_endpoint, "/v1/logs")
            }
            
            auth_headers = {
                "all": f"Authorization=ApiKey {api_key}"
            }
            
            # Elastic-specific resource attributes
            resource_attributes = {
                "data_stream.dataset": dataset,
                "data_stream.namespace": namespace
            }
            
            # Activate ADOT programmatically using DRY base method
            self._initialize_adot_programmatically(provider_endpoints, auth_headers, resource_attributes)
            
            # Use DRY helper to create standard trace attributes with Elastic-specific additions
            self.trace_attributes = self._create_standard_trace_attributes()
            self.trace_attributes.update({
                "data_stream.dataset": dataset,
                "data_stream.namespace": namespace
            })
            
            logging.info("✅ Elastic observability provider initialized with ADOT")
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
    
    # REQUIRED: Minimal implementations to satisfy abstract base class
    # ADOT auto-instrumentation handles everything automatically
    
    def _get_metrics_client_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Auto-instrumentation handles metrics - no manual config needed."""
        return {"type": "auto_instrumentation", "message": "ADOT handles metrics automatically"}
    
    def _get_log_client_config(self) -> Dict[str, Any]:
        """Auto-instrumentation handles logs - no manual config needed."""
        return {"type": "auto_instrumentation", "message": "ADOT handles logs automatically"}
    
    def _send_metrics_with_client(self, metrics_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Auto-instrumentation handles metrics - no manual sending needed."""
        print("📊 ADOT auto-instrumentation handles metrics automatically - no manual processing")
    
    def _emit_log_with_client(self, log_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Auto-instrumentation handles logs - no manual emitting needed."""
        print("📝 ADOT auto-instrumentation handles logs automatically - no manual processing")
    
    def get_auto_instrumentation_status(self) -> Dict[str, Any]:
        """Get the status of ADOT auto-instrumentation for Elastic."""
        return {
            "provider": "elastic",
            "adot_enabled": os.environ.get("OTEL_PYTHON_DISTRO") == "aws_distro",
            "traces_endpoint": os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", ""),
            "metrics_endpoint": os.environ.get("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", ""),
            "logs_endpoint": os.environ.get("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT", ""),
            "auto_logging": os.environ.get("OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED") == "true",
            "message": "✅ ADOT handles all telemetry automatically - no manual intervention required"
        }
    
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
