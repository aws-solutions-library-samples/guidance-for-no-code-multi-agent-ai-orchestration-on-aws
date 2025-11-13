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
            
            # Use secure logging for credentials validation
            logging.info("🔑 Dynatrace configuration validation:")
            self._log_credentials_securely({
                "dt_token": dt_token,
                "otlp_endpoint": otlp_endpoint
            })
            
            # Validate required credentials
            if not self._validate_required_credentials({
                "dt_token": dt_token,
                "otlp_endpoint": otlp_endpoint
            }):
                return {}
            
            # Set up environment variables for Dynatrace (CRITICAL for Strands integration)
            os.environ["DT_TOKEN"] = dt_token
            os.environ["OTLP_ENDPOINT"] = otlp_endpoint
            
            print(f"✅ Dynatrace environment variables set:")
            print(f"   DT_TOKEN: {os.environ.get('DT_TOKEN', 'NOT SET')[:20]}...")
            print(f"   OTLP_ENDPOINT: {os.environ.get('OTLP_ENDPOINT', 'NOT SET')}")
            
            # CRITICAL: Initialize OpenTelemetry for Dynatrace
            try:
                self._initialize_opentelemetry(dt_token, otlp_endpoint)
                print("🚀 OpenTelemetry initialized successfully for Dynatrace")
            except Exception as otel_error:
                print(f"⚠️ OpenTelemetry initialization failed: {otel_error}")
                print("   Traces will not be sent to Dynatrace")
                # Don't return empty dict - still provide trace attributes for debugging
            
            # Generate a unique session ID
            session_id = f"genai-session-{uuid.uuid4()}"
            
            # Set up trace attributes with configurable project name
            project_name = os.environ.get('PROJECT_NAME', 'genai-box')
            self.trace_attributes = {
                "session.id": f"{project_name}-session-{uuid.uuid4()}",
                "user.id": f"{project_name}-user",
                "dynatrace.tags": [
                    project_name,
                    "Strands-Agent",
                    "Production"
                ]
            }
            
            print(f"✅ Dynatrace observability provider initialized successfully")
            print(f"📊 Trace attributes: {self.trace_attributes}")
            return self.trace_attributes
            
        except Exception as e:
            print(f"❌ Error initializing Dynatrace observability provider: {str(e)}")
            import traceback
            traceback.print_exc()
            return {}
    
    def _initialize_opentelemetry(self, dt_token: str, otlp_endpoint: str):
        """Initialize OpenTelemetry using common base class method."""
        # Use common initialization with Dynatrace-specific config
        otlp_config = {
            "endpoint": otlp_endpoint,
            "headers": {"Authorization": f"Api-Token {dt_token}"},
            "resource_attributes": {
                "service.name": "genai-in-a-box",
                "service.version": "1.0.0",
                "deployment.environment": "production"
            }
        }
        
        print(f"📡 OTLP Endpoint: {otlp_endpoint}")
        print(f"🔑 Auth Header: Api-Token {dt_token[:20]}...")
        
        self._initialize_opentelemetry_common(otlp_config)
        
        # Initialize LLMetry after common setup
        self._initialize_llmetry()
    
    def _initialize_llmetry(self):
        """Initialize LLMetry for LLM-specific observability."""
        try:
            from traceloop.sdk import Traceloop
            
            print("🤖 Initializing LLMetry for LLM tracing...")
            
            # Initialize Traceloop (LLMetry) - it will use the existing OpenTelemetry setup
            Traceloop.init(
                app_name="genai-in-a-box",
                disable_batch=False,  # Use batching for better performance
            )
            
            print("🚀 LLMetry initialized successfully - LLM calls will be traced")
            print("📊 LLM-specific metrics: tokens, costs, latency, errors")
            
        except ImportError as import_error:
            print(f"⚠️ LLMetry not available: {import_error}")
            print("   Install with: pip install traceloop-sdk")
            print("   Falling back to basic OpenTelemetry tracing")
        except Exception as llmetry_error:
            print(f"⚠️ LLMetry initialization failed: {llmetry_error}")
            print("   Falling back to basic OpenTelemetry tracing")
            import traceback
            traceback.print_exc()
    
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
            
            # Ensure endpoint is for traces
            if not otlp_endpoint.endswith('/v1/traces'):
                if otlp_endpoint.endswith('/'):
                    otlp_endpoint = otlp_endpoint + 'v1/traces'
                else:
                    otlp_endpoint = otlp_endpoint + '/v1/traces'
            
            # Return Dynatrace OTLP configuration for Strands tracer
            return {
                "service_name": service_name,
                "otlp_endpoint": otlp_endpoint,
                "headers": {"Authorization": f"Api-Token {dt_token}"},
                "enable_console_export": False,
                "resource_attributes": {
                    "service.name": service_name,
                    "service.version": "1.0.0",
                    "deployment.environment": environment,
                    "dt.trace_sampled": "true"
                }
            }
            
        except Exception as e:
            print(f"⚠️ Error getting Strands tracer config for Dynatrace: {e}")
            return {}
    
    def _cleanup_environment_variables(self):
        """Clean up Dynatrace-specific environment variables."""
        import os
        dynatrace_env_vars = [
            "DT_TOKEN", "OTLP_ENDPOINT"
        ]
        
        removed_count = 0
        for env_var in dynatrace_env_vars:
            if env_var in os.environ:
                del os.environ[env_var]
                removed_count += 1
        
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
