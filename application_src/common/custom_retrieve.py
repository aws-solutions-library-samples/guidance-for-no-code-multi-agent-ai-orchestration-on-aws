"""
Custom retrieve tool that directly uses the Bedrock Knowledge Base.
"""

import os
import boto3
from strands import tool
from typing import Dict, Any, List

@tool
def custom_retrieve(text: str) -> Dict[str, Any]:
    """Retrieve information from Bedrock Knowledge Base."""
    try:
        # Get the knowledge base ID from the environment
        kb_id = os.environ.get("STRANDS_KNOWLEDGE_BASE_ID")
        region = os.environ.get("AWS_REGION", "us-east-1")
        
        print(f"Custom retrieve with text: {text}")
        print(f"STRANDS_KNOWLEDGE_BASE_ID: {kb_id}")
        print(f"AWS_REGION: {region}")
        
        if not kb_id:
            return {
                "status": "error",
                "content": [{"text": "Error: STRANDS_KNOWLEDGE_BASE_ID environment variable not set"}]
            }
        
        # Create a Bedrock agent client
        bedrock_agent = boto3.client('bedrock-agent-runtime', region_name=region)
        
        # Call the Bedrock Knowledge Base
        response = bedrock_agent.retrieve(
            knowledgeBaseId=kb_id,
            retrievalQuery={
                'text': text
            },
            retrievalConfiguration={
                'vectorSearchConfiguration': {
                    'numberOfResults': 5
                }
            }
        )
        
        print(f"Bedrock response: {response}")
        
        # Format the response
        content = []
        for result in response.get('retrievalResults', []):
            content.append({
                "text": result.get('content', {}).get('text', ''),
                "source": result.get('location', {}).get('s3Location', {}).get('uri', 'Unknown source'),
                "score": result.get('score', 0)
            })
        
        return {
            "status": "success",
            "content": content
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "content": [{"text": f"Error during retrieval: {str(e)}"}]
        }
