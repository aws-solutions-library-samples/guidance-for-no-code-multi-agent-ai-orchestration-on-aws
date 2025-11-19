"""
Base observability provider for GenAI-In-A-Box agent.
This module provides a base class for observability providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
import logging
import os
from secure_logging_utils import SecureLogger

class BaseObservabilityProvider(ABC):
    """Base class for observability providers with common Strands SDK integration."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the observability provider."""
        self.config = config
        self.provider_name = config.get("provider", "").lower()
        self.provider_details = config.get("provider_details", [])
        self.trace_attributes = {}
    
    def _validate_provider_is_active(self) -> bool:
        """Validate that this provider is currently the active provider."""
        # Import here to avoid circular imports
        from . import ObservabilityFactory
        
        if not ObservabilityFactory.is_provider_active(self.provider_name):
            logging.warning(f"{self.provider_name} provider attempting to operate but is not active. Current active: {ObservabilityFactory.get_active_provider_name()}")
            return False
        return True
    
    def _validate_active_or_skip(func):
        """Decorator to validate provider is active before execution."""
        def wrapper(self, *args, **kwargs):
            if not self._validate_provider_is_active():
                logging.debug(f"Skipping {func.__name__} for inactive {self.provider_name} provider")
                return {} if func.__name__.startswith('get_') else None
            return func(self, *args, **kwargs)
        return wrapper
    
    def _get_service_info(self) -> tuple[str, str]:
        """Common service name and version resolution logic."""
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
        
        return service_name, service_version
    
    def _normalize_otlp_endpoint(self, endpoint: str, path: str = '/v1/traces') -> str:
        """Normalize OTLP endpoint to ensure correct path."""
        if not endpoint.endswith(path):
            if endpoint.endswith('/'):
                endpoint = endpoint + path.lstrip('/')
            else:
                endpoint = endpoint + path
        return endpoint
    
    def _cleanup_environment_variables_by_list(self, env_var_list: list[str]) -> int:
        """Common environment variable cleanup logic."""
        import os
        removed_count = 0
        for env_var in env_var_list:
            if env_var in os.environ:
                del os.environ[env_var]
                removed_count += 1
        return removed_count
    
    def _validate_credentials_safely(self, credentials: list[tuple[str, Any]]) -> bool:
        """Validate credentials are present with minimal logging to avoid security risks."""
        missing_creds = []
        
        # Simple validation - no verbose logging around sensitive operations
        for cred_name, cred_value in credentials:
            if not cred_value:
                missing_creds.append(cred_name)
        
        if missing_creds:
            logging.error(f"Missing required {self.provider_name} credentials: {', '.join(missing_creds)}")
            return False
        
        logging.info(f"✅ {self.provider_name} credentials validated")
        return True
    
    @abstractmethod
    def initialize(self) -> Dict[str, Any]:
        """Initialize the observability provider and get the trace attributes."""
        pass
    
    def process_strands_metrics(self, agent_result, service_name: str, environment: str):
        """
        Process metrics from Strands AgentResult using common extraction + provider-specific sending.
        
        Args:
            agent_result: The AgentResult object returned by Strands Agent
            service_name: Service name for tagging/identification
            environment: Environment name for tagging/identification
        """
        # CRITICAL: Only process if this provider is currently active
        if not self._validate_provider_is_active():
            logging.debug(f"Skipping metrics processing for inactive {self.provider_name} provider")
            return
            
        try:
            if not hasattr(agent_result, 'metrics'):
                print("ℹ️ No metrics found in AgentResult")
                return
            
            print(f"📊 Processing Strands metrics for {self.provider_name}...")
            
            # Extract metrics using common logic
            metrics_data = self._extract_strands_metrics(agent_result.metrics, service_name, environment)
            
            # Send using provider-specific implementation
            self._send_metrics(metrics_data, service_name, environment)
            
            print(f"🎯 Strands metrics successfully forwarded to {self.provider_name}!")
            
        except Exception as e:
            print(f"⚠️ Error processing Strands metrics for {self.provider_name}: {e}")
            import traceback
            traceback.print_exc()
    
    def configure_strands_logging(self, service_name: str, environment: str):
        """Configure Strands SDK logging using common handler + provider-specific emission."""
        # CRITICAL: Only configure if this provider is currently active
        if not self._validate_provider_is_active():
            logging.debug(f"Skipping logging configuration for inactive {self.provider_name} provider")
            return
            
        try:
            print(f"📝 Configuring Strands SDK logging for {self.provider_name}...")
            
            # Create common handler with provider-specific emission
            handler = self._create_strands_log_handler(service_name, environment)
            
            # Add handler to Strands root logger
            strands_logger = logging.getLogger("strands")
            strands_logger.addHandler(handler)
            strands_logger.setLevel(logging.INFO)
            
            print(f"✅ Strands SDK logging configured for {self.provider_name}")
            
        except Exception as e:
            print(f"⚠️ Error configuring Strands logging for {self.provider_name}: {e}")
    
    @abstractmethod
    def get_strands_tracer_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get configuration for Strands get_tracer() - provider-specific."""
        pass
    
    def _build_standard_tracer_config(self, service_name: str, environment: str, 
                                     endpoint: str, headers: dict[str, str],
                                     additional_attributes: dict[str, Any] = None) -> dict[str, Any]:
        """Build standard tracer configuration with common patterns."""
        service_name, service_version = self._get_service_info()
        
        base_config = {
            "service_name": service_name,
            "otlp_endpoint": endpoint,
            "headers": headers,
            "enable_console_export": False,
            "resource_attributes": {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": environment
            }
        }
        
        # Add provider-specific attributes
        if additional_attributes:
            base_config["resource_attributes"].update(additional_attributes)
            
        return base_config
    
    def _create_standard_trace_attributes(self, additional_tags: list[str] = None) -> dict[str, Any]:
        """Create standard trace attributes with common patterns."""
        import uuid
        service_name, service_version = self._get_service_info()
        project_name = os.environ.get('PROJECT_NAME', 'genai-box')
        
        base_attributes = {
            "session.id": f"{service_name}-session-{uuid.uuid4()}",
            "user.id": f"{service_name}-user",
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment": os.environ.get('ENVIRONMENT', 'production')
        }
        
        # Add provider-specific tags
        if additional_tags:
            base_attributes[f"{self.provider_name}.tags"] = [
                project_name, "Strands-Agent", "Production"
            ] + additional_tags
        
        return base_attributes
    
    # Common helper methods (DRY principle)
    def _extract_strands_metrics(self, metrics, service_name: str, environment: str) -> Dict[str, Any]:
        """Extract metrics data from Strands metrics object - common logic."""
        metrics_data = {
            "service_name": service_name,
            "environment": environment,
            "tokens": {},
            "performance": {},
            "cycles": {},
            "tools": {}
        }
        
        # Extract token usage metrics
        if hasattr(metrics, 'accumulated_usage'):
            usage = metrics.accumulated_usage
            metrics_data["tokens"] = {
                "input": usage.get('inputTokens', 0),
                "output": usage.get('outputTokens', 0),
                "total": usage.get('totalTokens', 0)
            }
        
        # Extract performance metrics
        if hasattr(metrics, 'accumulated_metrics'):
            perf = metrics.accumulated_metrics
            if 'latencyMs' in perf:
                metrics_data["performance"]["latency_ms"] = perf['latencyMs']
        
        # Extract cycle metrics
        if hasattr(metrics, 'cycle_count'):
            metrics_data["cycles"]["count"] = metrics.cycle_count
            
        if hasattr(metrics, 'cycle_durations') and metrics.cycle_durations:
            metrics_data["cycles"]["total_duration"] = sum(metrics.cycle_durations)
            metrics_data["cycles"]["average_duration"] = sum(metrics.cycle_durations) / len(metrics.cycle_durations)
        
        # Extract tool metrics
        if hasattr(metrics, 'tool_metrics'):
            for tool_name, tool_metrics in metrics.tool_metrics.items():
                success_rate = tool_metrics.success_count / max(tool_metrics.call_count, 1)
                metrics_data["tools"][tool_name] = {
                    "call_count": tool_metrics.call_count,
                    "success_count": tool_metrics.success_count,
                    "error_count": tool_metrics.error_count,
                    "total_time": tool_metrics.total_time,
                    "success_rate": success_rate
                }
        
        return metrics_data
    
    def _create_strands_log_handler(self, service_name: str, environment: str):
        """Create common Strands log handler with provider-specific emission."""
        class StrandsLogHandler(logging.Handler):
            def __init__(self, provider_instance, service_name, environment):
                super().__init__()
                self.provider = provider_instance
                self.service_name = service_name
                self.environment = environment
                self.setLevel(logging.INFO)
            
            def emit(self, record):
                try:
                    # CRITICAL: Validate provider is still active before emitting logs
                    if not self.provider._validate_provider_is_active():
                        return  # Silently skip if provider is no longer active
                        
                    if record.name.startswith('strands'):
                        log_data = {
                            "message": self.format(record),
                            "level": record.levelname,
                            "logger": record.name,
                            "service": self.service_name,
                            "environment": self.environment
                        }
                        # Delegate to provider-specific implementation
                        self.provider._emit_log(log_data)
                except:
                    pass
        
        return StrandsLogHandler(self, service_name, environment)
    
    def _send_metrics(self, metrics_data: Dict[str, Any], service_name: str, environment: str):
        """Send extracted metrics data using common pattern + provider config."""
        try:
            client_config = self._get_metrics_client_config(service_name, environment)
            if not client_config:
                print(f"⚠️ No metrics client config for {self.provider_name}")
                return
                
            # Use provider-specific client to send metrics
            self._send_metrics_with_client(metrics_data, client_config)
            
        except Exception as e:
            print(f"⚠️ Error sending metrics to {self.provider_name}: {e}")
    
    def _emit_log(self, log_data: Dict[str, Any]):
        """Emit log data using common pattern + provider config."""
        try:
            client_config = self._get_log_client_config()
            if not client_config:
                print(f"⚠️ No log client config for {self.provider_name}")
                return
                
            # Use provider-specific client to emit log
            self._emit_log_with_client(log_data, client_config)
            
        except Exception as e:
            print(f"⚠️ Error emitting log to {self.provider_name}: {e}")
    
    @abstractmethod
    def _get_metrics_client_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get metrics client configuration - provider defines connection details only."""
        pass
    
    @abstractmethod 
    def _get_log_client_config(self) -> Dict[str, Any]:
        """Get log client configuration - provider defines connection details only."""
        pass
    
    @abstractmethod
    def _send_metrics_with_client(self, metrics_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Send metrics using provider-specific client - minimal implementation required."""
        pass
    
    @abstractmethod
    def _emit_log_with_client(self, log_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Emit log using provider-specific client - minimal implementation required."""
        pass
    
    def get_trace_attributes(self) -> Dict[str, Any]:
        """Get the trace attributes only if this provider is currently active."""
        # CRITICAL: Only return trace attributes if this provider is currently active
        if not self._validate_provider_is_active():
            logging.debug(f"Skipping trace attributes for inactive {self.provider_name} provider")
            return {}
            
        if not self.trace_attributes:
            return self.initialize()
        return self.trace_attributes
    
    def _initialize_opentelemetry_common(self, otlp_config: Dict[str, Any]):
        """Common OpenTelemetry initialization - eliminates duplication across providers."""
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            from opentelemetry.sdk.resources import Resource
            
            print("📦 OpenTelemetry packages imported successfully")
            
            # Create resource with service information
            resource = Resource.create(otlp_config.get("resource_attributes", {}))
            
            # Set up tracer provider
            tracer_provider = TracerProvider(resource=resource)
            trace.set_tracer_provider(tracer_provider)
            
            print("🔧 TracerProvider configured")
            
            # Create OTLP exporter with provider-specific config
            otlp_exporter = OTLPSpanExporter(
                endpoint=otlp_config["endpoint"],
                headers=otlp_config.get("headers", {})
            )
            
            # Add span processor
            span_processor = BatchSpanProcessor(otlp_exporter)
            tracer_provider.add_span_processor(span_processor)
            
            print(f"✅ OpenTelemetry configured for {self.provider_name}")
            
        except ImportError as import_error:
            print(f"❌ Missing OpenTelemetry dependencies: {import_error}")
            print("   Install with: pip install opentelemetry-api opentelemetry-sdk opentelemetry-exporter-otlp")
            raise
        except Exception as setup_error:
            print(f"❌ OpenTelemetry setup failed for {self.provider_name}: {setup_error}")
            import traceback
            traceback.print_exc()
            raise
    
    def cleanup(self):
        """Clean up the observability provider to prevent conflicts during transitions."""
        try:
            logging.info(f"Cleaning up {self.provider_name} observability provider")
            
            # Clean up environment variables specific to this provider
            self._cleanup_environment_variables()
            
            # Clean up OpenTelemetry configuration
            self._cleanup_opentelemetry()
            
            # Clean up logging handlers
            self._cleanup_logging()
            
            # Provider-specific cleanup
            self._provider_specific_cleanup()
            
            logging.info(f"✅ Cleaned up {self.provider_name} observability provider")
            
        except Exception as e:
            logging.warning(f"Error during {self.provider_name} cleanup: {e}")
    
    def _cleanup_environment_variables(self):
        """Clean up provider-specific environment variables."""
        # Override in subclasses to clean specific env vars
        pass
    
    def _cleanup_opentelemetry(self):
        """Clean up OpenTelemetry global state."""
        try:
            from opentelemetry import trace
            # Reset tracer provider to default
            trace.set_tracer_provider(trace.NoOpTracerProvider())
            logging.debug("OpenTelemetry tracer provider reset")
        except ImportError:
            pass  # OpenTelemetry not installed
        except Exception as e:
            logging.debug(f"Error resetting OpenTelemetry: {e}")
    
    def _cleanup_logging(self):
        """Clean up logging handlers that this provider added."""
        try:
            # Remove handlers from Strands logger that this provider added
            strands_logger = logging.getLogger("strands")
            handlers_to_remove = []
            
            for handler in strands_logger.handlers:
                # Check if this handler belongs to our provider
                if hasattr(handler, 'provider') and handler.provider == self:
                    handlers_to_remove.append(handler)
            
            for handler in handlers_to_remove:
                strands_logger.removeHandler(handler)
                handler.close()
            
            logging.debug(f"Removed {len(handlers_to_remove)} logging handlers")
            
        except Exception as e:
            logging.debug(f"Error cleaning up logging handlers: {e}")
    
    def _provider_specific_cleanup(self):
        """Override in subclasses for provider-specific cleanup."""
        pass
    
    def _log_endpoint_securely(self, label: str, endpoint: str) -> None:
        """
        Log API endpoint securely by masking sensitive information.
        
        Args:
            label: A descriptive label for the endpoint being logged
            endpoint: The API endpoint URL to log securely
        """
        try:
            if not endpoint:
                logging.info(f"   {label}: [EMPTY_ENDPOINT]")
                return
            
            # Parse URL and mask sensitive parameters
            from urllib.parse import urlparse, parse_qs, urlunparse
            import re
            
            parsed = urlparse(endpoint)
            if not parsed.scheme or not parsed.netloc:
                logging.info(f"   {label}: [INVALID_ENDPOINT]")
                return
            
            # Create base URL (scheme + netloc + path)
            safe_endpoint = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            
            # Handle query parameters - mask sensitive ones
            if parsed.query:
                try:
                    query_params = parse_qs(parsed.query, keep_blank_values=True)
                    safe_params = []
                    
                    for key, values in query_params.items():
                        # List of common sensitive parameter names
                        sensitive_params = [
                            'api_key', 'apikey', 'api-key', 'dd-api-key', 
                            'token', 'auth', 'authorization', 'key', 'secret',
                            'password', 'pass', 'pwd', 'credential', 'cred'
                        ]
                        
                        if key.lower() in sensitive_params:
                            safe_params.append(f"{key}=[REDACTED]")
                        else:
                            # For non-sensitive params, show the values
                            value_str = ','.join(str(v) for v in values)
                            safe_params.append(f"{key}={value_str}")
                    
                    if safe_params:
                        safe_endpoint += "?" + "&".join(safe_params)
                        
                except Exception:
                    # If parsing fails, just indicate that query params were masked
                    safe_endpoint += "?[QUERY_PARAMS_MASKED]"
            
            # Also mask sensitive patterns in the path itself
            safe_endpoint = re.sub(
                r'/(api[_-]?key|token|auth|secret)/[^/?#]+',
                r'/\1/[REDACTED]',
                safe_endpoint,
                flags=re.IGNORECASE
            )
            
            logging.info(f"   {label}: {safe_endpoint}")
            
        except Exception as e:
            logging.info(f"   {label}: [ENDPOINT_LOGGING_ERROR: {str(e)}]")

    def get_provider_config(self) -> Dict[str, Any]:
        """Get the provider configuration."""
        for provider in self.provider_details:
            if provider.get("name", "").lower() == self.provider_name:
                return provider.get("config", {})
        return {}
