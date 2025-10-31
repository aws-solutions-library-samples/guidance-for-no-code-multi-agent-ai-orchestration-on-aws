"""
Configuration constants and settings for the supervisor agent.
Centralizes all configuration values for easy maintenance.
"""
import os

# Performance settings for A2A client
A2A_CLIENT_TIMEOUT = 30  # Reduced timeout for faster failure detection (seconds)
A2A_KEEP_ALIVE = 60  # Seconds to keep connections alive
A2A_MAX_CONNECTIONS = 200  # Increased connection limit for better concurrency
A2A_KEEPALIVE_CONNECTIONS = 50  # More aggressive keepalive pool
A2A_RETRY_ATTEMPTS = 2  # Minimize retries for faster failure

# Health check isolation settings
HEALTH_CHECK_TIMEOUT = 2  # Short timeout for health checks
HEALTH_CHECK_MAX_CONNECTIONS = 10  # Separate connection pool for health checks

# Circuit breaker settings
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5  # Failures before opening circuit
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = 30  # Seconds before attempting recovery
CIRCUIT_BREAKER_SUCCESS_THRESHOLD = 2  # Successes needed to close circuit

# Streaming optimization settings
OPTIMAL_BATCH_SIZE = 500  # Characters, not events
OPTIMAL_BATCH_INTERVAL = 0.05  # Seconds - maximum delay before sending partial batch

# Agent discovery settings
AGENT_CARD_CACHE_TTL = 60  # 1-minute cache TTL
AGENT_DISCOVERY_TIMEOUT = 15.0  # Agent discovery timeout
URL_DISCOVERY_TIMEOUT = 10.0  # URL discovery timeout

# Environment variables
CONFIGURATION_API_ENDPOINT = os.environ.get('CONFIGURATION_API_ENDPOINT')
HOSTED_DNS = os.environ.get('HOSTED_DNS')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'development')

# Environment-aware fallback URLs when discovery fails
def get_fallback_agent_urls():
    """Get fallback agent URLs based on environment."""
    if ENVIRONMENT == 'production':
        # In production, should use proper service discovery - no hardcoded fallbacks
        return []
    elif ENVIRONMENT == 'staging':
        # Staging might use different service names or ports
        return [
            "http://staging-agent-1:9001",
            "http://staging-agent-2:9002"
        ]
    else:
        # Development environment - use docker-compose service names
        return [
            "http://agent-1:9001",
            "http://agent-2:9002"
        ]

# Dynamic fallback URLs based on environment
FALLBACK_AGENT_URLS = get_fallback_agent_urls()

# Model switching settings for throttling resilience - Top 5 Recent Anthropic US Models
ANTHROPIC_MODELS = [
    "us.anthropic.claude-opus-4-1-20250805-v1:0",        # 1st: Claude Opus 4.1 (Aug 2025) 
    "us.anthropic.claude-sonnet-4-20250514-v1:0",        # 2nd: Claude Sonnet 4 (May 2025)
    "us.anthropic.claude-opus-4-20250514-v1:0",          # 3rd: Claude Opus 4 (May 2025)
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",     # 4th: Claude 3.7 Sonnet (Feb 2025)
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0"      # 5th: Claude 3.5 Sonnet v2 (Oct 2024)
]

# Model switching configuration
DEFAULT_MODEL = ANTHROPIC_MODELS[0]  # Primary model
MODEL_COOLDOWN_SECONDS = 300  # 5 minutes before retrying a throttled model
MODEL_SWITCH_ON_THROTTLE = True  # Enable automatic model switching

# Aggressive throttling detection settings
AGGRESSIVE_THROTTLING_MODE = os.environ.get('AGGRESSIVE_THROTTLING_MODE', 'true').lower() == 'true'
AGGRESSIVE_TIMEOUT_SECONDS = 8.0  # Aggressive timeout for throttling detection
SLOW_RESPONSE_THRESHOLD = 8.0  # Consider responses >8s as potentially throttled
VERY_SLOW_THRESHOLD = 15.0  # Consider responses >15s as definitely throttled
CONSECUTIVE_SLOW_LIMIT = 2  # Switch models after 2 consecutive slow responses

# Server settings
DEFAULT_PORT = 9003
DEFAULT_HOST = "127.0.0.1"  # Secure default, use env var to override for containers
