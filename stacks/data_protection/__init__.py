"""
Data protection module for AWS CloudWatch Logs.

This module provides log group-level data protection policies using CloudWatch-native
managed data identifiers to automatically mask sensitive data including AWS credentials,
API keys, personal information, and platform-specific sensitive data patterns.
"""

__version__ = "1.0.0"
__author__ = "AWS CloudWatch Logs Data Protection Implementation"

from .identifiers import (
    ManagedDataIdentifierRegistry,
    CustomDataIdentifierBuilder,
    DataIdentifierValidator,
    get_credentials_identifiers,
    get_financial_identifiers,
    get_pii_identifiers,
    get_custom_platform_identifiers,
    build_identifier_arn,
    ManagedDataIdentifier,
    CustomDataIdentifier,
    DataProtectionPolicyConfig,
    DataProtectionPolicyType,
    ManagedDataIdentifierCategory
)

from .policies import (
    LogGroupDataProtectionPolicyBuilder,
    PolicyStatementGenerator,
    create_account_policy_document,
    validate_policy_size,
    merge_policy_statements,
    create_log_group_data_protection_policy,
    get_logs_unmask_permission,
    create_unmask_policy_statement
)

__all__ = [
    "ManagedDataIdentifierRegistry",
    "CustomDataIdentifierBuilder", 
    "DataIdentifierValidator",
    "get_credentials_identifiers",
    "get_financial_identifiers",
    "get_pii_identifiers",
    "get_custom_platform_identifiers",
    "build_identifier_arn",
    "ManagedDataIdentifier",
    "CustomDataIdentifier",
    "DataProtectionPolicyConfig",
    "DataProtectionPolicyType",
    "ManagedDataIdentifierCategory",
    "LogGroupDataProtectionPolicyBuilder",
    "PolicyStatementGenerator",
    "create_account_policy_document",
    "validate_policy_size",
    "merge_policy_statements",
    "create_log_group_data_protection_policy",
    "get_logs_unmask_permission",
    "create_unmask_policy_statement"
]
