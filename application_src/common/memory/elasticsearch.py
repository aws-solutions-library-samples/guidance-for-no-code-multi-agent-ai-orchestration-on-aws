"""
Elasticsearch memory provider for agent memory management.

Integrates the strands-agents Elasticsearch memory tool into the
Generative AI in the Box memory provider architecture.
"""

import logging
from typing import Any, Dict, List

from strands_tools.elasticsearch_memory import elasticsearch_memory

from .base import BaseMemoryProvider as BaseMemory

logger = logging.getLogger(__name__)


class ElasticsearchMemory(BaseMemory):
    """
    Elasticsearch-based memory provider using strands-tools.
    
    Provides vector-based memory storage and retrieval using
    Elasticsearch as the backend storage system.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Elasticsearch memory provider.
        
        Args:
            config: Configuration dictionary for the memory provider
        """
        super().__init__(config)
        self.provider_name = "elasticsearch"
        
        logger.info("Initialized Elasticsearch memory provider")
    
    def initialize(self) -> list:
        """Initialize the Elasticsearch memory provider and get the tools."""
        try:
            # Get provider configuration
            provider_config = self.get_provider_config()
            
            if not provider_config:
                logger.warning("No Elasticsearch configuration found")
                return []
            
            # Create wrapped elasticsearch_memory tool
            from strands import tool
            
            @tool
            def elasticsearch_memory_tool(action: str, content: str = None, query: str = None, 
                                         session_id: str = None) -> Dict[str, Any]:
                """
                Elasticsearch memory tool for storing and retrieving information.
                
                Args:
                    action: The action to perform ('store', 'retrieve', or 'clear')
                    content: The content to store (for 'store' action)
                    query: The query to search for (for 'retrieve' action)
                    session_id: Session ID for organizing memories
                    
                Returns:
                    Dictionary with the results of the operation
                """
                try:
                    # Create function call parameters
                    function_params = {
                        "action": action,
                        **provider_config
                    }
                    
                    if action == "store" and content:
                        function_params.update({
                            "memory": content,
                            "session_id": session_id or "default",
                            "timestamp": ElasticsearchMemory._get_timestamp()
                        })
                    elif action == "retrieve" and query:
                        function_params.update({
                            "query": query,
                            "n_results": 5,
                            "session_id": session_id or "default"
                        })
                    elif action == "clear":
                        function_params.update({
                            "session_id": session_id or "default"
                        })
                    
                    # Call elasticsearch_memory function
                    result = elasticsearch_memory(function_params)
                    
                    logger.debug(f"Elasticsearch memory operation {action} completed")
                    return result
                    
                except Exception as e:
                    error_msg = f"Error in elasticsearch_memory tool: {str(e)}"
                    logger.error(error_msg)
                    return {"status": "error", "message": error_msg}
            
            self.tools = [elasticsearch_memory_tool]
            logger.info(f"Successfully created {len(self.tools)} Elasticsearch memory tools")
            
            return self.tools
            
        except Exception as e:
            logger.error(f"Error initializing Elasticsearch memory provider: {str(e)}")
            return []
    
    def get_tools(self) -> List:
        """Get memory tools - following the same pattern as other providers."""
        if not hasattr(self, 'tools') or not self.tools:
            return self.initialize()
        return self.tools
    
    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
