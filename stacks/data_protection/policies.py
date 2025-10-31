"""
Data protection policy management for AWS CloudWatch Logs.

This module provides utilities for creating log group-level data protection policies
using AWS managed data identifiers and custom identifiers. It generates policy
documents that comply with AWS CloudWatch Logs data protection requirements.
"""

from typing import Dict, List, Optional, Any, Union
import json
import logging
from aws_cdk import aws_logs as logs, aws_iam as iam
from constructs import Construct

from .identifiers import (
    ManagedDataIdentifier,
    CustomDataIdentifier,
    DataProtectionPolicyConfig,
    DataProtectionPolicyType
)

logger = logging.getLogger(__name__)


class LogGroupDataProtectionPolicyBuilder:
    """Builder for log group-level data protection policies."""
    
    def __init__(self, region: str = "us-east-1"):
        """Initialize the policy builder with AWS region."""
        self.region = region
        self._managed_identifiers: List[ManagedDataIdentifier] = []
        self._custom_identifiers: List[CustomDataIdentifier] = []
        self._audit_findings_destination: Optional[str] = None
        self._enable_audit_findings: bool = True
    
    def add_managed_identifiers(self, identifiers: List[ManagedDataIdentifier]) -> 'LogGroupDataProtectionPolicyBuilder':
        """Add managed data identifiers to the policy."""
        self._managed_identifiers.extend(identifiers)
        return self
    
    def add_custom_identifiers(self, identifiers: List[CustomDataIdentifier]) -> 'LogGroupDataProtectionPolicyBuilder':
        """Add custom data identifiers to the policy."""
        self._custom_identifiers.extend(identifiers)
        return self
    
    def set_audit_findings_destination(self, destination_arn: str) -> 'LogGroupDataProtectionPolicyBuilder':
        """Set S3 bucket destination for audit findings."""
        self._audit_findings_destination = destination_arn
        return self
    
    def enable_audit_findings(self, enable: bool = True) -> 'LogGroupDataProtectionPolicyBuilder':
        """Enable or disable audit findings."""
        self._enable_audit_findings = enable
        return self
    
    def build_policy_document(self) -> str:
        """Build the complete data protection policy document."""
        try:
            policy_statements = []
            
            # Build data identification statement
            if self._managed_identifiers or self._custom_identifiers:
                data_identification = self._build_data_identification_statement()
                if data_identification:
                    policy_statements.append(data_identification)
            
            # Build audit findings statement if enabled
            if self._enable_audit_findings and self._audit_findings_destination:
                audit_statement = self._build_audit_findings_statement()
                if audit_statement:
                    policy_statements.append(audit_statement)
            
            if not policy_statements:
                raise ValueError("No valid policy statements generated")
            
            # Create complete policy document
            policy_document = {
                "Version": "2012-10-17",
                "Statement": policy_statements
            }
            
            # Validate policy size (must be under 30KB)
            policy_json = json.dumps(policy_document, separators=(',', ':'))
            if not validate_policy_size(policy_document):
                raise ValueError(f"Policy document exceeds 30KB limit (current size: {len(policy_json)} bytes)")
            
            return policy_json
            
        except Exception as e:
            logger.error(f"Error building data protection policy: {str(e)}")
            raise
    
    def _build_data_identification_statement(self) -> Optional[Dict[str, Any]]:
        """Build the data identification statement for the policy."""
        try:
            statement = {
                "Sid": "DataIdentificationStatement",
                "Effect": "Allow",
                "Action": [
                    "logs:StartLogGroupDataProtectionScan",
                    "logs:StopLogGroupDataProtectionScan"
                ],
                "Resource": "*"
            }
            
            # Add conditions for data identifiers
            conditions = {}
            
            # Add managed data identifiers
            if self._managed_identifiers:
                managed_arns = [identifier.arn for identifier in self._managed_identifiers]
                conditions["StringLike"] = {
                    "logs:dataIdentifier": managed_arns
                }
            
            # Add custom data identifiers as conditions
            if self._custom_identifiers:
                custom_names = [identifier.name for identifier in self._custom_identifiers]
                if "StringLike" not in conditions:
                    conditions["StringLike"] = {}
                conditions["StringLike"]["logs:customDataIdentifier"] = custom_names
            
            if conditions:
                statement["Condition"] = conditions
            
            return statement
            
        except Exception as e:
            logger.error(f"Error building data identification statement: {str(e)}")
            return None
    
    def _build_audit_findings_statement(self) -> Optional[Dict[str, Any]]:
        """Build the audit findings statement for CloudWatch Logs delivery."""
        try:
            if not self._audit_findings_destination:
                return None
            
            return {
                "Sid": "AuditFindingsStatement", 
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": [
                    self._audit_findings_destination,
                    f"{self._audit_findings_destination}:*"
                ]
            }
            
        except Exception as e:
            logger.error(f"Error building audit findings statement: {str(e)}")
            return None


