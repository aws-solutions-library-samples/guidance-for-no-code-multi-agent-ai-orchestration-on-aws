"""
Enhanced A2A Client with streaming-only support for message/stream protocol.
Implements proper A2A streaming using Server-Sent Events (SSE).
"""

import json
import logging
import os
import uuid
from typing import AsyncGenerator, Dict, Any, Optional, List
import httpx

logger = logging.getLogger(__name__)


class A2AStreamingClient:
    """
    Enhanced A2A client that supports streaming via the message/stream protocol.
    Implements proper Server-Sent Events handling per A2A specification.
    """
    
    def __init__(self, agent_urls: List[str], timeout: float = 600.0):
        """
        Initialize A2A streaming client.
        
        Args:
            agent_urls: List of agent URLs to communicate with
            timeout: Request timeout in seconds (default 600s / 10 minutes for VPC Lattice)
        """
        self.agent_urls = agent_urls
        self.timeout = timeout
        self.http_client = None
        
        logger.info(f"🕐 A2A Streaming Client initialized with {timeout}s timeout for VPC Lattice compatibility")
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            follow_redirects=True
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.http_client:
            await self.http_client.aclose()
    
    def _create_a2a_message(self, text: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Create A2A compliant message object.
        
        Args:
            text: Message text
            user_id: Optional user identifier to include in message
            
        Returns:
            A2A message object with proper structure
        """
        message = {
            "role": "user",
            "parts": [
                {
                    "kind": "text",
                    "text": text
                }
            ],
            "messageId": str(uuid.uuid4())
        }
        
        # Add user_id to message metadata if provided
        if user_id and user_id != "default_user":
            message["metadata"] = {"user_id": user_id}
        
        return message
    
    def _create_jsonrpc_request(self, method: str, message: Dict[str, Any], 
                               configuration: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Create JSON-RPC request for A2A communication.
        
        Args:
            method: A2A method name (always message/stream for streaming-only client)
            message: A2A message object
            configuration: Optional configuration
            
        Returns:
            JSON-RPC request object
        """
        params = {"message": message}
        if configuration:
            params["configuration"] = configuration
        
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": str(uuid.uuid4())
        }
    
    async def send_message_stream(self, agent_url: str, text: str) -> AsyncGenerator[str, None]:
        """
        Send streaming message using message/stream method with SSE.
        
        Args:
            agent_url: Target agent URL
            text: Message text
            
        Yields:
            Response chunks from the agent
        """
        if not self.http_client:
            raise RuntimeError("Client not initialized. Use async context manager.")
        
        try:
            message = self._create_a2a_message(text)
            request = self._create_jsonrpc_request("message/stream", message)
            
            logger.info(f"🌊 Sending A2A message/stream to {agent_url}")
            
            # Make streaming request
            async with self.http_client.stream(
                'POST',
                agent_url,
                json=request,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream"
                }
            ) as response:
                response.raise_for_status()
                
                # Check if response is SSE
                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    logger.warning(f"Expected text/event-stream, got {content_type}")
                
                # Process SSE stream
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    
                    # Process complete events
                    while "\n\n" in buffer:
                        event_data, buffer = buffer.split("\n\n", 1)
                        
                        # Parse SSE event
                        if event_data.startswith("data: "):
                            json_data = event_data[6:]  # Remove "data: " prefix
                            
                            try:
                                event = json.loads(json_data)
                                
                                # Process A2A streaming response
                                if "result" in event:
                                    result = event["result"]
                                    result_kind = result.get("kind")
                                    
                                    if result_kind == "artifact-update":
                                        # Extract text from artifact
                                        artifact = result.get("artifact", {})
                                        parts = artifact.get("parts", [])
                                        
                                        for part in parts:
                                            if part.get("kind") == "text" and "text" in part:
                                                yield part["text"]
                                    
                                    elif result_kind == "status-update":
                                        status = result.get("status", {})
                                        state = status.get("state")
                                        
                                        if state == "failed":
                                            # Extract error message if available
                                            if "message" in status and "parts" in status["message"]:
                                                for part in status["message"]["parts"]:
                                                    if part.get("kind") == "text":
                                                        yield f"Error: {part.get('text', 'Unknown error')}"
                                        
                                        # Check if this is the final event
                                        if result.get("final", False):
                                            logger.info("🏁 A2A streaming completed (final status received)")
                                            return
                                    
                                    elif result_kind == "task":
                                        # Initial task response - just log it
                                        task_id = result.get("id")
                                        logger.info(f"📋 A2A task created: {task_id}")
                                
                            except json.JSONDecodeError as e:
                                logger.warning(f"Failed to parse SSE JSON: {e}")
                                continue
                
                logger.info("✅ A2A streaming completed")
                
        except httpx.TimeoutException:
            error_msg = f"A2A stream to {agent_url} timed out after {self.timeout}s"
            logger.error(error_msg)
            yield f"Error: Request timed out"
            
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code} from {agent_url}"
            logger.error(error_msg)
            yield f"Error: HTTP {e.response.status_code}"
            
        except Exception as e:
            error_msg = f"Error in A2A streaming to {agent_url}: {str(e)}"
            logger.error(error_msg)
            yield f"Error: {str(e)}"
    
    async def send_to_agent(self, agent_url: str, text: str) -> AsyncGenerator[str, None]:
        """
        Send message to a specific agent URL using streaming.
        🎯 DIRECT TARGETING: Supervisor agent chooses the URL, we just send to it.
        
        Args:
            agent_url: Specific agent URL to send to (chosen by supervisor)
            text: Message text
            
        Yields:
            Response chunks from the targeted agent
        """
        # Resolve actual streaming URL from agent card if needed
        actual_agent_url = agent_url
        
        # If this looks like a discovery URL, try to resolve actual URL from agent card
        project_name = os.environ.get('PROJECT_NAME', 'genai-box')
        if not agent_url.startswith(f"http://{project_name}-"):  # Not already a VPC Lattice URL
            try:
                card_url = f"{agent_url}/.well-known/agent-card.json"
                logger.info(f"🔍 Resolving actual agent URL from card: {card_url}")
                
                response = await self.http_client.get(card_url)
                response.raise_for_status()
                
                agent_card = response.json()
                card_agent_url = agent_card.get("url", agent_url)
                
                if card_agent_url != agent_url:
                    actual_agent_url = card_agent_url
                    logger.info(f"🎯 Resolved to agent card URL: {actual_agent_url}")
                else:
                    logger.info(f"🔄 Using provided URL: {actual_agent_url}")
                    
            except Exception as e:
                logger.warning(f"Could not resolve agent card URL, using provided URL: {str(e)}")
        
        # Send to the specified agent
        try:
            async for chunk in self.send_message_stream(actual_agent_url, text):
                yield chunk
        except Exception as e:
            logger.error(f"Error communicating with agent at {actual_agent_url}: {str(e)}")
            yield f"Error: Failed to communicate with agent: {str(e)}"
    
    async def send_to_specific_agent(self, text: str, agent_name: str) -> AsyncGenerator[str, None]:
        """
        Send message to a specific agent by name using streaming.
        🎯 TARGETED STREAMING: Sends to identified agent, not first in list.
        
        Args:
            text: Message text
            agent_name: Name of the specific agent to target
            
        Yields:
            Response chunks from the targeted agent
        """
        if not self.agent_urls:
            yield "Error: No agent URLs available"
            return
        
        target_agent_url = None
        
        # Find the specific agent by name
        for discovery_url in self.agent_urls:
            try:
                # Fetch agent card to check name and get actual URL
                card_url = f"{discovery_url}/.well-known/agent-card.json"
                logger.info(f"🔍 Checking agent at {card_url} for name '{agent_name}'")
                
                response = await self.http_client.get(card_url)
                response.raise_for_status()
                
                agent_card = response.json()
                card_agent_name = agent_card.get("name", "")
                
                # Check if this is the target agent
                if agent_name.lower() in card_agent_name.lower() or card_agent_name.lower() in agent_name.lower():
                    # Get the actual streaming URL from agent card (VPC Lattice URL)
                    target_agent_url = agent_card.get("url", discovery_url)
                    logger.info(f"🎯 Found target agent '{card_agent_name}' at URL: {target_agent_url}")
                    break
                    
            except Exception as e:
                logger.warning(f"Error checking agent card at {discovery_url}: {str(e)}")
                continue
        
        if not target_agent_url:
            yield f"Error: Could not find agent with name '{agent_name}'"
            return
        
        # Send to the specific identified agent
        try:
            logger.info(f"🎯 Sending to specific agent '{agent_name}' at {target_agent_url}")
            async for chunk in self.send_message_stream(target_agent_url, text):
                yield chunk
        except Exception as e:
            logger.error(f"Error communicating with specific agent '{agent_name}' at {target_agent_url}: {str(e)}")
            yield f"Error: Failed to communicate with agent '{agent_name}': {str(e)}"


