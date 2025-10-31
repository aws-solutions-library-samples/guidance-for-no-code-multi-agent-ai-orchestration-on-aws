"""
Langfuse observability provider for GenAI-In-A-Box agent.
This module provides an observability provider for Langfuse with proper OpenTelemetry initialization.
"""

import os
import base64
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
        """Initialize OpenTelemetry with OTLP exporter for Langfuse - THE MISSING PIECE!"""
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
            
            # Build auth header
            auth_string = f"{public_key}:{secret_key}"
            auth_header = base64.b64encode(auth_string.encode()).decode()
            
            # Create OTLP exporter with proper headers
            endpoint = f"{host}/api/public/otel/v1/traces"
            headers = {"Authorization": f"Basic {auth_header}"}
            
            print(f"📡 OTLP Endpoint: {endpoint}")
            print(f"🔑 Auth Header: ✅ Configured")
            
            otlp_exporter = OTLPSpanExporter(
                endpoint=endpoint,
                headers=headers
            )
            
            # Add span processor
            span_processor = BatchSpanProcessor(otlp_exporter)
            tracer_provider.add_span_processor(span_processor)
            
            print("✅ OpenTelemetry configured with OTLP exporter for Langfuse")
            
        except ImportError as import_error:
            print(f"❌ Missing OpenTelemetry dependencies: {import_error}")
            print("   Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp")
            raise
        except Exception as setup_error:
            print(f"❌ OpenTelemetry setup failed: {setup_error}")
            import traceback
            traceback.print_exc()
            raise
