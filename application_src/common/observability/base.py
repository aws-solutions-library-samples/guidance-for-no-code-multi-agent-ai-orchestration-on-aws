"""
Base observability provider for GenAI-In-A-Box agent.
This module provides a base class for observability providers.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any

class BaseObservabilityProvider(ABC):
    """Base class for observability providers."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the observability provider."""
        self.config = config
        self.provider_name = config.get("provider", "").lower()
        self.provider_details = config.get("provider_details", [])
        self.trace_attributes = {}
    
    @abstractmethod
    def initialize(self) -> Dict[str, Any]:
        """Initialize the observability provider and get the trace attributes."""
        pass
    
    def get_trace_attributes(self) -> Dict[str, Any]:
        """Get the trace attributes."""
        if not self.trace_attributes:
            return self.initialize()
        return self.trace_attributes
    
    def get_provider_config(self) -> Dict[str, Any]:
        """Get the provider configuration."""
        for provider in self.provider_details:
            if provider.get("name", "").lower() == self.provider_name:
                return provider.get("config", {})
        return {}
