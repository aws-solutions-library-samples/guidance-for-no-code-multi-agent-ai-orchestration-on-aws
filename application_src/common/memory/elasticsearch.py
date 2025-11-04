"""
Elasticsearch memory provider for agent memory management.

Integrates the strands-agents Elasticsearch memory tool into the
Generative AI in the Box memory provider architecture.
"""

import logging
from typing import Any

from strands_tools.elasticsearch_memory import ElasticsearchMemoryTool

from .base import BaseMemory

logger = logging.getLogger(__name__)


class ElasticsearchMemory(BaseMemory):
    """
    Elasticsearch-based memory provider using strands-tools.
    
    Provides vector-based memory storage and retrieval using
    Elasticsearch as the backend storage system.
    """
    
    def __init__(self, config: list[dict[str, Any]]):
        """
        Initialize Elasticsearch memory provider.
        
        Args:
            config: List of configuration dictionaries containing:
                - cloud_id: Elasticsearch cloud deployment ID
                - api_key: API key for authentication
                - index_name: Index name for storing memories (optional)
                - dimensions: Vector dimensions for embeddings (optional)
        
        Raises:
            ValueError: If required configuration is missing
        """
        super().__init__(config)
        
        # Extract configuration parameters
        config_dict = {item['name']: item['config'] for item in config}
        
        # Validate required parameters
        required_params = ['cloud_id', 'api_key']
        for param in required_params:
            if param not in config_dict:
                raise ValueError(f"Missing required parameter: {param}")
        
        # Extract configuration with defaults
        cloud_id = config_dict['cloud_id']
        api_key = config_dict['api_key']
        index_name = config_dict.get('index_name', 'agent_memory')
        dimensions = int(config_dict.get('dimensions', 1024))
        
        # Initialize the Elasticsearch memory tool
        try:
            self.memory_tool = ElasticsearchMemoryTool(
                cloud_id=cloud_id,
                api_key=api_key,
                index_name=index_name,
                dimensions=dimensions
            )
            logger.info(
                f"Initialized Elasticsearch memory with index: {index_name}, "
                f"dimensions: {dimensions}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize Elasticsearch memory: {e}")
            raise
    
    def save(self, session_id: str, human_message: str, ai_message: str) -> None:
        """
        Save conversation to Elasticsearch memory.
        
        Args:
            session_id: Unique identifier for the conversation session
            human_message: The user's message
            ai_message: The AI's response
        """
        try:
            # Construct memory entry with context
            memory_text = f"User: {human_message}\nAssistant: {ai_message}"
            
            # Metadata for filtering and organization
            metadata = {
                "session_id": session_id,
                "type": "conversation",
                "timestamp": self._get_timestamp()
            }
            
            # Store in Elasticsearch
            result = self.memory_tool.add_memory(
                memory=memory_text,
                metadata=metadata
            )
            
            logger.debug(
                f"Saved conversation to Elasticsearch for session {session_id}: "
                f"{result.get('message', 'Success')}"
            )
            
        except Exception as e:
            logger.error(f"Failed to save memory for session {session_id}: {e}")
            raise
    
    def get_context(self, session_id: str, query: str | None = None) -> str:
        """
        Retrieve relevant context from Elasticsearch memory.
        
        Args:
            session_id: Unique identifier for the conversation session
            query: Optional search query for semantic retrieval
        
        Returns:
            Formatted string containing relevant conversation history
        """
        try:
            # Use query if provided, otherwise use session_id for filtering
            search_query = query if query else f"session:{session_id}"
            
            # Retrieve memories from Elasticsearch
            result = self.memory_tool.get_memories(
                query=search_query,
                n_results=5  # Configurable number of results
            )
            
            memories = result.get('memories', [])
            
            if not memories:
                logger.debug(f"No memories found for session {session_id}")
                return ""
            
            # Format memories for context
            context_parts = []
            for i, memory in enumerate(memories, 1):
                memory_text = memory.get('memory', '')
                context_parts.append(f"[Memory {i}]\n{memory_text}")
            
            context = "\n\n".join(context_parts)
            logger.debug(
                f"Retrieved {len(memories)} memories for session {session_id}"
            )
            
            return context
            
        except Exception as e:
            logger.error(
                f"Failed to retrieve context for session {session_id}: {e}"
            )
            # Return empty context on error to allow conversation to continue
            return ""
    
    def clear(self, session_id: str) -> None:
        """
        Clear memory for a specific session.
        
        Note: The strands-tools Elasticsearch memory tool clears ALL memories.
        For session-specific clearing, we would need to implement filtering,
        which is not currently supported by the underlying tool.
        
        Args:
            session_id: Unique identifier for the conversation session
        """
        try:
            logger.warning(
                f"Clearing ALL Elasticsearch memories (session-specific "
                f"clearing not supported by strands-tools). "
                f"Session ID: {session_id}"
            )
            
            result = self.memory_tool.clear_memories()
            
            logger.info(f"Cleared Elasticsearch memories: {result.get('message')}")
            
        except Exception as e:
            logger.error(f"Failed to clear memories for session {session_id}: {e}")
            raise
    
    @staticmethod
    def _get_timestamp() -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
