"""
Supervisor agent implementation using FastAPI with A2A coordination.
Manages coordination between specialized agents using A2A tools.
"""

import asyncio
import logging
import os
import sys
import argparse
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import PlainTextResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

# Import service layer components
from service import supervisor_service
from health import app_health
from streaming import agent_stream_processor, direct_stream_processor
from config import DEFAULT_HOST, DEFAULT_PORT, HOSTED_DNS

# Add common directory to path for configuration endpoints
current_dir = Path(__file__).parent
common_dir_container = Path("/app/common")
common_dir_local = current_dir.parent.parent / "common"

if common_dir_container.exists():
    sys.path.insert(0, str(common_dir_container))
else:
    sys.path.insert(0, str(common_dir_local))

# Import A2A agent card functionality
from a2a_agent_card import create_a2a_agent_card_provider

# Import enhanced logging configuration
from logging_config import get_logger

# Import health check middleware with robust fallback
try:
    from health_check_middleware import setup_health_check_suppression, add_health_check_middleware
except ImportError:
    try:
        from common.health_check_middleware import setup_health_check_suppression, add_health_check_middleware
    except ImportError:
        # Fallback: create no-op functions to prevent startup failure
        def setup_health_check_suppression():
            pass
        
        def add_health_check_middleware(app):
            pass

# Import OAuth authentication components from common module
from common.auth.middleware import (
    create_supervisor_auth_middleware, 
    get_current_user, 
    get_current_user_optional
)
from common.auth import initialize_auth_service, UserInfo
from common.secure_logging_utils import SecureLogger, log_exception_safely

# Enhanced logging configuration with agent name identification
logger = get_logger(__name__)


# Request models using modern type hints
class PromptRequest(BaseModel):
    """Request model for agent prompts."""
    prompt: str = Field(..., min_length=1, description="User prompt for the agent")
    user_id: str = Field(default="default_user", description="User identifier")
    agent_name: str = Field(default="supervisor_agent", description="Target agent name")


class DirectAgentRequest(BaseModel):
    """Request model for direct agent calls."""
    prompt: str = Field(..., min_length=1, description="Prompt to send to agent")
    agent_url: str = Field(..., description="URL of the target agent")
    timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="Request timeout in seconds")


# Define lifespan context manager for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management with proper error handling."""
    # Startup code
    logger.info("🚀 Starting supervisor agent application")
    try:
        # Set up health check log suppression
        setup_health_check_suppression()
        
        # Initialize authentication service - CRITICAL: This is required for supervisor agent security
        try:
            aws_region = os.environ.get('AWS_REGION', 'us-east-1')
            secrets_manager_arn = os.environ.get('SECRETS_MANAGER_ARN')
            
            if not secrets_manager_arn:
                logger.critical("❌ SECRETS_MANAGER_ARN environment variable not set")
                logger.critical("⚠️ Authentication is REQUIRED - supervisor agent cannot start without it")
                logger.critical("💡 Supervisor agent requires authentication to validate UI requests and forward tokens")
                raise RuntimeError("SECRETS_MANAGER_ARN must be set for supervisor agent authentication")
            
            logger.info("🔐 Initializing authentication service for supervisor agent...")
            auth_service = await initialize_auth_service(
                secret_arn=secrets_manager_arn,
                region=aws_region
            )
            
            # Check if initialization was actually successful
            if not auth_service or not auth_service.is_ready():
                logger.critical("❌ Authentication service failed to initialize - supervisor agent not ready")
                logger.critical("⚠️ Possible causes:")
                logger.critical("   1. IAM permissions missing for Secrets Manager")
                logger.critical("   2. Secret does not exist or is in wrong region")  
                logger.critical("   3. Secret format is invalid")
                logger.critical("💡 Check IAM role permissions and Secrets Manager secret")
                raise RuntimeError("Authentication service initialization failed - supervisor agent cannot start without auth")
                
            logger.info("✅ Authentication service initialized successfully for supervisor agent")
            
        except Exception:
            logger.critical("❌ FATAL: Failed to initialize authentication service for supervisor agent")
            logger.error("❌ Authentication initialization error")
            logger.critical("⚠️ Supervisor agent cannot start without authentication - this is a security requirement")
            # Re-raise the exception to prevent service startup
            raise
        
        # Initialize supervisor service
        await supervisor_service.initialize()
        logger.info("✅ Application startup completed")
    except Exception:
        logger.error("❌ Application startup failed")
        raise
    
    yield
    
    # Shutdown code
    try:
        await supervisor_service.cleanup()
        logger.info("✅ Application shutdown completed")
    except Exception:
        logger.error("⚠️ Error during shutdown")


