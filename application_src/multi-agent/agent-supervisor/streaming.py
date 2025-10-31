"""
Enhanced streaming module for agent responses with A2A streaming support.
Integrates with A2A protocol for proper inter-agent streaming communication.
"""
import asyncio
import logging
import time
import httpx
from typing import AsyncGenerator, Optional
from strands.types.exceptions import ModelThrottledException

# Import our enhanced A2A streaming client
import sys
from pathlib import Path
current_dir = Path(__file__).parent
common_dir_container = Path("/app/common")
common_dir_local = current_dir.parent.parent / "common"
if common_dir_container.exists():
    sys.path.insert(0, str(common_dir_container))
else:
    sys.path.insert(0, str(common_dir_local))

from a2a_streaming_client import A2AStreamingClient
from common.secure_logging_utils import log_exception_safely

logger = logging.getLogger(__name__)


class AgentStreamProcessor:
    """
    Simple processor for streaming agent responses.
    """
    
    async def process_agent_stream(
        self,
        enhanced_agent,
        prompt: str
    ) -> AsyncGenerator[str, None]:
        """
        Process agent streaming with immediate model switching support.
        
        Args:
            enhanced_agent: The enhanced agent wrapper with immediate model switching
            prompt: The prompt to send to the agent
            
        Yields:
            str: Response chunks from the agent
        """
        if not enhanced_agent:
            logger.error("No enhanced agent provided for streaming")
            yield "Error: Enhanced agent not available"
            return
        
        try:
            logger.info(f"Processing streaming request with enhanced agent, prompt length: {len(prompt)}")
            
            # Use enhanced agent streaming with immediate model switching
            async for item in enhanced_agent.stream_async_with_switching(prompt):
                if "data" in item:
                    chunk = item['data']
                    if chunk:
                        yield chunk
            
            logger.info("Enhanced streaming completed successfully")
            
        except Exception:
            # Enhanced agent handles all model switching internally
            # If we get here, it means all models failed or there's a non-recoverable error
            logger.exception("Enhanced streaming failed after model switching attempts")
            yield "Error: Enhanced streaming failed after model switching attempts"


class DirectStreamProcessor:
    """
    Simple processor for direct agent-to-agent streaming calls.
    """
    
    async def process_direct_stream(
        self,
        http_client: httpx.AsyncClient,
        agent_url: str,
        prompt: str,
        timeout: float = 30.0
    ) -> AsyncGenerator[str, None]:
        """
        Process direct streaming to another agent.
        
        Args:
            http_client: HTTP client for making requests
            agent_url: URL of the target agent
            prompt: Prompt to send
            timeout: Request timeout
            
        Yields:
            str: Response chunks from the target agent
        """
        if not http_client:
            logger.error("No HTTP client provided for direct streaming")
            yield "Error: HTTP client not available"
            return
        
        try:
            logger.info(f"Starting direct stream to {agent_url}")
            
            # Prepare request payload
            payload = {
                "prompt": prompt,
                "user_id": "supervisor_agent",
                "agent_name": "direct_call"
            }
            
            # Make streaming request
            async with http_client.stream(
                'POST',
                f"{agent_url}/agent-streaming",
                json=payload,
                timeout=timeout
            ) as response:
                response.raise_for_status()
                
                async for chunk in response.aiter_text():
                    if chunk:
                        yield chunk
            
            logger.info("Direct streaming completed successfully")
            
        except httpx.TimeoutException:
            error_msg = f"Direct stream to {agent_url} timed out after {timeout}s"
            logger.error(error_msg)
            yield f"Error: Request timed out"
            
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error {e.response.status_code} from {agent_url}: {e.response.text}"
            logger.error(error_msg)
            yield f"Error: HTTP {e.response.status_code}"
            
        except Exception:
            logger.exception(f"Error in direct streaming to {agent_url}")
            yield "Error: Direct streaming failed"


# Global instances
_agent_stream_processor = AgentStreamProcessor()
_direct_stream_processor = DirectStreamProcessor()

