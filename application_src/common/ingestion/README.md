# Document Ingestion Module

## Overview

The Document Ingestion module is responsible for ingesting documents from Amazon S3, processing them (chunking, embedding), and storing them in a vector database. This module supports multiple vector database backends including Amazon Bedrock Knowledge Base and Elasticsearch, with an extensible architecture for adding new vector databases.

## Features

- Document ingestion from Amazon S3
- Document chunking with configurable strategies
- Embedding generation using Amazon Bedrock models
- Vector storage in Amazon Bedrock Knowledge Base or Elasticsearch
- Metadata tracking and management
- Configurable processing pipeline
- Extensible architecture for adding new vector database support

## Prerequisites

- Python 3.8+
- AWS account with access to:
  - Amazon S3
  - Amazon Bedrock (for embeddings and Knowledge Base)
  - IAM permissions for creating/accessing resources
- For Elasticsearch:
  - Elasticsearch cluster (self-hosted or Elastic Cloud)
  - Authentication credentials (username/password or API key)

### IAM Policy Requirements

When using Bedrock Knowledge Base, ensure that the IAM role used by the Knowledge Base has the necessary permissions to access your S3 bucket. If you encounter permission errors during ingestion, check and update the IAM policy.

#### Sample IAM Policy for S3 Access

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": "s3:ListBucket",
            "Resource": "arn:aws:s3:::your-bucket-name"
        },
        {
            "Effect": "Allow",
            "Action": "s3:GetObject",
            "Resource": "arn:aws:s3:::your-bucket-name/*"
        }
    ]
}
```

Replace `your-bucket-name` with the name of your S3 bucket containing the documents to be ingested.

This policy grants the necessary permissions for:
- `s3:ListBucket`: Required to list objects in the bucket
- `s3:GetObject`: Required to read the content of objects in the bucket

You can attach this policy to the IAM role used by Bedrock Knowledge Base (typically named something like `AmazonBedrockExecutionRoleForKnowledgeBase_*`).

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-org/GenAI-In-A-Box.git
cd GenAI-In-A-Box/modules/ingestion
```

Create a python virtual environment.
```
python -m venv .venv
source .venv/bin/activate
```


2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Directory Structure

```
ingestion/
├── __init__.py                    # Package initialization
├── ingestion.py                   # Main ingestion class
├── requirements.txt               # Package dependencies
├── run_bedrock_kb.sh              # Script to run with Bedrock KB
├── run_elasticsearch.sh           # Script to run with Elasticsearch
├── example_usage.py               # Usage examples
├── config/                        # Configuration files
│   ├── bedrock_kb_template.json   # Template for Bedrock KB configuration
│   ├── bedrock_kb_test.json       # Test configuration for Bedrock KB
│   ├── elasticsearch_template.json # Template for Elasticsearch configuration
│   └── elasticsearch_test.json    # Test configuration for Elasticsearch
├── vector_stores/                 # Vector store implementations
│   ├── __init__.py                # Package initialization
│   ├── base.py                    # Base class for vector stores
│   ├── factory.py                 # Factory for creating vector store instances
│   ├── elasticsearch_store.py     # Elasticsearch implementation
│   ├── bedrock_kb_store.py        # Bedrock KB implementation
│   └── template_store.py.example  # Template for new implementations
```

## File References

- `ingestion.py`: Main class that orchestrates the ingestion process
- `vector_stores/base.py`: Abstract base class defining the interface for all vector stores
- `vector_stores/factory.py`: Factory pattern implementation for dynamically loading vector stores
- `vector_stores/elasticsearch_store.py`: Elasticsearch vector store implementation
- `vector_stores/bedrock_kb_store.py`: Amazon Bedrock Knowledge Base vector store implementation
- `config/bedrock_kb_template.json`: Template configuration for Bedrock KB
- `config/elasticsearch_template.json`: Template configuration for Elasticsearch
- `run_bedrock_kb.sh`: Shell script to run ingestion with Bedrock KB
- `run_elasticsearch.sh`: Shell script to run ingestion with Elasticsearch

## Usage

### 1. Using the Module in Your Python Code

You can import and use the DocumentIngestion class in your Python code:

