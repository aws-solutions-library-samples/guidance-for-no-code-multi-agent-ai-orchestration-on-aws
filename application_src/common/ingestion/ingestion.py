"""
Main ingestion module for document processing and vector storage using LangChain.
"""

import os
import uuid
import logging
import time
import json
import boto3
from typing import Dict, List, Any, Optional, Tuple, Callable

# LangChain imports
from langchain_community.document_loaders import S3FileLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from langchain_community.embeddings import BedrockEmbeddings

# Local imports
from vector_stores import get_vector_store

# Configure logging
logger = logging.getLogger(__name__)

class DocumentIngestion:
    """
    Main class for document ingestion, processing, and vector storage using LangChain.
    
    This class orchestrates the entire ingestion process:
    1. Loading documents from S3 using LangChain document loaders
    2. Chunking documents using LangChain text splitters
    3. Generating embeddings using Amazon Bedrock models
    4. Storing in vector database (Bedrock Knowledge Base or Elasticsearch)
    5. Managing metadata
    """
    
    def __init__(self, vector_db_type: str = "elasticsearch", config: Dict[str, Any] = None):
        """
        Initialize the document ingestion module.
        
        Args:
            vector_db_type: Type of vector database to use ("bedrock_kb" or "elasticsearch", default: "elasticsearch")
            config: Configuration parameters for the ingestion process
        """
        self.vector_db_type = vector_db_type
        self.config = self._validate_and_set_defaults(config or {})
        
        # Initialize AWS clients
        self.s3_client = boto3.client('s3', region_name=self.config["region"])
        self.bedrock_client = boto3.client('bedrock-runtime', region_name=self.config["region"])
        
        # Initialize embedding model
        self.embedding_model = BedrockEmbeddings(
            client=self.bedrock_client,
            model_id=self.config["embedding_model_id"]
        )
        
        # Initialize vector store
        self.vector_store = get_vector_store(vector_db_type, self.config, self.embedding_model)
        if not self.vector_store:
            raise ValueError(f"Failed to initialize vector store of type: {vector_db_type}")
        
        logger.info(f"Initialized DocumentIngestion with vector database: {vector_db_type}")
    
    def _validate_and_set_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate configuration and set default values.
        
        Args:
            config: User-provided configuration
            
        Returns:
            Validated configuration with defaults
        """
        # Create a new dict with defaults
        validated_config = {
            "region": "us-east-1",
            "embedding_model_id": "amazon.titan-embed-text-v1",
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "max_retries": 3,
            "retry_delay": 1,
            "metadata_bucket": config.get("metadata_bucket", None)
        }
        
        # Update with user-provided values
        validated_config.update(config)
        
        # Get validator for the vector DB type
        validator = self._get_vector_db_validator(self.vector_db_type)
        
        # Validate using the appropriate validator
        if validator:
            validator(validated_config)
        
        return validated_config

    def _get_vector_db_validator(self, vector_db_type: str) -> Optional[Callable]:
        """
        Get the validator function for a specific vector database type.
        
        Args:
            vector_db_type: Type of vector database
            
        Returns:
            Validator function for the specified vector database type
        """
        validators = {
            "bedrock_kb": self._validate_bedrock_kb_config,
            "elasticsearch": self._validate_elasticsearch_config,
            # Add new validators here as needed
        }
        
        return validators.get(vector_db_type)

    def _validate_bedrock_kb_config(self, config: Dict[str, Any]):
        """
        Validate Bedrock Knowledge Base configuration.
        
        If bedrock_kb_id is not provided, set a flag to create a new KB.
        """
        if "bedrock_kb_id" not in config:
            # Set flag to create a new KB instead of throwing an error
            config["create_new_kb"] = True
            project_name = os.environ.get('PROJECT_NAME', 'genai-box')
            config["bedrock_kb_name"] = config.get("bedrock_kb_name", f"{project_name}-kb-{uuid.uuid4().hex[:8]}")
            logger.info(f"No bedrock_kb_id provided, will create a new KB with name: {config['bedrock_kb_name']}")

    def _validate_elasticsearch_config(self, config: Dict[str, Any]):
        """
        Validate Elasticsearch configuration.
        
        If elasticsearch_index is not provided, set a default index name.
        """
        if "elasticsearch_endpoint" not in config:
            raise ValueError("elasticsearch_endpoint is required for Elasticsearch Cloud")
            
        if "elasticsearch_index" not in config:
            # Set default index name instead of throwing an error
            project_name = os.environ.get('PROJECT_NAME', 'genai-box')
            config["elasticsearch_index"] = f"{project_name}-documents-{uuid.uuid4().hex[:8]}"
            config["create_new_index"] = True
            logger.info(f"No elasticsearch_index provided, will create a new index: {config['elasticsearch_index']}")
    
    def ingest_document(self, bucket_name: str, object_key: str, 
                        metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Ingest a document from S3, process it, and store it in the vector database.
        
        Args:
            bucket_name: S3 bucket name
            object_key: S3 object key
            metadata: Optional metadata for the document
            
        Returns:
            Dictionary with ingestion results
        """
        try:
            # Generate IDs
            document_id = f"doc-{uuid.uuid4()}"
            ingestion_id = f"ing-{uuid.uuid4()}"
            
            # Initialize metadata
            if metadata is None:
                metadata = {}
            
            metadata.update({
                "document_id": document_id,
                "ingestion_id": ingestion_id,
                "bucket_name": bucket_name,
                "object_key": object_key,
                "status": "processing",
                "created_at": time.time(),
                "updated_at": time.time()
            })
            
            # Store initial metadata in S3
            self._store_metadata(document_id, metadata)
            
            # Special handling for Bedrock KB - direct S3 ingestion
            if self.vector_db_type == "bedrock_kb":
                self._update_status(document_id, "ingesting")
                
                # Use the BedrockKBVectorStore's direct S3 ingestion capability
                ingestion_result = self.vector_store.ingest_s3_object(bucket_name, object_key)
                
                # Update metadata with ingestion job info
                metadata.update({
                    "bedrock_kb_ingestion_job_id": ingestion_result["ingestion_job_id"],
                    "status": "ingestion_started"
                })
                self._store_metadata(document_id, metadata)
                
                return {
                    "document_id": document_id,
                    "ingestion_id": ingestion_id,
                    "status": "ingestion_started",
                    "bedrock_kb_ingestion_job_id": ingestion_result["ingestion_job_id"],
                    "metadata": metadata
                }
            
            # For other vector stores, process the document using LangChain
            # Update status
            self._update_status(document_id, "loading")
            
            # Load document using LangChain's S3FileLoader
            loader = S3FileLoader(bucket_name, object_key, region_name=self.config["region"])
            documents = loader.load()
            
            if not documents:
                raise ValueError(f"No content extracted from document: {object_key}")
            
            # Extract document content and update metadata
            document_content = documents[0].page_content
            doc_metadata = documents[0].metadata
            
            # Update metadata with document info
            metadata.update(doc_metadata)
            self._store_metadata(document_id, metadata)
            
            # Update status
            self._update_status(document_id, "chunking")
            
            # Chunk document using LangChain's RecursiveCharacterTextSplitter
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=self.config["chunk_size"],
                chunk_overlap=self.config["chunk_overlap"],
                length_function=len,
                separators=["\n\n", "\n", " ", ""]
            )
            
            chunks = text_splitter.split_text(document_content)
            
            # Create LangChain documents from chunks
            langchain_docs = []
            for i, chunk in enumerate(chunks):
                chunk_metadata = metadata.copy()
                chunk_metadata["chunk_id"] = f"{document_id}-chunk-{i}"
                chunk_metadata["chunk_index"] = i
                langchain_docs.append(Document(page_content=chunk, metadata=chunk_metadata))
            
            # Update status
            self._update_status(document_id, "storing")
            
            # Store in vector database
            self.vector_store.add_documents(langchain_docs)
            
            # Update status
            self._update_status(document_id, "completed")
            
            return {
                "document_id": document_id,
                "ingestion_id": ingestion_id,
                "status": "completed",
                "chunks": len(chunks),
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Error ingesting document {object_key}: {str(e)}")
            
            if 'document_id' in locals():
                self._update_status(document_id, "failed", error=str(e))
                
                return {
                    "document_id": document_id,
                    "ingestion_id": ingestion_id if 'ingestion_id' in locals() else None,
                    "status": "failed",
                    "error": str(e)
                }
            else:
                raise
    
    def _store_metadata(self, document_id: str, metadata: Dict[str, Any]):
        """
        Store document metadata in S3.
        
        Args:
            document_id: Document ID
            metadata: Document metadata
        """
        try:
            # Store metadata in S3
            metadata_bucket = self.config.get("metadata_bucket")
            
            if metadata_bucket:
                metadata_key = f"metadata/{document_id}.json"
                self.s3_client.put_object(
                    Bucket=metadata_bucket,
                    Key=metadata_key,
                    Body=json.dumps(metadata),
                    ContentType="application/json"
                )
                logger.info(f"Stored metadata for document {document_id} in S3")
        except Exception as e:
            logger.warning(f"Error storing metadata for document {document_id}: {str(e)}")
    
    def _update_status(self, document_id: str, status: str, error: str = None):
        """
        Update the status of a document ingestion.
        
        Args:
            document_id: Document ID
            status: New status
            error: Optional error message
        """
        try:
            # Get existing metadata
            metadata = self.get_document_metadata(document_id)
            
            if metadata:
                # Update status
                metadata["status"] = status
                metadata["updated_at"] = time.time()
                
                if error:
                    metadata["error"] = error
                
                # Store updated metadata
                self._store_metadata(document_id, metadata)
                
            logger.info(f"Document {document_id} status updated to {status}")
        except Exception as e:
            logger.warning(f"Error updating status for document {document_id}: {str(e)}")
    
    def get_ingestion_status(self, ingestion_id: str) -> Dict[str, Any]:
        """
        Get the status of a document ingestion.
        
        Args:
            ingestion_id: Ingestion ID
            
        Returns:
            Dictionary with ingestion status
        """
        try:
            # Get metadata by ingestion ID
            metadata_bucket = self.config.get("metadata_bucket")
            
            if not metadata_bucket:
                return {"status": "unknown", "error": "No metadata bucket configured"}
            
            # List objects with prefix to find the document with this ingestion ID
            response = self.s3_client.list_objects_v2(
                Bucket=metadata_bucket,
                Prefix="metadata/"
            )
            
            for obj in response.get("Contents", []):
                try:
                    metadata_obj = self.s3_client.get_object(
                        Bucket=metadata_bucket,
                        Key=obj["Key"]
                    )
                    metadata = json.loads(metadata_obj["Body"].read().decode("utf-8"))
                    
                    if metadata.get("ingestion_id") == ingestion_id:
                        # For Bedrock KB, check the ingestion job status
                        if self.vector_db_type == "bedrock_kb" and metadata.get("status") == "ingestion_started":
                            if "bedrock_kb_ingestion_job_id" in metadata:
                                job_status = self.vector_store.get_ingestion_job_status(
                                    metadata["bedrock_kb_ingestion_job_id"]
                                )
                                
                                # Update metadata with job status
                                if job_status["status"] in ["COMPLETE", "FAILED"]:
                                    metadata["status"] = "completed" if job_status["status"] == "COMPLETE" else "failed"
                                    metadata["updated_at"] = time.time()
                                    if job_status["status"] == "FAILED":
                                        metadata["error"] = job_status["error_message"]
                                    
                                    # Store updated metadata
                                    self._store_metadata(metadata["document_id"], metadata)
                                
                                # Add job status to metadata
                                metadata["job_status"] = job_status
                        
                        return metadata
                except:
                    continue
            
            return {"status": "not_found", "ingestion_id": ingestion_id}
            
        except Exception as e:
            logger.error(f"Error getting ingestion status for {ingestion_id}: {str(e)}")
            return {"status": "error", "error": str(e), "ingestion_id": ingestion_id}
    
    def get_document_metadata(self, document_id: str) -> Dict[str, Any]:
        """
        Get metadata for a document.
        
        Args:
            document_id: Document ID
            
        Returns:
            Dictionary with document metadata
        """
        try:
            metadata_bucket = self.config.get("metadata_bucket")
            
            if not metadata_bucket:
                return {"status": "unknown", "error": "No metadata bucket configured"}
            
            metadata_key = f"metadata/{document_id}.json"
            
            try:
                metadata_obj = self.s3_client.get_object(
                    Bucket=metadata_bucket,
                    Key=metadata_key
                )
                metadata = json.loads(metadata_obj["Body"].read().decode("utf-8"))
                return metadata
            except self.s3_client.exceptions.NoSuchKey:
                return {"status": "not_found", "document_id": document_id}
            
        except Exception as e:
            logger.error(f"Error getting metadata for document {document_id}: {str(e)}")
            return {"status": "error", "error": str(e), "document_id": document_id}
    
    def delete_document(self, document_id: str) -> Dict[str, Any]:
        """
        Delete a document from the vector database and metadata.
        
        Args:
            document_id: Document ID
            
        Returns:
            Dictionary with deletion status
        """
        try:
            # Get document metadata
            metadata = self.get_document_metadata(document_id)
            
            if metadata.get("status") == "not_found":
                return {"status": "not_found", "document_id": document_id}
            
            # Delete from vector database
            delete_success = self.vector_store.delete(document_id)
            
            if not delete_success and self.vector_db_type == "bedrock_kb":
                logger.warning("Direct document deletion not supported for Bedrock KB")
            
            # Delete metadata
            try:
                metadata_bucket = self.config.get("metadata_bucket")
                
                if metadata_bucket:
                    metadata_key = f"metadata/{document_id}.json"
                    self.s3_client.delete_object(
                        Bucket=metadata_bucket,
                        Key=metadata_key
                    )
                    logger.info(f"Deleted metadata for document {document_id}")
            except Exception as e:
                logger.warning(f"Error deleting metadata for document {document_id}: {str(e)}")
            
            return {
                "document_id": document_id,
                "status": "deleted"
            }
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {str(e)}")
            return {
                "document_id": document_id,
                "status": "error",
                "error": str(e)
            }
    
    def query_similar(self, query: str, top_k: int = 10, 
                      filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Query the vector database for similar documents.
        
        Args:
            query: Query text
            top_k: Number of results to return
            filters: Optional filters for the query
            
        Returns:
            List of similar documents with metadata
        """
        try:
            # Use the vector store's similarity search with score
            docs_with_scores = self.vector_store.similarity_search_with_score(
                query=query,
                k=top_k,
                filter=filters
            )
            
            # Format results
            results = []
            for doc, score in docs_with_scores:
                results.append({
                    "text": doc.page_content,
                    "score": score,
                    "document_id": doc.metadata.get("document_id", ""),
                    "metadata": doc.metadata
                })
            
            return results
                
        except Exception as e:
            logger.error(f"Error querying similar documents: {str(e)}")
            return []