# Wrapper functions for FastAPI endpoints
async def agent_stream_processor(request):
    """
    Process streaming agent request using the service layer.
    
    Args:
        request: PromptRequest with prompt, user_id, agent_name
        
    Returns:
        StreamingResponse with agent output
    """
    from fastapi.responses import StreamingResponse
    from service import supervisor_service
    
    start_time = time.time()
    prompt = request.prompt
    
    logger.info(f"🎯 A2A STREAMING COORDINATION: Received request for agent coordination")
    
    if not prompt:
        async def error_generator():
            yield "Error: No prompt provided"
        return StreamingResponse(error_generator(), media_type="text/plain")
    
    async def generate():
        try:
            # Get the supervisor agent from the service
            supervisor_agent = await supervisor_service.get_agent()
            if not supervisor_agent:
                yield "Error: Supervisor agent not available"
                return
                
            # A2A-focused prompt that explicitly instructs tool usage with user context
            user_id = getattr(request, 'user_id', 'default_user')
            coordination_prompt = f"""I am a supervisor agent with access to A2A (Agent-to-Agent) tools to coordinate with specialized agents.

User ID: {user_id}
User request: {prompt}

I need to use my A2A tools to handle this request for this specific user:
1. First, use a2a_list_discovered_agents to see what agents are available
2. Then use a2a_send_message to send the user's request to the appropriate specialized agent
3. Wait for the response and relay it back to the user

I must use my A2A tools - I should NOT attempt to handle this request myself. Remember to include the user context when communicating with other agents."""
            
            logger.info(f"🤝 Streaming A2A coordination with specialized agents")
            
            # Track streaming metrics
            first_chunk_received = False
            chunks_received = 0
            total_chars_streamed = 0
            agent_call_detected = False
            
            # Stream responses from the supervisor agent with A2A coordination
            async for event in supervisor_agent.stream_async(coordination_prompt):
                if "data" in event:
                    chunks_received += 1
                    chunk_text = event["data"]
                    total_chars_streamed += len(chunk_text)
                    
                    # Track first chunk timing
                    if not first_chunk_received:
                        first_chunk_received = True
                        first_chunk_time = time.time() - start_time
                        logger.info(f"⚡ First chunk from A2A streaming coordination in {first_chunk_time:.4f}s")
                    
                    # Check for A2A tool usage indicators
                    if any(tool_indicator in chunk_text for tool_indicator in [
                        "a2a_list_discovered_agents", "a2a_send_message", "a2a_discover_agent"
                    ]):
                        agent_call_detected = True
                    
                    yield chunk_text
            
            elapsed = time.time() - start_time
            
            # Final logging
            if agent_call_detected:
                logger.info(f"🎯 STREAMING AGENT COORDINATION SUMMARY: A2A tools detected, Total coordination time: {elapsed:.4f}s")
            else:
                logger.warning(f"⚠️ NO SPECIALIZED AGENT CALLED (STREAMING): Supervisor handled request directly in {elapsed:.4f}s")
            
            logger.info(f"✅ A2A streaming coordination completed in {elapsed:.4f}s with {chunks_received} chunks ({total_chars_streamed} chars)")
            
        except Exception:
            logger.exception("Error in A2A streaming coordination")
            yield "Error: Streaming coordination failed"
    
    return StreamingResponse(generate(), media_type="text/plain")


async def direct_stream_processor(request):
    """
    Process direct streaming agent request.
    
    Args:
        request: DirectAgentRequest with prompt, agent_url, timeout
        
    Returns:
        StreamingResponse with direct agent output
    """
    from fastapi.responses import StreamingResponse
    from service import supervisor_service
    
    start_time = time.time()
    prompt = request.prompt
    agent_url = request.agent_url
    timeout = request.timeout
    
    logger.info(f"🔄 Direct streaming request to {agent_url}")
    
    if not prompt or not agent_url:
        async def error_generator():
            yield "Error: Missing prompt or agent URL"
        return StreamingResponse(error_generator(), media_type="text/plain")
    
    async def generate():
        try:
            # Get HTTP client from service
            if not supervisor_service.http_client:
                yield "Error: HTTP client not available"
                return
                
            # Use the direct stream processor
            async for chunk in _direct_stream_processor.process_direct_stream(
                supervisor_service.http_client, agent_url, prompt, timeout
            ):
                yield chunk
                
        except Exception:
            logger.exception("Error in direct streaming")
            yield "Error: Direct streaming failed"
    
    return StreamingResponse(generate(), media_type="text/plain")
