"""
Constants for IAM permissions boundaries.

This module defines policy names, ARNs, and other constants used across
the IAM permissions boundaries implementation.
"""

# Boundary policy names
AGENT_SERVICE_BOUNDARY_POLICY_NAME = "AgentServicePermissionsBoundary"
CONFIGURATION_API_BOUNDARY_POLICY_NAME = "ConfigurationApiPermissionsBoundary"  
SUPERVISOR_AGENT_BOUNDARY_POLICY_NAME = "SupervisorAgentPermissionsBoundary"

# Policy name prefix for all boundary policies
BOUNDARY_POLICY_PREFIX = "GenerativeAI"

# Full policy names with prefix
FULL_AGENT_SERVICE_BOUNDARY_POLICY_NAME = f"{BOUNDARY_POLICY_PREFIX}{AGENT_SERVICE_BOUNDARY_POLICY_NAME}"
FULL_CONFIGURATION_API_BOUNDARY_POLICY_NAME = f"{BOUNDARY_POLICY_PREFIX}{CONFIGURATION_API_BOUNDARY_POLICY_NAME}"
FULL_SUPERVISOR_AGENT_BOUNDARY_POLICY_NAME = f"{BOUNDARY_POLICY_PREFIX}{SUPERVISOR_AGENT_BOUNDARY_POLICY_NAME}"

# Service types for boundary policy mapping
class ServiceType:
    """Enumeration of service types for boundary policy assignment."""
    AGENT_SERVICE = "agent_service"
    CONFIGURATION_API = "configuration_api"
    SUPERVISOR_AGENT = "supervisor_agent"

# Mapping of service types to boundary policy names
SERVICE_TYPE_TO_POLICY_NAME = {
    ServiceType.AGENT_SERVICE: FULL_AGENT_SERVICE_BOUNDARY_POLICY_NAME,
    ServiceType.CONFIGURATION_API: FULL_CONFIGURATION_API_BOUNDARY_POLICY_NAME,
    ServiceType.SUPERVISOR_AGENT: FULL_SUPERVISOR_AGENT_BOUNDARY_POLICY_NAME
}

# AWS services allowed for each service type
AGENT_SERVICE_ALLOWED_SERVICES = [
    "bedrock",
    "ssm", 
    "logs",
    "s3",
    "dynamodb",
    "rds-data",
    "secretsmanager",
    "ecs",
    "ecr",
    "ec2",
    "vpc-lattice",
    "kms"
]

CONFIGURATION_API_ALLOWED_SERVICES = [
    "cloudformation",
    "iam",
    "ecs", 
    "ec2",
    "elasticloadbalancing",
    "logs",
    "ssm",
    "secretsmanager",  # Required for reading Cognito/Auth0/Okta/Ping authentication secrets
    "cognito-idp",  # Required for Cognito User Pool role management and group operations
    "vpc-lattice",
    "ecr",
    "kms",
    "s3",
    "bedrock"
]

SUPERVISOR_AGENT_ALLOWED_SERVICES = [
    "bedrock",
    "ssm",
    "logs", 
    "ecs",
    "ecr",
    "ec2",
    "kms",
    "secretsmanager",  # ← CRITICAL: Required for authentication service initialization
    "cognito-idp"     # ← CRITICAL: Required for JWT token validation from Cognito User Pool
]

# High-risk actions that should be restricted across all service types
RESTRICTED_ACTIONS = [
    # Account-level changes
    "organizations:*",
    "account:*",
    "billing:*",
    "budgets:*",
    "ce:*",  # Cost Explorer
    "cur:*",  # Cost and Usage Reports
    
    # Cross-account access
    "sts:AssumeRole",
    "sts:AssumeRoleWithSAML", 
    "sts:AssumeRoleWithWebIdentity",
    
    # High-risk IAM operations
    "iam:CreateUser",
    "iam:DeleteUser",
    "iam:CreateAccessKey",
    "iam:CreateLoginProfile",
    "iam:CreateServiceLinkedRole",
    "iam:DeleteAccountPasswordPolicy",
    "iam:PutAccountPasswordPolicy",
    "iam:UpdateAccessKey",
    "iam:UpdateLoginProfile",
    
    # Network security - VPC level changes only (security group management allowed for Configuration API)
    "ec2:CreateVpc",
    "ec2:DeleteVpc",
    "ec2:ModifyVpcAttribute",
    
    # Data protection
    "kms:CreateKey",
    "kms:ScheduleKeyDeletion",
    "kms:DeleteAlias",
    "kms:CreateGrant",
    
    # Service control
    "config:DeleteConfigRule",
    "config:DeleteConfigurationRecorder",
    "cloudtrail:DeleteTrail",
    "cloudtrail:StopLogging"
]
