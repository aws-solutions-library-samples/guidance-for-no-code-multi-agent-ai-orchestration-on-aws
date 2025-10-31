"""
Input Validation Utilities

Provides secure input validation functions to prevent injection attacks
and ensure data integrity across the application.
"""

import re
import html
import urllib.parse
from typing import Dict, List, Optional, Any, Union
import logging

logger = logging.getLogger(__name__)

class InputValidator:
    """Comprehensive input validation utilities."""
    
    @staticmethod
    def sanitize_string(input_str: str, max_length: int = 1000) -> str:
        """Sanitize string input to prevent injection attacks."""
        if not isinstance(input_str, str):
            return ""
        
        if len(input_str) > max_length:
            input_str = input_str[:max_length]
        
        # HTML escape
        sanitized = html.escape(input_str)
        
        # Remove null bytes
        sanitized = sanitized.replace('\x00', '')
        
        # Normalize whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized)
        
        return sanitized.strip()
    
    @staticmethod
    def check_sql_injection(input_str: str) -> bool:
        """Check for SQL injection attempts."""
        if not isinstance(input_str, str):
            return False
        
        dangerous_sql_words = [
            'union', 'select', 'insert', 'update', 'delete', 'drop',
            'exec', 'execute', 'xp_', 'sp_', '--', '#', '/*', '*/'
        ]
        
        input_lower = input_str.lower()
        for word in dangerous_sql_words:
            if word in input_lower:
                logger.warning(f"Potential SQL injection detected: {word}")
                return True
        
        return False
    
    @staticmethod
    def check_xss(input_str: str) -> bool:
        """Check for XSS attempts."""
        if not isinstance(input_str, str):
            return False
        
        dangerous_patterns = [
            '<script', '<iframe', 'javascript:', 'vbscript:',
            'onload=', 'onerror=', 'onclick=', 'onmouseover='
        ]
        
        input_lower = input_str.lower()
        for pattern in dangerous_patterns:
            if pattern in input_lower:
                logger.warning(f"Potential XSS detected: {pattern}")
                return True
        
        return False
    
    @staticmethod
    def check_path_traversal(input_str: str) -> bool:
        """Check for path traversal attempts."""
        if not isinstance(input_str, str):
            return False
        
        dangerous_patterns = ['../', '..\\', '%2e%2e', '0x2e0x2e']
        
        # URL decode the input
        decoded = urllib.parse.unquote(input_str)
        
        for pattern in dangerous_patterns:
            if pattern in decoded:
                logger.warning(f"Potential path traversal detected: {pattern}")
                return True
        
        return False
    
    @classmethod
    def validate_input(cls, input_data: Any, max_length: int = 10000) -> bool:
        """Comprehensive input validation."""
        if input_data is None:
            return True
        
        if isinstance(input_data, str):
            if len(input_data) > max_length:
                logger.warning(f"Input exceeds maximum length: {len(input_data)} > {max_length}")
                return False
            
            if cls.check_sql_injection(input_data):
                return False
            
            if cls.check_xss(input_data):
                return False
            
            if cls.check_path_traversal(input_data):
                return False
        
        elif isinstance(input_data, dict):
            for key, value in input_data.items():
                if not cls.validate_input(key, max_length):
                    return False
                if not cls.validate_input(value, max_length):
                    return False
        
        elif isinstance(input_data, list):
            for item in input_data:
                if not cls.validate_input(item, max_length):
                    return False
        
        return True

def validate_and_sanitize_input(input_data: Any, max_length: int = 1000) -> Any:
    """Validate and sanitize input data."""
    validator = InputValidator()
    
    if isinstance(input_data, str):
        if not validator.validate_input(input_data, max_length=max_length):
            raise ValueError("Invalid input detected")
        return validator.sanitize_string(input_data, max_length)
    
    elif isinstance(input_data, dict):
        sanitized = {}
        for key, value in input_data.items():
            sanitized_key = validate_and_sanitize_input(key, max_length)
            sanitized_value = validate_and_sanitize_input(value, max_length)
            sanitized[sanitized_key] = sanitized_value
        return sanitized
    
    elif isinstance(input_data, list):
        return [validate_and_sanitize_input(item, max_length) for item in input_data]
    
    return input_data
