"""
Direct Elasticsearch knowledge base provider for GenAI-In-A-Box agent.
This module provides a knowledge base provider using direct Elasticsearch client with Langchain.
"""

import traceback
import re
from typing import List, Dict, Any
import boto3
from strands import tool
from ..base import BaseKnowledgeBaseProvider

# Import Langchain components with error handling
try:
    from langchain_community.vectorstores import ElasticsearchStore
    from langchain_community.embeddings import BedrockEmbeddings
    try:
        # Try new import path first (langchain-core)
        from langchain_core.documents import Document
    except ImportError:
        # Fallback to old import path
        from langchain.schema.document import Document
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Langchain import failed in elastic.py: {e}")
    ElasticsearchStore = None
    BedrockEmbeddings = None
    Document = None
    LANGCHAIN_AVAILABLE = False

class ElasticKnowledgeBaseProvider(BaseKnowledgeBaseProvider):
    """Knowledge base provider for Elasticsearch using direct client with Langchain."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Elasticsearch knowledge base provider."""
        super().__init__(config)
        self.provider_name = "elasticsearch"
        self.es_client = None
        self.retriever = None
        self.is_initialized = False
        self.index_name = None
        self.embedding_model = None
    
    def initialize(self) -> List:
        """Initialize the Elasticsearch knowledge base provider and get the tools."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses # is_initialized is a boolean attribute, not a function
            return self.tools
            
        try:
            provider_config = self.get_provider_config()
            
            # Get Elasticsearch credentials
            es_url = provider_config.get("es_url", "")
            es_api_key = provider_config.get("es_api_key", "")
            self.index_name = provider_config.get("index_name", "")
            
            # Get embedding model ID from config
            from config import Config
            config_instance = Config(self.config.get("agent_name", "qa_agent"))
            model_config = config_instance.get_model_config()
            embedding_model_id = model_config.get("embedding_model_id", "amazon.titan-embed-text-v2:0")
            
            if not es_url:
                print("Error: Elasticsearch URL is required")
                return []
            
            # Validate URL format    
            if not self._validate_elasticsearch_url(es_url):
                print(f"Error: Elasticsearch URL '{es_url}' must include scheme, host, and port (e.g., 'https://localhost:9200')")
                return []
                
            if not es_api_key:
                print("Error: Elasticsearch API key is required") 
                return []
                
            if not self.index_name:
                print("Error: Elasticsearch index name is required")
                return []
            
            print(f"Initializing Elasticsearch provider with URL: {es_url}, index: {self.index_name}")
            
            # Extract cloud ID from URL if it's an Elastic Cloud URL
            cloud_id = None
            if "elastic.cloud" in es_url:
                # Extract the cloud ID from the URL
                # Format: https://{deployment_name}-{random_id}.{region}.aws.elastic.cloud:{port}
                match = re.match(r'https://([^.]+)-([^.]+)\.([^.]+)\.aws\.elastic\.cloud', es_url)
                if match:
                    deployment_name = match.group(1)
                    random_id = match.group(2)
                    region = match.group(3)
                    cloud_id = f"{deployment_name}:{random_id}"
                    print(f"Extracted cloud ID: {cloud_id}")
            
            # Initialize Bedrock embeddings
            self.embedding_model = BedrockEmbeddings(
                model_id=embedding_model_id,
                client=boto3.client("bedrock-runtime")
            )
            print(f"Initialized Bedrock embeddings with model: {embedding_model_id}")
            
            # Initialize Elasticsearch vector store
            if cloud_id:
                # Use cloud ID for Elastic Cloud
                vector_store = ElasticsearchStore(
                    index_name=self.index_name,
                    embedding=self.embedding_model,
                    es_cloud_id=cloud_id,
                    es_api_key=es_api_key
                )
            else:
                # Use URL for self-hosted Elasticsearch
                vector_store = ElasticsearchStore(
                    index_name=self.index_name,
                    embedding=self.embedding_model,
                    es_url=es_url,
                    es_api_key=es_api_key
                )
            
            # Create retriever
            self.retriever = vector_store.as_retriever(
                search_kwargs={"k": 5}  # Return top 5 results
            )
            
            print(f"Successfully initialized Elasticsearch retriever for index: {self.index_name}")
            
            # Create tools
            self._create_tools()
            self.is_initialized = True
            
            print(f"Direct Elasticsearch knowledge base provider initialized with {len(self.tools)} tools")
            for tool_func in self.tools:
                print(f"  - {tool_func.__name__ if hasattr(tool_func, '__name__') else str(tool_func)}")
            
            return self.tools
            
        except Exception as e:
            print(f"Error initializing direct Elasticsearch knowledge base provider: {str(e)}")
            traceback.print_exc()
            self.close()
            return []
    
    def _create_tools(self):
        """Create Elasticsearch search tools using Langchain retriever."""
        
        @tool
        def retriever_elasticsearch_semantic_search(query: str, top_k: int = 5) -> str:
            """Perform semantic search in Elasticsearch using embeddings."""
            try:
                print(f"Performing semantic search in index '{self.index_name}' for: {query}")
                
                # Override the default k value by updating search_kwargs
                self.retriever.search_kwargs["k"] = top_k
                
                # Use invoke() method for new langchain versions, with fallback to old method
                try:
                    docs = self.retriever.invoke(query)
                except AttributeError:
                    # Fallback to old method name for compatibility
                    docs = self.retriever.get_relevant_documents(query)
                
                if not docs:
                    return f"No semantic search results found for query: '{query}'"
                
                response = f"Found {len(docs)} semantically relevant documents for query: '{query}'\n\n"
                
                for i, doc in enumerate(docs, 1):
                    response += f"{i}. Content: {doc.page_content}\n"
                    if doc.metadata:
                        response += f"   Metadata: {doc.metadata}\n"
                    response += "\n"
                
                return response
                
            except Exception as e:
                error_msg = f"Error performing semantic search: {str(e)}"
                print(error_msg)
                traceback.print_exc()
                return error_msg
        
        print("Creating Elasticsearch search tools:")
        print(f"  1. retriever_elasticsearch_semantic_search: {retriever_elasticsearch_semantic_search}")
        
        self.tools = [retriever_elasticsearch_semantic_search]
    
    def _validate_elasticsearch_url(self, url: str) -> bool:
        """Validate that the Elasticsearch URL has the required components."""
        try:
            if not url or not url.strip():
                return False
                
            # Basic URL format check
            url_pattern = r'^https?://[^/]+:\d+/?.*$'
            if re.match(url_pattern, url):
                return True
                
            # Check for Elastic Cloud format
            cloud_pattern = r'^https://[^.]+\.([^.]+\.)?elastic\.cloud(:\d+)?/?.*$'
            if re.match(cloud_pattern, url):
                return True
                
            return False
        except Exception:
            return False
    
    def close(self):
        """Close the Elasticsearch client."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses
            try:
                self.is_initialized = False
                self.tools = []
                self.retriever = None
                self.embedding_model = None
                print("Direct Elasticsearch client closed")
            except Exception as e:
                print(f"Error closing direct Elasticsearch client: {str(e)}")
                traceback.print_exc()
                
    def __del__(self):
        """Destructor to ensure client is closed."""
        self.close()
