"""
Runtime utilities for AWS CloudWatch Logs data protection.

This module provides runtime functionality for data protection features including
status checking, permission validation, and sensitive data pattern detection
for client-side validation and testing purposes.
"""

import re
import logging
from typing import Dict, List, Optional, Any, Pattern
import boto3
from botocore.exceptions import ClientError, BotoCoreError
from secure_logging_utils import log_exception_safely

logger = logging.getLogger(__name__)


class DataProtectionManager:
    """Runtime manager for data protection features and status checking."""
    
    def __init__(self, region_name: str = "us-east-1"):
        """Initialize the data protection manager."""
        self.region = region_name
        self._logs_client = None
        self._iam_client = None
    
    @property
    def logs_client(self):
        """Lazy initialization of CloudWatch Logs client."""
        if not self._logs_client:
            self._logs_client = boto3.client('logs', region_name=self.region)
        return self._logs_client
    
    @property
    def iam_client(self):
        """Lazy initialization of IAM client."""
        if not self._iam_client:
            self._iam_client = boto3.client('iam', region_name=self.region)
        return self._iam_client
    
    def is_data_protection_enabled(self) -> bool:
        """Check if data protection is active for the current AWS account."""
        try:
            # Try to list data protection policies to check if service is available
            response = self.logs_client.describe_account_policies(
                policyType="DATA_PROTECTION_POLICY"
            )
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'AccessDeniedException':
                logger.warning("No permissions to check data protection policies")
                return False
            elif error_code == 'ServiceUnavailableException':
                logger.info("Data protection service not available in this region")
                return False
            else:
                logger.error(f"Unexpected error checking data protection status: {error_code}")
                return False
        except Exception as e:
            logger.error(f"Error checking data protection status: {type(e).__name__}")
            return False
    
    def get_log_group_data_protection_policy(self, log_group_name: str) -> Optional[Dict[str, Any]]:
        """Get data protection policy for a specific log group."""
        try:
            response = self.logs_client.get_data_protection_policy(
                logGroupIdentifier=log_group_name
            )
            return response.get('policyDocument')
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == 'ResourceNotFoundException':
                logger.info(f"No data protection policy found for log group: {log_group_name}")
                return None
            else:
                logger.error(f"Error getting data protection policy for log group {log_group_name}: {error_code}")
                return None
        except Exception as e:
            logger.error(f"Unexpected error getting data protection policy: {type(e).__name__}")
            return None
    
    def list_protected_log_groups(self) -> List[str]:
        """List all log groups with data protection policies."""
        try:
            protected_groups = []
            paginator = self.logs_client.get_paginator('describe_log_groups')
            
            for page in paginator.paginate():
                for log_group in page.get('logGroups', []):
                    log_group_name = log_group.get('logGroupName')
                    if log_group_name and self.get_log_group_data_protection_policy(log_group_name):
                        protected_groups.append(log_group_name)
            
            return protected_groups
            
        except Exception as e:
            log_exception_safely(logger, "Error listing protected log groups", e)
            return []
    
    def validate_user_unmask_permissions(self, log_group_arn: str) -> bool:
        """Check if the current user has permissions to unmask data in log group."""
        try:
            # Use IAM policy simulator to check unmask permissions
            response = self.iam_client.simulate_principal_policy(
                PolicySourceArn=f"arn:aws:sts::{self._get_account_id()}:assumed-role/current-user/session",
                ActionNames=['logs:Unmask'],
                ResourceArns=[log_group_arn]
            )
            
            evaluation_results = response.get('EvaluationResults', [])
            if evaluation_results:
                decision = evaluation_results[0].get('EvalDecision')
                return decision == 'allowed'
            
            return False
            
        except Exception as e:
            log_exception_safely(logger, "Error validating unmask permissions", e)
            return False
    
    def _get_account_id(self) -> str:
        """Get current AWS account ID."""
        try:
            sts_client = boto3.client('sts', region_name=self.region)
            response = sts_client.get_caller_identity()
            return response.get('Account', '')
        except Exception as e:
            log_exception_safely(logger, "Error getting account ID", e)
            return ''


