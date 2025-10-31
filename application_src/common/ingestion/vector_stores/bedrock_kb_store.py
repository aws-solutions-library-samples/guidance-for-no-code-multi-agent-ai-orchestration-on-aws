"""
Amazon Bedrock Knowledge Base vector store implementation.
"""

import logging
import uuid
import boto3
import time
from typing import Dict, List, Any, Optional, Tuple

from langchain.schema import Document
from langchain.embeddings.base import Embeddings

from .base import VectorStoreBase
from .factory import register_vector_store

# Configure logging
logger = logging.getLogger(__name__)

@register_vector_store("bedrock_kb")
class BedrockKBVectorStore(VectorStoreBase):
    """Amazon Bedrock Knowledge Base vector store implementation."""
    
    def __init__(self, config: Dict[str, Any], embedding_model: Embeddings):
        """
        Initialize Bedrock KB vector store.
        
        Args:
            config: Configuration parameters
            embedding_model: Embedding model to use
        """
        self.config = config
        self.embedding_model = embedding_model
        
        # Initialize AWS clients
        self.bedrock_agent_client = boto3.client('bedrock-agent', region_name=config["region"])
        self.bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime', region_name=config["region"])
        
        # Check if we need to create a new KB
        if "bedrock_kb_id" not in config or not config["bedrock_kb_id"]:
            self._create_knowledge_base()
        else:
            logger.info(f"Using existing Bedrock Knowledge Base with ID: {config['bedrock_kb_id']}")
    
    def _create_knowledge_base(self):
        """Create a new Bedrock Knowledge Base."""
        try:
            project_name = os.environ.get('PROJECT_NAME', 'genai-box')
            kb_name = self.config.get("bedrock_kb_name", f"{project_name}-kb-{uuid.uuid4().hex[:8]}")
            
            # Check if role_arn is provided
            if "role_arn" not in self.config:
                raise ValueError("role_arn is required to create a new Bedrock Knowledge Base")
            
            # Following the pattern from the AWS Samples repository
            # https://github.com/aws-samples/amazon-bedrock-samples/blob/main/rag/knowledge-bases/features-examples/utils/knowledge_base.py
            
            # Create a new Knowledge Base with minimal configuration
            # Let AWS create the OpenSearch Serverless collection automatically
            response = self.bedrock_agent_client.create_knowledge_base(
                name=kb_name,
                roleArn=self.config["role_arn"],
                knowledgeBaseConfiguration={
                    'type': 'VECTOR',
                    'vectorKnowledgeBaseConfiguration': {
                        'embeddingModelArn': f"arn:aws:bedrock:{self.config['region']}::foundation-model/{self.config['embedding_model_id']}"
                    }
                },
                storageConfiguration={
                    'type': 'OPENSEARCH_SERVERLESS',
                    'opensearchServerlessConfiguration': {
                        'fieldMapping': {
                            'metadataField': 'metadata',
                            'textField': 'text',
                            'vectorField': 'vector'
                        },
                        'vectorIndexName': 'vector-index'
                    }
                }
            )
            
            self.config["bedrock_kb_id"] = response["knowledgeBase"]["knowledgeBaseId"]
            logger.info(f"Created new Bedrock Knowledge Base with ID: {self.config['bedrock_kb_id']}")
            
            # Wait for the Knowledge Base to become active - using exponential backoff with timeout
            status = "CREATING"
            max_attempts = 60  # Maximum 5 minutes (60 attempts * 5 seconds)
            attempt = 0
            wait_time = 2  # Start with 2 seconds
            
            while status == "CREATING" and attempt < max_attempts:
                time.sleep(wait_time)  # nosemgrep: arbitrary-sleep
                attempt += 1
                
                # Exponential backoff: increase wait time up to 10 seconds max
                wait_time = min(wait_time * 1.2, 10)
                
                kb_info = self.bedrock_agent_client.get_knowledge_base(
                    knowledgeBaseId=self.config["bedrock_kb_id"]
                )
                
                status = kb_info["knowledgeBase"]["status"]
                logger.info(f"Knowledge Base status: {status} (attempt {attempt}/{max_attempts})")
                
                if status == "FAILED":
                    failure_reasons = kb_info["knowledgeBase"].get("failureReasons", [])
                    logger.error(f"Knowledge Base creation failed: {failure_reasons}")
                    raise ValueError(f"Knowledge Base creation failed: {failure_reasons}")
            
            if status == "CREATING":
                raise TimeoutError("Knowledge Base creation timed out after 5 minutes")
            
            # Get the storage configuration details
            storage_config = kb_info["knowledgeBase"]["storageConfiguration"]
            if "opensearchServerlessConfiguration" in storage_config:
                collection_arn = storage_config["opensearchServerlessConfiguration"]["collectionArn"]
                logger.info(f"Knowledge Base using OpenSearch Serverless collection: {collection_arn}")
            
            return self.config["bedrock_kb_id"]
        except Exception as e:
            logger.error(f"Error deleting existing knowledge base: {str(e)}")  # nosemgrep: logging-error-without-handling
            raise
    
    def _ensure_data_source(self, bucket_name: str) -> str:
        """
        Ensure a data source exists for the given S3 bucket.
        
        Args:
            bucket_name: S3 bucket name
            
        Returns:
            Data source ID
        """
        try:
            # Check if we already have a data source for this bucket
            data_source_id = self.config.get("bedrock_data_source_id")
            
            if data_source_id:
                return data_source_id
            
            # Create a new data source
            response = self.bedrock_agent_client.create_data_source(
                knowledgeBaseId=self.config["bedrock_kb_id"],
                name=f"s3-data-source-{uuid.uuid4().hex[:8]}",
                description="Data source created by GenAI-in-a-Box ingestion module",
                dataSourceConfiguration={
                    'type': 'S3',
                    's3Configuration': {
                        'bucketArn': f"arn:aws:s3:::{bucket_name}"
                    }
                }
            )
            
            data_source_id = response["dataSource"]["dataSourceId"]
            self.config["bedrock_data_source_id"] = data_source_id
            logger.info(f"Created new Bedrock KB data source with ID: {data_source_id}")
            
            return data_source_id
        except Exception as e:
            logger.error(f"Error creating knowledge base: {str(e)}")  # nosemgrep: logging-error-without-handling
            raise
    
    def add_documents(self, documents: List[Document]) -> Any:
        """
        Add documents to the vector store.
        
        Note: This method is not directly applicable for Bedrock KB.
        Documents should be ingested from S3 using the ingest_s3_object method.
        
        Args:
            documents: List of LangChain Document objects
            
        Returns:
            Implementation-specific result
        """
        logger.warning("Direct document addition not supported for Bedrock KB. Use ingest_s3_object instead.")
        return None
    
    def ingest_s3_object(self, bucket_name: str, object_key: str) -> Dict[str, Any]:
        """
        Ingest a document from S3 into Bedrock KB.
        
        Args:
            bucket_name: S3 bucket name
            object_key: S3 object key
            
        Returns:
            Dictionary with ingestion job details
        """
        try:
            # Ensure we have a data source for this bucket
            data_source_id = self._ensure_data_source(bucket_name)
            
            # Start ingestion job - using the correct API parameters
            # Following the pattern from the notebook
            response = self.bedrock_agent_client.start_ingestion_job(
                knowledgeBaseId=self.config["bedrock_kb_id"],
                dataSourceId=data_source_id
            )
            
            ingestion_job_id = response["ingestionJob"]["ingestionJobId"]
            logger.info(f"Started Bedrock KB ingestion job with ID: {ingestion_job_id}")
            
            # Wait for the ingestion job to complete - using exponential backoff with timeout
            status = "STARTING"
            max_attempts = 120  # Maximum 10 minutes (120 attempts)
            attempt = 0
            wait_time = 2  # Start with 2 seconds
            
            while status not in ["COMPLETE", "FAILED", "STOPPED"] and attempt < max_attempts:
                time.sleep(wait_time)  # nosemgrep: arbitrary-sleep
                attempt += 1
                
                # Exponential backoff: increase wait time up to 15 seconds max for longer operations
                wait_time = min(wait_time * 1.1, 15)
                
                job_status = self.get_ingestion_job_status(ingestion_job_id)
                status = job_status["status"]
                logger.info(f"Ingestion job status: {status} (attempt {attempt}/{max_attempts})")
            
            if status not in ["COMPLETE", "FAILED", "STOPPED"]:
                logger.warning("Ingestion job polling timed out - job may still be running")
                status = "TIMEOUT"
            
            if status == "COMPLETE":
                logger.info("Ingestion job completed successfully")
            else:
                logger.error(f"Ingestion job failed: {job_status.get('error_message', '')}")
            
            return {
                "ingestion_job_id": ingestion_job_id,
                "knowledge_base_id": self.config["bedrock_kb_id"],
                "data_source_id": data_source_id,
                "bucket_name": bucket_name,
                "object_key": object_key,
                "status": status
            }
        except Exception as e:
            logger.error(f"Error creating data source: {str(e)}")  # nosemgrep: logging-error-without-handling
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
            # Following the pattern from the notebook
            retrieval_config = {
                'vectorSearchConfiguration': {
                    'numberOfResults': k
                }
            }
            
            # Add filter if provided
            if filter and len(filter) > 0:
                filter_parts = []
                for key, value in filter.items():
                    if isinstance(value, str):
                        filter_parts.append(f"{key} = '{value}'")
                    else:
                        filter_parts.append(f"{key} = {value}")
                
                if filter_parts:
                    filter_string = " AND ".join(filter_parts)
                    retrieval_config['vectorSearchConfiguration']['filter'] = filter_string
            
            # Perform retrieval using the runtime client
            response = self.bedrock_agent_runtime_client.retrieve(
                knowledgeBaseId=self.config["bedrock_kb_id"],
                retrievalQuery={
                    'text': query
                },
                retrievalConfiguration=retrieval_config
            )
            
            # Convert to LangChain documents
            documents = []
            for result in response.get("retrievalResults", []):
                text = result.get("content", {}).get("text", "")
                metadata = result.get("metadata", {})
                metadata["score"] = result.get("score", 0)
                metadata["source"] = result.get("location", {}).get("s3Location", {}).get("uri", "")
                
                documents.append(Document(page_content=text, metadata=metadata))
            
            return documents
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
            # Get documents from similarity search
            documents = self.similarity_search(query, k, filter)
            
            # Extract scores and create tuples
            results = []
            for doc in documents:
                score = doc.metadata.pop("score", 0)
                results.append((doc, score))
            
            return results
        except Exception as e:
            logger.error(f"Error performing similarity search with score: {str(e)}")
            return []
    
    def delete(self, document_id: str) -> bool:
        """
        Delete documents by ID.
        
        Note: Direct document deletion is not supported for Bedrock KB.
        
        Args:
            document_id: Document ID to delete
            
        Returns:
            True if successful, False otherwise
        """
        logger.warning("Direct document deletion not supported for Bedrock KB")
        return False
    
    def get_ingestion_job_status(self, ingestion_job_id: str) -> Dict[str, Any]:
        """
        Get the status of an ingestion job.
        
        Args:
            ingestion_job_id: Ingestion job ID
            
        Returns:
            Dictionary with job status
        """
        try:
            response = self.bedrock_agent_client.get_ingestion_job(
                knowledgeBaseId=self.config["bedrock_kb_id"],
                dataSourceId=self.config["bedrock_data_source_id"],
                ingestionJobId=ingestion_job_id
            )
            
            return {
                "status": response["ingestionJob"]["status"],
                "statistics": response["ingestionJob"].get("statistics", {}),
                "error_message": response["ingestionJob"].get("failureReason", ""),
                "created_at": response["ingestionJob"].get("startTime", ""),
                "completed_at": response["ingestionJob"].get("endTime", "")
            }
        except Exception as e:
            logger.error(f"Error getting ingestion job status: {str(e)}")
            return {"status": "ERROR", "error_message": str(e)}