```python
from ingestion import DocumentIngestion
import json

# Load configuration from test file
with open('config/elasticsearch_test.json', 'r') as f:
    config_data = json.load(f)

# Extract the main config (excluding documents and queries)
config = {k: v for k, v in config_data.items() if k not in ['documents', 'queries']}

# Initialize with Elasticsearch (default)
ingestion = DocumentIngestion(
    config=config
)

# Or initialize with Bedrock Knowledge Base
with open('config/bedrock_kb_test.json', 'r') as f:
    bedrock_config_data = json.load(f)

bedrock_config = {k: v for k, v in bedrock_config_data.items() if k not in ['documents', 'queries']}

ingestion = DocumentIngestion(
    vector_db_type="bedrock_kb",
    config=bedrock_config
)

# Ingest a document from the test configuration
document = bedrock_config_data['documents'][0]
result = ingestion.ingest_document(
    bucket_name=document['bucket_name'],
    object_key=document['object_key'],
    metadata=document.get('metadata', {})
)

# Get document_id and ingestion_id from the result
document_id = result["document_id"]
ingestion_id = result["ingestion_id"]
print(f"Document ID: {document_id}")
print(f"Ingestion ID: {ingestion_id}")

# Get ingestion status using the ingestion_id
status = ingestion.get_ingestion_status(ingestion_id)
print(f"Ingestion status: {status['status']}")

# Get document metadata using the document_id
metadata = ingestion.get_document_metadata(document_id)
print(f"Document metadata: {metadata}")

# Query similar documents using a query from the test configuration
query = bedrock_config_data['queries'][0]
results = ingestion.query_similar(
    query=query['text'],
    top_k=query.get('top_k', 5),
    filters=query.get('filters', {})
)

# Process results
for result in results:
    print(f"Score: {result['score']}")
    print(f"Text: {result['text'][:100]}...")
    print(f"Document ID: {result['document_id']}")
    print()
```

### 2. Running the Module Independently

First, ensure that you have configured your `{provider}_template.json` file. 
For example, configure `elasticsearch_template.json` file by replacing the values indicated with `REPLACE_THIS_EXAMPLE=`. The examples serves as a good indicators of what those values would look like.

Once configured, then you can use the provided shell scripts to run the ingestion process:

#### For Bedrock Knowledge Base:

```bash
# Using the template configuration (you need to fill in the values first)
./run_bedrock_kb.sh config/bedrock_kb_template.json

# Using the test configuration
./run_bedrock_kb.sh config/bedrock_kb_test.json
```

#### For Elasticsearch:

```bash
# Using the template configuration (you need to fill in the values first)
./run_elasticsearch.sh config/elasticsearch_template.json

# Using the test configuration
./run_elasticsearch.sh config/elasticsearch_test.json
```

### 3. Adding a New Vector Store

To add support for a new vector database (e.g., MongoDB):

1. Create a new file in the `vector_stores` directory with the naming convention `[database_name]_store.py`:

```bash
# Path: /Users/ayanray/GitProjects/GenAI-In-A-Box/modules/ingestion/vector_stores/mongodb_store.py
cp vector_stores/template_store.py.example vector_stores/mongodb_store.py
```

2. Implement the required methods in your new class:

```python
# File: /Users/ayanray/GitProjects/GenAI-In-A-Box/modules/ingestion/vector_stores/mongodb_store.py
from typing import Dict, List, Any, Optional, Tuple
from langchain.schema import Document
from langchain.embeddings.base import Embeddings

from .base import VectorStoreBase
from .factory import register_vector_store

@register_vector_store("mongodb")
class MongoDBVectorStore(VectorStoreBase):
    def __init__(self, config: Dict[str, Any], embedding_model: Embeddings):
        self.config = config
        self.embedding_model = embedding_model
        
        # Initialize MongoDB client
        from pymongo import MongoClient
        self.client = MongoClient(config["mongodb_uri"])
        self.db = self.client[config["mongodb_database"]]
        self.collection = self.db[config["mongodb_collection"]]
        
        # Initialize vector search index if needed
        # ...
        
    def add_documents(self, documents: List[Document]) -> Any:
        # Implement document addition logic
        # ...
        
    def similarity_search(self, query: str, k: int = 4, filter: Optional[Dict[str, Any]] = None) -> List[Document]:
        # Implement similarity search logic
        # ...
        
    def similarity_search_with_score(self, query: str, k: int = 4, filter: Optional[Dict[str, Any]] = None) -> List[Tuple[Document, float]]:
        # Implement similarity search with score logic
        # ...
        
    def delete(self, document_id: str) -> bool:
        # Implement deletion logic
        # ...
```

3. Create configuration template files in the `config` directory:

```bash
# Create a template configuration file
# Path: /Users/ayanray/GitProjects/GenAI-In-A-Box/modules/ingestion/config/mongodb_template.json
touch config/mongodb_template.json
```

4. Add the configuration template:

```json
{
    "region": "",
    "embedding_model_id": "amazon.titan-embed-text-v1",
    "mongodb_uri": "",
    "mongodb_database": "",
    "mongodb_collection": "",
    "metadata_bucket": "",
    "chunk_size": 1000,
    "chunk_overlap": 200
}
```

5. Create a test configuration file:

