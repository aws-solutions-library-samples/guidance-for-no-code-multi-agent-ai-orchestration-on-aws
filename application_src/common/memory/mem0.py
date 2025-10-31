"""
Mem0 memory provider for GenAI-In-A-Box agent.
This module provides a memory provider for Mem0 with enhanced retrieval capabilities.
"""

import os
import uuid
import traceback
from typing import List, Dict, Any, Optional
import importlib
from .base import BaseMemoryProvider

# Default user ID for memory operations when none is provided
DEFAULT_USER_ID = "ayanray@amazon.com"

class Mem0MemoryProvider(BaseMemoryProvider):
    """Memory provider for Mem0 with enhanced retrieval capabilities."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Mem0 memory provider."""
        super().__init__(config)
        self.provider_name = "mem0"
        self.default_user_id = DEFAULT_USER_ID
        
        # Configure memory environment variables for optimal performance
        os.environ["AWS_REGION"] = "us-east-1"  # Ensure correct region
        os.environ["MEM0_EMBEDDING_MODEL"] = "amazon.titan-embed-text-v2:0"  # Specify exact model version
        os.environ["MEM0_DEBUG"] = "true"  # Enable debug mode
        
        # Set up environment variables from config
        provider_config = self.get_provider_config()
        mem0_api_key = provider_config.get("mem0_api_key", "")
        if mem0_api_key:
            os.environ["MEM0_API_KEY"] = mem0_api_key
            print(f"✅ MEM0_API_KEY set from config")
        else:
            print("⚠️ MEM0_API_KEY not found in config")
    
    def initialize(self) -> List:
        """Initialize the Mem0 memory provider and get the tools."""
        try:
            # Import the mem0_memory module
            try:
                mem0_module = importlib.import_module('strands_tools.mem0_memory')
                
                # Check if there's a mem0_memory function in the module
                if hasattr(mem0_module, 'mem0_memory'):
                    # Create an enhanced wrapper function with better retrieval logic
                    from strands import tool
                    
                    @tool
                    def mem0_memory(action: str, content: str = None, query: str = None, user_id: str = None) -> Dict[str, Any]:
                        """
                        Enhanced memory tool for storing and retrieving information with improved retrieval logic.
                        
                        Args:
                            action: The action to perform ('store', 'retrieve', or 'list')
                            content: The content to store (required for 'store' action)
                            query: The query to search for (required for 'retrieve' action)
                            user_id: The user ID to associate with the memory
                            
                        Returns:
                            A dictionary with the results of the operation
                        """
                        try:
                            # Use the provided user_id or fall back to default if none is provided
                            effective_user_id = user_id if user_id else self.default_user_id
                            print(f"🧠 Calling mem0_memory with action={action}, user_id={effective_user_id}")
                            
                            # Create the tool input
                            tool_input = {
                                "name": "mem0_memory",
                                "toolUseId": f"mem0_{uuid.uuid4()}",
                                "input": {
                                    "action": action,
                                    "user_id": effective_user_id
                                }
                            }
                            
                            # Add content or query based on action
                            if action == "store" and content:
                                tool_input["input"]["content"] = content
                                print(f"📝 Storing content: {content[:100]}...")
                            elif action == "retrieve" and query:
                                tool_input["input"]["query"] = query
                                print(f"🔍 Retrieving with query: {query}")
                            elif action == "list":
                                print(f"📋 Listing all memories for user: {effective_user_id}")
                            
                            # Call the original mem0_memory function
                            result = mem0_module.mem0_memory(tool_input)
                            
                            # Enhanced result processing for better retrieval feedback
                            if action == "retrieve":
                                if isinstance(result, dict):
                                    memories = result.get("memories", [])
                                    if memories:
                                        print(f"✅ Retrieved {len(memories)} memories")
                                        # Format memories for better agent understanding
                                        formatted_memories = []
                                        for memory in memories:
                                            if isinstance(memory, dict):
                                                memory_text = memory.get("text", memory.get("content", str(memory)))
                                                formatted_memories.append(memory_text)
                                            else:
                                                formatted_memories.append(str(memory))
                                        
                                        # Don't add extra fields - only modify the content for better readability
                                        print(f"📚 Found memories: {'; '.join(formatted_memories[:3])}")
                                    else:
                                        print(f"❌ No memories found for query: {query}")
                                else:
                                    print(f"⚠️ Unexpected result format: {type(result)}")
                            elif action == "store":
                                if isinstance(result, dict) and result.get("status") == "success":
                                    print(f"✅ Successfully stored memory")
                                else:
                                    print(f"⚠️ Storage result: {result}")
                            
                            print(f"🧠 mem0_memory result: {result}")
                            return result
                            
                        except Exception as e:
                            error_msg = f"Error in mem0_memory wrapper: {str(e)}"
                            print(f"❌ {error_msg}")
                            traceback.print_exc()
                            return {
                                "status": "error", 
                                "message": error_msg
                            }
                    
                    self.tools = [mem0_memory]
                    print(f"✅ Successfully created {len(self.tools)} memory tools")
                else:
                    print("❌ No mem0_memory function found in module")
                    self.tools = []
                    
            except ImportError as e:
                print(f"❌ Error importing mem0_memory module: {e}")
                self.tools = []
            
            return self.tools
            
        except Exception as e:
            print(f"❌ Error initializing Mem0 memory provider: {str(e)}")
            traceback.print_exc()
            return []
    
    def get_tools(self) -> List:
        """Get memory tools - following the same pattern as knowledge base providers."""
        if not hasattr(self, 'tools') or not self.tools:
            return self.initialize()
        return self.tools
