"""
Base agent service module following DRY principles and SOLID design patterns.
Provides common functionality for all agent implementations.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import json
import uuid

# Import A2A agent card functionality
from a2a_agent_card import create_a2a_agent_card_provider

# Import enhanced logging configuration
from logging_config import get_logger
from secure_logging_utils import log_exception_safely

# Configure logging with agent name identification
logger = get_logger(__name__)

# Import health check middleware with robust fallback
try:
    from .health_check_middleware import setup_health_check_suppression, add_health_check_middleware
except ImportError:
    try:
        from health_check_middleware import setup_health_check_suppression, add_health_check_middleware
    except ImportError:
        # Fallback: create no-op functions to prevent startup failure
        def setup_health_check_suppression():
            pass
        
        def add_health_check_middleware(app):
            pass


class MessageRequest(BaseModel):
    """Request model for chat messages following modern type hints."""
    message: str = Field(..., min_length=1, description="User message")
    user_id: str = Field(default="default_user", description="User identifier")
    conversation_id: str = Field(default="default", description="Conversation identifier")


class MessageResponse(BaseModel):
    """Response model for chat messages."""
    response: str = Field(..., description="Agent response")
    user_id: str = Field(..., description="User identifier")
    conversation_id: str = Field(..., description="Conversation identifier")
    timestamp: str = Field(..., description="Response timestamp in ISO format")


# A2A Protocol Models
class A2AMessageSendParams(BaseModel):
    """A2A protocol message/send and message/stream parameters."""
    message: dict = Field(..., description="A2A message object with parts")
    configuration: Optional[dict] = Field(None, description="Optional configuration")
    metadata: Optional[dict] = Field(None, description="Optional metadata")


class A2AStreamingRequest(BaseModel):
    """A2A streaming request model for message/stream endpoint."""
    jsonrpc: str = Field(default="2.0", description="JSON-RPC version")
    method: str = Field(default="message/stream", description="A2A method name")
    params: A2AMessageSendParams = Field(..., description="A2A message parameters")
    id: Optional[str] = Field(default=None, description="Request ID")


class BaseAgentService:
    """
    Base service class for all agents following single responsibility principle.
    
    Provides common functionality:
    - Agent lifecycle management
    - Configuration handling
    - Error handling with proper logging
    - Message processing
    """
    
    def __init__(self, agent_name: str, agent_description: str, port: int):
        """Initialize base agent service with configuration."""
        self.agent_name = agent_name
        self.agent_description = agent_description
        self.port = port
        self.agent = None
        self.initialization_complete = False
        self.creation_time = datetime.now(timezone.utc)
        
        # Add common directory to Python path dynamically
        self._setup_python_path()
        
    def _setup_python_path(self) -> None:
        """Setup Python path for importing common modules."""
        current_dir = Path(__file__).parent
        # In container: /app/common, locally: common directory
        common_dir_container = Path("/app/common")
        common_dir_local = current_dir
        
        # Add common directory to path (higher priority for container)
        if common_dir_container.exists():
            if str(common_dir_container) not in sys.path:
                sys.path.insert(0, str(common_dir_container))
        else:
            if str(common_dir_local) not in sys.path:
                sys.path.insert(0, str(common_dir_local))
    
    def initialize_agent(self) -> None:
        """Initialize the Strands agent with proper error handling."""
        try:
            # Import here to avoid circular imports
            from agent_template import create_agent
            
            self.agent = create_agent(
                agent_name=self.agent_name,
                agent_description=self.agent_description
            )
            self.initialization_complete = True
            logger.info(f"✅ Agent '{self.agent_name}' initialized successfully")
        except Exception as e:
            log_exception_safely(logger, f"Failed to initialize agent '{self.agent_name}'", e)
            raise
    
    def get_agent(self):
        """Get the initialized agent instance with proper guard check."""
        if self.agent is None:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        return self.agent
    
    async def process_message(self, request: MessageRequest) -> str:
        """
        Process a user message and return agent response.
        
        Args:
            request: Message request containing user input
            
        Returns:
            Agent response string
        """
        if self.agent is None:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        try:
            # Use proper guard check as per coding principles
            if request.message is not None and len(request.message.strip()) > 0:
                response = self.agent(request.message)
                return str(response)
            else:
                raise HTTPException(status_code=400, detail="Message cannot be empty")
        except Exception as e:
            log_exception_safely(logger, "Error processing message", e)
            raise HTTPException(status_code=500, detail="Error processing message")
    
    async def process_streaming_message(self, request: MessageRequest) -> AsyncGenerator[str, None]:
        """
        Process a user message with streaming response.
        
        Args:
            request: Message request containing user input
            
        Yields:
            Response chunks as they become available
        """
        if self.agent is None:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        try:
            # Use proper guard check
            if request.message is not None and len(request.message.strip()) > 0:
                # Enhanced streaming implementation can be added here
                response = self.agent(request.message)
                yield str(response)
            else:
                raise HTTPException(status_code=400, detail="Message cannot be empty")
        except Exception as e:
            log_exception_safely(logger, "Error processing streaming message", e)
            raise HTTPException(status_code=500, detail="Error processing message")

    async def process_a2a_streaming_message(self, message_content: str, request_id: str) -> AsyncGenerator[str, None]:
        """
        Process A2A streaming message and yield Server-Sent Events.
        
        Args:
            message_content: The extracted message text
            request_id: JSON-RPC request ID for correlation
            
        Yields:
            Server-Sent Events formatted A2A responses
        """
        if self.agent is None:
            raise HTTPException(status_code=503, detail="Agent not initialized")
        
        try:
            # Generate unique IDs for A2A protocol
            task_id = str(uuid.uuid4())
            context_id = str(uuid.uuid4())
            message_id = str(uuid.uuid4())
            artifact_id = str(uuid.uuid4())
            
            # Create initial task response per A2A spec
            initial_task = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "kind": "task",
                    "id": task_id,
                    "contextId": context_id,
                    "status": {
                        "state": "submitted",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    },
                    "history": [{
                        "role": "user",
                        "parts": [{
                            "kind": "text",
                            "text": message_content
                        }],
                        "messageId": message_id,
                        "taskId": task_id,
                        "contextId": context_id
                    }]
                }
            }
            
            # Send initial task status
            yield f"data: {json.dumps(initial_task)}\n\n"
            
            # Send working status
            working_status = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "kind": "status-update",
                    "taskId": task_id,
                    "contextId": context_id,
                    "status": {
                        "state": "working",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    },
                    "final": False
                }
            }
            yield f"data: {json.dumps(working_status)}\n\n"
            
            # Process message through agent with streaming if available
            if hasattr(self.agent, 'stream_async'):
                logger.info("🌊 Using agent streaming capabilities for A2A streaming")
                full_response = ""
                async for event in self.agent.stream_async(message_content):
                    if "data" in event:
                        chunk = event["data"]
                        if chunk:
                            full_response += chunk
                            # Send artifact update for each chunk
                            artifact_update = {
                                "jsonrpc": "2.0", 
                                "id": request_id,
                                "result": {
                                    "kind": "artifact-update",
                                    "taskId": task_id,
                                    "contextId": context_id,
                                    "artifact": {
                                        "artifactId": artifact_id,
                                        "name": "streaming_response",
                                        "parts": [{
                                            "kind": "text",
                                            "text": chunk
                                        }]
                                    },
                                    "append": len(full_response) > len(chunk),
                                    "lastChunk": False
                                }
                            }
                            yield f"data: {json.dumps(artifact_update)}\n\n"
            else:
                logger.info("📝 Using synchronous agent for A2A streaming")
                # Fallback to synchronous processing
                full_response = str(self.agent(message_content))
            
            # Send final artifact update
            final_artifact = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "kind": "artifact-update",
                    "taskId": task_id,
                    "contextId": context_id,
                    "artifact": {
                        "artifactId": artifact_id,
                        "name": "final_response",
                        "parts": [{
                            "kind": "text",
                            "text": full_response if hasattr(self.agent, 'stream_async') else full_response
                        }]
                    },
                    "append": False,
                    "lastChunk": True
                }
            }
            yield f"data: {json.dumps(final_artifact)}\n\n"
            
            # Send final status update
            final_status = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "kind": "status-update",
                    "taskId": task_id,
                    "contextId": context_id,
                    "status": {
                        "state": "completed",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    },
                    "final": True
                }
            }
            yield f"data: {json.dumps(final_status)}\n\n"
            
        except Exception as e:
            log_exception_safely(logger, "Error in A2A streaming", e)
            # Send error status
            error_status = {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "kind": "status-update",
                    "taskId": task_id if 'task_id' in locals() else str(uuid.uuid4()),
                    "contextId": context_id if 'context_id' in locals() else str(uuid.uuid4()),
                    "status": {
                        "state": "failed",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": {
                            "role": "agent",
                            "parts": [{
                                "kind": "text",
                                "text": "Error processing request"
                            }],
                            "messageId": str(uuid.uuid4())
                        }
                    },
                    "final": True
                }
            }
            yield f"data: {json.dumps(error_status)}\n\n"


def create_agent_app(agent_name: str, agent_description: str, port: int) -> tuple[FastAPI, BaseAgentService]:
    """
    Factory function to create a FastAPI application with agent service.
    
    Follows factory pattern for better testability and consistency.
    
    Args:
        agent_name: Name of the agent (e.g., 'qa_agent')
        agent_description: Description of the agent's purpose
        port: Port number for the server
        
    Returns:
        Tuple of (FastAPI app, AgentService instance)
    """
    
    # Create agent service instance
    agent_service = BaseAgentService(agent_name, agent_description, port)
    
    # Create A2A agent card provider for discovery
    agent_card_provider = create_a2a_agent_card_provider(agent_name, agent_description, port)
    
    # Create FastAPI application
    app = FastAPI(
        title=f"{agent_name.replace('_', ' ').title()}",
        description=agent_description,
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # Add health check suppression middleware
    add_health_check_middleware(app)
    
    @app.on_event("startup")
    async def startup_event():  # nosemgrep: useless-inner-function
        """Initialize agent on startup."""
        logger.info(f"🚀 Starting {agent_name}...")
        # Set up health check log suppression
        setup_health_check_suppression()
        agent_service.initialize_agent()
        logger.info("✅ Agent startup complete")
    
    @app.on_event("shutdown")
    async def shutdown_event():  # nosemgrep: useless-inner-function
        """Clean up resources on shutdown."""
        logger.info(f"🔄 Shutting down {agent_name}...")
        # Add any cleanup logic here
        logger.info("✅ Shutdown complete")
    
    @app.get("/", response_model=dict[str, str])
    async def root():  # nosemgrep: useless-inner-function
        """Root endpoint providing basic agent information."""
        return {
            "name": agent_name.replace('_', ' ').title(),
            "status": "active",
            "agent_name": agent_service.agent_name,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    # Enhanced A2A JSON-RPC endpoint supporting both message/send and message/stream
    @app.post("/")
    async def enhanced_a2a_jsonrpc_endpoint(request_data: dict):  # nosemgrep: useless-inner-function
        """
        Enhanced A2A JSON-RPC endpoint supporting both message/send and message/stream.
        Handles incoming messages from other agents via the A2A framework.
        """
        method = request_data.get("method", "message/send")
        
        if method == "message/stream":
            # Handle streaming request
            try:
                logger.info(f"🌊 A2A JSON-RPC streaming request received by {agent_name}")
                
                request_id = request_data.get("id", str(uuid.uuid4()))
                params = request_data.get("params", {})
                
                # Extract message content
                message_content = None
                if "message" in params and "parts" in params["message"]:
                    text_parts = []
                    for part in params["message"]["parts"]:
                        if isinstance(part, dict) and part.get("kind") == "text" and "text" in part:
                            text_parts.append(part["text"])
                    
                    if text_parts:
                        message_content = " ".join(text_parts)
                    else:
                        # Return error as regular JSON response for streaming
                        error_response = {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {
                                "code": -32602,
                                "message": "No text content in message"
                            }
                        }
                        return JSONResponse(content=error_response, status_code=400)
                
                if not message_content:
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": "Invalid message format"
                        }
                    }
                    return JSONResponse(content=error_response, status_code=400)
                
                # Return A2A compliant streaming response
                return StreamingResponse(
                    agent_service.process_a2a_streaming_message(message_content, request_id),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no"
                    }
                )
                
            except Exception as e:
                log_exception_safely(logger, "Error in A2A JSON-RPC streaming", e)
                return JSONResponse(
                    status_code=500,
                    content={
                        "jsonrpc": "2.0",
                        "id": request_data.get("id"),
                        "error": {
                            "code": -32603,
                            "message": "Internal error occurred"
                        }
                    }
                )
        else:
            # Handle non-streaming requests (existing logic)
            try:
                logger.info(f"🔄 A2A message received by {agent_name}: {request_data}")
                
                # Extract message from A2A JSON-RPC format
                message_content = None
                
                if "params" in request_data and "message" in request_data["params"]:
                    message_obj = request_data["params"]["message"]
                    
                    # Handle A2A message structure with parts
                    if isinstance(message_obj, dict) and "parts" in message_obj:
                        # Extract text from parts array
                        text_parts = []
                        for part in message_obj["parts"]:
                            if isinstance(part, dict) and part.get("kind") == "text" and "text" in part:
                                text_parts.append(part["text"])
                        
                        if text_parts:
                            message_content = " ".join(text_parts)
                            logger.info(f"🔍 Extracted A2A message text: {message_content}")
                        else:
                            logger.error(f"❌ No text parts found in A2A message: {message_obj}")
                            return {"error": "No text content in message", "code": -32602}
                            
                    elif isinstance(message_obj, str):
                        # Simple string message
                        message_content = message_obj
                    else:
                        logger.error(f"❌ Unsupported A2A message format: {message_obj}")
                        return {"error": "Unsupported message format", "code": -32602}
                        
                elif "message" in request_data:
                    message_content = request_data["message"]
                else:
                    logger.error(f"❌ Invalid A2A message format: {request_data}")
                    return {"error": "Invalid message format", "code": -32602}
                
                if not message_content:
                    logger.error(f"❌ Empty message content extracted")
                    return {"error": "Empty message content", "code": -32602}
                
                # Create message request
                message_request = MessageRequest(
                    message=message_content,
                    user_id=request_data.get("params", {}).get("user_id", "a2a_agent"),
                    conversation_id=request_data.get("params", {}).get("conversation_id", "a2a_session")
                )
                
                # Process message through agent
                response = await agent_service.process_message(message_request)
                
                # Return A2A-compliant JSON-RPC response
                message_id = str(uuid.uuid4())
                context_id = str(uuid.uuid4())
                
                # Return Message object for simple responses (A2A spec allows either Task or Message)
                return {
                    "jsonrpc": "2.0",
                    "id": request_data.get("id"),
                    "result": {
                        "kind": "message",
                        "messageId": message_id,
                        "parts": [
                            {
                                "kind": "text",
                                "text": response
                            }
                        ],
                        "role": "agent",
                        "contextId": context_id
                    }
                }
                
            except Exception as e:
                log_exception_safely(logger, "Error processing A2A message", e)
                return {
                    "jsonrpc": "2.0", 
                    "id": request_data.get("id"),
                    "error": {
                        "code": -32603,
                        "message": "Internal error occurred"
                    }
                }
    
    @app.post("/chat", response_model=MessageResponse)
    async def chat_endpoint(request: MessageRequest) -> MessageResponse:  # nosemgrep: useless-inner-function
        """
        Main chat endpoint for synchronous message processing.
        
        Args:
            request: Message request from user
            
        Returns:
            Agent response with metadata
        """
        try:
            response = await agent_service.process_message(request)
            
            return MessageResponse(
                response=response,
                user_id=request.user_id,
                conversation_id=request.conversation_id,
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        except HTTPException:
            raise
        except Exception as e:
            log_exception_safely(logger, "Unexpected error in chat endpoint", e)
            raise HTTPException(status_code=500, detail="Internal server error")
    
    @app.get("/health")
    async def health_check():  # nosemgrep: useless-inner-function
        """Basic health check endpoint."""
        uptime_seconds = (datetime.now(timezone.utc) - agent_service.creation_time).total_seconds()
        
        return {
            "status": "healthy" if agent_service.initialization_complete else "initializing",
            "agent_name": agent_service.agent_name,
            "uptime_seconds": uptime_seconds,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    @app.get("/.well-known/agent-card.json")
    async def agent_card_endpoint():  # nosemgrep: useless-inner-function
        """
        A2A agent discovery endpoint.
        Returns standardized agent metadata for discovery by other agents.
        """
        try:
            # Get current agent instance for runtime information
            current_agent = None
            if agent_service.initialization_complete:
                try:
                    current_agent = agent_service.get_agent()
                except Exception:
                    # Agent not initialized yet, that's okay
                    current_agent = None
            
            # Generate agent card with current runtime information using A2A framework
            card_data = agent_card_provider.generate_well_known_response(current_agent)
            
            # Update base URL with actual host information if available
            hosted_dns = os.environ.get('HOSTED_DNS')
            http_url = os.environ.get('HTTP_URL')
            
            if hosted_dns:
                card_data["base_url"] = f"http://{hosted_dns}"
            elif http_url:
                card_data["base_url"] = http_url
            
            return JSONResponse(
                content=card_data,
                headers={
                    "Content-Type": "application/json",
                    "Cache-Control": "no-cache, must-revalidate",
                    "Access-Control-Allow-Origin": "*"
                }
            )
            
        except Exception as e:
            log_exception_safely(logger, "Error generating agent card", e)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Failed to generate agent card",
                    "agent_id": agent_service.agent_name,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )

    # A2A Protocol REST-style Streaming Endpoint (alternative to JSON-RPC at root)
    @app.post("/v1/message:stream")
    async def a2a_rest_streaming_endpoint(request_data: dict):  # nosemgrep: useless-inner-function
        """
        A2A REST-style streaming endpoint for message/stream per A2A protocol specification.
        Alternative to JSON-RPC streaming at root endpoint.
        Returns Server-Sent Events with proper A2A response format.
        """
        try:
            logger.info(f"🌊 A2A REST streaming request received by {agent_name}")
            
            # For REST endpoint, extract message directly from params
            message_content = None
            if "message" in request_data and "parts" in request_data["message"]:
                text_parts = []
                for part in request_data["message"]["parts"]:
                    if isinstance(part, dict) and part.get("kind") == "text" and "text" in part:
                        text_parts.append(part["text"])
                
                if text_parts:
                    message_content = " ".join(text_parts)
                    logger.info(f"🔍 Extracted A2A REST streaming message text: {message_content}")
                else:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "No text content in message"
                        }
                    )
            else:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Invalid message format - expected message with parts"
                    }
                )
            
            # Generate a request ID for REST-style requests
            request_id = str(uuid.uuid4())
            
            # Return A2A compliant streaming response
            return StreamingResponse(
                agent_service.process_a2a_streaming_message(message_content, request_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
            
        except Exception as e:
            log_exception_safely(logger, "Error in A2A REST streaming endpoint", e)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal error occurred"
                }
            )

    
    # Add configuration endpoints using our reusable module
    try:
        from config_endpoints import add_config_endpoints
        
        config_endpoints = add_config_endpoints(
            app=app,
            agent_name=agent_service.agent_name,
            port=port,
            agent_instance_getter=agent_service.get_agent,
            agent_service=agent_service,
            extra_runtime_info={
                "hosted_dns": os.environ.get('HOSTED_DNS'),
                "http_url": os.environ.get('HTTP_URL', f'http://0.0.0.0:{port}'),
                "agent_type": "fastapi",
                "supports_streaming": True
            }
        )
        
        # Pass the agent card provider and FastAPI app references for updates
        config_endpoints.agent_card_provider = agent_card_provider
        config_endpoints.fastapi_app = app
    except Exception as e:
        log_exception_safely(logger, "⚠️ Could not add configuration endpoints", e)
    
    return app, agent_service


def run_agent(agent_name: str, agent_description: str, port: int):
    """
    Run an agent server with the provided configuration.
    
    Uses environment variables for configuration following 12-factor principles.
    
    Args:
        agent_name: Name of the agent
        agent_description: Description of the agent's purpose  
        port: Port number for the server
    """
    
    # Configuration from environment variables
    # Default to 0.0.0.0 for container environments, allow override
    host = os.environ.get('HOST', '0.0.0.0')  # nosec: B104 # Container networking requires binding to all interfaces
    log_level = os.environ.get('LOG_LEVEL', 'info').lower()
    
    # Create FastAPI application
    app, agent_service = create_agent_app(agent_name, agent_description, port)
    
    # Log server startup information
    logger.info(f"🌐 Starting {agent_name} server on {host}:{port}")
    
    try:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=True
        )
    except Exception as e:
        log_exception_safely(logger, "Server startup failed", e)
        raise
