"""
Elasticsearch vector store implementation.
"""

import logging
from typing import Dict, List, Any, Optional, Tuple

from langchain.schema import Document
from langchain.embeddings.base import Embeddings
# Use langchain_community instead of langchain-elasticsearch
from langchain_community.vectorstores import ElasticsearchStore

from .base import VectorStoreBase
from .factory import register_vector_store

# Configure logging
logger = logging.getLogger(__name__)

@register_vector_store("elasticsearch")
class ElasticsearchVectorStore(VectorStoreBase):
    """Elasticsearch vector store implementation."""
    
    def __init__(self, config: Dict[str, Any], embedding_model: Embeddings):
        """
        Initialize Elasticsearch vector store.
        
        Args:
            config: Configuration parameters
            embedding_model: Embedding model to use
        """
        self.config = config
        self.embedding_model = embedding_model
        
        # Initialize ElasticsearchStore
        es_params = {
            "es_url": config["elasticsearch_endpoint"],
            "index_name": config["elasticsearch_index"],
            "embedding": embedding_model,
            "distance_strategy": "COSINE"  # Use string instead of enum
        }
        
        # Add authentication parameters if provided
        if "elasticsearch_username" in config and "elasticsearch_password" in config:
            es_params["es_user"] = config["elasticsearch_username"]
            es_params["es_password"] = config["elasticsearch_password"]
        elif "elasticsearch_api_key" in config:
            es_params["es_api_key"] = config["elasticsearch_api_key"]
        
        self.store = ElasticsearchStore(**es_params)
        
        logger.info(f"Initialized Elasticsearch vector store with index: {config['elasticsearch_index']}")
    
    def add_documents(self, documents: List[Document]) -> Any:
        """
        Add documents to the vector store.
        
        Args:
            documents: List of LangChain Document objects
            
        Returns:
            Implementation-specific result
        """
        try:
            result = self.store.add_documents(documents)
            logger.info(f"Added {len(documents)} documents to Elasticsearch")
            return result
        except Exception as e:
            logger.error(f"Error adding documents to Elasticsearch: {str(e)}")
            raise
    
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
        try:
            return self.store.similarity_search(query, k=k, filter=filter)
        except Exception as e:
            logger.error(f"Error performing similarity search: {str(e)}")
            return []
    
    def similarity_search_with_score(self, query: str, k: int = 4, filter: Optional[Dict[str, Any]] = None) -> List[Tuple[Document, float]]:
        """
        Perform similarity search with scores.
        
        Args:
            query: Query text
            k: Number of results to return
            filter: Optional filters for the query
            
        Returns:
            List of tuples (document, score)
        """
        try:
            return self.store.similarity_search_with_score(query, k=k, filter=filter)
        except Exception as e:
            logger.error(f"Error performing similarity search with score: {str(e)}")
            return []
    
    def delete(self, document_id: str) -> bool:
        """
        Delete documents by ID.
        
        Args:
            document_id: Document ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        try:
            es_client = self.store.client
            es_client.delete_by_query(
                index=self.config["elasticsearch_index"],
                body={
                    "query": {
                        "term": {
                            "metadata.document_id": document_id
                        }
                    }
                }
            )
            logger.info(f"Deleted document {document_id} from Elasticsearch")
            return True
        except Exception as e:
            logger.error(f"Error deleting document from Elasticsearch: {str(e)}")
            return False