# Create FastAPI app
app = FastAPI(
    title="Agent Supervisor",
    description="Supervisor agent that coordinates with other specialized agents using A2A tools",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add health check suppression middleware
add_health_check_middleware(app)

# Add OAuth authentication middleware using common module
SupervisorAuthMiddleware = create_supervisor_auth_middleware(supervisor_service)
app.add_middleware(SupervisorAuthMiddleware)
logger.info("✅ Common OAuth authentication middleware added to supervisor agent")

# Create A2A agent card provider for discovery
supervisor_agent_card_provider = create_a2a_agent_card_provider(
    "supervisor_agent", 
    "Supervisor agent that coordinates with other specialized agents using A2A tools",
    9003
)


@app.get("/")
async def root():
    """Root endpoint with service information."""
    try:
        return supervisor_service.get_service_info()
    except Exception as e:
        logger.error("Error getting service info")
        log_exception_safely(logger, e, "Error getting service info")
        return {
            "name": "Agent Supervisor",
            "status": "active",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@app.get("/health")
async def health_check():
    """Enhanced health check endpoint."""
    try:
        return app_health.get_basic_health()
    except Exception as e:
        logger.error("Health check failed")
        log_exception_safely(logger, e, "Health check failed")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": "Health check failed",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


@app.get("/.well-known/agent-card.json")
async def supervisor_agent_card_endpoint():
    """
    A2A agent discovery endpoint for supervisor agent.
    Returns standardized agent metadata for discovery by other agents.
    """
    try:
        # Get current supervisor agent instance for runtime information
        current_agent = None
        if supervisor_service._initialization_complete:
            try:
                current_agent = await supervisor_service.get_agent()
            except Exception:
                # Agent not initialized yet, that's okay
                current_agent = None
        
        # Generate agent card with current runtime information and supervisor-specific capabilities
        extra_capabilities = {
            "a2a_calls": True,  # Supervisor can make A2A calls
            "coordination": True,  # Can coordinate between agents
            "agent_discovery": True  # Can discover other agents
        }
        
        # Add supervisor-specific endpoints
        extra_endpoints = [
            {
                "path": "/agent",
                "method": "POST",
                "description": "Coordinate with specialized agents via A2A tools",
                "content_type": "application/json"
            },
            {
                "path": "/agent-streaming", 
                "method": "POST",
                "description": "Stream coordination responses from specialized agents",
                "content_type": "text/plain",
                "streaming": True
            },
            {
                "path": "/direct-agent",
                "method": "POST", 
                "description": "Direct agent-to-agent communication",
                "content_type": "application/json"
            },
            {
                "path": "/refresh-agent-urls",
                "method": "POST",
                "description": "Refresh agent URLs from configuration API without restart",
                "content_type": "application/json"
            }
        ]
        
        card_data = supervisor_agent_card_provider.generate_well_known_response(
            current_agent, 
            extra_capabilities=extra_capabilities,
            extra_endpoints=extra_endpoints
        )
        
        # Update base URL with actual host information if available
        hosted_dns = os.environ.get('HOSTED_DNS')
        http_url = os.environ.get('HTTP_URL')
        
        if hosted_dns:
            card_data["base_url"] = f"http://{hosted_dns}"
        elif http_url:
            card_data["base_url"] = http_url
        
        # Add supervisor-specific metadata
        card_data["agent_type"] = "supervisor"
        card_data["coordination_enabled"] = True
        card_data["known_agents"] = supervisor_service.get_service_info().get('known_agents', [])
        
        return JSONResponse(
            content=card_data,
            headers={
                "Content-Type": "application/json",
                "Cache-Control": "no-cache, must-revalidate",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except Exception as e:
        logger.error("Error generating supervisor agent card")
        log_exception_safely(logger, e, "Error generating supervisor agent card")
        return JSONResponse(
            status_code=500,
            content={
                "error": "Failed to generate agent card",
                "agent_id": "supervisor_agent",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


@app.post('/agent')
async def deprecated_agent_endpoint(
    request: PromptRequest,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    DEPRECATED: Non-streaming endpoint redirected to streaming for consistency.
    All UI communication with supervisor agent should use streaming for optimal UX.
    """
    logger.warning("🚨 DEPRECATED ENDPOINT: /agent called - redirecting to streaming endpoint")
    logger.info("💡 STREAMING ENFORCED: All supervisor communication uses streaming for better UX")
    
    # Redirect to streaming endpoint for consistency (call without current_user since it's handled by middleware)
    return await agent_stream_processor(request)


@app.post('/direct-agent')
async def direct_agent_call(
    request: DirectAgentRequest,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Endpoint that directly calls another agent using the direct stream processor.
    """
    try:
        result = await direct_stream_processor(request)
        return result
    except Exception as e:
        logger.error("Error in direct agent call")
        log_exception_safely(logger, e, "Error in direct agent call")
        raise HTTPException(status_code=500, detail="Direct agent call failed")


@app.post('/agent-streaming')
async def get_agent_streaming_response(
    request: PromptRequest,
    current_user: UserInfo = Depends(get_current_user)
):
    """
    Endpoint to stream information from supervisor agent with A2A coordination.
    Uses the streaming module from the service layer.
    """
    try:
        result = await agent_stream_processor(request)
        return result
    except Exception as e:
        logger.error("Error in streaming response")
        log_exception_safely(logger, e, "Error in streaming response")
        raise HTTPException(status_code=500, detail="Streaming response failed")


# Add A2A streaming support to supervisor agent
@app.post("/v1/message:stream")
async def supervisor_a2a_streaming_endpoint(request_data: dict):
    """
    A2A streaming endpoint for supervisor agent implementing message/stream protocol.
    Returns Server-Sent Events with proper A2A response format.
    """
    try:
        logger.info(f"🌊 A2A streaming request received by supervisor agent")
        
        # Validate JSON-RPC structure
        if not isinstance(request_data, dict):
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32600,
                        "message": "Invalid Request"
                    }
                }
            )
        
        request_id = request_data.get("id", str(uuid.uuid4()))
        method = request_data.get("method")
        params = request_data.get("params", {})
        
        # Validate method
        if method != "message/stream":
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": "Method not found"
                    }
                }
            )
        
        # Extract message content from A2A format
        message_content = None
        if "message" in params and "parts" in params["message"]:
            text_parts = []
            for part in params["message"]["parts"]:
                if isinstance(part, dict) and part.get("kind") == "text" and "text" in part:
                    text_parts.append(part["text"])
            
            if text_parts:
                message_content = " ".join(text_parts)
                logger.info(f"🔍 Extracted supervisor A2A streaming message: {message_content}")
            else:
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32602,
                            "message": "No text content in message"
                        }
                    }
                )
        else:
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Invalid message format"
                    }
                }
            )
        
        # Create PromptRequest for existing streaming processor
        prompt_request = PromptRequest(
            prompt=message_content,
            user_id="a2a_client",
            agent_name="supervisor_agent"
        )
        
        # Use existing streaming processor for A2A coordination
        streaming_response = await agent_stream_processor(prompt_request)
        return streaming_response
        
    except Exception as e:
        logger.error("Error in supervisor A2A streaming endpoint")
        log_exception_safely(logger, e, "Error in supervisor A2A streaming endpoint")
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "id": request_data.get("id") if isinstance(request_data, dict) else None,
                "error": {
                    "code": -32603,
                    "message": "Internal error occurred"
                }
            }
        )


