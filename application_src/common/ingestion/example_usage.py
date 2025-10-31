"""
Example usage of the Document Ingestion module.
"""

import json
import logging
from ingestion import DocumentIngestion

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_config(config_file):
    """Load configuration from a JSON file."""
    with open(config_file, 'r', encoding='utf-8') as f:
        config_data = json.load(f)
    
    # Extract the main config and documents from the config file
    config = {k: v for k, v in config_data.items() if k not in ['documents', 'queries']}
    documents = config_data.get('documents', [])
    queries = config_data.get('queries', [])
    
    return config, documents, queries

def bedrock_kb_example():
    """Example usage with Bedrock Knowledge Base."""
    # Load configuration from test file
    config, documents, queries = load_config('config/bedrock_kb_test.json')
    
    # Initialize with Bedrock Knowledge Base
    ingestion = DocumentIngestion(
        vector_db_type="bedrock_kb",
        config=config
    )
    
    # Ingest a document
    if documents:
        document = documents[0]
        result = ingestion.ingest_document(
            bucket_name=document['bucket_name'],
            object_key=document['object_key'],
            metadata=document.get('metadata', {})
        )
        
        logger.info(f"Document ingested with ID: {result['document_id']}")
        logger.info(f"Ingestion ID: {result['ingestion_id']}")
        logger.info(f"Status: {result['status']}")
        
        # Get ingestion status
        if result['status'] == 'ingestion_started':
            status = ingestion.get_ingestion_status(result["ingestion_id"])
            logger.info(f"Current status: {status['status']}")
    
    # Query similar documents
    if queries:
        query = queries[0]
        query_results = ingestion.query_similar(
            query=query['text'],
            top_k=query.get('top_k', 3),
            filters=query.get('filters', {})
        )
        
        logger.info(f"Found {len(query_results)} results:")
        for i, result in enumerate(query_results):
            logger.info(f"{i+1}. Score: {result['score']:.4f}")
            logger.info(f"   Text: {result['text'][:200]}...")
            logger.info(f"   Document ID: {result['document_id']}")

def elasticsearch_example():
    """Example usage with Elasticsearch."""
    # Load configuration from test file
    config, documents, queries = load_config('config/elasticsearch_test.json')
    
    # Initialize with Elasticsearch
    ingestion = DocumentIngestion(
        vector_db_type="elasticsearch",
        config=config
    )
    
    # Ingest a document
    if documents:
        document = documents[0]
        result = ingestion.ingest_document(
            bucket_name=document['bucket_name'],
            object_key=document['object_key'],
            metadata=document.get('metadata', {})
        )
        
        logger.info(f"Document ingested with ID: {result['document_id']}")
        logger.info(f"Ingestion ID: {result['ingestion_id']}")
        logger.info(f"Status: {result['status']}")
    
    # Query similar documents
    if queries:
        query = queries[0]
        query_results = ingestion.query_similar(
            query=query['text'],
            top_k=query.get('top_k', 3),
            filters=query.get('filters', {})
        )
        
        logger.info(f"Found {len(query_results)} results:")
        for i, result in enumerate(query_results):
            logger.info(f"{i+1}. Score: {result['score']:.4f}")
            logger.info(f"   Text: {result['text'][:200]}...")
            logger.info(f"   Document ID: {result['document_id']}")

if __name__ == "__main__":
    # Choose which example to run
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "elasticsearch":
        elasticsearch_example()
    else:
        bedrock_kb_example()
