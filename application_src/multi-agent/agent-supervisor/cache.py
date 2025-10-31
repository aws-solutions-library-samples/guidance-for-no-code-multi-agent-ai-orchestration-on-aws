"""
Agent card cache implementation for performance optimization.
Provides TTL-based caching to reduce redundant agent discovery calls.
"""
import logging
import time
from typing import Dict, Optional, Any

from config import AGENT_CARD_CACHE_TTL

logger = logging.getLogger(__name__)


class AgentCardCache:
    """
    TTL-based cache for agent card information.
    Reduces redundant agent discovery API calls for better performance.
    """
    
    def __init__(self, ttl_seconds: int = AGENT_CARD_CACHE_TTL):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.cache_time: Dict[str, float] = {}
        self.ttl = ttl_seconds

    def get(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached agent card for the given URL.
        
        Args:
            url: Agent URL to lookup
            
        Returns:
            Cached agent card if valid, None if expired or not found
        """
        if url in self.cache and time.time() - self.cache_time[url] < self.ttl:
            return self.cache[url]
        return None

    def set(self, url: str, agent_card: Dict[str, Any]) -> None:
        """
        Store agent card in cache with current timestamp.
        
        Args:
            url: Agent URL to cache
            agent_card: Agent card data to store
        """
        self.cache[url] = agent_card
        self.cache_time[url] = time.time()

    def invalidate(self, url: str) -> None:
        """Remove a specific URL from cache."""
        self.cache.pop(url, None)
        self.cache_time.pop(url, None)

    def clear(self) -> None:
        """Clear all cached entries."""
        cache_size = len(self.cache)
        self.cache.clear()
        self.cache_time.clear()
        logger.info(f"Cleared {cache_size} cached agent cards")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        current_time = time.time()
        valid_entries = sum(
            1 for cache_time in self.cache_time.values()
            if current_time - cache_time < self.ttl
        )
        
        return {
            "total_entries": len(self.cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self.cache) - valid_entries,
            "ttl_seconds": self.ttl
        }


# Global agent card cache instance
agent_card_cache = AgentCardCache()