class PolicyStatementGenerator:
    """Generator for individual policy statements."""
    
    @staticmethod
    def create_data_protection_statement(
        identifiers: List[Union[ManagedDataIdentifier, CustomDataIdentifier]],
        log_group_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a data protection statement for specific identifiers."""
        try:
            statement = {
                "Sid": "LogGroupDataProtectionStatement",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroupDataProtectionPolicy",
                    "logs:PutLogGroupDataProtectionPolicy",
                    "logs:GetLogGroupDataProtectionPolicy",
                    "logs:DeleteLogGroupDataProtectionPolicy"
                ]
            }
            
            # Set resource constraint if log group name provided
            if log_group_name:
                statement["Resource"] = f"arn:aws:logs:*:*:log-group:{log_group_name}:*"
            else:
                statement["Resource"] = "*"
            
            return statement
            
        except Exception as e:
            logger.error(f"Error creating data protection statement: {str(e)}")
            raise
    
    @staticmethod
    def create_cloudwatch_audit_delivery_statement(log_group_arn: str) -> Dict[str, Any]:
        """Create audit findings delivery statement for CloudWatch Logs."""
        return {
            "Sid": "AuditFindingsDelivery",
            "Effect": "Allow", 
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": [
                log_group_arn,
                f"{log_group_arn}:*"
            ]
        }


def create_account_policy_document(identifiers: List[str], custom_identifiers: List[Dict]) -> Dict:
    """Create CloudWatch Logs data protection policy document for log groups."""
    try:
        # Build the data identifiers section
        data_identifiers = []
        
        # Add managed data identifiers
        for identifier_arn in identifiers:
            data_identifiers.append({
                "Name": identifier_arn.split("/")[-1],
                "Arn": identifier_arn
            })
        
        # Add custom data identifiers
        for custom_id in custom_identifiers:
            data_identifiers.append({
                "Name": custom_id["name"],
                "DataIdentifier": {
                    "Regex": custom_id["regex"],
                    "Keywords": custom_id.get("keywords", []),
                    "IgnoreWords": custom_id.get("ignore_words", []),
                    "MaximumMatchDistance": custom_id.get("maximum_match_distance", 50)
                }
            })
        
        # Build the complete policy document
        policy_document = {
            "Name": "PlatformDataProtectionPolicy",
            "Description": "Data protection policy for multi-agent AI platform log groups",
            "Version": "2021-06-01",
            "Statement": [
                {
                    "Sid": "audit-policy",
                    "DataIdentifier": data_identifiers,
                    "Operation": {
                        "Audit": {
                            "FindingsDestination": {}
                        }
                    }
                }
            ]
        }
        
        return policy_document
        
    except Exception as e:
        logger.error(f"Error creating account policy document: {str(e)}")
        raise


def validate_policy_size(policy_document: Dict) -> bool:
    """Validate that policy document is under AWS 30KB limit."""
    try:
        policy_json = json.dumps(policy_document, separators=(',', ':'))
        policy_size_bytes = len(policy_json.encode('utf-8'))
        max_size_bytes = 30 * 1024  # 30KB limit
        
        if policy_size_bytes > max_size_bytes:
            logger.error(f"Policy document size {policy_size_bytes} bytes exceeds {max_size_bytes} bytes limit")
            return False
        
        logger.debug(f"Policy document size: {policy_size_bytes} bytes (under {max_size_bytes} bytes limit)")
        return True
        
    except Exception as e:
        logger.error(f"Error validating policy size: {str(e)}")
        return False


def merge_policy_statements(statements: List[Dict]) -> Dict:
    """Merge multiple policy statements into a single policy document."""
    try:
        if not statements:
            raise ValueError("No statements provided to merge")
        
        merged_policy = {
            "Version": "2012-10-17", 
            "Statement": []
        }
        
        # Add all statements to the merged policy
        for statement in statements:
            if isinstance(statement, dict) and "Statement" in statement:
                # Handle nested policy documents
                if isinstance(statement["Statement"], list):
                    merged_policy["Statement"].extend(statement["Statement"])
                else:
                    merged_policy["Statement"].append(statement["Statement"])
            elif isinstance(statement, dict):
                # Handle individual statements
                merged_policy["Statement"].append(statement)
        
        # Validate the merged policy size
        if not validate_policy_size(merged_policy):
            raise ValueError("Merged policy document exceeds size limits")
        
        return merged_policy
        
    except Exception as e:
        logger.error(f"Error merging policy statements: {str(e)}")
        raise


def create_log_group_data_protection_policy(
    scope: Construct,
    policy_id: str,
    log_group: logs.LogGroup,
    config: DataProtectionPolicyConfig
) -> Optional[Any]:
    """Create a log group-level data protection policy using CDK constructs."""
    try:
        # Build policy document for CloudWatch Logs data protection
        # Note: Using raw CloudFormation since CDK may not have high-level construct yet
        data_identifiers = []
        
        # Add managed identifiers
        for identifier in config.managed_identifiers:
            data_identifiers.append({
                "Name": identifier.arn.split("/")[-1],
                "Arn": identifier.arn
            })
        
        # Add custom identifiers
        for identifier in config.custom_identifiers:
            data_identifiers.append({
                "Name": identifier.name,
                "DataIdentifier": {
                    "Regex": identifier.regex,
                    "Keywords": identifier.keywords or [],
                    "IgnoreWords": identifier.ignore_words or [],
                    "MaximumMatchDistance": identifier.maximum_match_distance or 50
                }
            })
        
        # Build policy document
        policy_document = {
            "Name": f"PlatformDataProtectionPolicy-{policy_id}",
            "Description": "Data protection policy for multi-agent AI platform log group",
            "Version": "2021-06-01",
            "Statement": [
                {
                    "Sid": "audit-policy",
                    "DataIdentifier": data_identifiers,
                    "Operation": {
                        "Audit": {
                            "FindingsDestination": {}
                        }
                    }
                }
            ]
        }
        
        # Add audit findings destination - always enabled with CloudWatch Logs
        if config.audit_findings_destination:
            policy_document["Statement"][0]["Operation"]["Audit"]["FindingsDestination"]["CloudWatchLogs"] = {
                "LogGroup": config.audit_findings_destination
            }
        
        # Convert to JSON
        policy_json = json.dumps(policy_document)
        
        # Use raw CloudFormation resource since CDK construct may not be available
        from aws_cdk import CfnResource
        
        data_protection_policy = CfnResource(
            scope,
            policy_id,
            type="AWS::Logs::DataProtectionPolicy",
            properties={
                "LogGroupIdentifier": log_group.log_group_name,
                "PolicyDocument": policy_json
            }
        )
        
        return data_protection_policy
        
    except Exception as e:
        logger.error(f"Error creating log group data protection policy: {str(e)}")
        return None


def get_logs_unmask_permission() -> str:
    """Get the IAM permission required for viewing unmasked log data."""
    return "logs:Unmask"


def create_unmask_policy_statement(log_group_arns: List[str]) -> Dict[str, Any]:
    """Create IAM policy statement for unmasking data in specific log groups."""
    return {
        "Sid": "UnmaskLogGroupData",
        "Effect": "Allow",
        "Action": [
            "logs:Unmask"
        ],
        "Resource": log_group_arns
    }