# Enhanced A2A JSON-RPC endpoint for supervisor supporting both message/send and message/stream
async def supervisor_enhanced_a2a_endpoint(request_data: dict):
    """Handle both sync and streaming A2A requests for supervisor agent."""
    method = request_data.get("method", "message/send")
    
    if method == "message/stream":
        return await supervisor_a2a_streaming_endpoint(request_data)
    else:
        # Handle synchronous requests via existing /agent endpoint
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
                return {
                    "jsonrpc": "2.0",
                    "id": request_data.get("id"),
                    "error": {
                        "code": -32602,
                        "message": "No text content in message"
                    }
                }
        
        if not message_content:
            return {
                "jsonrpc": "2.0",
                "id": request_data.get("id"),
                "error": {
                    "code": -32602,
                    "message": "Invalid message format"
                }
            }
        
        # Create PromptRequest
        prompt_request = PromptRequest(
            prompt=message_content,
            user_id="a2a_client",
            agent_name="supervisor_agent"
        )
        
        # Use existing /agent endpoint logic
        response = await get_agent_response(prompt_request)
        
        # Convert PlainTextResponse to A2A JSON-RPC format
        import uuid
        response_text = response.body.decode() if hasattr(response, 'body') else str(response)
        
        return {
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "result": {
                "kind": "message",
                "messageId": str(uuid.uuid4()),
                "parts": [
                    {
                        "kind": "text",
                        "text": response_text
                    }
                ],
                "role": "agent",
                "contextId": str(uuid.uuid4())
            }
        }

