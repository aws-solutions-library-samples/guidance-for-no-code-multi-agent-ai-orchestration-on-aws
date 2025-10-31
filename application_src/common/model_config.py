"""
Shared model configuration for all agents.
Centralizes model definitions and switching settings.
"""

# Model switching settings for throttling resilience - Top 6 Recent Anthropic US Models
ANTHROPIC_MODELS = [
    "us.anthropic.claude-opus-4-1-20250805-v1:0",        # 1st: Claude Opus 4.1 (Aug 2025) 
    "us.anthropic.claude-sonnet-4-20250514-v1:0",        # 2nd: Claude Sonnet 4 (May 2025)
    "us.anthropic.claude-opus-4-20250514-v1:0",          # 3rd: Claude Opus 4 (May 2025)
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0",     # 4th: Claude 3.7 Sonnet (Feb 2025)
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0",     # 5th: Claude 3.5 Sonnet v2 (Oct 2024)
    "us.anthropic.claude-3-5-haiku-20241022-v1:0"       # 6th: Claude 3.5 Haiku (Oct 2024) - for error compatibility
]

# Model switching configuration
DEFAULT_MODEL = ANTHROPIC_MODELS[0]  # Primary model
MODEL_COOLDOWN_SECONDS = 300  # 5 minutes before retrying a throttled model
MODEL_SWITCH_ON_THROTTLE = True  # Enable automatic model switching

# Aggressive throttling detection settings
AGGRESSIVE_TIMEOUT_SECONDS = 8.0  # Aggressive timeout for throttling detection
SLOW_RESPONSE_THRESHOLD = 8.0  # Consider responses >8s as potentially throttled
VERY_SLOW_THRESHOLD = 15.0  # Consider responses >15s as definitely throttled
CONSECUTIVE_SLOW_LIMIT = 2  # Switch models after 2 consecutive slow responses
