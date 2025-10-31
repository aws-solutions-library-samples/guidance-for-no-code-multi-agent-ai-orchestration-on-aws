"""
Vector store implementations for the ingestion module.
"""

from .factory import register_vector_store, get_vector_store
from .base import VectorStoreBase
from .elasticsearch_store import ElasticsearchVectorStore

# Import all vector store implementations here
# This allows them to register themselves with the factory

__all__ = [
    "register_vector_store",
    "get_vector_store",
    "VectorStoreBase",
    "ElasticsearchVectorStore"
]
