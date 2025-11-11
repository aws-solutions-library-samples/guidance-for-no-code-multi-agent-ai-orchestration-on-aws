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
        """Initialize OpenTelemetry with OTLP exporter for Elastic."""
        try:
            # Import OpenTelemetry components
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.resources import Resource
            
            logger.debug("OpenTelemetry packages imported successfully")
            
            # Get dataset and namespace from config
            provider_config = self.get_provider_config()
            dataset = provider_config.get("dataset", "generic.otel")
            namespace = provider_config.get("namespace", "default")
            
            # Get service name and version (same logic as trace_attributes)
            service_name = (
                self.config.get("agent_name") or 
                os.environ.get('AGENT_NAME') or 
                os.environ.get('SERVICE_NAME') or 
                'genai-in-a-box'
            )
            service_version = (
                self.config.get("agent_version") or 
                os.environ.get('SERVICE_VERSION') or 
                '1.0.0'
            )
            
            # Create resource with service information
            # Include data stream routing attributes for Elastic
            resource = Resource.create({
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": os.environ.get('ENVIRONMENT', 'production'),
                "data_stream.dataset": dataset,
                "data_stream.namespace": namespace
            })
            
            # Set up tracer provider
            tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(tracer_provider)
            
            logger.debug("TracerProvider configured")
            
            # Create OTLP exporter with Elastic API Key authentication
            headers = {"Authorization": f"ApiKey {api_key}"}
            
            logger.debug(f"Data Stream: traces-{dataset}-{namespace}")
            logger.debug("OTLP Endpoint Configuration:")
            logger.debug(f"   Base endpoint from config: {otlp_endpoint}")
            
            # Ensure the endpoint has the correct OTLP traces path
            # Elastic OTLP endpoint should end with /v1/traces
            if not otlp_endpoint.endswith('/v1/traces'):
                if otlp_endpoint.endswith('/'):
                    otlp_endpoint = otlp_endpoint + 'v1/traces'
                else:
                    otlp_endpoint = otlp_endpoint + '/v1/traces'
            
            logger.debug(f"   Final OTLP traces endpoint: {otlp_endpoint}")
            logger.debug("   Headers: Authorization=ApiKey [REDACTED]")
            
            otlp_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers=headers
            )
            
            logger.debug("OTLP Exporter created successfully")
            logger.debug(f"   Exporter endpoint: {otlp_exporter._endpoint}")
            logger.debug(f"   Exporter will send traces to: {otlp_endpoint}")
            
            # Wrap the exporter to add detailed error logging and resilience
            class ResilientOTLPSpanExporter:
                def __init__(self, wrapped_exporter):
                    self._wrapped = wrapped_exporter
                    self._failed_exports = 0
                    self._max_failures = 5  # Stop trying after 5 consecutive failures
                    
                def export(self, spans):
                    # Skip export if we've had too many failures
                    if self._failed_exports >= self._max_failures:
                        from opentelemetry.sdk.trace.export import SpanExportResult
                        logger.warning(f"OTLP Export Skipped: Too many consecutive failures ({self._failed_exports})")
                        return SpanExportResult.FAILURE
                    
                    try:
                        logger.debug("OTLP Export Debug:")
                        logger.debug(f"   Sending {len(spans)} spans to: {self._wrapped._endpoint}")
                        logger.debug(f"   Request headers: {self._wrapped._headers}")
                        result = self._wrapped.export(spans)
                        logger.debug(f"   Export result: {result}")
                        
                        # Reset failure counter on success
                        if result.name == 'SUCCESS':
                            self._failed_exports = 0
                        else:
                            self._failed_exports += 1
                            logger.warning(f"Export failed, failure count: {self._failed_exports}")
                            
                        return result
                    except Exception as e:
                        self._failed_exports += 1
                        logger.error(f"OTLP Export Error (failure {self._failed_exports}/{self._max_failures}):")
                        logger.error(f"   Error type: {type(e).__name__}")
                        logger.error(f"   Error message: {str(e)}")
                        logger.error(f"   Endpoint attempted: {self._wrapped._endpoint}")
                        
                        # Only log full traceback for first few failures to reduce log spam
                        if self._failed_exports <= 3:
                            logger.exception("OTLP Export Exception details:")
                        
                        # Return failure instead of raising to prevent crash
                        from opentelemetry.sdk.trace.export import SpanExportResult
                        return SpanExportResult.FAILURE
                        
                def shutdown(self):
                    return self._wrapped.shutdown()
                    
                def force_flush(self, timeout_millis: int = 30000):
                    return self._wrapped.force_flush(timeout_millis)
            
            # Wrap the exporter for resilience and debugging
            resilient_exporter = ResilientOTLPSpanExporter(otlp_exporter)
            
            # Add span processor with resilient exporter
            span_processor = BatchSpanProcessor(resilient_exporter)
            tracer_provider.add_span_processor(span_processor)
            
            logger.info("OpenTelemetry configured with OTLP exporter for Elastic")
            
        except ImportError as import_error:
            logger.error(f"Missing OpenTelemetry dependencies: {import_error}")
            logger.error("Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp")
            raise
        except Exception as setup_error:
            logger.exception("OpenTelemetry setup failed")
            raise
