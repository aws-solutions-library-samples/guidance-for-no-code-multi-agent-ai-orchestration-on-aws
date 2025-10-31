"""
Direct Bedrock Knowledge Base provider for GenAI-In-A-Box agent.
This module provides a knowledge base provider using direct Bedrock Knowledge Base client.
"""

import os
import traceback
from typing import List, Dict, Any
from strands_tools import retrieve
from ..base import BaseKnowledgeBaseProvider

class BedrockKnowledgeBaseProvider(BaseKnowledgeBaseProvider):
    """Knowledge base provider for Bedrock Knowledge Base using direct client."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Bedrock Knowledge Base provider."""
        super().__init__(config)
        self.provider_name = "bedrock knowledge base"
        self.is_initialized = False
    
    def initialize(self) -> List:
        """Initialize the Bedrock Knowledge Base provider and get the tools."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses
            return self.tools
            
        try:
            provider_config = self.get_provider_config()
            
            # Get Bedrock KB credentials
            kb_id = provider_config.get("knowledge_base_id", "")
            region = provider_config.get("region", "us-east-1")
            
            if not kb_id:
                print("Error: Bedrock Knowledge Base ID is required")
                return []
            
            # Set environment variables for Bedrock Knowledge Base
            print(f"Setting KNOWLEDGE_BASE_ID={kb_id}")
            os.environ["KNOWLEDGE_BASE_ID"] = kb_id
            
            print(f"Setting AWS_REGION={region}")
            os.environ["AWS_REGION"] = region
            
            # Create tools
            self._create_tools()
            self.is_initialized = True
            
            print(f"Bedrock Knowledge Base provider initialized with {len(self.tools)} tools")
            
            return self.tools
            
        except Exception as e:
            print(f"Error initializing Bedrock Knowledge Base provider: {str(e)}")
            traceback.print_exc()
            self.close()
            return []
    
    def _create_tools(self):
        """Create Bedrock Knowledge Base search tools."""
        # Use the retrieve tool directly from strands_tools
        self.tools = [retrieve]
    
    def close(self):
        """Close the Bedrock Knowledge Base client."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses
            try:
                self.is_initialized = False
                self.tools = []
                print("Bedrock Knowledge Base client closed")
            except Exception as e:
                print(f"Error closing Bedrock Knowledge Base client: {str(e)}")
                traceback.print_exc()
                
    def __del__(self):
        """Destructor to ensure client is closed."""
        self.close()
