"""
Circuit breaker implementation for handling failures gracefully.
Provides resilience against cascading failures and automatic recovery.
"""
import logging
from datetime import datetime
from enum import Enum

from config import (
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD
)

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open" 
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Circuit breaker pattern implementation for handling failures.
    
    States:
    - CLOSED: Normal operation, requests allowed
    - OPEN: Failure threshold reached, requests blocked
    - HALF_OPEN: Testing recovery, limited requests allowed
    """
    
    def __init__(self, failure_threshold: int, recovery_timeout: int, success_threshold: int = 1):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
        
    def can_execute(self) -> bool:
        """Check if operation can be executed based on circuit state."""
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if self.last_failure_time and (
                datetime.now() - self.last_failure_time
            ).total_seconds() >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info("Circuit breaker entering HALF_OPEN state")
                return True
            return False
        elif self.state == CircuitState.HALF_OPEN:
            return True
        return False
    
    def record_success(self):
        """Record a successful operation."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info("Circuit breaker CLOSED - service recovered")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = max(0, self.failure_count - 1)
    
    def record_failure(self):
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit breaker OPENED due to {self.failure_count} failures")
        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker returned to OPEN state after failure in HALF_OPEN")
    
    def get_status(self) -> dict:
        """Get current circuit breaker status."""
        return {
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat() if self.last_failure_time else None
        }


# Global circuit breaker for Bedrock operations
bedrock_circuit_breaker = CircuitBreaker(
    failure_threshold=CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    recovery_timeout=CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    success_threshold=CIRCUIT_BREAKER_SUCCESS_THRESHOLD
)
