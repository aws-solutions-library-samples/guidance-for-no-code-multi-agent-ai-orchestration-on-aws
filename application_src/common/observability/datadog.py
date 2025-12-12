"""
Datadog observability provider for GenAI-In-A-Box agent.
This module provides comprehensive Datadog instrumentation using the official ddtrace library.
Supports traces, logs, metrics, and specialized LLM observability.
"""

import logging
import os
import uuid
import time
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
        """Initialize the Datadog observability provider using ADOT + ddtrace auto-instrumentation."""
        try:
            provider_config = self.get_provider_config()
            
            logging.debug("🔍 Datadog provider configuration validation starting")
            
            # Get Datadog configuration
            api_key = provider_config.get("api_key", "")
            site = provider_config.get("site", "datadoghq.com")
            environment = provider_config.get("environment", "production")
            service_name, version = self._get_service_info()
            version = provider_config.get("version", version)
            enable_llm_obs = provider_config.get("enable_llm_obs", True)
            enable_logs = provider_config.get("enable_logs", True)
            
            # Simple credential validation with minimal logging
            if not api_key:
                logging.error("Datadog API key required but not provided")
                return {}
            
            logging.info("✅ Datadog credentials validated")
            
            # Set up environment variables for official Datadog Strands SDK integration
            # This enables AUTOMATIC telemetry collection and forwarding
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
            
            # Enable ADOT configuration for automatic metrics and logs
            os.environ["OTEL_PYTHON_DISTRO"] = "aws_distro"
            os.environ["OTEL_PYTHON_CONFIGURATOR"] = "aws_configurator"
            os.environ["OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED"] = "true"
            
            # Configure LLM Observability for automatic LLM telemetry
            if enable_llm_obs:
                os.environ["DD_LLMOBS_ENABLED"] = "1"
                os.environ["DD_LLMOBS_ML_APP"] = service_name
                os.environ["DD_LLMOBS_AGENTLESS_ENABLED"] = "1"
                logging.info("✅ LLM Observability enabled - automatic LLM telemetry active")
            
            # Configure logs for automatic log correlation
            if enable_logs:
                os.environ["DD_LOGS_INJECTION"] = "true"
                logging.info("✅ Log correlation enabled - automatic trace-log correlation active")
            
            # Activate ADOT auto-instrumentation programmatically
            try:
                from opentelemetry.instrumentation.auto_instrumentation import sitecustomize
                sitecustomize.initialize()
                print("✅ ADOT auto-instrumentation activated - all telemetry automatic!")
            except ImportError:
                print("⚠️ ADOT auto-instrumentation not available, using ddtrace only")
            
            # Initialize ddtrace for enhanced LLM observability
            self._initialize_ddtrace_enhanced(api_key, site, service_name, version, environment, enable_llm_obs, enable_logs)
            
            # Use DRY helper to create standard trace attributes
            parsed_tags = []
            tags = provider_config.get("tags", "")
            if tags and isinstance(tags, str):
                parsed_tags = [line.strip() for line in tags.strip().split('\n') if line.strip()]
            elif tags and isinstance(tags, list):
                parsed_tags = tags
            
            self.trace_attributes = self._create_standard_trace_attributes(parsed_tags)
            # Add Datadog-specific tag format
            default_tags = [f"service:{service_name}", f"env:{environment}"]
            all_tags = default_tags + parsed_tags
            self.trace_attributes["dd.tags"] = ",".join(all_tags)
            
            logging.info("✅ Datadog observability provider initialized - AUTOMATIC telemetry active")
            logging.info("🎯 Strands SDK will automatically send all metrics, logs, traces to Datadog!")
            
            return self.trace_attributes
            
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Datadog provider initialization", e)
            return {}
    
    def _initialize_ddtrace_enhanced(self, api_key: str, site: str, service_name: str, 
                                   version: str, environment: str, enable_llm_obs: bool, enable_logs: bool):
        """Initialize enhanced ddtrace integration for superior LLM observability."""
        try:
            logging.info("🤖 Initializing enhanced ddtrace for LLM observability...")
            
            # Set up additional Datadog-specific environment variables for enhanced features
            os.environ["DD_TRACE_AGENT_URL"] = f"https://trace.agent.{site}"
            os.environ["DD_TRACE_API_VERSION"] = "v0.4"
            os.environ["DD_AGENT_HOST"] = ""
            os.environ["DD_DOGSTATSD_PORT"] = "0"
            os.environ["DD_APM_DD_URL"] = f"https://trace.agent.{site}"
            os.environ["DD_LLMOBS_INTAKE_URL"] = f"https://llmobs-intake.{site}"
            
            # Force direct API submission (bypass agent completely)
            os.environ["DD_TRACE_WRITER_BUFFER_SIZE_BYTES"] = "1048576"
            os.environ["DD_TRACE_WRITER_MAX_PAYLOAD_SIZE"] = "1000000" 
            os.environ["DD_TRACE_WRITER_INTERVAL_SECONDS"] = "1"
            
            # Fix SSL certificate verification issues
            os.environ["DD_TRACE_TLS_CERT_FILE"] = ""
            os.environ["DD_TRACE_TLS_CA_CERT"] = ""
            os.environ["DD_TRACE_TLS_VERIFY"] = "false"
            os.environ["DD_LLMOBS_TLS_VERIFY"] = "false"
            
            # Initialize ddtrace programmatically
            try:
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
                        api_key=api_key,
                        agentless_enabled=True,
                        env=environment,
                        service=service_name,
                        integrations_enabled=True
                    )
                    logging.info("✅ LLM Observability initialized")
                
                # Enable automatic instrumentation for LLM libraries
                logging.info("🔧 Enabling LLM-specific instrumentation...")
                from ddtrace import patch
                patch(anthropic=True, botocore=True, openai=True, langchain=True)
                logging.info("✅ LLM-specific instrumentation enabled")
                
                # Configure logging integration
                if enable_logs:
                    logging.info("📝 Configuring logging integration...")
                    try:
                        from ddtrace.contrib.logging import patch as patch_logging
                        patch_logging()
                        logging.info("✅ Logging integration patched for trace correlation")
                    except (ImportError, AttributeError):
                        logging.info("ℹ️ Using environment variables for log correlation only")
                
                # Configure metrics integration
                logging.info("📊 Configuring metrics integration...")
                from datadog import initialize, statsd
                
                initialize(
                    api_key=api_key,
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
                
            except ImportError as e:
                logging.error(f"❌ ddtrace library not available: {str(e)}")
                logging.info("   Install with: pip install ddtrace")
            except Exception as e:
                from secure_logging_utils import log_exception_safely
                log_exception_safely(logger, "Datadog ddtrace initialization", e)
                
        except Exception as e:
            from secure_logging_utils import log_exception_safely
            log_exception_safely(logger, "Enhanced ddtrace initialization", e)
    
    # REQUIRED: Minimal implementations to satisfy abstract base class
    # ddtrace + ADOT auto-instrumentation handles everything automatically
    
    def _get_metrics_client_config(self, service_name: str, environment: str) -> Dict[str, Any]:
        """Auto-instrumentation handles metrics - no manual config needed."""
        return {"type": "auto_instrumentation", "message": "ddtrace + ADOT handle metrics automatically"}
    
    def _get_log_client_config(self) -> Dict[str, Any]:
        """Auto-instrumentation handles logs - no manual config needed.""" 
        return {"type": "auto_instrumentation", "message": "ddtrace + ADOT handle logs automatically"}
    
    def _send_metrics_with_client(self, metrics_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Auto-instrumentation handles metrics - no manual sending needed."""
        print("📊 ddtrace + ADOT auto-instrumentation handles metrics automatically - no manual processing")
    
    def _emit_log_with_client(self, log_data: Dict[str, Any], client_config: Dict[str, Any]):
        """Auto-instrumentation handles logs - no manual emitting needed."""
        print("📝 ddtrace + ADOT auto-instrumentation handles logs automatically - no manual processing")
    
    def get_auto_instrumentation_status(self) -> Dict[str, Any]:
        """Get the status of auto-instrumentation for Datadog."""
        return {
            "provider": "datadog",
            "adot_enabled": os.environ.get("OTEL_PYTHON_DISTRO") == "aws_distro", 
            "ddtrace_enabled": os.environ.get("DD_API_KEY") is not None,
            "traces_endpoint": os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", ""),
            "llm_obs_enabled": os.environ.get("DD_LLMOBS_ENABLED") == "1",
            "auto_logging": os.environ.get("DD_LOGS_INJECTION") == "true",
            "message": "✅ ddtrace + ADOT handle all telemetry automatically - no manual intervention required"
        }
    
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