# Override the root POST endpoint to also handle A2A for supervisor
@app.post("/", response_class=StreamingResponse)
async def supervisor_root_endpoint(request_data: dict):
    """
    Enhanced supervisor root endpoint supporting A2A JSON-RPC (both sync and streaming).
    """
    method = request_data.get("method", "message/send")
    
    if method in ["message/send", "message/stream"]:
        return await supervisor_enhanced_a2a_endpoint(request_data)
    else:
        return {
            "jsonrpc": "2.0",
            "id": request_data.get("id"),
            "error": {
                "code": -32601,
                "message": "Method not found"
            }
        }


@app.post('/refresh-agent-urls')
async def refresh_agent_urls():
    """
    Endpoint to refresh agent URLs from configuration API.
    
    This allows the supervisor agent to update its known agent list without requiring a restart.
    Useful when new agents are added or existing agents change their URLs.
    """
    try:
        logger.info("🔄 Agent URLs refresh requested via API")
        result = await supervisor_service.refresh_agent_urls()
        
        # Service raises exceptions on error, so if we get here it's success
        # Only return safe fields to prevent information disclosure
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "urls_changed": result.get("urls_changed", False),
                "total_agents": result.get("total_agents", 0)
            }
        )
            
    except Exception as e:
        logger.error("Error in refresh agent URLs endpoint")
        log_exception_safely(logger, e, "Error in refresh agent URLs endpoint")
        raise HTTPException(
            status_code=500,
            detail="Failed to refresh agent URLs"
        )


@app.post('/refresh-config')
async def refresh_supervisor_config():
    """
    Endpoint to refresh supervisor configuration from SSM parameters.
    
    This allows updating the supervisor agent's system prompt, model settings,
    and other configuration without requiring a restart. Configuration is loaded
    from SSM parameters and the agent is reinitialized with new settings.
    """
    try:
        logger.info("🔄 Supervisor configuration refresh requested via API")
        
        # Refresh supervisor configuration from SSM
        config_refreshed = supervisor_service.refresh_supervisor_config()
        
        if config_refreshed:
            # Get the updated configuration
            config = supervisor_service.get_supervisor_config()
            system_prompt = supervisor_service.get_supervisor_system_prompt()
            
            # If supervisor agent exists, recreate it with new configuration
            if supervisor_service.supervisor_agent and supervisor_service.provider:
                from custom_bedrock_provider import ModelSwitchingBedrockProvider
                custom_bedrock_provider = ModelSwitchingBedrockProvider()
                custom_switching_model = custom_bedrock_provider.create_switching_model(
                    initial_model_id=config.get('model_id'),
                    region='us-east-1',
                    max_tokens=config.get('max_tokens', 4000),
                    temperature=config.get('temperature', 0.7),
                    top_p=config.get('top_p', 0.9)
                )
                
                supervisor_service.supervisor_agent = supervisor_service.supervisor_agent.__class__(
                    name=config.get('agent_name', 'Supervisor Agent'),
                    description=config.get('agent_description', 'A supervisor agent that coordinates with other specialized agents'),
                    system_prompt=system_prompt,
                    tools=supervisor_service.provider.tools,
                    model=custom_switching_model
                )
                
                logger.info(f"✅ Supervisor agent recreated with updated configuration")
                logger.info(f"   - Model: {config.get('model_id')}")
                logger.info(f"   - Agent name: {config.get('agent_name')}")
                logger.info(f"   - System prompt length: {len(system_prompt)} characters")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Supervisor configuration refreshed successfully",
                "config_updated": config_refreshed,
                "agent_name": config.get('agent_name') if config_refreshed else None,
                "model_id": config.get('model_id') if config_refreshed else None,
                "system_prompt_length": len(system_prompt) if config_refreshed else None,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
            
    except Exception as e:
        logger.error("Error in refresh supervisor config endpoint")
        log_exception_safely(logger, e, "Error in refresh supervisor config endpoint")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": "Failed to refresh supervisor configuration",
                "config_updated": False,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