```bash
# Create a test configuration file
# Path: /Users/ayanray/GitProjects/GenAI-In-A-Box/modules/ingestion/config/mongodb_test.json
touch config/mongodb_test.json
```

6. Add the test configuration with actual values:

```json
{
    "region": "us-east-1",
    "embedding_model_id": "amazon.titan-embed-text-v1",
    "mongodb_uri": "mongodb://username:password@hostname:port",
    "mongodb_database": "vector_db",
    "mongodb_collection": "documents",
    "metadata_bucket": "your-metadata-bucket",
    "chunk_size": 1000,
    "chunk_overlap": 200,
    "documents": [
        {
            "bucket_name": "your-documents-bucket",
            "object_key": "path/to/document.pdf",
            "metadata": {
                "title": "Document Title",
                "author": "Author Name",
                "source": "Source Information",
                "category": "Category",
                "tags": ["Tag1", "Tag2"]
            }
        }
    ],
    "queries": [
        {
            "text": "Your query text here",
            "top_k": 3,
            "filters": {}
        }
    ]
}
```

7. Create a shell script to run with your new vector store:

```bash
# Create a shell script
# Path: /Users/ayanray/GitProjects/GenAI-In-A-Box/modules/ingestion/run_mongodb.sh
touch run_mongodb.sh
chmod +x run_mongodb.sh
```

8. Add the shell script content:

```bash
#!/bin/bash

# Script to run document ingestion with MongoDB

# Check if config file is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <config_file>"
    echo "Example: $0 config/mongodb_test.json"
    exit 1
fi

CONFIG_FILE=$1

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: Config file $CONFIG_FILE not found"
    exit 1
fi

# Run the ingestion script
python -c "
import json
import sys
from ingestion import DocumentIngestion

# Load configuration
with open('$CONFIG_FILE', 'r') as f:
    config_data = json.load(f)

# Extract the main config and documents from the config file
config = {k: v for k, v in config_data.items() if k not in ['documents', 'queries']}
documents = config_data.get('documents', [])
queries = config_data.get('queries', [])

# Initialize the ingestion module
print('Initializing DocumentIngestion with MongoDB...')
ingestion = DocumentIngestion(
    vector_db_type='mongodb',
    config=config
)

# Ingest documents
for document in documents:
    print(f\"Ingesting document: {document['object_key']}...\")
    result = ingestion.ingest_document(
        bucket_name=document['bucket_name'],
        object_key=document['object_key'],
        metadata=document.get('metadata', {})
    )
    print(f\"Document ingested with ID: {result['document_id']}\")
    print(f\"Status: {result['status']}\")
    print()

# Run queries
for query in queries:
    print(f\"Running query: {query['text']}\")
    results = ingestion.query_similar(
        query=query['text'],
        top_k=query.get('top_k', 5),
        filters=query.get('filters', {})
    )
    print(f\"Found {len(results)} results:\")
    for i, result in enumerate(results):
        print(f\"{i+1}. Score: {result['score']:.4f}\")
        print(f\"   Text: {result['text'][:200]}...\")
        print(f\"   Document ID: {result['document_id']}\")
        print()
"

exit $?
```

9. Use your new vector store:

```python
ingestion = DocumentIngestion(
    vector_db_type="mongodb",
    config=your_mongodb_config
)
```

## Configuration Options

### Common Configuration Parameters

- `region`: AWS region (default: "us-east-1")
- `embedding_model_id`: Bedrock embedding model ID (default: "amazon.titan-embed-text-v1")
- `chunk_size`: Size of document chunks in characters (default: 1000)
- `chunk_overlap`: Overlap between chunks in characters (default: 200)
- `metadata_bucket`: S3 bucket for storing document metadata

### Bedrock Knowledge Base Configuration

- `bedrock_kb_id`: ID of the Bedrock Knowledge Base (optional - will create new KB if not provided)
- `bedrock_kb_name`: Name for the new KB (used if creating a new KB)
- `role_arn`: IAM role ARN with permissions for Bedrock KB (required only if creating a new KB)

### Elasticsearch Configuration

- `elasticsearch_endpoint`: Elasticsearch endpoint URL
- `elasticsearch_index`: Elasticsearch index name (optional - will create new index if not provided)
- `elasticsearch_username`: Elasticsearch username (optional)
- `elasticsearch_password`: Elasticsearch password (optional)
- `elasticsearch_api_key`: Elasticsearch API key (optional)

## Error Handling

The module implements comprehensive error handling and retry logic for:
- S3 access issues
- Document processing failures
- Embedding generation errors
- Vector database connectivity problems

## Logging

The module uses Python's standard logging module. You can configure the logging level and format in your application:

```python
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

[License information to be added]
