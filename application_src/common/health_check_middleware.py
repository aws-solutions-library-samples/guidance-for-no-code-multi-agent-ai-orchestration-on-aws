"""
Health check logging suppression middleware for FastAPI applications.
Prevents load balancer health checks from cluttering application logs.
"""

import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class HealthCheckLoggingFilter(logging.Filter):
    """
    Logging filter to suppress uvicorn access logs for health check endpoints.
    This works at the uvicorn level to prevent health check spam in logs.
    """
    
    def __init__(self):
        super().__init__()
        self.health_check_paths = ['/health', '/.well-known/agent-card.json', '/api/health']
    
    def filter(self, record: logging.LogRecord) -> bool:
        """
        Filter out health check requests from uvicorn access logs.
        
        Args:
            record: Log record to evaluate
            
        Returns:
            True if log should be kept, False if it should be suppressed
        """
        # Filter uvicorn access logs and any other access logs
        if 'uvicorn' in record.name or 'access' in record.name.lower():
            message = record.getMessage()
            
            # Check if this is a health check request - be more comprehensive
            for path in self.health_check_paths:
                if (f'GET {path}' in message or f'"{path}' in message) and ('200 OK' in message or '200' in message):
                    return False  # Suppress health check logs
        
        # Also check for any log message that looks like health check access
        message = record.getMessage()
        if any(f'GET {path}' in message for path in self.health_check_paths) and '200' in message:
            return False
        
        return True  # Keep all other logs


class HealthCheckSuppressionMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware to suppress health check logging.
    Works in conjunction with the logging filter for complete suppression.
    """
    
    def __init__(self, app, health_check_paths=None):
        super().__init__(app)
        self.health_check_paths = health_check_paths or ['/health', '/.well-known/agent-card.json', '/api/health']
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """
        Process request and suppress logging for health checks.
        
        Args:
            request: Incoming HTTP request
            call_next: Next middleware/endpoint in chain
            
        Returns:
            HTTP response
        """
        # Check if this is a health check request
        is_health_check = any(request.url.path.endswith(path) for path in self.health_check_paths)
        
        if is_health_check:
            # Process request normally but mark as health check
            response = await call_next(request)
            # Add header to indicate health check (useful for debugging)
            response.headers["X-Health-Check"] = "true"
            return response
        else:
            # Normal request processing
            return await call_next(request)


def setup_health_check_suppression():
    """
    Set up health check logging suppression at the uvicorn level.
    This function should be called during application startup.
    """
    # Add logging filter to uvicorn access logger
    uvicorn_access_logger = logging.getLogger('uvicorn.access')
    
    # Check if filter is already added to prevent duplicates
    existing_filters = [f for f in uvicorn_access_logger.filters if isinstance(f, HealthCheckLoggingFilter)]
    
    if not existing_filters:
        health_filter = HealthCheckLoggingFilter()
        uvicorn_access_logger.addFilter(health_filter)
        
        # Also apply to root logger in case access logs go there
        root_logger = logging.getLogger()
        root_logger.addFilter(health_filter)
        
        print("✅ Health check logging suppression filter installed")


def add_health_check_middleware(app):
    """
    Add health check suppression middleware to a FastAPI application.
    
    Args:
        app: FastAPI application instance
    """
    app.add_middleware(HealthCheckSuppressionMiddleware)
    print("✅ Health check suppression middleware added to FastAPI app")