@app.get('/config/current')
async def get_current_supervisor_config():
    """
    Endpoint to get the current supervisor configuration.
    
    Returns the current configuration loaded from SSM parameters including
    agent settings, model configuration, and system prompt information.
    """
    try:
        logger.info("📋 Current supervisor configuration requested via API")
        
        config = supervisor_service.get_supervisor_config()
        system_prompt = supervisor_service.get_supervisor_system_prompt()
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "config": config,
                "system_prompt": system_prompt,
                "system_prompt_length": len(system_prompt),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
            
    except Exception as e:
        logger.error("Error getting current supervisor config")
        log_exception_safely(logger, e, "Error getting current supervisor config")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error", 
                "message": "Failed to get current configuration",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )


# Add configuration endpoints using common module
try:
    from config_endpoints import add_config_endpoints
    
    add_config_endpoints(
        app=app,
        agent_name='supervisor_agent',
        port=9003,
        agent_instance_getter=supervisor_service.get_agent,
        service_info_getter=supervisor_service,
        extra_runtime_info={
            "hosted_dns": os.environ.get('HOSTED_DNS'),
            "http_url": os.environ.get('HTTP_URL', 'http://0.0.0.0:9003'),
            "agent_type": "supervisor",
            "supports_streaming": True,
            "a2a_enabled": True
        }
    )
    logger.info("✅ Configuration endpoints added to supervisor-agent")
except Exception as e:
    logger.error("⚠️ Could not add configuration endpoints")
    log_exception_safely(logger, e, "Could not add configuration endpoints")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Agent Supervisor')
    parser.add_argument('--watch', action='store_true', 
                       help='Enable file watching for development')
    args = parser.parse_args()

    # Use hosted DNS from environment variable
    hosted_dns = os.environ.get('HOSTED_DNS')

    # Configure uvicorn options
    uvicorn_config = {
        "app": app,
        "host": "0.0.0.0",  # nosec: B104 # Container networking requires binding to all interfaces
        "port": 9003,
        "log_level": "info"
    }

    # Add file watching for development
    if args.watch:
        logging.info("🔄 File watching enabled for development")
        uvicorn_config.update({
            "reload": True,
            "reload_dirs": [".", "../common"],
            "reload_includes": ["*.py"],
            "reload_excludes": ["__pycache__/*", "*.pyc"]
        })

    if hosted_dns:
        logging.info(f"Using Hosted DNS: {hosted_dns}")
    else:
        logging.info("HOSTED_DNS environment variable not set, running locally")

    # Run the server
    logger.info("🌐 Starting supervisor agent server on 0.0.0.0:9003")
    try:
        uvicorn.run(**uvicorn_config)
    except Exception as e:
        logger.error("Server startup failed")
        log_exception_safely(logger, e, "Server startup failed")
        raise

# Sample Request Examples:
'''
curl -X POST http://localhost:9003/agent \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Find out top 3 deals by deal value from Snowflake"
  }'

curl -X POST http://localhost:9003/agent-streaming \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Find out top 3 deals by deal value from Snowflake"
  }'

curl -X POST http://localhost:9003/refresh-agent-urls \
  -H "Content-Type: application/json"

curl http://localhost:9003/health
curl http://localhost:9003/config/status
'''
