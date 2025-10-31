"""
Data identifier management for AWS CloudWatch Logs data protection.

This module provides AWS managed data identifiers and custom data identifiers
for platform-specific sensitive data patterns. It supports log group-level
data protection policies that automatically detect and mask sensitive information.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import re
import logging

logger = logging.getLogger(__name__)


class DataProtectionPolicyType(Enum):
    """Types of data protection policies supported."""
    LOG_GROUP_LEVEL = "log_group"


class ManagedDataIdentifierCategory(Enum):
    """Categories of AWS managed data identifiers."""
    CREDENTIALS = "credentials"
    FINANCIAL = "financial"
    PII = "pii"
    PHI = "phi"
    DEVICE = "device"


@dataclass
class ManagedDataIdentifier:
    """AWS managed data identifier configuration."""
    arn: str
    category: ManagedDataIdentifierCategory
    description: str
    keywords_required: bool = False


@dataclass
class CustomDataIdentifier:
    """Custom data identifier for platform-specific patterns."""
    name: str
    regex: str
    keywords: Optional[List[str]] = None
    ignore_words: Optional[List[str]] = None
    maximum_match_distance: Optional[int] = None


@dataclass
class DataProtectionPolicyConfig:
    """Complete data protection policy configuration."""
    managed_identifiers: List[ManagedDataIdentifier]
    custom_identifiers: List[CustomDataIdentifier]
    policy_type: DataProtectionPolicyType = DataProtectionPolicyType.LOG_GROUP_LEVEL
    audit_findings_destination: Optional[str] = None
    enable_audit_findings: bool = True


class ManagedDataIdentifierRegistry:
    """Registry for AWS managed data identifiers with ARN templates."""
    
    # AWS managed data identifier templates
    # These ARNs are constructed based on AWS region and service
    _MANAGED_IDENTIFIERS = {
        # AWS Credentials and API Keys
        "aws-access-key": {
            "category": ManagedDataIdentifierCategory.CREDENTIALS,
            "description": "AWS Access Key ID patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/aws-access-key"
        },
        "aws-secret-key": {
            "category": ManagedDataIdentifierCategory.CREDENTIALS,
            "description": "AWS Secret Access Key patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/aws-secret-key"
        },
        "aws-session-token": {
            "category": ManagedDataIdentifierCategory.CREDENTIALS,
            "description": "AWS Session Token patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/aws-session-token"
        },
        
        # Generic credentials and tokens
        "api-key": {
            "category": ManagedDataIdentifierCategory.CREDENTIALS,
            "description": "Generic API key patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/api-key"
        },
        "auth-token": {
            "category": ManagedDataIdentifierCategory.CREDENTIALS,
            "description": "Authentication token patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/auth-token"
        },
        "password": {
            "category": ManagedDataIdentifierCategory.CREDENTIALS,
            "description": "Password patterns in logs",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/password"
        },
        
        # Personal Identifiable Information (PII)
        "email-address": {
            "category": ManagedDataIdentifierCategory.PII,
            "description": "Email address patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/email-address"
        },
        "phone-number": {
            "category": ManagedDataIdentifierCategory.PII,
            "description": "Phone number patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/phone-number"
        },
        "ip-address": {
            "category": ManagedDataIdentifierCategory.PII,
            "description": "IP address patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/ip-address"
        },
        "social-security-number": {
            "category": ManagedDataIdentifierCategory.PII,
            "description": "Social Security Number patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/ssn"
        },
        
        # Financial data
        "credit-card": {
            "category": ManagedDataIdentifierCategory.FINANCIAL,
            "description": "Credit card number patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/credit-card"
        },
        "bank-account": {
            "category": ManagedDataIdentifierCategory.FINANCIAL,
            "description": "Bank account number patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/bank-account"
        },
        
        # Device identifiers
        "mac-address": {
            "category": ManagedDataIdentifierCategory.DEVICE,
            "description": "MAC address patterns",
            "arn_template": "arn:aws:dataprotection::{region}:data-identifier/mac-address"
        }
    }
    
    @classmethod
    def get_identifier_by_name(cls, name: str, region: str = "us-east-1") -> Optional[ManagedDataIdentifier]:
        """Get a managed data identifier by name."""
        if name in cls._MANAGED_IDENTIFIERS:
            config = cls._MANAGED_IDENTIFIERS[name]
            arn = config["arn_template"].format(region=region)
            return ManagedDataIdentifier(
                arn=arn,
                category=config["category"],
                description=config["description"]
            )
        return None
    
    @classmethod
    def get_identifiers_by_category(cls, category: ManagedDataIdentifierCategory, region: str = "us-east-1") -> List[ManagedDataIdentifier]:
        """Get all managed data identifiers for a specific category."""
        identifiers = []
        for name, config in cls._MANAGED_IDENTIFIERS.items():
            if config["category"] == category:
                arn = config["arn_template"].format(region=region)
                identifiers.append(ManagedDataIdentifier(
                    arn=arn,
                    category=config["category"],
                    description=config["description"]
                ))
        return identifiers
    
    @classmethod
    def get_all_identifiers(cls, region: str = "us-east-1") -> List[ManagedDataIdentifier]:
        """Get all available managed data identifiers."""
        identifiers = []
        for name, config in cls._MANAGED_IDENTIFIERS.items():
            arn = config["arn_template"].format(region=region)
            identifiers.append(ManagedDataIdentifier(
                arn=arn,
                category=config["category"],
                description=config["description"]
            ))
        return identifiers


class CustomDataIdentifierBuilder:
    """Builder for custom data identifiers targeting platform-specific patterns."""
    
    @staticmethod
    def build_agent_config_identifier() -> CustomDataIdentifier:
        """Build custom identifier for agent configuration secrets."""
        return CustomDataIdentifier(
            name="agent-config-secrets",
            regex=r'(?i)(observability_key|database_password|auth_token|api_key|secret_key)\s*[:=]\s*["\']?([a-zA-Z0-9\-_]{8,})["\']?',
            keywords=["observability", "database", "auth", "api", "secret"],
            ignore_words=["example", "placeholder", "dummy", "test"],
            maximum_match_distance=50
        )
    
    @staticmethod
    def build_ssm_parameter_identifier() -> CustomDataIdentifier:
        """Build custom identifier for SSM parameter values in logs."""
        return CustomDataIdentifier(
            name="ssm-parameter-values",
            regex=r'(?i)(parameter\s+value|ssm\s+value|retrieved\s+parameter)\s*[:=]\s*["\']?([a-zA-Z0-9\-_/]{10,})["\']?',
            keywords=["parameter", "ssm", "retrieved"],
            ignore_words=["example", "test", "demo"],
            maximum_match_distance=30
        )
    
    @staticmethod
    def build_bedrock_token_identifier() -> CustomDataIdentifier:
        """Build custom identifier for Bedrock and AI service tokens."""
        return CustomDataIdentifier(
            name="bedrock-ai-tokens",
            regex=r'(?i)(bedrock[_-]?token|ai[_-]?key|model[_-]?token|inference[_-]?key)\s*[:=]\s*["\']?([a-zA-Z0-9\-_]{16,})["\']?',
            keywords=["bedrock", "ai", "model", "inference"],
            ignore_words=["example", "placeholder", "dummy"],
            maximum_match_distance=40
        )
    
    @staticmethod
    def build_database_connection_identifier() -> CustomDataIdentifier:
        """Build custom identifier for database connection strings."""
        return CustomDataIdentifier(
            name="database-connections",
            regex=r'(?i)(connection[_-]?string|db[_-]?url|database[_-]?uri|jdbc[_-]?url)\s*[:=]\s*["\']?([^"\'\s]{20,})["\']?',
            keywords=["connection", "database", "jdbc", "uri"],
            ignore_words=["example", "localhost", "test"],
            maximum_match_distance=60
        )
    
    @staticmethod
    def build_jwt_token_identifier() -> CustomDataIdentifier:
        """Build custom identifier for JWT tokens."""
        return CustomDataIdentifier(
            name="jwt-tokens",
            regex=r'(?i)(jwt[_-]?token|bearer[_-]?token|auth[_-]?header)\s*[:=]\s*["\']?(eyJ[a-zA-Z0-9\-_]{20,})["\']?',
            keywords=["jwt", "bearer", "auth", "token"],
            ignore_words=["example", "placeholder"],
            maximum_match_distance=30
        )


class DataIdentifierValidator:
    """Validator for data identifier configurations."""
    
    @staticmethod
    def validate_managed_identifier(identifier: ManagedDataIdentifier) -> bool:
        """Validate a managed data identifier configuration."""
        try:
            # Validate ARN format
            if not identifier.arn.startswith("arn:aws:dataprotection"):
                logger.error(f"Invalid ARN format for managed identifier: {identifier.arn}")
                return False
            
            # Validate category
            if not isinstance(identifier.category, ManagedDataIdentifierCategory):
                logger.error(f"Invalid category for managed identifier: {identifier.category}")
                return False
            
            # Validate description
            if not identifier.description or len(identifier.description.strip()) == 0:
                logger.error("Description cannot be empty for managed identifier")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating managed identifier: {str(e)}")
            return False
    
    @staticmethod
    def validate_custom_identifier(identifier: CustomDataIdentifier) -> bool:
        """Validate a custom data identifier configuration."""
        try:
            # Validate name
            if not identifier.name or len(identifier.name.strip()) == 0:
                logger.error("Name cannot be empty for custom identifier")
                return False
            
            # Validate regex pattern
            if not identifier.regex:
                logger.error("Regex pattern cannot be empty for custom identifier")
                return False
            
            # Test regex compilation
            try:
                re.compile(identifier.regex)
            except re.error as e:
                logger.error(f"Invalid regex pattern in custom identifier '{identifier.name}': {str(e)}")
                return False
            
            # Validate keywords if present
            if identifier.keywords and not isinstance(identifier.keywords, list):
                logger.error(f"Keywords must be a list for custom identifier '{identifier.name}'")
                return False
            
            # Validate ignore_words if present
            if identifier.ignore_words and not isinstance(identifier.ignore_words, list):
                logger.error(f"Ignore words must be a list for custom identifier '{identifier.name}'")
                return False
            
            # Validate maximum_match_distance if present
            if identifier.maximum_match_distance is not None:
                if not isinstance(identifier.maximum_match_distance, int) or identifier.maximum_match_distance < 0:
                    logger.error(f"Maximum match distance must be a non-negative integer for custom identifier '{identifier.name}'")
                    return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating custom identifier: {str(e)}")
            return False
    
    @staticmethod
    def validate_policy_config(config: DataProtectionPolicyConfig) -> bool:
        """Validate a complete data protection policy configuration."""
        try:
            # Validate policy type
            if not isinstance(config.policy_type, DataProtectionPolicyType):
                logger.error(f"Invalid policy type: {config.policy_type}")
                return False
            
            # Validate managed identifiers
            if not config.managed_identifiers:
                logger.warning("No managed identifiers specified in policy configuration")
            else:
                for identifier in config.managed_identifiers:
                    if not DataIdentifierValidator.validate_managed_identifier(identifier):
                        return False
            
            # Validate custom identifiers
            if config.custom_identifiers:
                for identifier in config.custom_identifiers:
                    if not DataIdentifierValidator.validate_custom_identifier(identifier):
                        return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating policy configuration: {str(e)}")
            return False


def get_credentials_identifiers(region: str = "us-east-1") -> List[ManagedDataIdentifier]:
    """Get AWS managed data identifiers for credentials and authentication tokens."""
    return ManagedDataIdentifierRegistry.get_identifiers_by_category(
        ManagedDataIdentifierCategory.CREDENTIALS, region
    )


def get_financial_identifiers(region: str = "us-east-1") -> List[ManagedDataIdentifier]:
    """Get AWS managed data identifiers for financial data."""
    return ManagedDataIdentifierRegistry.get_identifiers_by_category(
        ManagedDataIdentifierCategory.FINANCIAL, region
    )


def get_pii_identifiers(region: str = "us-east-1") -> List[ManagedDataIdentifier]:
    """Get AWS managed data identifiers for personally identifiable information."""
    return ManagedDataIdentifierRegistry.get_identifiers_by_category(
        ManagedDataIdentifierCategory.PII, region
    )


def get_custom_platform_identifiers() -> List[CustomDataIdentifier]:
    """Get custom data identifiers for platform-specific sensitive data patterns."""
    builder = CustomDataIdentifierBuilder()
    return [
        builder.build_agent_config_identifier(),
        builder.build_ssm_parameter_identifier(),
        builder.build_bedrock_token_identifier(),
        builder.build_database_connection_identifier(),
        builder.build_jwt_token_identifier()
    ]


def build_identifier_arn(region: str, identifier_type: str, identifier_name: str) -> str:
    """Build a managed data identifier ARN."""
    return f"arn:aws:dataprotection::{region}:data-identifier/{identifier_type}-{identifier_name}"
