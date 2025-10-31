"""
Main FastAPI application module.

This is the main entry point for the Configuration API service,
following clean architecture principles with proper dependency injection.
"""

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.api import health_router, discovery_router, config_router, form_schema_router, deployment_router, registry_router
from app.api.auth import router as auth_router
from app.middleware import OAuth2BearerMiddleware

# Import enhanced logging configuration with agent name identification
import sys
from pathlib import Path

# Add common directory to path with multiple fallback options
common_paths = [
    Path("/app/common"),  # Container path
    Path(__file__).parent / "common",  # Local development relative path
    Path(__file__).parent.parent / "common",  # Alternative local path
]

common_dir_found = None
for common_dir in common_paths:
    if common_dir.exists():
        common_dir_found = common_dir
        if str(common_dir) not in sys.path:
            sys.path.insert(0, str(common_dir))
        break

# Removed debug logging - deployment working successfully

# Try to import with fallback to standard logging
try:
    from logging_config import get_logger
    from secure_logging_utils import log_exception_safely
    # Configure structured logging with agent name identification
    logger = get_logger(__name__)
except ImportError:
    # Fallback to standard logging if logging_config not available
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    logger.warning("Could not import enhanced logging_config, using standard logging")
    
    # Fallback secure logging function
    def log_exception_safely(logger, message, exception):
        logger.error(f"{message}: {str(exception)}")

# Import health check middleware with robust fallback
try:
    from common.health_check_middleware import setup_health_check_suppression, add_health_check_middleware
except ImportError:
    try:
        from health_check_middleware import setup_health_check_suppression, add_health_check_middleware
    except ImportError:
        # Fallback: create no-op functions to prevent startup failure
        def setup_health_check_suppression():
            pass
        
        def add_health_check_middleware(app):
            pass