class SensitiveDataDetector:
    """Client-side detector for sensitive data patterns for validation and testing."""
    
    def __init__(self):
        """Initialize the sensitive data detector with compiled patterns."""
        self._patterns: Dict[str, Pattern] = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[str, Pattern]:
        """Compile regex patterns for sensitive data detection."""
        patterns = {}
        
        # AWS Credential patterns
        patterns['aws_access_key'] = re.compile(r'(?i)(aws[_-]?access[_-]?key[_-]?id|access[_-]?key)\s*[:=]\s*["\']?(AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16})["\']?')
        patterns['aws_secret_key'] = re.compile(r'(?i)(aws[_-]?secret[_-]?access[_-]?key|secret[_-]?key)\s*[:=]\s*["\']?([A-Za-z0-9/+=]{40})["\']?')
        patterns['aws_session_token'] = re.compile(r'(?i)(aws[_-]?session[_-]?token|session[_-]?token)\s*[:=]\s*["\']?([A-Za-z0-9/+=]{100,})["\']?')
        
        # Generic API keys and tokens
        patterns['api_key'] = re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?([a-zA-Z0-9\-_]{16,})["\']?')
        patterns['auth_token'] = re.compile(r'(?i)(auth[_-]?token|authorization[_-]?token|bearer[_-]?token)\s*[:=]\s*["\']?([a-zA-Z0-9\-_\.]{20,})["\']?')
        patterns['password'] = re.compile(r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?([^\s"\']{8,})["\']?')
        
        # Personal information
        patterns['email'] = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        patterns['phone'] = re.compile(r'(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
        patterns['ssn'] = re.compile(r'\b\d{3}-?\d{2}-?\d{4}\b')
        patterns['ip_address'] = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')
        
        # Financial data
        patterns['credit_card'] = re.compile(r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3[0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b')
        
        # Platform-specific patterns
        patterns['agent_config_secrets'] = re.compile(r'(?i)(observability_key|database_password|auth_token|api_key|secret_key)\s*[:=]\s*["\']?([a-zA-Z0-9\-_]{8,})["\']?')
        patterns['ssm_parameter_values'] = re.compile(r'(?i)(parameter\s+value|ssm\s+value|retrieved\s+parameter)\s*[:=]\s*["\']?([a-zA-Z0-9\-_/]{10,})["\']?')
        patterns['bedrock_tokens'] = re.compile(r'(?i)(bedrock[_-]?token|ai[_-]?key|model[_-]?token|inference[_-]?key)\s*[:=]\s*["\']?([a-zA-Z0-9\-_]{16,})["\']?')
        patterns['database_connections'] = re.compile(r'(?i)(connection[_-]?string|db[_-]?url|database[_-]?uri|jdbc[_-]?url)\s*[:=]\s*["\']?([^"\'\s]{20,})["\']?')
        patterns['jwt_tokens'] = re.compile(r'(?i)(jwt[_-]?token|bearer[_-]?token|auth[_-]?header)\s*[:=]\s*["\']?(eyJ[a-zA-Z0-9\-_]{20,})["\']?')
        
        return patterns
    
    def detect_sensitive_data(self, text: str) -> Dict[str, List[str]]:
        """
        Detect sensitive data patterns in text.
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary mapping pattern types to found matches
        """
        findings = {}
        
        for pattern_name, pattern in self._patterns.items():
            matches = pattern.findall(text)
            if matches:
                # Extract the sensitive part from match groups
                sensitive_values = []
                for match in matches:
                    if isinstance(match, tuple):
                        # For patterns with groups, take the last group (the value)
                        sensitive_values.append(match[-1] if match else '')
                    else:
                        sensitive_values.append(match)
                
                if sensitive_values:
                    findings[pattern_name] = sensitive_values
        
        return findings
    
    def mask_sensitive_data(self, text: str, mask_char: str = '*') -> str:
        """
        Mask sensitive data in text for safe logging.
        
        Args:
            text: Text to mask
            mask_char: Character to use for masking
            
        Returns:
            Text with sensitive data masked
        """
        masked_text = text
        
        for pattern_name, pattern in self._patterns.items():
            def replace_match(match):
                if isinstance(match.group(), tuple):
                    # For grouped patterns, mask only the sensitive part
                    full_match = match.group(0)
                    sensitive_part = match.group(-1)
                    return full_match.replace(sensitive_part, mask_char * min(len(sensitive_part), 8))
                else:
                    # For non-grouped patterns, mask most of the match
                    match_text = match.group(0)
                    return match_text[:4] + mask_char * (len(match_text) - 8) + match_text[-4:]
            
            masked_text = pattern.sub(replace_match, masked_text)
        
        return masked_text
    
    def validate_sensitive_data_patterns(self, text: str) -> List[str]:
        """
        Validate text against known sensitive data patterns.
        
        Args:
            text: Text to validate
            
        Returns:
            List of detected pattern types
        """
        detected_patterns = []
        findings = self.detect_sensitive_data(text)
        
        for pattern_type, matches in findings.items():
            if matches:
                detected_patterns.append(pattern_type)
        
        return detected_patterns


def is_data_protection_enabled() -> bool:
    """Check if data protection is active in the current environment."""
    try:
        manager = DataProtectionManager()
        return manager.is_data_protection_enabled()
    except Exception as e:
        log_exception_safely(logger, "Error checking data protection status", e)
        return False


def get_logs_unmask_permission() -> str:
    """Get the IAM permission required for unmasking log data."""
    return "logs:Unmask"


def validate_sensitive_data_patterns(text: str) -> List[str]:
    """
    Validate text against known sensitive data patterns.
    
    Args:
        text: Text to validate
        
    Returns:
        List of detected pattern types
    """
    try:
        detector = SensitiveDataDetector()
        return detector.validate_sensitive_data_patterns(text)
    except Exception as e:
        log_exception_safely(logger, "Error validating sensitive data patterns", e)
        return []


def mask_sensitive_data_for_logging(text: str, mask_char: str = '*') -> str:
    """
    Mask sensitive data in text for safe logging.
    
    Args:
        text: Text to mask
        mask_char: Character to use for masking
        
    Returns:
        Text with sensitive data masked for safe logging
    """
    try:
        detector = SensitiveDataDetector()
        return detector.mask_sensitive_data(text, mask_char)
    except Exception as e:
        log_exception_safely(logger, "Error masking sensitive data", e)
        return text  # Return original text if masking fails


def get_data_protection_policy_document(log_group_name: str, region: str = "us-east-1") -> Optional[Dict[str, Any]]:
    """
    Get data protection policy document for a log group.
    
    Args:
        log_group_name: Name of the log group
        region: AWS region
        
    Returns:
        Policy document or None if not found
    """
    try:
        manager = DataProtectionManager(region)
        return manager.get_log_group_data_protection_policy(log_group_name)
    except Exception as e:
        log_exception_safely(logger, "Error getting data protection policy document", e)
        return None


def validate_log_group_protection_status(log_group_name: str, region: str = "us-east-1") -> Dict[str, Any]:
    """
    Validate data protection status for a specific log group.
    
    Args:
        log_group_name: Name of the log group to check
        region: AWS region
        
    Returns:
        Dictionary with protection status details
    """
    try:
        manager = DataProtectionManager(region)
        
        status = {
            "log_group_name": log_group_name,
            "has_data_protection_policy": False,
            "policy_document": None,
            "service_available": False,
            "error": None
        }
        
        # Check if data protection service is available
        status["service_available"] = manager.is_data_protection_enabled()
        
        if status["service_available"]:
            # Get policy document for log group
            policy_doc = manager.get_log_group_data_protection_policy(log_group_name)
            if policy_doc:
                status["has_data_protection_policy"] = True
                status["policy_document"] = policy_doc
        
        return status
        
    except Exception as e:
        log_exception_safely(logger, f"Error validating protection status for log group {log_group_name}", e)
        return {
            "log_group_name": log_group_name,
            "has_data_protection_policy": False,
            "policy_document": None,
            "service_available": False,
            "error": "Protection status validation failed"
        }


def create_safe_log_message(message: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Create a safe log message with sensitive data masked.
    
    Args:
        message: Original log message
        context: Additional context data to include
        
    Returns:
        Safe log message with sensitive data masked
    """
    try:
        # Mask sensitive data in the main message
        safe_message = mask_sensitive_data_for_logging(message)
        
        # Add context if provided, also masked
        if context:
            safe_context = {}
            for key, value in context.items():
                if isinstance(value, str):
                    safe_context[key] = mask_sensitive_data_for_logging(value)
                else:
                    safe_context[key] = value
            
            safe_message += f" | Context: {safe_context}"
        
        return safe_message
        
    except Exception as e:
        log_exception_safely(logger, "Error creating safe log message", e)
        return f"[LOG_PROCESSING_ERROR] Original message length: {len(message)} chars"
