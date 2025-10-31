"""
MongoDB Atlas knowledge base provider for GenAI-In-A-Box agent.
This module provides a knowledge base provider using MongoDB Atlas with Langchain.
"""

import traceback
from typing import List, Dict, Any
import boto3
from strands import tool
from ..base import BaseKnowledgeBaseProvider

# Import Langchain components with optional handling
try:
    from langchain_mongodb import MongoDBAtlasVectorSearch
    LANGCHAIN_MONGODB_AVAILABLE = True
except ImportError:
    LANGCHAIN_MONGODB_AVAILABLE = False
    MongoDBAtlasVectorSearch = None

try:
    from langchain_community.embeddings import BedrockEmbeddings
    from langchain.schema.document import Document
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    BedrockEmbeddings = None
    Document = None

try:
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False
    MongoClient = None

class MongoDBKnowledgeBaseProvider(BaseKnowledgeBaseProvider):
    """Knowledge base provider for MongoDB Atlas using direct client with Langchain."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the MongoDB Atlas knowledge base provider."""
        super().__init__(config)
        self.provider_name = "mongodb"
        self.mongo_client = None
        self.retriever = None
        self.is_initialized = False
        self.database_name = None
        self.collection_name = None
        self.index_name = None
        self.embedding_model = None
    
    def initialize(self) -> List:
        """Initialize the MongoDB Atlas knowledge base provider and get the tools."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses
            return self.tools

        # Check if required dependencies are available
        if not LANGCHAIN_MONGODB_AVAILABLE:
            print("Error: langchain_mongodb is not available. Please install it to use MongoDB Atlas provider.")
            return []
            
        if not LANGCHAIN_AVAILABLE:
            print("Error: langchain_community is not available. Please install langchain to use MongoDB Atlas provider.")
            return []
            
        if not PYMONGO_AVAILABLE:
            print("Error: pymongo is not available. Please install it to use MongoDB Atlas provider.")
            return []
            
        try:
            provider_config = self.get_provider_config()
            
            # Get MongoDB Atlas credentials
            mongodb_uri = provider_config.get("mongodb_atlas_cluster_uri", "")
            self.database_name = provider_config.get("database_name", "")
            self.collection_name = provider_config.get("collection_name", "")
            self.index_name = provider_config.get("index_name", "")
            
            # Get embedding model ID from config
            try:
                from ...config import Config
                config_instance = Config(self.config.get("agent_name", "qa_agent"))
                model_config = config_instance.get_model_config()
                embedding_model_id = model_config.get("embedding_model_id", "amazon.titan-embed-text-v2:0")
            except (ImportError, Exception) as e:
                # Fallback to default embedding model if config import fails
                embedding_model_id = "amazon.titan-embed-text-v2:0"
                print(f"Using default embedding model due to config error: {embedding_model_id}")
                print(f"Config error details: {str(e)}")
            
            if not mongodb_uri:
                print("Error: MongoDB Atlas cluster URI is required")
                return []
                
            if not self.database_name:
                print("Error: MongoDB database name is required")
                return []
                
            if not self.collection_name:
                print("Error: MongoDB collection name is required")
                return []
                
            if not self.index_name:
                print("Error: MongoDB Atlas vector search index name is required")
                return []
            
            print(f"Initializing MongoDB Atlas provider with database: {self.database_name}, collection: {self.collection_name}, index: {self.index_name}")
            
            # Initialize MongoDB client
            self.mongo_client = MongoClient(mongodb_uri)
            
            # Test connection
            try:
                # Ping the database to test connection
                self.mongo_client.admin.command('ping')
                print("Successfully connected to MongoDB Atlas")
            except Exception as e:
                print(f"Failed to connect to MongoDB Atlas: {str(e)}")
                return []
            
            # Get the collection reference
            mongodb_collection = self.mongo_client[self.database_name][self.collection_name]
            
            # Initialize Bedrock embeddings
            self.embedding_model = BedrockEmbeddings(
                model_id=embedding_model_id,
                client=boto3.client("bedrock-runtime")
            )
            print(f"Initialized Bedrock embeddings with model: {embedding_model_id}")
            
            # Initialize MongoDB Atlas vector store
            vector_store = MongoDBAtlasVectorSearch(
                collection=mongodb_collection,
                embedding=self.embedding_model,
                index_name=self.index_name,
                relevance_score_fn="cosine",
            )
            
            # Create retriever
            self.retriever = vector_store.as_retriever(
                search_kwargs={"k": 5}  # Return top 5 results
            )
            
            print(f"Successfully initialized MongoDB Atlas retriever for collection: {self.database_name}.{self.collection_name}")
            
            # Create tools
            self._create_tools()
            self.is_initialized = True
            
            print(f"MongoDB Atlas knowledge base provider initialized with {len(self.tools)} tools")
            for tool_func in self.tools:
                print(f"  - {tool_func.__name__ if hasattr(tool_func, '__name__') else str(tool_func)}")
            
            return self.tools
            
        except Exception as e:
            print(f"Error initializing MongoDB Atlas knowledge base provider: {str(e)}")
            traceback.print_exc()
            self.close()
            return []
    
    def _create_tools(self):
        """Create MongoDB Atlas search tools using Langchain retriever."""
        
        @tool
        def retriever_mongodb_semantic_search(query: str, top_k: int = 5) -> str:
            """Perform semantic search in MongoDB Atlas using embeddings."""
            try:
                print(f"Performing semantic search in collection '{self.database_name}.{self.collection_name}' for: {query}")
                
                # Override the default k value by updating search_kwargs
                self.retriever.search_kwargs["k"] = top_k
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
        
        print("Creating MongoDB Atlas search tools:")
        print(f"  1. retriever_mongodb_semantic_search: {retriever_mongodb_semantic_search}")
        
        self.tools = [retriever_mongodb_semantic_search]
    
    def close(self):
        """Close the MongoDB client."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses
            try:
                self.is_initialized = False
                self.tools = []
                self.retriever = None
                self.embedding_model = None
                if self.mongo_client:
                    self.mongo_client.close()
                    self.mongo_client = None
                print("MongoDB Atlas client closed")
            except Exception as e:
                print(f"Error closing MongoDB Atlas client: {str(e)}")
                traceback.print_exc()
                
    def __del__(self):
        """Destructor to ensure client is closed."""
        self.close()
