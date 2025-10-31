"""
Bedrock AgentCore memory provider for GenAI-In-A-Box agent.
This module provides a memory provider using Amazon Bedrock AgentCore with both short-term and long-term memory capabilities.
Based on the official AWS Bedrock AgentCore samples and patterns.
"""

import os
import uuid
import traceback
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from .base import BaseMemoryProvider

# Import Bedrock AgentCore components
try:
    from bedrock_agentcore.memory import MemoryClient
    from bedrock_agentcore.memory.constants import StrategyType
    BEDROCK_AGENTCORE_AVAILABLE = True
except ImportError:
    print("⚠️ bedrock-agentcore library not available. Install with: pip install bedrock-agentcore")
    BEDROCK_AGENTCORE_AVAILABLE = False

# Default user ID for memory operations when none is provided (must comply with AWS namespace pattern)
DEFAULT_USER_ID = "ayanray_amazon_com"

class BedrockAgentCoreMemoryProvider(BaseMemoryProvider):
    """Memory provider for Bedrock AgentCore with short-term and long-term memory capabilities."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Bedrock AgentCore memory provider."""
        super().__init__(config)
        self.provider_name = "bedrock_agentcore"
        self.default_user_id = DEFAULT_USER_ID
        
        # Check if bedrock-agentcore is available
        if not BEDROCK_AGENTCORE_AVAILABLE:
            print("❌ bedrock-agentcore library not available")
            self.memory_client = None
            return
        
        # Get provider configuration
        provider_config = self.get_provider_config()
        self.region = provider_config.get("region", "us-east-1")
        self.memory_id = provider_config.get("memory_id", None)
        self.memory_name = provider_config.get("memory_name", "GenAI_In_A_Box_Memory")
        
        # Initialize Bedrock AgentCore Memory client
        try:
            self.memory_client = MemoryClient(region_name=self.region)
            print(f"✅ Bedrock AgentCore Memory client initialized for region: {self.region}")
            
            # Initialize or get existing memory resource
            if not self.memory_id:
                self.memory_id = self._initialize_memory_resource()
                
        except Exception as e:
            print(f"❌ Error initializing Bedrock AgentCore Memory client: {str(e)}")
            self.memory_client = None
    
    def _initialize_memory_resource(self) -> str:
        """Initialize or get existing memory resource with strategies."""
        try:
            # If memory_id is already provided in config, validate it first
            if hasattr(self, 'memory_id') and self.memory_id and self.memory_id != "default-memory":
                if self._is_valid_memory_id(self.memory_id):
                    print(f"✅ Using provided memory ID: {self.memory_id}")
                    return self.memory_id
                else:
                    print(f"⚠️ Provided memory ID {self.memory_id} is invalid, will generate new one")
            
            # Try to list existing memories to find one with our name
            try:
                memories = self.memory_client.list_memories()
                for memory in memories:
                    if memory.get('name') == self.memory_name:
                        memory_id = memory['id']
                        if self._is_valid_memory_id(memory_id):
                            print(f"✅ Using existing memory resource: {memory_id}")
                            return memory_id
                        else:
                            print(f"⚠️ Existing memory {memory_id} has invalid format")
            except Exception as e:
                print(f"⚠️ Error listing memories: {e}")
            
            # Generate unique memory name to avoid conflicts
            # AWS memory names: [a-zA-Z][a-zA-Z0-9_]{0,47} (no hyphens allowed)
            unique_suffix = str(uuid.uuid4()).replace('-', '')[:10]
            unique_memory_name = f"{self.memory_name}_{unique_suffix}"
            
            print(f"🔧 Creating new memory resource: {unique_memory_name}")
            
            # Define memory strategies based on AgentCore samples
            strategies = [
                {
                    StrategyType.USER_PREFERENCE.value: {
                        "name": "UserPreferences",
                        "description": "Captures user preferences and behaviors",
                        "namespaces": [f"{os.environ.get('PROJECT_NAME', 'genai-box')}/user/{{actorId}}/preferences"],
                    }
                },
                {
                    StrategyType.SEMANTIC.value: {
                        "name": "SemanticMemory", 
                        "description": "Stores factual information from conversations",
                        "namespaces": [f"{os.environ.get('PROJECT_NAME', 'genai-box')}/user/{{actorId}}/semantic"],
                    }
                }
            ]
            
            # Create memory resource with unique name
            memory = self.memory_client.create_memory_and_wait(
                name=unique_memory_name,
                description="Memory resource for GenAI-In-A-Box agent with user preferences and semantic storage",
                strategies=strategies
            )
            
            memory_id = memory['id']
            print(f"✅ Created memory resource: {memory_id}")
            return memory_id
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error initializing memory resource: {error_msg}")
            
            # Check if it's a duplicate name error
            if "already exists" in error_msg.lower():
                print("🔄 Memory name conflict detected, trying with different name...")
                try:
                    # Generate a new unique name and try again
                    timestamp = str(int(datetime.now().timestamp()))[-6:]
                    fallback_name = f"GenAI_Memory_{timestamp}"
                    
                    memory = self.memory_client.create_memory_and_wait(
                        name=fallback_name,
                        description="Memory resource for GenAI-In-A-Box agent",
                        strategies=[
                            {
                                StrategyType.SEMANTIC.value: {
                                    "name": "SemanticMemory",
                                    "description": "Stores factual information",
                                    "namespaces": ["genai/user/{actorId}/semantic"],
                                }
                            }
                        ]
                    )
                    
                    memory_id = memory['id']
                    print(f"✅ Created fallback memory resource: {memory_id}")
                    return memory_id
                    
                except Exception as fallback_error:
                    print(f"❌ Fallback memory creation failed: {fallback_error}")
            
            # If we have a memory_id from config, try to use it even if there was an error
            if hasattr(self, 'memory_id') and self.memory_id and self.memory_id != "default-memory":
                print(f"⚠️ Falling back to provided memory ID: {self.memory_id}")
                return self.memory_id
            return "default-memory"

    def _is_valid_memory_id(self, memory_id: str) -> bool:
        """Validate memory ID format: [a-zA-Z][a-zA-Z0-9-_]{0,99}-[a-zA-Z0-9]{10}"""
        import re
        # Pattern allows: letter + alphanumeric/underscore/dash (0-99 chars) + dash + alphanumeric (exactly 10 chars)
        pattern = r'^[a-zA-Z][a-zA-Z0-9_-]{0,99}-[a-zA-Z0-9]{10}$'  
        return bool(re.match(pattern, memory_id))

    def initialize(self) -> List:
        """Initialize the Bedrock AgentCore memory provider and get the tools."""
        try:
            if not BEDROCK_AGENTCORE_AVAILABLE or not self.memory_client:
                print("❌ Bedrock AgentCore not available")
                return []
            
            # Import strands tool decorator
            try:
                from strands import tool
            except ImportError:
                print("❌ Could not import strands tool decorator")
                return []
            
            @tool
            def bedrock_memory_store(content: str, user_id: str = None, session_id: str = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
                """
                Store information in Bedrock AgentCore memory using events.
                
                Args:
                    content: The content to store in memory
                    user_id: The user ID (actor_id) to associate with the memory
                    session_id: The session ID for the conversation
                    metadata: Additional metadata to store with the memory
                    
                Returns:
                    A dictionary with the results of the store operation
                """
                try:
                    effective_user_id = user_id if user_id else self.default_user_id
                    effective_session_id = session_id if session_id else f"session_{uuid.uuid4()}"
                    
                    print(f"🧠 Storing memory for user: {effective_user_id}")
                    print(f"📝 Content: {content[:100]}...")
                    
                    # Create event for AgentCore Memory
                    event_id = str(uuid.uuid4())
                    
                    # Store using AgentCore Memory event pattern
                    response = self.memory_client.create_event(
                        memory_id=self.memory_id,
                        actor_id=effective_user_id,
                        session_id=effective_session_id,
                        messages=[(content, "USER")]
                    )
                    
                    print(f"✅ Successfully stored memory event: {event_id}")
                    return {
                        "status": "success",
                        "message": "Memory stored successfully",
                        "event_id": event_id,
                        "memory_id": self.memory_id
                    }
                        
                except Exception as e:
                    error_msg = f"Error storing memory: {str(e)}"
                    print(f"❌ {error_msg}")
                    traceback.print_exc()
                    return {
                        "status": "error",
                        "message": error_msg
                    }
            
            @tool
            def bedrock_memory_retrieve(query: str, user_id: str = None, namespace: str = None, limit: int = 10) -> Dict[str, Any]:
                """
                Retrieve information from Bedrock AgentCore memory using semantic search.
                
                Args:
                    query: The query to search for in memory
                    user_id: The user ID (actor_id) to search memories for
                    namespace: Specific namespace to search (optional)
                    limit: Maximum number of memories to retrieve
                    
                Returns:
                    A dictionary with the retrieved memories
                """
                try:
                    effective_user_id = user_id if user_id else self.default_user_id
                    print(f"🔍 Retrieving memories for user: {effective_user_id}")
                    print(f"🔍 Query: {query}")
                    
                    # Use AgentCore Memory retrieve_memories method
                    if namespace:
                        # Search specific namespace
                        namespace_formatted = namespace.format(actorId=effective_user_id)
                        memories = self.memory_client.retrieve_memories(
                            memory_id=self.memory_id,
                            namespace=namespace_formatted,
                            query=query,
                            top_k=limit
                        )
                    else:
                        # Search both user preference and semantic namespaces
                        all_memories = []
                        
                        project_name = os.environ.get('PROJECT_NAME', 'genai-box')
                        
                        # Search user preferences
                        try:
                            pref_memories = self.memory_client.retrieve_memories(
                                memory_id=self.memory_id,
                                namespace=f"{project_name}/user/{effective_user_id}/preferences",
                                query=query,
                                top_k=limit//2
                            )
                            all_memories.extend(pref_memories)
                        except Exception as e:
                            print(f"⚠️ Could not retrieve from preferences namespace: {e}")
                        
                        # Search semantic memories
                        try:
                            semantic_memories = self.memory_client.retrieve_memories(
                                memory_id=self.memory_id,
                                namespace=f"{project_name}/user/{effective_user_id}/semantic",
                                query=query,
                                top_k=limit//2
                            )
                            all_memories.extend(semantic_memories)
                        except Exception as e:
                            print(f"⚠️ Could not retrieve from semantic namespace: {e}")
                        
                        memories = all_memories[:limit]
                    
                    if memories:
                        print(f"✅ Retrieved {len(memories)} memories")
                        # Format memories for display
                        formatted_memories = []
                        for mem in memories[:3]:
                            try:
                                if isinstance(mem, dict):
                                    # Try different possible content fields
                                    content = mem.get('content', mem.get('text', mem.get('message', str(mem))))
                                    # Ensure content is a string before slicing
                                    content_str = str(content) if content is not None else "No content"
                                    formatted_memories.append(content_str[:100])
                                else:
                                    # Handle non-dict memory objects
                                    mem_str = str(mem) if mem is not None else "Empty memory"
                                    formatted_memories.append(mem_str[:100])
                            except Exception as format_error:
                                print(f"⚠️ Error formatting memory: {format_error}")
                                formatted_memories.append("Error formatting memory")
                        
                        if formatted_memories:
                            print(f"📚 Found memories: {'; '.join(formatted_memories)}")
                        else:
                            print(f"📚 Retrieved {len(memories)} memories (formatting issues)")
                    else:
                        print(f"❌ No memories found for query: {query}")
                    
                    return {
                        "status": "success",
                        "memories": memories,
                        "count": len(memories),
                        "query": query
                    }
                    
                except Exception as e:
                    error_msg = f"Error retrieving memories: {str(e)}"
                    print(f"❌ {error_msg}")
                    traceback.print_exc()
                    return {
                        "status": "error",
                        "message": error_msg,
                        "memories": []
                    }
            
            @tool
            def bedrock_memory_list(user_id: str = None, session_id: str = None, limit: int = 20) -> Dict[str, Any]:
                """
                List events and sessions from Bedrock AgentCore memory.
                
                Args:
                    user_id: The user ID (actor_id) to list memories for
                    session_id: Specific session ID to list (optional)
                    limit: Maximum number of items to list
                    
                Returns:
                    A dictionary with memory information
                """
                try:
                    effective_user_id = user_id if user_id else self.default_user_id
                    print(f"📋 Listing memories for user: {effective_user_id}")
                    
                    # Note: list_sessions method is not available in current Bedrock AgentCore API
                    # Instead, we'll use retrieve_memories to get available memories
                    try:
                        # Try to retrieve some memories to show what's available
                        memories = self.memory_client.retrieve_memories(
                            memory_id=self.memory_id,
                            namespace=f"genai/user/{effective_user_id}/preferences",
                            query="",  # Empty query to get any available memories
                            top_k=limit
                        )
                        
                        memories_info = {
                            "memories": memories,
                            "memory_count": len(memories),
                            "note": "Retrieved from preferences namespace"
                        }
                        
                        # Also try semantic namespace
                        try:
                            semantic_memories = self.memory_client.retrieve_memories(
                                memory_id=self.memory_id,
                                namespace=f"genai/user/{effective_user_id}/semantic",
                                query="",
                                top_k=limit
                            )
                            memories_info["semantic_memories"] = semantic_memories
                            memories_info["semantic_count"] = len(semantic_memories)
                            memories_info["total_count"] = len(memories) + len(semantic_memories)
                        except Exception as e:
                            print(f"⚠️ Could not retrieve from semantic namespace: {e}")
                            memories_info["total_count"] = len(memories)
                        
                    except Exception as e:
                        print(f"⚠️ Could not retrieve memories for listing: {e}")
                        memories_info = {
                            "memories": [],
                            "memory_count": 0,
                            "total_count": 0,
                            "note": "Memory listing not available - use retrieve with specific queries"
                        }
                    
                    print(f"📋 Found {memories_info.get('total_count', 0)} total memories")
                    
                    return {
                        "status": "success",
                        "memories": memories_info,
                        "count": memories_info.get("total_count", 0)
                    }
                    
                except Exception as e:
                    error_msg = f"Error listing memories: {str(e)}"
                    print(f"❌ {error_msg}")
                    traceback.print_exc()
                    return {
                        "status": "error",
                        "message": error_msg,
                        "memories": []
                    }
            
            @tool
            def bedrock_memory_get_strategies(user_id: str = None) -> Dict[str, Any]:
                """
                Get memory strategies and their configurations.
                
                Args:
                    user_id: The user ID (for context, not used in strategy retrieval)
                    
                Returns:
                    A dictionary with memory strategies information
                """
                try:
                    effective_user_id = user_id if user_id else self.default_user_id
                    print(f"🔧 Getting memory strategies for memory: {self.memory_id}")
                    
                    # Check if memory_id is valid before calling get_memory_strategies
                    if not self._is_valid_memory_id(self.memory_id):
                        return {
                            "status": "error",
                            "message": f"Invalid memory ID format: {self.memory_id}",
                            "strategies": []
                        }
                    
                    # Get memory strategies
                    strategies = self.memory_client.get_memory_strategies(self.memory_id)
                    
                    print(f"✅ Retrieved {len(strategies)} memory strategies")
                    
                    return {
                        "status": "success",
                        "strategies": strategies,
                        "count": len(strategies),
                        "memory_id": self.memory_id
                    }
                    
                except Exception as e:
                    error_msg = str(e)
                    print(f"❌ Error getting memory strategies: {error_msg}")
                    
                    # Handle specific validation errors
                    if "validation error" in error_msg.lower() and "memoryId" in error_msg:
                        print(f"⚠️ Memory ID validation failed. Attempting to reinitialize memory resource...")
                        try:
                            # Try to reinitialize memory resource
                            new_memory_id = self._initialize_memory_resource()
                            if new_memory_id != self.memory_id:
                                self.memory_id = new_memory_id
                                print(f"✅ Reinitialized with new memory ID: {self.memory_id}")
                                
                                # Try getting strategies again with new ID
                                if self._is_valid_memory_id(self.memory_id):
                                    strategies = self.memory_client.get_memory_strategies(self.memory_id)
                                    return {
                                        "status": "success",
                                        "strategies": strategies,
                                        "count": len(strategies),
                                        "memory_id": self.memory_id
                                    }
                        except Exception as reinit_error:
                            print(f"❌ Memory reinitialization failed: {reinit_error}")
                    
                    traceback.print_exc()
                    return {
                        "status": "error",
                        "message": error_msg,
                        "strategies": []
                    }
            
            self.tools = [bedrock_memory_store, bedrock_memory_retrieve, bedrock_memory_list, bedrock_memory_get_strategies]
            print(f"✅ Successfully created {len(self.tools)} Bedrock AgentCore memory tools")
            return self.tools
            
        except Exception as e:
            print(f"❌ Error initializing Bedrock AgentCore memory provider: {str(e)}")
            traceback.print_exc()
            return []
    
    def _store_memory(self, memory_data: Dict[str, Any], memory_type: str) -> Dict[str, Any]:
        """Store memory using Bedrock AgentCore."""
        try:
            # Implementation based on Bedrock AgentCore short-term and long-term memory patterns
            if memory_type == "short_term":
                return self._store_short_term_memory(memory_data)
            elif memory_type == "long_term":
                return self._store_long_term_memory(memory_data)
            else:
                return {"success": False, "error": f"Invalid memory type: {memory_type}"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _store_short_term_memory(self, memory_data: Dict[str, Any]) -> Dict[str, Any]:
        """Store short-term memory using Bedrock AgentCore strands pattern."""
        try:
            # Based on the short-term memory sample from AgentCore
            # Using strands agent pattern for session-based memory
            print(f"📝 Storing short-term memory: {memory_data['content'][:50]}...")
            
            # Create memory session if not exists
            session_id = f"session_{memory_data['user_id']}_{datetime.utcnow().strftime('%Y%m%d')}"
            
            # Store in session-based memory using Bedrock AgentCore pattern
            # This follows the strands agent pattern from the sample
            memory_entry = {
                "id": memory_data["memory_id"],
                "content": memory_data["content"],
                "timestamp": memory_data["timestamp"],
                "user_id": memory_data["user_id"],
                "session_id": session_id,
                "type": "short_term"
            }
            
            # In a real implementation, this would call:
            # self.bedrock_client.invoke_agent() with memory storage parameters
            # For now, we'll simulate successful storage
            
            return {"success": True, "memory_id": memory_data["memory_id"], "session_id": session_id}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _store_long_term_memory(self, memory_data: Dict[str, Any]) -> Dict[str, Any]:
        """Store long-term memory using Bedrock AgentCore hooks pattern."""
        try:
            # Based on the long-term memory sample from AgentCore
            # Using hooks for persistent memory storage
            print(f"💾 Storing long-term memory: {memory_data['content'][:50]}...")
            
            # Create persistent memory entry using hooks pattern
            memory_entry = {
                "id": memory_data["memory_id"],
                "content": memory_data["content"],
                "timestamp": memory_data["timestamp"],
                "user_id": memory_data["user_id"],
                "type": "long_term",
                "metadata": memory_data.get("metadata", {}),
                "importance": memory_data.get("importance", "medium")  # For prioritization
            }
            
            # In a real implementation, this would use hooks to:
            # 1. Store in persistent storage (DynamoDB, RDS, etc.)
            # 2. Index for semantic search
            # 3. Apply retention policies
            # 4. Trigger memory consolidation processes
            
            # Example hook pattern:
            # hook_result = self._execute_memory_hook("store_long_term", memory_entry)
            
            return {"success": True, "memory_id": memory_data["memory_id"], "type": "long_term"}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _retrieve_memory(self, query: str, memory_type: str, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """Retrieve memories from Bedrock AgentCore."""
        try:
            # Implementation based on Bedrock AgentCore retrieval patterns
            if memory_type == "short_term":
                return self._retrieve_short_term_memory(query, user_id, limit)
            elif memory_type == "long_term":
                return self._retrieve_long_term_memory(query, user_id, limit)
            else:
                return []
                
        except Exception as e:
            print(f"❌ Error retrieving {memory_type} memory: {str(e)}")
            return []
    
    def _retrieve_short_term_memory(self, query: str, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """Retrieve short-term memories using Bedrock AgentCore strands pattern."""
        try:
            print(f"🔍 Searching short-term memory for: {query}")
            
            # Get current session ID
            session_id = f"session_{user_id}_{datetime.utcnow().strftime('%Y%m%d')}"
            
            # In a real implementation, this would:
            # 1. Query the current session's memory store
            # 2. Use semantic search to find relevant memories
            # 3. Apply recency weighting for short-term memories
            
            # Example retrieval pattern:
            # memories = self._query_session_memory(session_id, query, limit)
            
            # For now, return empty list - actual implementation would query Bedrock AgentCore
            return []
            
        except Exception as e:
            print(f"❌ Error retrieving short-term memory: {str(e)}")
            return []
    
    def _retrieve_long_term_memory(self, query: str, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """Retrieve long-term memories using Bedrock AgentCore hooks pattern."""
        try:
            print(f"🔍 Searching long-term memory for: {query}")
            
            # In a real implementation, this would use hooks to:
            # 1. Query persistent memory store with semantic search
            # 2. Apply importance weighting
            # 3. Consider memory age and relevance
            # 4. Use vector embeddings for similarity matching
            
            # Example hook pattern:
            # search_params = {
            #     "query": query,
            #     "user_id": user_id,
            #     "limit": limit,
            #     "memory_type": "long_term"
            # }
            # memories = self._execute_memory_hook("retrieve_long_term", search_params)
            
            # For now, return empty list - actual implementation would query Bedrock AgentCore
            return []
            
        except Exception as e:
            print(f"❌ Error retrieving long-term memory: {str(e)}")
            return []
    
    def _list_memories(self, memory_type: str, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """List memories from Bedrock AgentCore."""
        try:
            # Implementation based on Bedrock AgentCore listing patterns
            if memory_type == "short_term":
                return self._list_short_term_memories(user_id, limit)
            elif memory_type == "long_term":
                return self._list_long_term_memories(user_id, limit)
            else:
                return []
                
        except Exception as e:
            print(f"❌ Error listing {memory_type} memories: {str(e)}")
            return []
    
    def _list_short_term_memories(self, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """List short-term memories using Bedrock AgentCore strands pattern."""
        try:
            # For now, return empty list - in a real implementation, this would
            # list all short-term memories from the Bedrock AgentCore store
            print(f"📋 Listing short-term memories for user: {user_id}")
            return []
            
        except Exception as e:
            print(f"❌ Error listing short-term memories: {str(e)}")
            return []
    
    def _list_long_term_memories(self, user_id: str, limit: int) -> List[Dict[str, Any]]:
        """List long-term memories using Bedrock AgentCore hooks pattern."""
        try:
            # For now, return empty list - in a real implementation, this would
            # list all long-term memories from the Bedrock AgentCore store using hooks
            print(f"📋 Listing long-term memories for user: {user_id}")
            return []
            
        except Exception as e:
            print(f"❌ Error listing long-term memories: {str(e)}")
            return []
    
    def _execute_memory_hook(self, hook_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a memory hook using Bedrock AgentCore pattern."""
        try:
            # This method would implement the hook execution pattern from the AgentCore samples
            # Hooks are used for long-term memory operations like storage, retrieval, and maintenance
            
            print(f"🪝 Executing memory hook: {hook_name}")
            
            # In a real implementation, this would:
            # 1. Prepare hook parameters
            # 2. Call the appropriate Bedrock AgentCore hook
            # 3. Handle the response and any errors
            # 4. Return structured results
            
            # Example hook execution:
            # hook_response = self.bedrock_client.invoke_agent(
            #     agentId=self.agent_id,
            #     agentAliasId=self.agent_alias_id,
            #     sessionId=params.get("session_id", "default"),
            #     inputText=f"Execute hook: {hook_name} with params: {params}"
            # )
            
            # For now, return a placeholder response
            return {"success": True, "hook": hook_name, "result": []}
            
        except Exception as e:
            print(f"❌ Error executing hook {hook_name}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _create_memory_embedding(self, content: str) -> List[float]:
        """Create embeddings for memory content using Bedrock."""
        try:
            # In a real implementation, this would use Bedrock's embedding models
            # to create vector embeddings for semantic search
            
            # Example:
            # response = self.bedrock_client.invoke_model(
            #     modelId="amazon.titan-embed-text-v1",
            #     body=json.dumps({"inputText": content})
            # )
            # embedding = json.loads(response['body'].read())['embedding']
            
            # For now, return empty list
            return []
            
        except Exception as e:
            print(f"❌ Error creating embedding: {str(e)}")
            return []
    
    def _consolidate_memories(self, user_id: str) -> Dict[str, Any]:
        """Consolidate short-term memories into long-term storage."""
        try:
            # This method would implement memory consolidation logic
            # Moving important short-term memories to long-term storage
            
            print(f"🔄 Consolidating memories for user: {user_id}")
            
            # In a real implementation, this would:
            # 1. Analyze short-term memories for importance
            # 2. Identify patterns and relationships
            # 3. Move significant memories to long-term storage
            # 4. Clean up expired short-term memories
            
            return {"success": True, "consolidated": 0}
            
        except Exception as e:
            print(f"❌ Error consolidating memories: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def create_memory_hooks(self, actor_id: str, session_id: str):
        """Create memory hooks for automatic memory management."""
        if not BEDROCK_AGENTCORE_AVAILABLE or not self.memory_client:
            print("❌ Bedrock AgentCore not available, cannot create hooks")
            return None
            
        return BedrockAgentCoreMemoryHooks(
            memory_id=self.memory_id,
            memory_client=self.memory_client,
            actor_id=actor_id,
            session_id=session_id
        )
    
    def get_tools(self) -> List:
        """Get memory tools - following the same pattern as other memory providers."""
        if not hasattr(self, 'tools') or not self.tools:
            return self.initialize()
        return self.tools


class BedrockAgentCoreMemoryHooks:
    """Memory hooks for Bedrock AgentCore following the official samples pattern."""
    
    def __init__(self, memory_id: str, memory_client, actor_id: str, session_id: str):
        """Initialize memory hooks."""
        self.memory_id = memory_id
        self.memory_client = memory_client
        self.actor_id = actor_id
        self.session_id = session_id
        
        # Get namespaces from memory strategies with validation
        try:
            # Validate memory ID first
            if self._is_valid_memory_id(memory_id):
                strategies = self.memory_client.get_memory_strategies(self.memory_id)
                self.namespaces = {
                    strategy["type"]: strategy["namespaces"][0] 
                    for strategy in strategies
                }
                print(f"✅ Memory hooks initialized with namespaces: {list(self.namespaces.keys())}")
            else:
                print(f"⚠️ Invalid memory ID format for hooks: {memory_id}")
                raise ValueError(f"Invalid memory ID format: {memory_id}")
        except Exception as e:
            print(f"⚠️ Could not get memory strategies: {e}")
            # Use fallback namespaces
            self.namespaces = {
                "userPreferenceMemoryStrategy": f"genai/user/{actor_id}/preferences",
                "semanticMemoryStrategy": f"genai/user/{actor_id}/semantic"
            }
            print(f"✅ Using fallback namespaces: {list(self.namespaces.keys())}")

    def _is_valid_memory_id(self, memory_id: str) -> bool:
        """Validate memory ID format: [a-zA-Z][a-zA-Z0-9-_]{0,99}-[a-zA-Z0-9]{10}"""
        import re
        # Pattern allows: letter + alphanumeric/underscore/dash (0-99 chars) + dash + alphanumeric (exactly 10 chars)
        pattern = r'^[a-zA-Z][a-zA-Z0-9_-]{0,99}-[a-zA-Z0-9]{10}$'  
        return bool(re.match(pattern, memory_id))
    
    def retrieve_user_context(self, event):
        """Retrieve user context before processing query (MessageAddedEvent handler)."""
        try:
            # Import here to avoid circular imports
            from strands.hooks import MessageAddedEvent
            
            if not isinstance(event, MessageAddedEvent):
                return
                
            messages = event.agent.messages
            if (messages[-1]["role"] == "user" and 
                "toolResult" not in messages[-1]["content"][0]):
                
                user_query = messages[-1]["content"][0]["text"]
                print(f"🔍 Retrieving context for query: {user_query[:100]}...")
                
                # Retrieve context from all namespaces
                all_context = []
                
                for context_type, namespace in self.namespaces.items():
                    try:
                        # Format namespace with actual actor_id
                        formatted_namespace = namespace.format(actorId=self.actor_id)
                        
                        memories = self.memory_client.retrieve_memories(
                            memory_id=self.memory_id,
                            namespace=formatted_namespace,
                            query=user_query,
                            top_k=3
                        )
                        
                        if memories:
                            all_context.extend(memories)
                            print(f"📚 Retrieved {len(memories)} memories from {context_type}")
                            
                    except Exception as e:
                        print(f"⚠️ Could not retrieve from {context_type}: {e}")
                
                # Inject context into the conversation if found
                if all_context:
                    context_text = "\n".join([
                        f"Context: {mem.get('content', mem.get('text', str(mem)))}" 
                        for mem in all_context[:5]  # Limit to top 5 most relevant
                    ])
                    
                    # Add context as a system message
                    context_message = {
                        "role": "system",
                        "content": [{"text": f"Relevant user context:\n{context_text}"}]
                    }
                    
                    # Insert context before the user message
                    event.agent.messages.insert(-1, context_message)
                    print(f"✅ Injected {len(all_context)} context items into conversation")
                    
        except Exception as e:
            print(f"❌ Error retrieving user context: {e}")
            import traceback
            traceback.print_exc()
    
    def save_interaction(self, event):
        """Save interaction after agent response (AfterInvocationEvent handler)."""
        try:
            # Import here to avoid circular imports
            from strands.hooks import AfterInvocationEvent
            
            if not isinstance(event, AfterInvocationEvent):
                return
                
            messages = event.agent.messages
            if len(messages) >= 2 and messages[-1]["role"] == "assistant":
                
                # Get last user query and agent response
                user_message = None
                assistant_message = messages[-1]["content"][0]["text"]
                
                # Find the last user message
                for msg in reversed(messages[:-1]):
                    if msg["role"] == "user":
                        user_message = msg["content"][0]["text"]
                        break
                
                if user_message:
                    # Create event for memory storage
                    event_id = str(uuid.uuid4())
                    
                    # Store the interaction
                    self.memory_client.create_event(
                        memory_id=self.memory_id,
                        actor_id=self.actor_id,
                        session_id=self.session_id,
                        messages=[(user_message, "USER"), (assistant_message, "ASSISTANT")]
                    )
                    
                    print(f"✅ Saved interaction to memory: {event_id}")
                    
        except Exception as e:
            print(f"❌ Error saving interaction: {e}")
            import traceback
            traceback.print_exc()
    
    def register_hooks(self, registry):
        """Register memory hooks with the agent."""
        try:
            # Check if registry is available
            if registry is None:
                print("⚠️ Hook registry not available - manual registration needed")
                return False
            
            # Import here to avoid circular imports
            from strands.hooks import MessageAddedEvent, AfterInvocationEvent
            
            registry.add_callback(MessageAddedEvent, self.retrieve_user_context)
            registry.add_callback(AfterInvocationEvent, self.save_interaction)
            print("✅ Bedrock AgentCore memory hooks registered")
            return True
            
        except ImportError as e:
            print(f"⚠️ Could not import Strands hooks: {e}")
            return False
        except AttributeError as e:
            print(f"⚠️ Agent doesn't have hook_registry attribute: {e}")
            return False
        except Exception as e:
            print(f"❌ Error registering hooks: {e}")
            return False
