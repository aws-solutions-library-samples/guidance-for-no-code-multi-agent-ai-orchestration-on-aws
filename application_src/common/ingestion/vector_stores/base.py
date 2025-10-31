"""
Base class for vector store implementations.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from langchain.schema import Document
from langchain.embeddings.base import Embeddings

class VectorStoreBase(ABC):
    """
    Abstract base class for vector store implementations.
    
    All vector store implementations should inherit from this class
    and implement its abstract methods.
    """
    
    @abstractmethod
    def __init__(self, config: Dict[str, Any], embedding_model: Embeddings):
        """
        Initialize the vector store.
        
        Args:
            config: Configuration parameters
            embedding_model: Embedding model to use
        """
        pass
    
    @abstractmethod
    def add_documents(self, documents: List[Document]) -> Any:
        """
        Add documents to the vector store.
        
        Args:
            documents: List of LangChain Document objects
            
        Returns:
            Implementation-specific result
        """
        pass
    
    @abstractmethod
    def similarity_search(self, query: str, k: int = 4, filter: Optional[Dict[str, Any]] = None) -> List[Document]:
        """
        Perform similarity search.
        
        Args:
            query: Query text
            k: Number of results to return
            filter: Optional filters for the query
            
        Returns:
            List of similar documents
        """
        pass
    
    @abstractmethod
    def similarity_search_with_score(self, query: str, k: int = 4, filter: Optional[Dict[str, Any]] = None) -> List[tuple]:
        """
        Perform similarity search with scores.
        
        Args:
            query: Query text
            k: Number of results to return
            filter: Optional filters for the query
            
        Returns:
            List of tuples (document, score)
        """
        pass
    
    @abstractmethod
    def delete(self, document_id: str) -> bool:
        """
        Delete documents by ID.
        
        Args:
            document_id: Document ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        pass
