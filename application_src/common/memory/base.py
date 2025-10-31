"""
Base memory provider for GenAI-In-A-Box agent.
This module provides a base class for memory providers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseMemoryProvider(ABC):
    """Base class for memory providers."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the memory provider."""
        self.config = config
        self.provider_name = config.get("provider", "")
        self.provider_details = config.get("provider_details", [])
        self.tools = []
    
    @abstractmethod
    def initialize(self) -> List:
        """Initialize the memory provider and get the tools."""
        pass
    
    def get_tools(self) -> List:
        """Get the memory tools."""
        if not self.tools:
            return self.initialize()
        return self.tools
    
    def get_provider_config(self) -> Dict[str, Any]:
        """Get the provider configuration."""
        for provider in self.provider_details:
            if provider.get("name", "").lower() == self.provider_name.lower():
                return provider.get("config", {})
        return {}
