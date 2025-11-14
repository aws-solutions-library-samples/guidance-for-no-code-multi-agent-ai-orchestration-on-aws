"""
Secure Logging Utilities

Provides secure logging functions that prevent sensitive data exposure
and log injection attacks while preserving debugging capability.
"""

import re
import json
import logging
import traceback
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import hashlib

class SecureLogger:
    """Secure logging utilities to prevent sensitive data exposure while maintaining debugging capability."""
    
    def __init__(self):
        self.debug_mode = os.environ.get('DEBUG_STACK_TRACES', 'false').lower() == 'true'
        self.logger = logging.getLogger(__name__)
    
    @staticmethod
    def sanitize_message(message: str) -> str:
        """Sanitize log message to remove sensitive data while preserving structure."""
        if not isinstance(message, str):
            return str(message)
        
        sanitized = message
        
        # Mask potential sensitive data but preserve context
        sensitive_patterns = [
            (r'(password["\']?\s*[:=]\s*["\']?)([^\s"\']+)', r'\1***MASKED***'),
            (r'(secret["\']?\s*[:=]\s*["\']?)([^\s"\']+)', r'\1***MASKED***'),
            (r'(api_key["\']?\s*[:=]\s*["\']?)([^\s"\']+)', r'\1***MASKED***'),
            (r'(token["\']?\s*[:=]\s*["\']?)([^\s"\']+)', r'\1***MASKED***'),
            (r'(key["\']?\s*[:=]\s*["\']?)([^\s"\']+)', r'\1***MASKED***'),
            # Mask AWS ARNs and secrets while preserving structure
            (r'(arn:aws:secretsmanager:[^:]+:[^:]+:secret:)([^/\s]+)', r'\1***MASKED***'),
            (r'(arn:aws:rds:[^:]+:[^:]+:cluster:)([^/\s]+)', r'\1***MASKED***'),
        ]
        
        for pattern, replacement in sensitive_patterns:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        
        # Clean up control characters but preserve newlines for stack traces
        sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', sanitized)
        
        # Limit message length but preserve important debugging info
        if len(sanitized) > 3000:
            sanitized = sanitized[:3000] + "... [truncated for security]"
        
        return sanitized
    
    def log_exception_securely(self, logger_instance: logging.Logger, context: str, exception: Exception):
        """
        Log exceptions securely with appropriate level of detail based on environment.
        Preserves debugging info while preventing sensitive data exposure.
        """
        # Always log the sanitized error message
        error_message = self.sanitize_message(str(exception))
        logger_instance.error(f"{context}: {error_message}")
        
        # In debug mode or development, log more detailed stack trace to separate debug logger
        if self.debug_mode or os.environ.get('NODE_ENV') == 'development':
            # Create debug logger for detailed traces (should be configured to write to secure location)
            debug_logger = logging.getLogger(f"{logger_instance.name}.debug")
            debug_logger.debug(f"DETAILED_TRACE for {context}:")
            debug_logger.debug(f"Exception type: {type(exception).__name__}")
            
            # Log sanitized stack trace
            stack_trace = traceback.format_exc()
            sanitized_trace = self.sanitize_message(stack_trace)
            debug_logger.debug(f"Stack trace: {sanitized_trace}")
        
        # For production, create a correlation ID for support teams
        correlation_id = self.hash_sensitive_value(f"{context}:{str(exception)}")
        logger_instance.error(f"Error correlation ID: {correlation_id} (for support reference)")
    
    @staticmethod
    def hash_sensitive_value(value: str) -> str:
        """Create a hash of sensitive value for logging purposes only (not password hashing).
        
        Note: This is for logging obfuscation, not password security.
        For password hashing, use bcrypt, scrypt, or Argon2.
        """
        if not value:
            return ""
        
        # Use SHA-256 for logging obfuscation only (NOT password hashing)
        # This is appropriate for configuration/endpoint obfuscation in logs
        hash_obj = hashlib.sha256(value.encode('utf-8'))
        return hash_obj.hexdigest()[:16]  # First 16 characters for logging
    
    @staticmethod
    def create_safe_context_info(context_data: Dict[str, Any]) -> Dict[str, str]:
        """Create safe context information for debugging while protecting sensitive data."""
        safe_context = {}
        
        for key, value in context_data.items():
            if any(sensitive in key.lower() for sensitive in ['password', 'secret', 'key', 'token']):
                # Hash sensitive values but keep key names for debugging
                safe_context[key] = f"HASHED:{SecureLogger.hash_sensitive_value(str(value))}"
            elif isinstance(value, (dict, list)):
                # For complex objects, provide type and size info
                safe_context[key] = f"{type(value).__name__}(size={len(value) if hasattr(value, '__len__') else 'unknown'})"
            else:
                # For non-sensitive values, include first few characters
                str_val = str(value)
                if len(str_val) > 100:
                    safe_context[key] = f"{str_val[:50]}...{str_val[-10:]} (length={len(str_val)})"
                else:
                    safe_context[key] = str_val
                    
        return safe_context

def sanitize_for_logging(data: Any) -> str:
    """Sanitize any data for safe logging."""
    secure_logger = SecureLogger()
    return secure_logger.sanitize_message(str(data))

def log_exception_safely(logger_instance: logging.Logger, context: str, exception: Exception, extra_context: Optional[Dict[str, Any]] = None):
    """
    Convenience function to log exceptions securely with optional context.
    This should be used instead of logger.exception() to prevent security issues.
    """
    secure_logger = SecureLogger()
    secure_logger.log_exception_securely(logger_instance, context, exception)
    
    # Log additional context if provided
    if extra_context:
        safe_context = secure_logger.create_safe_context_info(extra_context)
        logger_instance.error(f"Context for {context}: {json.dumps(safe_context, indent=2)}")
