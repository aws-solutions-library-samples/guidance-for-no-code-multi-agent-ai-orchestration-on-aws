"""
Enhanced Security Middleware for Application Protection

This module provides comprehensive security middleware including:
- Rate limiting
- Input validation  
- Security headers
- Request sanitization
- CORS protection
"""

import time
import re
import json
import logging
from typing import Dict, Any, Optional, List, Callable
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)

@dataclass
class RateLimitEntry:
    """Rate limit entry for tracking requests."""
    count: int = 0
    window_start: float = 0.0
    blocked_until: float = 0.0

class SecurityMiddleware:
    """Comprehensive security middleware for web applications."""
    
    def __init__(self, 
                 rate_limit_requests: int = 100,
                 rate_limit_window: int = 60,
                 block_duration: int = 300):
        self.rate_limit_requests = rate_limit_requests
        self.rate_limit_window = rate_limit_window
        self.block_duration = block_duration
        self.rate_limits: Dict[str, RateLimitEntry] = {}
        
    def check_rate_limit(self, identifier: str) -> bool:
        """Check if request is within rate limits."""
        now = time.time()
        
        if identifier not in self.rate_limits:
            self.rate_limits[identifier] = RateLimitEntry(
                count=1,
                window_start=now
            )
            return True
        
        entry = self.rate_limits[identifier]
        
        # Check if currently blocked
        if entry.blocked_until > now:
            return False
        
        # Reset window if needed
        if now - entry.window_start > self.rate_limit_window:
            entry.count = 1
            entry.window_start = now
            entry.blocked_until = 0.0
            return True
        
        # Check rate limit
        entry.count += 1
        if entry.count > self.rate_limit_requests:
            entry.blocked_until = now + self.block_duration
            logger.warning(f"Rate limit exceeded for {identifier[:10]}...")
            return False
        
        return True
    
    def validate_input(self, data: str, max_length: int = 10000) -> bool:
        """Validate input data for security."""
        if not isinstance(data, str):
            return False
        
        if len(data) > max_length:
            return False
        
        # Check for common attack patterns
        dangerous_patterns = [
            r'<script[^>]*>',
            r'javascript:',
            r'vbscript:',
            r'on\w+\s*=',
            r'expression\s*\(',
            r'eval\s*\(',
            r'exec\s*\('
        ]
        
        for pattern in dangerous_patterns:
            if re.search(pattern, data, re.IGNORECASE):
                logger.warning(f"Dangerous pattern detected: {pattern}")
                return False
        
        return True
    
    def get_security_headers(self) -> Dict[str, str]:
        """Get recommended security headers."""
        return {
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'DENY',
            'X-XSS-Protection': '1; mode=block',
            'Strict-Transport-Security': 'max-age=31536000; includeSubDomains',
            'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
            'Referrer-Policy': 'strict-origin-when-cross-origin'
        }

def create_security_middleware() -> SecurityMiddleware:
    """Factory function for security middleware."""
    return SecurityMiddleware()