@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle application startup and shutdown events.
    
    This replaces the deprecated @app.on_event decorators with
    the modern lifespan event handler approach.
    """
    # Startup
    aws_region = os.environ.get('AWS_REGION', 'us-east-1')
    logger.info(f"Configuration API starting up in region: {aws_region}")
    
    # Set up health check log suppression
    setup_health_check_suppression()
    logger.info("✅ Health check log suppression activated")
    
    # Initialize authentication service - CRITICAL: This is required for API security
    try:
        from common.auth import initialize_auth_service
        
        logger.info("🔐 Initializing authentication service...")
        
        # Generic authentication configuration - supports any identity provider
        secrets_manager_arn = os.environ.get('SECRETS_MANAGER_ARN')
        auth_provider_type = os.environ.get('AUTH_PROVIDER_TYPE', 'cognito').lower()
        
        if not secrets_manager_arn:
            logger.critical("❌ SECRETS_MANAGER_ARN environment variable not set")
            logger.critical("⚠️ Authentication is REQUIRED - service cannot start without it")
            raise RuntimeError("SECRETS_MANAGER_ARN must be set for authentication")
        
        # All provider types currently use the same initialization
        # Future: Add provider-specific initialization when supporting other providers
        auth_service = await initialize_auth_service(
            secret_arn=secrets_manager_arn,
            region=aws_region
        )
        
        # Check if initialization was actually successful
        if not auth_service or not auth_service.is_ready():
            logger.critical("❌ Authentication service failed to initialize - service not ready")
            logger.critical("⚠️ Possible causes:")
            logger.critical("   1. IAM permissions missing for Secrets Manager")
            logger.critical("   2. Secret does not exist or is in wrong region")
            logger.critical("   3. Secret format is invalid")
            logger.critical("💡 Check IAM role permissions and Secrets Manager secret")
            raise RuntimeError("Authentication service initialization failed - cannot start without auth")
        
        if auth_provider_type != 'cognito':
            logger.warning(f"⚠️ Provider type '{auth_provider_type}' not yet implemented - using Cognito")
        logger.info(f"✅ Authentication service initialized successfully with {auth_provider_type} provider")
            
    except Exception as e:
        logger.critical("❌ FATAL: Failed to initialize authentication service")
        log_exception_safely(logger, "❌ Authentication service initialization error", e)
        logger.critical("⚠️ Service cannot start without authentication - this is a security requirement")
        # Re-raise the exception to prevent service startup
        raise
    
    
    # Initialize SSM parameters defensively
    try:
        from app.services.ssm_service import SSMService
        from app.services.parameter_initialization import ParameterInitializationService
        
        logger.info("🔐 Initializing SSM parameters with SecureString encryption...")
        ssm_service = SSMService(aws_region)
        param_init_service = ParameterInitializationService(ssm_service)
        
        initialization_success = param_init_service.initialize_default_agent_parameters()
        
        if initialization_success:
            logger.info("✅ All SSM parameters initialized successfully with SecureString encryption")
            
            # Log initialization status
            status = param_init_service.get_initialization_status()
            logger.info(f"Parameter status: {status}")
        else:
            logger.warning("⚠️ Parameter initialization failed - continuing with existing parameters")
    
    except Exception as e:
        log_exception_safely(logger, "Error during parameter initialization", e)
        logger.info("Continuing startup - parameters may need manual creation")
    
    # Initialize Bedrock model cache at startup for fast form schema generation
    try:
        from app.services.bedrock_model_service import BedrockModelService
        
        logger.info("🤖 Initializing Bedrock model cache at application startup...")
        await BedrockModelService.initialize_global_model_cache(aws_region)
        logger.info("✅ Bedrock model cache initialization complete")
        
    except Exception as e:
        log_exception_safely(logger, "❌ Error during Bedrock model cache initialization", e)
        logger.info("Continuing startup - form schemas will use live API calls (slower)")
    
    logger.info("All services initialized successfully")
    logger.info("Ready to handle agent configuration requests")
    
    yield
    
    # Shutdown
    logger.info("Configuration API shutting down")
    logger.info("All resources cleaned up successfully")


def create_application() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    # Initialize FastAPI with comprehensive metadata
    app = FastAPI(
        title="GenAI In a Box Configuration API",
        description="Configuration management service for AI agents with VPC Lattice discovery",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan
    )
    
    # Configure CORS for cross-origin requests with secure defaults
    # Allow specific origins from environment or use secure defaults
    allowed_origins = os.environ.get('CORS_ALLOWED_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,  # Use environment-configured origins instead of wildcard
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],  # Explicit methods instead of wildcard
        allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "User-Agent"],  # Explicit headers instead of wildcard
    )
    
    # Add health check suppression middleware
    add_health_check_middleware(app)
    logger.info("✅ Health check suppression middleware added to Configuration API")
    
    # Add OAuth 2.0 Bearer token authentication middleware from common module
    ConfigApiAuthMiddleware = OAuth2BearerMiddleware
    app.add_middleware(ConfigApiAuthMiddleware)
    logger.info("✅ Common OAuth 2.0 Bearer token authentication middleware added")
    
    # Add validation error handler
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        """Handle Pydantic validation errors with detailed logging."""
        errors = exc.errors()
        logger.warning(f"Validation error on {request.method} {request.url}: {errors}")
        
        # Create user-friendly error message
        error_details = []
        for error in errors:
            loc = " -> ".join(str(x) for x in error["loc"])
            msg = error["msg"]
            error_details.append(f"{loc}: {msg}")
        
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Validation error", 
                "errors": error_details,
                "raw_errors": errors
            }
        )

    # Register API routers
    app.include_router(auth_router, tags=["Authentication"])
    app.include_router(health_router, tags=["Health"])
    app.include_router(discovery_router, tags=["Discovery"])
    app.include_router(config_router, tags=["Configuration"])
    app.include_router(form_schema_router, tags=["Form Schema"])
    app.include_router(deployment_router, tags=["Deployment"])
    app.include_router(registry_router, tags=["Service Registry"])
    
    return app


# Create the application instance
app = create_application()


if __name__ == '__main__':
    # Get port from environment variable with default fallback
    port = int(os.environ.get('PORT', 8000))
    
    # Get host from environment variable with secure default
    # Use 0.0.0.0 only when explicitly configured (e.g., in containers)
    host = os.environ.get('HOST', '127.0.0.1')
    
    # Development server configuration
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    )
