"""
Dynatrace observability provider for GenAI-In-A-Box agent.
This module provides an observability provider for Dynatrace with proper OpenTelemetry initialization.
"""

import os
import uuid
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
            
            print(f"🔍 Dynatrace provider config: {provider_config}")
            
            # Get Dynatrace configuration
            dt_token = provider_config.get("dt_token", "")
            otlp_endpoint = provider_config.get("otlp_endpoint", "")
            
            print(f"🔑 Dynatrace credentials check:")
            print(f"   DT Token: {'✅ Present' if dt_token else '❌ Missing'}")
            print(f"   OTLP Endpoint: {otlp_endpoint if otlp_endpoint else '❌ Missing'}")
            
            if not dt_token:
                print("❌ Error: Dynatrace token (dt_token) is required")
                return {}
                
            if not otlp_endpoint:
                print("❌ Error: Dynatrace OTLP endpoint (otlp_endpoint) is required")
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
        """Initialize OpenTelemetry with OTLP exporter for Dynatrace and LLMetry for LLM tracing."""
        try:
            # Import OpenTelemetry components
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.resources import Resource
            
            print("📦 OpenTelemetry packages imported successfully")
            
            # Create resource with service information
            resource = Resource.create({
                "service.name": "genai-in-a-box",
                "service.version": "1.0.0",
                "deployment.environment": "production"
            })
            
            # Set up tracer provider
            tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(tracer_provider)
            
            print("🔧 TracerProvider configured")
            
            # Create OTLP exporter with Dynatrace API token
            headers = {"Authorization": f"Api-Token {dt_token}"}
            
            print(f"📡 OTLP Endpoint: {otlp_endpoint}")
            print(f"🔑 Auth Header: Api-Token {dt_token[:20]}...")
            
            otlp_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers=headers
            )
            
            # Add span processor
            span_processor = BatchSpanProcessor(otlp_exporter)
            tracer_provider.add_span_processor(span_processor)
            
            print("✅ OpenTelemetry configured with OTLP exporter for Dynatrace")
            
            # Initialize LLMetry for LLM-specific tracing
            self._initialize_llmetry()
            
        except ImportError as import_error:
            print(f"❌ Missing OpenTelemetry dependencies: {import_error}")
            print("   Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp traceloop-sdk")
            raise
        except Exception as setup_error:
            print(f"❌ OpenTelemetry setup failed: {setup_error}")
            import traceback
            traceback.print_exc()
            raise
    
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