# Streaming-only tool creation function
def create_a2a_streaming_tools(agent_urls: List[str]) -> List[callable]:
    """
    Create A2A streaming tools for Strands agents that yield chunks as they arrive.
    🌊 STREAMING ONLY: All tools use message/stream protocol for real-time communication.
    
    Args:
        agent_urls: List of agent URLs to communicate with
        
    Returns:
        List of streaming tool functions for Strands agent
    """
    
    # Import strands tool decorator
    try:
        from strands.tools import tool
    except ImportError:
        # Fallback if tool decorator not available
        def tool(func):  # nosemgrep: useless-inner-function
            return func
    
    @tool
    async def a2a_send_message(text: str, agent_url: str = None) -> str:
        """
        Send message to a specific agent and collect streaming response.
        🎯 SIMPLE ROUTING: Supervisor chooses agent, A2A client just sends to it.
        
        Args:
            text: Message to send to the agent  
            agent_url: Optional specific agent URL (if not provided, uses first available)
            
        Returns:
            Complete response collected from streaming chunks
        """
        try:
            logger.info(f"🎯 A2A SEND MESSAGE: Sending to {'specific agent' if agent_url else 'available agent'} - {text[:100]}...")
            async with A2AStreamingClient(agent_urls) as client:
                full_response = ""
                chunk_count = 0
                
                if agent_url:
                    # Send to specific agent URL provided by supervisor
                    async for chunk in client.send_to_agent(agent_url, text):
                        chunk_count += 1
                        full_response += chunk
                else:
                    # Fallback to first available agent
                    discovery_url = agent_urls[0] if agent_urls else None
                    if not discovery_url:
                        return "Error: No agents available"
                    
                    async for chunk in client.send_to_agent(discovery_url, text):
                        chunk_count += 1
                        full_response += chunk
                
                logger.info(f"✅ A2A SEND COMPLETE: Collected {len(full_response)} characters from {chunk_count} streaming chunks")
                return full_response if full_response else "No response received"
                
        except Exception as e:
            logger.error(f"❌ A2A SEND ERROR: {str(e)}")
            return f"Error sending to agent: {str(e)}"
    
    @tool
    async def a2a_coordinate_specific_agent(text: str, agent_name: str) -> str:
        """
        Send message to a specific agent by name and collect streaming response.
        🎯 TARGETED COORDINATION: Sends to identified agent, not first in list.
        
        Args:
            text: Message to send to the agent
            agent_name: Name of the specific agent to target
            
        Returns:
            Complete response collected from streaming chunks for consolidation
        """
        try:
            logger.info(f"🎯 A2A TARGET COORDINATE: Sending to specific agent '{agent_name}' - {text[:100]}...")
            async with A2AStreamingClient(agent_urls) as client:
                full_response = ""
                chunk_count = 0
                
                async for chunk in client.send_to_specific_agent(text, agent_name):
                    chunk_count += 1
                    full_response += chunk
                
                logger.info(f"✅ A2A TARGET COMPLETE: Collected {len(full_response)} characters from {chunk_count} streaming chunks from '{agent_name}'")
                return full_response if full_response else "No response received"
                
        except Exception as e:
            logger.error(f"❌ A2A TARGET ERROR: {str(e)}")
            return f"Error coordinating with specific agent '{agent_name}': {str(e)}"
    
    @tool
    async def a2a_send_message_streaming(text: str):
        """
        Send message to another agent using A2A streaming protocol with real-time streaming.
        🌊🔥 STREAMING TOOL: Yields chunks as they arrive for immediate streaming to user.
        Simple transport layer - supervisor chooses which agent.
        
        Args:
            text: Message to send to the agent
            
        Yields:
            str: Response chunks from the agent as they arrive
        """
        try:
            logger.info(f"🌊🔥 A2A STREAMING TOOL CALL: Real-time streaming to agent - {text[:100]}...")
            async with A2AStreamingClient(agent_urls) as client:
                chunk_count = 0
                total_chars = 0
                
                # Use first available agent (supervisor should use specific tools if it wants specific agents)
                discovery_url = agent_urls[0] if agent_urls else None
                if not discovery_url:
                    yield "Error: No agents available"
                    return
                
                async for chunk in client.send_to_agent(discovery_url, text):
                    chunk_count += 1
                    total_chars += len(chunk)
                    
                    # Log first few chunks for debugging
                    if chunk_count <= 3:
                        logger.info(f"🌊🔥 A2A STREAMING CHUNK {chunk_count}: {chunk[:50]}...")
                    
                    yield chunk
                
                logger.info(f"✅ A2A STREAMING TOOL COMPLETE: {chunk_count} chunks, {total_chars} characters streamed")
                
        except Exception as e:
            logger.error(f"❌ A2A STREAMING TOOL ERROR: {str(e)}")
            yield f"Error communicating with agent: {str(e)}"
    
    @tool
    async def a2a_list_discovered_agents() -> str:
        """
        List all discovered A2A agents and their capabilities.
        
        Returns:
            JSON string listing available agents and their capabilities
        """
        try:
            logger.info("🔍 A2A TOOL CALL: Listing discovered agents...")
            agents_info = []
            
            async with A2AStreamingClient(agent_urls) as client:
                for agent_url in agent_urls:
                    try:
                        # Get agent card
                        card_url = f"{agent_url}/.well-known/agent-card.json"
                        logger.info(f"🔍 Fetching agent card from: {card_url}")
                        
                        response = await client.http_client.get(card_url)
                        response.raise_for_status()
                        
                        agent_card = response.json()
                        
                        agents_info.append({
                            "url": agent_url,
                            "name": agent_card.get("name", "Unknown Agent"),
                            "description": agent_card.get("description", "No description"),
                            "capabilities": agent_card.get("capabilities", {}),
                            "skills": agent_card.get("skills", []),
                            "streaming_supported": agent_card.get("capabilities", {}).get("streaming", False)
                        })
                        
                        logger.info(f"✅ Found agent: {agent_card.get('name')}")
                        
                    except Exception as e:
                        logger.error(f"Error fetching agent card from {agent_url}: {str(e)}")
                        agents_info.append({
                            "url": agent_url,
                            "name": "Unknown Agent",
                            "description": f"Error: {str(e)}",
                            "capabilities": {},
                            "skills": [],
                            "streaming_supported": False
                        })
            
            result = json.dumps(agents_info, indent=2)
            logger.info(f"✅ A2A TOOL RESPONSE: Found {len(agents_info)} agents")
            return result
            
        except Exception as e:
            logger.error(f"❌ A2A TOOL ERROR: {str(e)}")
            return f"Error discovering agents: {str(e)}"
    
    @tool
    async def a2a_discover_agent(agent_url: str) -> str:
        """
        Discover specific agent capabilities by fetching its agent card.
        
        Args:
            agent_url: URL of the agent to discover
            
        Returns:
            JSON string with agent capabilities
        """
        try:
            logger.info(f"🔍 A2A TOOL CALL: Discovering agent at {agent_url}")
            async with A2AStreamingClient([agent_url]) as client:
                card_url = f"{agent_url}/.well-known/agent-card.json"
                logger.info(f"🔍 Discovering agent at: {card_url}")
                
                response = await client.http_client.get(card_url)
                response.raise_for_status()
                
                agent_card = response.json()
                
                discovery_info = {
                    "url": agent_url,
                    "name": agent_card.get("name", "Unknown Agent"),
                    "description": agent_card.get("description", "No description"),
                    "version": agent_card.get("version", "unknown"),
                    "protocolVersion": agent_card.get("protocolVersion", "unknown"),
                    "preferredTransport": agent_card.get("preferredTransport", "JSONRPC"),
                    "capabilities": agent_card.get("capabilities", {}),
                    "skills": agent_card.get("skills", []),
                    "endpoints": agent_card.get("endpoints", []),
                    "additionalInterfaces": agent_card.get("additionalInterfaces", [])
                }
                
                result = json.dumps(discovery_info, indent=2)
                logger.info(f"✅ A2A TOOL RESPONSE: Discovered agent {agent_card.get('name')}")
                return result
                
        except Exception as e:
            logger.error(f"❌ A2A TOOL ERROR: {str(e)}")
            return f"Error discovering agent: {str(e)}"
    
    # Return simple streaming tools - let supervisor handle agent selection
    # 🌊 SIMPLE + STREAMING: Essential tools without overcomplicating agent selection  
    tools = [a2a_send_message, a2a_send_message_streaming, a2a_list_discovered_agents, a2a_discover_agent]
    
    # Set tool names for Strands recognition
    a2a_send_message.__name__ = "a2a_send_message"
    a2a_send_message_streaming.__name__ = "a2a_send_message_streaming"
    a2a_list_discovered_agents.__name__ = "a2a_list_discovered_agents" 
    a2a_discover_agent.__name__ = "a2a_discover_agent"
    
    return tools


class A2AStreamingGeneratorToolProvider:
    """
    A2A tool provider with streaming generator tools for real-time communication.
    🌊 STREAMING ONLY: Enables end-to-end streaming from worker agents to supervisor agent.
    """
    
    def __init__(self, known_agent_urls: List[str]):
        """
        Initialize A2A streaming tool provider.
        
        Args:
            known_agent_urls: List of known agent URLs
        """
        self.known_agent_urls = known_agent_urls
        self._tools = None
        
        logger.info(f"🌊🔥 A2A Streaming Tool Provider initialized with {len(known_agent_urls)} URLs")
        for i, url in enumerate(known_agent_urls):
            logger.info(f"   Agent {i+1}: {url}")
    
    @property
    def tools(self) -> List[callable]:
        """Get the A2A streaming tools."""
        if self._tools is None:
            self._tools = create_a2a_streaming_tools(self.known_agent_urls)
        return self._tools
    
    def get_tools(self) -> List[callable]:
        """Get the A2A streaming tools (alternative method name)."""
        return self.tools


# Backwards compatibility alias
A2AStreamingToolProvider = A2AStreamingGeneratorToolProvider
EnhancedA2AClientToolProvider = A2AStreamingGeneratorToolProvider
