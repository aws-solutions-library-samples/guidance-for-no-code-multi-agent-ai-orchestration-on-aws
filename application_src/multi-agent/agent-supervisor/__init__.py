"""
Supervisor Agent Package

A modular, production-ready supervisor agent with clean architecture:
- Separated concerns for maintainability
- Circuit breaker pattern for resilience  
- Optimized streaming with batching
- Ultra-fast health checks
- TTL-based caching
- Centralized configuration
"""

from config import *
from circuit_breaker import bedrock_circuit_breaker, CircuitState
from health import app_health
from cache import agent_card_cache
from streaming import agent_stream_processor, direct_stream_processor
from service import supervisor_service
from model_switcher import model_switcher

__version__ = "2.0.0"
__author__ = "AWS GenAI Team"
__description__ = "Modular supervisor agent with clean architecture"

# Export main components
__all__ = [
    # Configuration
    "A2A_CLIENT_TIMEOUT", "CIRCUIT_BREAKER_FAILURE_THRESHOLD", 
    "OPTIMAL_BATCH_SIZE", "DEFAULT_HOST", "DEFAULT_PORT",
    
    # Core components
    "bedrock_circuit_breaker", "app_health", "agent_card_cache",
    "agent_stream_processor", "direct_stream_processor", "supervisor_service",
    "model_switcher",
    
    # Enums
    "CircuitState",
    
    # Metadata
    "__version__", "__author__", "__description__"
]
