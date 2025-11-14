"""
Dynatrace observability provider for GenAI-In-A-Box agent.
This module provides an observability provider for Dynatrace with proper OpenTelemetry initialization.
"""

import os
import uuid
import logging
from typing import Dict, Any
from .base import BaseObservabilityProvider

class DynatraceObservabilityProvider(BaseObservabilityProvider):
    """Observability provider for Dynatrace."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Dynatrace observability provider."""
        super().__init__(config)
        self.provider_name = "dynatrace"
    
    def initialize(self) -> Dict[str, Any]:
        """Initialize the Dynatrace observability provider and get the trace attributes."""
        try:
            provider_config = self.get_provider_config()
            
            logging.debug("🔍 Dynatrace provider configuration validation starting")
            
            # Get Dynatrace configuration
            dt_token = provider_config.get("dt_token", "")
            otlp_endpoint = provider_config.get("otlp_endpoint", "")
            
            # Simple credential validation with minimal logging
            if not dt_token or not otlp_endpoint:
                logging.error("Dynatrace dt_token and otlp_endpoint required but not provided")
                return {}
            
            logging.info("Dynatrace credentials validated")
            
            # Set up environment variables for Dynatrace (CRITICAL for Strands integration)
            os.environ["DT_TOKEN"] = dt_token
            os.environ["OTLP_ENDPOINT"] = otlp_endpoint
            
            # Log environment variable setup securely
            logging.info("✅ Dynatrace environment variables configured:")
            logging.info("   DT_TOKEN: ✅ Set")
            self._log_endpoint_securely("OTLP_ENDPOINT", otlp_endpoint)
            
            # CRITICAL: Initialize OpenTelemetry for Dynatrace
            try:
                self._initialize_opentelemetry(dt_token, otlp_endpoint)
                logging.info("🚀 OpenTelemetry initialized successfully for Dynatrace")
            except Exception as otel_error:
                from secure_logging_utils import log_exception_safely
                log_exception_safely(logger, "Dynatrace OpenTelemetry initialization", otel_error)
                logging.warning("   Traces will not be sent to Dynatrace")
                # Don't return empty dict - still provide trace attributes for debugging
            
            # Use DRY helper to create standard trace attributes
            self.trace_attributes = self._create_standard_trace_attributes()
            
            logging.info("✅ Dynatrace observability provider initialized successfully")
            logging.debug("📊 Trace attributes configured")
            return self.trace_attributes
            
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Dynatrace provider initialization", e)
            return {}
    
    def _initialize_opentelemetry(self, dt_token: str, otlp_endpoint: str):
        """Initialize OpenTelemetry using common base class method."""
        # Log endpoint securely (no clear text)
        self._log_endpoint_securely("Dynatrace OTLP endpoint", otlp_endpoint)
        logging.debug("🔑 Auth Header: ✅ Configured (not logged)")
        
        # Use common initialization with Dynatrace-specific config
        service_name, service_version = self._get_service_info()
        otlp_config = {
            "endpoint": otlp_endpoint,
            "headers": {"Authorization": f"Api-Token {dt_token}"},
            "resource_attributes": {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": "production"
            }
        }
        
        self._initialize_opentelemetry_common(otlp_config)
        
        # Initialize LLMetry after common setup
        self._initialize_llmetry()
    
    def _initialize_llmetry(self):
        """Initialize LLMetry for LLM-specific observability."""
        try:
            from traceloop.sdk import Traceloop
            
            logging.info("🤖 Initializing LLMetry for LLM tracing...")
            
            # Initialize Traceloop (LLMetry) - it will use the existing OpenTelemetry setup
            Traceloop.init(
                app_name="genai-in-a-box",
                disable_batch=False,  # Use batching for better performance
            )
            
            logging.info("🚀 LLMetry initialized successfully - LLM calls will be traced")
            logging.info("📊 LLM-specific metrics: tokens, costs, latency, errors")
            
        except ImportError as import_error:
            logging.warning(f"⚠️ LLMetry not available: {str(import_error)}")
            logging.info("   Install with: pip install traceloop-sdk")
            logging.info("   Falling back to basic OpenTelemetry tracing")
        except Exception as llmetry_error:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Dynatrace LLMetry initialization", llmetry_error)
            logging.info("   Falling back to basic OpenTelemetry tracing")
    
    def _get_metrics_client_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get Dynatrace metrics client configuration."""
        provider_config = self.get_provider_config()
        return {
            "type": "dynatrace_otlp_metrics",
            "dt_token": provider_config.get("dt_token", ""),
            "otlp_endpoint": provider_config.get("otlp_endpoint", "").replace('/v1/traces', '/v1/metrics'),
            "tags": {"service": service_name, "env": environment}
        }
    
    def _get_log_client_config(self) -> Dict[str, Any]:
        """Get Dynatrace log client configuration."""
        return {"type": "dynatrace_otlp_spans"}
    
    def _send_metrics_with_client(self, metrics_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Send metrics using Dynatrace OTLP - minimal implementation."""
        from opentelemetry import metrics as otel_metrics
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        
        # Create OTLP metric exporter
        exporter = OTLPMetricExporter(
            endpoint=client_config["otlp_endpoint"],
            headers={"Authorization": f"Api-Token {client_config['dt_token']}"}
        )
        reader = PeriodicExportingMetricReader(exporter, export_interval_millis=10000)
        meter = MeterProvider(metric_readers=[reader]).get_meter("strands")
        
        # Send metrics
        if metrics_data["tokens"]:
            counter = meter.create_up_down_counter("strands_tokens")
            counter.add(metrics_data["tokens"]["total"], client_config["tags"])
            print(f"✅ Sent {metrics_data['tokens']['total']} tokens to Dynatrace")
    
    def _emit_log_with_client(self, log_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Emit log using Dynatrace OTLP spans - minimal implementation."""
        from opentelemetry import trace
        tracer = trace.get_tracer("strands-logs")
        with tracer.start_as_current_span("strands_log") as span:
            span.set_attribute("log.message", log_data["message"])
            span.set_attribute("log.level", log_data["level"])
            span.set_attribute("dt.trace_sampled", "true")
    
    def get_strands_tracer_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get configuration for Strands get_tracer() to send traces to Dynatrace."""
        # CRITICAL: Only return config if this provider is currently active
        if not self._validate_provider_is_active():
            logging.debug(f"Skipping tracer config for inactive {self.provider_name} provider")
            return {}
            
        try:
            provider_config = self.get_provider_config()
            dt_token = provider_config.get("dt_token", "")
            otlp_endpoint = provider_config.get("otlp_endpoint", "")
            
            # Use DRY helper to normalize endpoint and build config
            normalized_endpoint = self._normalize_otlp_endpoint(otlp_endpoint, "/v1/traces")
            headers = {"Authorization": f"Api-Token {dt_token}"}
            additional_attributes = {"dt.trace_sampled": "true"}
            
            # Log endpoint securely
            self._log_endpoint_securely("Dynatrace tracer endpoint", normalized_endpoint)
            
            return self._build_standard_tracer_config(service_name, environment, normalized_endpoint, headers, additional_attributes)
            
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Dynatrace tracer config generation", e)
            return {}
    
    def _cleanup_environment_variables(self):
        """Clean up Dynatrace-specific environment variables."""
        dynatrace_env_vars = [
            "DT_TOKEN", "OTLP_ENDPOINT"
        ]
        
        removed_count = self._cleanup_environment_variables_by_list(dynatrace_env_vars)
        logging.debug(f"Removed {removed_count} Dynatrace environment variables")
    
    def _provider_specific_cleanup(self):
        """Dynatrace-specific cleanup for provider transitions."""
        try:
            # Clean up LLMetry/Traceloop if it was enabled
            try:
                from traceloop.sdk import Traceloop
                # Traceloop doesn't have a clean shutdown method, but we can try to disable
                logging.debug("Dynatrace LLMetry cleanup - requires restart for full cleanup")
            except ImportError:
                pass
            
            logging.info("Dynatrace-specific cleanup completed")
            
        except Exception as e:
            logging.warning(f"Error in Dynatrace-specific cleanup: {e}")
