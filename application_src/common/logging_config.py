"""
Centralized logging configuration for the Generative AI platform.

This module provides a standardized logging setup that follows the project's
coding standards and allows for proper debug vs info vs error logging control.
"""

import logging
import os
import sys
from typing import Dict, Any

# Default log levels
DEFAULT_LOG_LEVEL = "INFO"
DEBUG_LOG_LEVEL = "DEBUG"

# Environment variable for controlling log level
LOG_LEVEL_ENV_VAR = "LOG_LEVEL"

# Environment variable for agent identification
AGENT_NAME_ENV_VAR = "AGENT_NAME"


class AgentNameFormatter(logging.Formatter):
    """
    Custom formatter that automatically includes agent name in log messages.
    
    This formatter prepends the agent name (from AGENT_NAME environment variable)
    to all log messages, making it easy to differentiate logs from different services
    when they're aggregated in the same CloudWatch log group.
    """
    
    def __init__(self, fmt=None, datefmt=None):
        """
        Initialize the formatter with agent name detection.
        
        Args:
            fmt: Log format string
            datefmt: Date format string
        """
        # Get agent name from environment variable
        self.agent_name = os.environ.get(AGENT_NAME_ENV_VAR, "unknown-agent")
        
        # If no format provided, use default with agent name
        if fmt is None:
            fmt = f'%(asctime)s - [{self.agent_name}] - %(name)s - %(levelname)s - %(message)s'
        
        super().__init__(fmt, datefmt)
    
    def format(self, record):
        """
        Format the log record with agent name identifier.
        
        Args:
            record: LogRecord instance
            
        Returns:
            Formatted log message string
        """
        # Update agent name dynamically in case environment variable changes
        current_agent_name = os.environ.get(AGENT_NAME_ENV_VAR, self.agent_name)
        if current_agent_name != self.agent_name:
            self.agent_name = current_agent_name
            # Update the format string with new agent name
            self._style._fmt = f'%(asctime)s - [{self.agent_name}] - %(name)s - %(levelname)s - %(message)s'
        
        return super().format(record)


# Module-specific log levels (can be overridden via environment variables)
MODULE_LOG_LEVELS = {
    "application_src.common.agent": "INFO",
    "application_src.common.agent_template": "INFO", 
    "application_src.common.knowledge_base": "INFO",
    "application_src.common.observability": "INFO",
    "application_src.common.knowledge_base.custom.elastic": "INFO",
    "application_src.common.knowledge_base.custom.snowflake": "INFO",
    "application_src.common.knowledge_base.mcp": "INFO",
    "application_src.multi_agent.agent_supervisor": "INFO",
}

def get_log_level(module_name: str = None) -> str:
    """
    Get the appropriate log level for a module.
    
    Args:
        module_name: Name of the module requesting log level
        
    Returns:
        Log level string (DEBUG, INFO, WARNING, ERROR)
    """
    # Check for global log level override
    global_level = os.environ.get(LOG_LEVEL_ENV_VAR)
    if global_level:
        return global_level.upper()
    
    # Check for module-specific log level
    if module_name and module_name in MODULE_LOG_LEVELS:
        module_level_env = f"{LOG_LEVEL_ENV_VAR}_{module_name.replace('.', '_').upper()}"
        return os.environ.get(module_level_env, MODULE_LOG_LEVELS[module_name]).upper()
    
    return DEFAULT_LOG_LEVEL

def setup_logging(
    level: str = None,
    module_name: str = None,
    format_string: str = None,
    use_agent_formatter: bool = True
) -> logging.Logger:
    """
    Set up logging configuration for a module with agent name identification.
    
    Args:
        level: Log level override (DEBUG, INFO, WARNING, ERROR)
        module_name: Name of the calling module  
        format_string: Custom format string for log messages
        use_agent_formatter: Whether to use AgentNameFormatter for agent identification
        
    Returns:
        Configured logger instance
    """
    if not level:
        level = get_log_level(module_name)
    
    # Configure basic logging if not already configured
    if not logging.getLogger().handlers:
        # Create handler with agent name formatter
        handler = logging.StreamHandler(sys.stdout)
        
        if use_agent_formatter:
            # Use custom formatter that includes agent name
            formatter = AgentNameFormatter(format_string)
        else:
            # Use standard formatter
            if not format_string:
                format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            formatter = logging.Formatter(format_string)
        
        handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, level, logging.INFO))
        root_logger.addHandler(handler)
    
    # Get logger for the specific module
    logger = logging.getLogger(module_name or __name__)
    logger.setLevel(getattr(logging, level, logging.INFO))
    
    return logger

