"""
Factory for creating vector store instances.
"""

import logging
import importlib
import os
from typing import Dict, Any, Optional, Callable, Type

from langchain.embeddings.base import Embeddings
from .base import VectorStoreBase

# Configure logging
logger = logging.getLogger(__name__)

# Registry for vector store classes
VECTOR_STORE_REGISTRY = {}

def register_vector_store(vector_db_type: str):
    """
    Decorator to register a vector store class.
    
    Args:
        vector_db_type: Type identifier for the vector store
        
    Returns:
        Decorator function
    """
    def decorator(cls):
        VECTOR_STORE_REGISTRY[vector_db_type] = cls
        logger.info(f"Registered vector store: {vector_db_type}")
        return cls
    return decorator

def get_vector_store(vector_db_type: str, config: Dict[str, Any], 
                     embedding_model: Optional[Embeddings] = None) -> Optional[VectorStoreBase]:
    """
    Get a vector store instance based on type.
    
    Args:
        vector_db_type: Type of vector store
        config: Configuration parameters
        embedding_model: Embedding model to use
        
    Returns:
        Vector store instance
    """
    # Ensure all vector store implementations are imported
    _import_vector_stores()
    
    if vector_db_type not in VECTOR_STORE_REGISTRY:
        logger.error(f"Unsupported vector store type: {vector_db_type}")
        return None
    
    try:
        vector_store_class = VECTOR_STORE_REGISTRY[vector_db_type]
        return vector_store_class(config, embedding_model)
    except Exception as e:
        logger.error(f"Error creating vector store: {str(e)}")
        return None

def _import_vector_stores():
    """
    Import all vector store implementations in the package.
    
    This ensures that all vector stores are registered with the factory.
    Uses a whitelist approach for security.
    """
    # Whitelist of allowed vector store modules to prevent arbitrary code execution
    ALLOWED_MODULES = [
        'bedrock_kb_store',
        'elasticsearch_store',
        'template_store'
    ]
    
    for module_name in ALLOWED_MODULES:
        try:
            # Import the module using whitelisted module names only
            importlib.import_module(f".{module_name}", package=__package__)
        except ImportError as e:
            logger.warning(f"Error importing vector store module {module_name}: {str(e)}")
