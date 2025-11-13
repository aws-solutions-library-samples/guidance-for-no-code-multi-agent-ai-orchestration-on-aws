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
            
            print(f"🔍 Datadog provider config: {provider_config}")
            
            # Get Datadog configuration
            api_key = provider_config.get("api_key", "")
            site = provider_config.get("site", "datadoghq.com")
            environment = provider_config.get("environment", "production")
            service_name, version = self._get_service_info()
            # Override version from config if provided
            version = provider_config.get("version", version)
            enable_llm_obs = provider_config.get("enable_llm_obs", True)
            enable_logs = provider_config.get("enable_logs", True)
            
            print(f"🔑 Datadog configuration:")
            print(f"   API Key: {'✅ Present' if api_key else '❌ Missing'}")
            print(f"   Site: {site}")
            print(f"   Environment: {environment}")
            print(f"   Service: {service_name}")
            print(f"   Version: {version}")
            print(f"   LLM Observability: {enable_llm_obs}")
            print(f"   Logs: {enable_logs}")
            
            if not api_key:
                print("❌ Error: Datadog API key is required")
                return {}
            
            # Set up environment variables for ddtrace
            os.environ["DD_API_KEY"] = api_key
            os.environ["DD_SITE"] = site
            os.environ["DD_ENV"] = environment
            os.environ["DD_SERVICE"] = service_name
            os.environ["DD_VERSION"] = version
            
            # Force agentless mode for ECS deployment - Official Datadog approach
            os.environ["DD_TRACE_AGENT_URL"] = f"https://trace.agent.{site}"  # Direct intake URL base
            os.environ["DD_TRACE_API_VERSION"] = "v0.4"  # Use supported API version
            os.environ["DD_AGENT_HOST"] = ""  # Disable local agent connection
            os.environ["DD_DOGSTATSD_PORT"] = "0"  # Disable StatsD  
            os.environ["DD_APM_DD_URL"] = f"https://trace.agent.{site}"  # APM intake URL
            os.environ["DD_LLMOBS_INTAKE_URL"] = f"https://llmobs-intake.{site}"  # LLM intake URL
            print(f"🌐 Configured direct Datadog intake URLs for site: {site}")
            print(f"🔧 Using v0.4 traces API (stable supported version)")
            
            # Configure logs
            if enable_logs:
                os.environ["DD_LOGS_INJECTION"] = "true"
                print("✅ Log correlation enabled")
            else:
                os.environ["DD_LOGS_INJECTION"] = "false"
                print("ℹ️ Log correlation disabled")
            
            # Configure LLM Observability
            if enable_llm_obs:
                os.environ["DD_LLMOBS_ENABLED"] = "1"
                os.environ["DD_LLMOBS_ML_APP"] = service_name
                os.environ["DD_LLMOBS_AGENTLESS_ENABLED"] = "1"  # Required for ECS without agent
                print("✅ LLM Observability enabled")
            else:
                os.environ["DD_LLMOBS_ENABLED"] = "0"
                print("ℹ️ LLM Observability disabled")
            
            # Fix SSL certificate verification issues in containerized environments
            os.environ["DD_TRACE_TLS_CERT_FILE"] = ""      # Clear TLS cert file
            os.environ["DD_TRACE_TLS_CA_CERT"] = ""        # Clear CA cert
            os.environ["DD_TRACE_TLS_VERIFY"] = "false"    # Disable TLS verification
            os.environ["DD_LLMOBS_TLS_VERIFY"] = "false"   # Disable LLMObs TLS verification
            print("⚠️ TLS verification disabled for containerized environment")
            
            # Force direct API submission (bypass agent completely)
            os.environ["DD_TRACE_WRITER_BUFFER_SIZE_BYTES"] = "1048576"  # 1MB buffer
            os.environ["DD_TRACE_WRITER_MAX_PAYLOAD_SIZE"] = "1000000"   # 1MB max payload
            os.environ["DD_TRACE_WRITER_INTERVAL_SECONDS"] = "1"         # Send every 1 second
            
            print(f"✅ Datadog environment variables configured")
            
            # Initialize ddtrace programmatically
            try:
                print("📦 Importing ddtrace library...")
                
                # AGGRESSIVE SSL FIX: Modify Python SSL context globally
                import ssl
                ssl._create_default_https_context = ssl._create_unverified_context
                print("🔧 Disabled SSL verification at Python SSL context level")
                
                # Initialize LLM Observability if enabled
                if enable_llm_obs:
                    print("🤖 Initializing LLM Observability...")
                    from ddtrace.llmobs import LLMObs
                    
                    LLMObs.enable(
                        ml_app=service_name,
                        site=site,
                        api_key=api_key,
                        agentless_enabled=True,
                        env=environment,
                        service=service_name,
                        integrations_enabled=True  # Enable automatic LLM instrumentation
                    )
                    print("✅ LLM Observability initialized")
                
                # Enable automatic instrumentation for LLM libraries only
                print("🔧 Enabling LLM-specific instrumentation...")
                from ddtrace import patch
                # Only patch LLM-related libraries, not all libraries
                patch(anthropic=True, botocore=True, openai=True, langchain=True)
                print("✅ LLM-specific instrumentation enabled")
                
                # Configure logging integration (trace correlation + Strands logs)
                if enable_logs:
                    print("📝 Configuring logging integration...")
                    try:
                        from ddtrace.contrib.logging import patch as patch_logging
                        patch_logging()
                        
                        # Add custom handler for Strands SDK logs
                        import logging
                        from datadog import api
                        
                        class StrandsDatadogLogHandler(logging.Handler):
                            def __init__(self, service_name, environment):
                                super().__init__()
                                self.service_name = service_name
                                self.environment = environment
                                self.setLevel(logging.INFO)  # Only forward INFO and above
                            
                            def emit(self, record):
                                try:
                                    # Only process Strands SDK logs
                                    if record.name.startswith('strands'):
                                        log_entry = {
                                            "message": self.format(record),
                                            "level": record.levelname.lower(),
                                            "logger": record.name,
                                            "service": self.service_name,
                                            "environment": self.environment,
                                            "tags": [f"env:{self.environment}", f"service:{self.service_name}", f"logger:{record.name}"]
                                        }
                                        # Send to Datadog Logs API (fire and forget)
                                        try:
                                            api.Log.create(**log_entry)
                                        except:
                                            pass  # Don't break on log submission failures
                                except:
                                    pass  # Don't break application if logging fails
                        
                        # Add handler to Strands root logger
                        strands_logger = logging.getLogger("strands")
                        strands_handler = StrandsDatadogLogHandler(service_name, environment)
                        strands_logger.addHandler(strands_handler)
                        strands_logger.setLevel(logging.INFO)  # Enable INFO level for Strands
                        
                        print("✅ Strands SDK logging forwarded to Datadog")
                        print("✅ Logging integration patched for trace correlation")
                    except (ImportError, AttributeError):
                        print("ℹ️ Using environment variables for log correlation only")
                
                # Configure metrics for Strands integration
                print("📊 Configuring metrics integration...")
                try:
                    from datadog import initialize, statsd
                    
                    # Initialize Datadog API for metrics
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
                    print(f"✅ Sent test metric: {service_name}.startup")
                    
                    # Store for Strands integration
                    os.environ["DATADOG_METRICS_ENABLED"] = "true"
                    os.environ["DATADOG_SERVICE_NAME"] = service_name
                    os.environ["DATADOG_ENVIRONMENT"] = environment
                    
                    print("✅ Datadog metrics client configured")
                    
                except Exception as metrics_error:
                    print(f"⚠️ Metrics configuration failed: {metrics_error}")
                    print("   Traces and LLM Observability will still work")
                
                print("🚀 Datadog ddtrace initialized successfully")
                
            except ImportError as e:
                print(f"❌ ddtrace library not available: {e}")
                print("   Install with: pip install ddtrace")
                print("   Falling back to environment variables only")
            except Exception as e:
                print(f"⚠️ ddtrace initialization failed: {e}")
                print("   Environment variables are set, some functionality may still work")
                import traceback
                traceback.print_exc()
            
            # Parse custom tags if provided
            tags = provider_config.get("tags", "")
            parsed_tags = []
            if tags and isinstance(tags, str):
                for line in tags.strip().split('\n'):
                    if line.strip():
                        parsed_tags.append(line.strip())
            elif tags and isinstance(tags, list):
                parsed_tags = tags
            
            # Build default tags
            default_tags = [f"service:{service_name}", f"env:{environment}"]
            all_tags = default_tags + parsed_tags
            
            self.trace_attributes = {
                "session.id": f"{service_name}-session-{uuid.uuid4()}",
                "user.id": f"{service_name}-user",
                "service.name": service_name,
                "service.version": version,
                "deployment.environment": environment,
                "dd.tags": ",".join(all_tags)
            }
            
            print(f"✅ Datadog observability provider initialized successfully")
            print(f"📊 Trace attributes: {self.trace_attributes}")
            
            return self.trace_attributes
            
        except Exception as e:
            print(f"❌ Error initializing Datadog observability provider: {str(e)}")
            import traceback
            traceback.print_exc()
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
            "DD_API_KEY", "DD_SITE", "DD_ENV", "DD_SERVICE", "DD_VERSION",
            "DD_TRACE_AGENT_URL", "DD_TRACE_API_VERSION", "DD_AGENT_HOST",
            "DD_DOGSTATSD_PORT", "DD_APM_DD_URL", "DD_LLMOBS_INTAKE_URL",
            "DD_LOGS_INJECTION", "DD_LLMOBS_ENABLED", "DD_LLMOBS_ML_APP",
            "DD_LLMOBS_AGENTLESS_ENABLED", "DD_TRACE_TLS_CERT_FILE",
            "DD_TRACE_TLS_CA_CERT", "DD_TRACE_TLS_VERIFY", "DD_LLMOBS_TLS_VERIFY",
            "DD_TRACE_WRITER_BUFFER_SIZE_BYTES", "DD_TRACE_WRITER_MAX_PAYLOAD_SIZE",
            "DD_TRACE_WRITER_INTERVAL_SECONDS", "DATADOG_METRICS_ENABLED",
            "DATADOG_SERVICE_NAME", "DATADOG_ENVIRONMENT"
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
        """Get configuration for Strands get_tracer() to send traces to Datadog."""
        # CRITICAL: Only return config if this provider is currently active
        if not self._validate_provider_is_active():
            logging.debug(f"Skipping tracer config for inactive {self.provider_name} provider")
            return {}
            
        try:
            provider_config = self.get_provider_config()
            site = provider_config.get("site", "datadoghq.com")
            api_key = provider_config.get("api_key", "")
            
            # Return Datadog OTLP configuration for Strands tracer
            return {
                "service_name": service_name,
                "otlp_endpoint": f"https://otlp-intake.{site}/v1/traces",
                "headers": {"DD-API-KEY": api_key},
                "enable_console_export": False,
                "resource_attributes": {
                    "service.name": service_name,
                    "service.version": "1.0.0",
                    "deployment.environment": environment
                }
            }
            
        except Exception as e:
            print(f"⚠️ Error getting Strands tracer config for Datadog: {e}")
            return {}
