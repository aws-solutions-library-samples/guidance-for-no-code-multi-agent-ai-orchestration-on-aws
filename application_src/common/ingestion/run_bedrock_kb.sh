#!/bin/bash

# Script to run document ingestion with Bedrock Knowledge Base

# Check if config file is provided
if [ -z "$1" ]; then
    echo "Usage: $0 <config_file>"
    echo "Example: $0 config/bedrock_kb_config.json"
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
import time
from ingestion import DocumentIngestion

# Load configuration
with open('$CONFIG_FILE', 'r') as f:
    config_data = json.load(f)

# Extract the main config and documents from the config file
config = {k: v for k, v in config_data.items() if k not in ['documents', 'queries']}
documents = config_data.get('documents', [])
queries = config_data.get('queries', [])

# Initialize the ingestion module
print('Initializing DocumentIngestion with Bedrock Knowledge Base...')
ingestion = DocumentIngestion(
    vector_db_type='bedrock_kb',
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
    document_id = result['document_id']
    ingestion_id = result['ingestion_id']
    print(f\"Document ingested with ID: {document_id}\")
    print(f\"Ingestion ID: {ingestion_id}\")
    print(f\"Initial status: {result['status']}\")
    
    # Wait for the ingestion job to complete
    if result['status'] == 'ingestion_started':
        print(\"Waiting for ingestion job to complete...\")
        max_retries = 30
        retry_delay = 10  # seconds
        
        for i in range(max_retries):
            status = ingestion.get_ingestion_status(ingestion_id)
            print(f\"Current status: {status['status']} (Attempt {i+1}/{max_retries})\")
            
            if status['status'] == 'completed':
                print(\"Ingestion job completed successfully!\")
                break
            elif status['status'] == 'failed':
                error_msg = status.get('error', 'Unknown error')
                if 'job_status' in status and 'error_message' in status['job_status']:
                    error_msg = status['job_status']['error_message']
                print(f\"Ingestion job failed: {error_msg}\")
                break
            
            print(f\"Waiting {retry_delay} seconds before checking again...\")
            time.sleep(retry_delay)
        
        # Get final status
        final_status = ingestion.get_ingestion_status(ingestion_id)
        print(f\"Final status: {final_status['status']}\")
        
        if 'job_status' in final_status:
            print(f\"Job status details: {final_status['job_status']}\")
    
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
