#!/bin/bash

# Script to run document ingestion with Elasticsearch

# Check if config file is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <config_file>"
    echo "Example: $0 config/elasticsearch_config.json"
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
print('Initializing DocumentIngestion with Elasticsearch...')
ingestion = DocumentIngestion(
    vector_db_type='elasticsearch',
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
