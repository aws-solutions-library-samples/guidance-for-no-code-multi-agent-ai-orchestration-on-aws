"""
Simple performance monitoring without complex optimization.
"""
import time
import logging
from typing import Dict, Any
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class SimplePerformanceManager:
    """Simple performance monitoring."""
    
    def __init__(self):
        self.start_time = time.time()
        self.request_count = 0
        self.error_count = 0
        
    async def initialize(self):
        """Initialize performance manager."""
        logger.info("Simple performance manager initialized")
        
    async def shutdown(self):
        """Shutdown performance manager."""
        logger.info("Simple performance manager shutdown")
    
    @asynccontextmanager
    async def request_context(self):
        """Simple request context."""
        try:
            self.request_count += 1
            yield
        except Exception as e:
            self.error_count += 1
            raise
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get simple performance stats."""
        uptime = time.time() - self.start_time
        rps = self.request_count / max(uptime, 1)
        error_rate = (self.error_count / max(self.request_count, 1)) * 100
        
        return {
            "uptime_seconds": round(uptime, 2),
            "total_requests": self.request_count,
            "requests_per_second": round(rps, 2),
            "error_count": self.error_count,
            "error_rate_percent": round(error_rate, 2),
        }


# Global simple performance manager
performance_manager = SimplePerformanceManager()
