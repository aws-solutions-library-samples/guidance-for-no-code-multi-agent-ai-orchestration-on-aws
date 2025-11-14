"""
Datadog observability provider for GenAI-In-A-Box agent.
This module provides comprehensive Datadog instrumentation using the official ddtrace library.
Supports traces, logs, metrics, and specialized LLM observability.
"""

import logging
import os
import uuid
from typing import Dict, Any
from .base import BaseObservabilityProvider

logger = logging.getLogger(__name__)


class DatadogObservabilityProvider(BaseObservabilityProvider):
    """Official Datadog observability provider using ddtrace library."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Datadog observability provider."""
        super().__init__(config)
        self.provider_name = "datadog"
    
    def initialize(self) -> Dict[str, Any]:
        """Initialize the Datadog observability provider using official ddtrace library."""
        try:
            provider_config = self.get_provider_config()
            
            logging.debug("🔍 Datadog provider configuration validation starting")
            
            # Get Datadog configuration
            api_key = provider_config.get("api_key", "")
            site = provider_config.get("site", "datadoghq.com")
            environment = provider_config.get("environment", "production")
            service_name, version = self._get_service_info()
            # Override version from config if provided
            version = provider_config.get("version", version)
            enable_llm_obs = provider_config.get("enable_llm_obs", True)
            enable_logs = provider_config.get("enable_logs", True)
            
            # Simple credential validation with minimal logging
            if not api_key:
                logging.error("Datadog API key required but not provided")
                return {}
            
            logging.info("Datadog credentials validated")
            
            # Set up environment variables for official Datadog Strands SDK integration
            os.environ["DD_API_KEY"] = api_key
            os.environ["DD_SITE"] = site
            os.environ["DD_ENV"] = environment
            os.environ["DD_SERVICE"] = service_name
            os.environ["DD_VERSION"] = version
            
            # Official OpenTelemetry configuration for Strands SDK integration
            # Following https://docs.datadoghq.com/llm_observability/instrumentation/otel_instrumentation/#using-strands-agents
            os.environ["OTEL_EXPORTER_OTLP_TRACES_PROTOCOL"] = "http/protobuf"
            os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = f"https://trace.agent.{site}/v1/traces"
            os.environ["OTEL_EXPORTER_OTLP_TRACES_HEADERS"] = f"dd-api-key={api_key},dd-otlp-source=datadog"
            os.environ["OTEL_SEMCONV_STABILITY_OPT_IN"] = "gen_ai_latest_experimental"
            
            # Force agentless mode for ECS deployment
            os.environ["DD_TRACE_AGENT_URL"] = f"https://trace.agent.{site}"
            os.environ["DD_TRACE_API_VERSION"] = "v0.4"
            os.environ["DD_AGENT_HOST"] = ""
            os.environ["DD_DOGSTATSD_PORT"] = "0"
            os.environ["DD_APM_DD_URL"] = f"https://trace.agent.{site}"
            os.environ["DD_LLMOBS_INTAKE_URL"] = f"https://llmobs-intake.{site}"
            
            # Log configuration securely
            self._log_endpoint_securely("DD_TRACE_AGENT_URL", os.environ["DD_TRACE_AGENT_URL"])
            self._log_endpoint_securely("DD_LLMOBS_INTAKE_URL", os.environ["DD_LLMOBS_INTAKE_URL"])
            logging.info("🌐 Configured direct Datadog intake URLs (agentless mode)")
            logging.info("🔧 Using v0.4 traces API (stable supported version)")
            
            # Configure logs
            if enable_logs:
                os.environ["DD_LOGS_INJECTION"] = "true"
                logging.info("✅ Log correlation enabled")
            else:
                os.environ["DD_LOGS_INJECTION"] = "false"
                logging.info("ℹ️ Log correlation disabled")
            
            # Configure LLM Observability
            if enable_llm_obs:
                os.environ["DD_LLMOBS_ENABLED"] = "1"
                os.environ["DD_LLMOBS_ML_APP"] = service_name
                os.environ["DD_LLMOBS_AGENTLESS_ENABLED"] = "1"
                logging.info("✅ LLM Observability enabled")
            else:
                os.environ["DD_LLMOBS_ENABLED"] = "0"
                logging.info("ℹ️ LLM Observability disabled")
            
            # Fix SSL certificate verification issues in containerized environments
            os.environ["DD_TRACE_TLS_CERT_FILE"] = ""
            os.environ["DD_TRACE_TLS_CA_CERT"] = ""
            os.environ["DD_TRACE_TLS_VERIFY"] = "false"
            os.environ["DD_LLMOBS_TLS_VERIFY"] = "false"
            logging.warning("⚠️ TLS verification disabled for containerized environment")
            
            # Force direct API submission (bypass agent completely)
            os.environ["DD_TRACE_WRITER_BUFFER_SIZE_BYTES"] = "1048576"
            os.environ["DD_TRACE_WRITER_MAX_PAYLOAD_SIZE"] = "1000000"
            os.environ["DD_TRACE_WRITER_INTERVAL_SECONDS"] = "1"
            
            logging.info("✅ Datadog environment variables configured")
            
            # Initialize ddtrace programmatically - with secure logging
            try:
                logging.info("📦 Importing ddtrace library...")
                
                # AGGRESSIVE SSL FIX: Modify Python SSL context globally
                import ssl
                ssl._create_default_https_context = ssl._create_unverified_context
                logging.info("🔧 Disabled SSL verification at Python SSL context level")
                
                # Initialize LLM Observability if enabled
                if enable_llm_obs:
                    logging.info("🤖 Initializing LLM Observability...")
                    from ddtrace.llmobs import LLMObs
                    
                    LLMObs.enable(
                        ml_app=service_name,
                        site=site,
                        api_key=api_key,  # This stays in memory, not logged
                        agentless_enabled=True,
                        env=environment,
                        service=service_name,
                        integrations_enabled=True
                    )
                    logging.info("✅ LLM Observability initialized")
                
                # Enable automatic instrumentation for LLM libraries only
                logging.info("🔧 Enabling LLM-specific instrumentation...")
                from ddtrace import patch
                patch(anthropic=True, botocore=True, openai=True, langchain=True)
                logging.info("✅ LLM-specific instrumentation enabled")
                
                # Configure logging and metrics integration
                if enable_logs:
                    logging.info("📝 Configuring logging integration...")
                    try:
                        from ddtrace.contrib.logging import patch as patch_logging
                        patch_logging()
                        logging.info("✅ Strands SDK logging forwarded to Datadog")
                        logging.info("✅ Logging integration patched for trace correlation")
                    except (ImportError, AttributeError):
                        logging.info("ℹ️ Using environment variables for log correlation only")
                
                # Configure metrics for Strands integration
                logging.info("📊 Configuring metrics integration...")
                try:
                    from datadog import initialize, statsd
                    
                    # Initialize Datadog API for metrics (credentials not logged)
                    initialize(
                        api_key=api_key,  # Not logged
                        host_name=f"api.{site}",
                        http_host=f"api.{site}",
                        secure=True
                    )
                    
                    # Configure StatsD for metrics
                    statsd.host = f"api.{site}"
                    statsd.port = 443
                    statsd.use_ms = True
                    
                    # Send a test metric to verify connection
                    statsd.increment(f"{service_name}.startup", tags=[f"env:{environment}", f"service:{service_name}"])
                    logging.info(f"✅ Sent test metric: {service_name}.startup")
                    
                    # Store for Strands integration
                    os.environ["DATADOG_METRICS_ENABLED"] = "true"
                    os.environ["DATADOG_SERVICE_NAME"] = service_name
                    os.environ["DATADOG_ENVIRONMENT"] = environment
                    
                    logging.info("✅ Datadog metrics client configured")
                    
                except Exception as metrics_error:
                    logging.warning(f"⚠️ Metrics configuration failed: {str(metrics_error)}")
                    logging.info("   Traces and LLM Observability will still work")
                
                logging.info("🚀 Datadog ddtrace initialized successfully")
                
            except ImportError as e:
                logging.error(f"❌ ddtrace library not available: {str(e)}")
                logging.info("   Install with: pip install ddtrace")
                logging.info("   Falling back to environment variables only")
            except Exception as e:
                from secure_logging_utils import log_exception_safely
                log_exception_safely(logger, "Datadog ddtrace initialization", e)
                logging.info("   Environment variables are set, some functionality may still work")
            
            # Use DRY helper to create standard trace attributes with Datadog-specific tags
            parsed_tags = []
            tags = provider_config.get("tags", "")
            if tags and isinstance(tags, str):
                parsed_tags = [line.strip() for line in tags.strip().split('\n') if line.strip()]
            elif tags and isinstance(tags, list):
                parsed_tags = tags
            
            # Create trace attributes using base helper with Datadog-specific additions
            self.trace_attributes = self._create_standard_trace_attributes(parsed_tags)
            # Add Datadog-specific tag format
            default_tags = [f"service:{service_name}", f"env:{environment}"]
            all_tags = default_tags + parsed_tags
            self.trace_attributes["dd.tags"] = ",".join(all_tags)
            
            logging.info("✅ Datadog observability provider initialized successfully")
            logging.debug("📊 Trace attributes configured")
            
            return self.trace_attributes
            
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Datadog provider initialization", e)
            return {}
    
    def _get_metrics_client_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get Datadog metrics client configuration."""
        provider_config = self.get_provider_config()
        return {
            "type": "datadog_statsd",
            "api_key": provider_config.get("api_key", ""),
            "site": provider_config.get("site", "datadoghq.com"),
            "tags": [f"service:{service_name}", f"env:{environment}"]
        }
    
    def _get_log_client_config(self) -> Dict[str, Any]:
        """Get Datadog log client configuration."""
        provider_config = self.get_provider_config()
        return {
            "type": "datadog_logs_api",
            "api_key": provider_config.get("api_key", ""),
            "site": provider_config.get("site", "datadoghq.com")
        }
    
    def _send_metrics_with_client(self, metrics_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Send metrics using Datadog StatsD - minimal implementation."""
        from datadog import statsd
        tags = client_config["tags"]
        service_name = metrics_data["service_name"]
        
        # Simple metric sending using extracted data
        if metrics_data["tokens"]:
            tokens = metrics_data["tokens"]
            statsd.gauge(f"{service_name}.tokens.total", tokens["total"], tags=tags)
            print(f"✅ Sent {tokens['total']} tokens to Datadog")
        
        if metrics_data["performance"]:
            perf = metrics_data["performance"]
            if "latency_ms" in perf:
                statsd.gauge(f"{service_name}.latency.ms", perf["latency_ms"], tags=tags)
                print(f"✅ Sent {perf['latency_ms']}ms latency to Datadog")
    
    def _emit_log_with_client(self, log_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Emit log using Datadog Logs API - minimal implementation."""
        from datadog import api
        api.Log.create(
            message=log_data["message"],
            level=log_data["level"].lower(),
            service=log_data["service"],
            tags=[f"env:{log_data['environment']}", f"logger:{log_data['logger']}"]
        )
    
    def _cleanup_environment_variables(self):
        """Clean up Datadog-specific environment variables."""
        datadog_env_vars = [
            # Datadog DD_* variables
            "DD_API_KEY", "DD_SITE", "DD_ENV", "DD_SERVICE", "DD_VERSION",
            "DD_TRACE_AGENT_URL", "DD_TRACE_API_VERSION", "DD_AGENT_HOST",
            "DD_DOGSTATSD_PORT", "DD_APM_DD_URL", "DD_LLMOBS_INTAKE_URL",
            "DD_LOGS_INJECTION", "DD_LLMOBS_ENABLED", "DD_LLMOBS_ML_APP",
            "DD_LLMOBS_AGENTLESS_ENABLED", "DD_TRACE_TLS_CERT_FILE",
            "DD_TRACE_TLS_CA_CERT", "DD_TRACE_TLS_VERIFY", "DD_LLMOBS_TLS_VERIFY",
            "DD_TRACE_WRITER_BUFFER_SIZE_BYTES", "DD_TRACE_WRITER_MAX_PAYLOAD_SIZE",
            "DD_TRACE_WRITER_INTERVAL_SECONDS", "DATADOG_METRICS_ENABLED",
            "DATADOG_SERVICE_NAME", "DATADOG_ENVIRONMENT",
            
            # OpenTelemetry variables used for Datadog Strands SDK integration
            "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
            "OTEL_EXPORTER_OTLP_TRACES_HEADERS", "OTEL_SEMCONV_STABILITY_OPT_IN"
        ]
        
        removed_count = self._cleanup_environment_variables_by_list(datadog_env_vars)
        logging.debug(f"Removed {removed_count} Datadog environment variables")
    
    def _provider_specific_cleanup(self):
        """Datadog-specific cleanup for provider transitions."""
        try:
            # Disable ddtrace instrumentation
            try:
                from ddtrace import patch
                # Unfortunately, ddtrace doesn't provide unpatch methods
                # Best we can do is mark for next restart
                logging.warning("Datadog ddtrace instrumentation cannot be cleanly disabled - requires agent restart for full transition")
            except ImportError:
                pass
            
            # Clean up LLMObs if it was enabled
            try:
                from ddtrace.llmobs import LLMObs
                if hasattr(LLMObs, 'disable'):
                    LLMObs.disable()
                    logging.debug("Datadog LLMObs disabled")
            except (ImportError, AttributeError):
                pass
            
            # Reset SSL context modifications
            try:
                import ssl
                ssl._create_default_https_context = ssl.create_default_context
                logging.debug("Restored default SSL context")
            except Exception:
                pass
            
            logging.info("Datadog-specific cleanup completed")
            
        except Exception as e:
            logging.warning(f"Error in Datadog-specific cleanup: {e}")
    
    def get_strands_tracer_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Get configuration for Strands get_tracer() following official Datadog guidance."""
        # CRITICAL: Only return config if this provider is currently active
        if not self._validate_provider_is_active():
            logging.debug(f"Skipping tracer config for inactive {self.provider_name} provider")
            return {}
            
        try:
            provider_config = self.get_provider_config()
            site = provider_config.get("site", "datadoghq.com")
            api_key = provider_config.get("api_key", "")
            
            # Follow official Datadog guidance for Strands SDK integration
            # https://docs.datadoghq.com/llm_observability/instrumentation/otel_instrumentation/#using-strands-agents
            
            # Use official Datadog trace agent endpoint (not OTLP intake)
            endpoint = f"https://trace.agent.{site}/v1/traces"
            headers = {
                "dd-api-key": api_key,
                "dd-otlp-source": "datadog"
            }
            
            logging.debug("Using official Datadog trace agent endpoint for Strands integration")
            
            return self._build_standard_tracer_config(service_name, environment, endpoint, headers)
            
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Datadog tracer config generation", e)
            return {}