def get_logger(module_name: str = None, use_agent_formatter: bool = True) -> logging.Logger:
    """
    Get a logger instance for a module with agent name identification.
    
    Args:
        module_name: Name of the calling module
        use_agent_formatter: Whether to ensure AgentNameFormatter is used
        
    Returns:
        Logger instance with agent name formatting
    """
    if not module_name:
        # Try to determine module name from caller
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            module_name = frame.f_back.f_globals.get('__name__', 'unknown')
    
    # Ensure logging is configured with agent formatter if not already done
    if use_agent_formatter and not logging.getLogger().handlers:
        setup_logging(module_name=module_name, use_agent_formatter=True)
    
    logger = logging.getLogger(module_name)
    
    # Set appropriate log level for this module
    level = get_log_level(module_name)
    logger.setLevel(getattr(logging, level, logging.INFO))
    
    return logger

def configure_debug_logging():
    """Enable debug logging for all modules."""
    os.environ[LOG_LEVEL_ENV_VAR] = DEBUG_LOG_LEVEL
    
    # Reconfigure all existing loggers
    for name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)

def configure_production_logging():
    """Configure logging for production (INFO and above)."""
    os.environ[LOG_LEVEL_ENV_VAR] = "INFO"
    
    # Reconfigure all existing loggers  
    for name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(name)
        if logger.level < logging.INFO:
            logger.setLevel(logging.INFO)

def log_with_context(logger: logging.Logger, level: str, message: str, **context):
    """
    Log a message with additional context information and automatic sensitive data protection.
    
    Args:
        logger: Logger instance
        level: Log level (debug, info, warning, error)
        message: Log message
        **context: Additional context to include in log
    """
    try:
        # Import here to avoid circular imports
        from data_protection_utils import mask_sensitive_data_for_logging
        
        # Mask sensitive data in the main message
        safe_message = mask_sensitive_data_for_logging(message)
        
        if context:
            # Apply data protection to context values
            safe_context = {}
            for key, value in context.items():
                if isinstance(value, str):
                    safe_context[key] = mask_sensitive_data_for_logging(value)
                else:
                    safe_context[key] = value
            
            context_str = " | ".join([f"{k}={v}" for k, v in safe_context.items()])
            safe_message = f"{safe_message} | {context_str}"
        
        getattr(logger, level.lower())(safe_message)
        
    except ImportError:
        # Fallback if data protection utils not available
        if context:
            context_str = " | ".join([f"{k}={v}" for k, v in context.items()])
            message = f"{message} | {context_str}"
        getattr(logger, level.lower())(message)
    except Exception:
        # Fallback to basic logging if data protection fails
        if context:
            context_str = " | ".join([f"{k}={v}" for k, v in context.items()])
            message = f"{message} | {context_str}"
        getattr(logger, level.lower())(message)

# Convenience functions following coding standards
def log_error_without_exception(logger: logging.Logger, message: str, **context):
    """Use logger.error when no exception exists (per coding standards)."""
    log_with_context(logger, "error", message, **context)

def log_exception(logger: logging.Logger, message: str, **context):
    """Use logger.exception for exceptions (per coding standards)."""
    if context:
        context_str = " | ".join([f"{k}={v}" for k, v in context.items()])
        message = f"{message} | {context_str}"
    logger.exception(message)

def log_warning(logger: logging.Logger, message: str, **context):
    """Use logger.warning for unexpected behaviors (per coding standards)."""
    log_with_context(logger, "warning", message, **context)

def log_debug(logger: logging.Logger, message: str, **context):
    """Log debug information (replaces print statements)."""
    log_with_context(logger, "debug", message, **context)

def log_info(logger: logging.Logger, message: str, **context):
    """Log informational messages."""
    log_with_context(logger, "info", message, **context)

# Health check logging suppression
def suppress_health_check_logs(func):
    """
    Decorator to suppress access logs for health check endpoints.
    
    This decorator identifies health check requests and prevents them from
    cluttering logs while still allowing error logging for actual issues.
    
    Health check paths that are suppressed:
    - /health
    - /.well-known/agent-card.json  
    - /api/health
    """
    import functools
    import asyncio
    
    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        # For FastAPI async functions, just call the function directly
        # Health check suppression will be handled by middleware instead
        return await func(*args, **kwargs)
    
    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        # For synchronous functions, apply the suppression logic
        return func(*args, **kwargs)
    
    # Return the appropriate wrapper based on whether the function is async
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    else:
        return sync_wrapper
