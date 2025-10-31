"""
IAM permissions boundary policy definitions and factory methods.

This module provides classes and functions for creating service-specific
IAM permissions boundary policies.
"""

from typing import Dict, List, Any
import aws_cdk as cdk
from aws_cdk import aws_iam as iam

from .constants import (
    AGENT_SERVICE_ALLOWED_SERVICES,
    CONFIGURATION_API_ALLOWED_SERVICES,
    SUPERVISOR_AGENT_ALLOWED_SERVICES,
    RESTRICTED_ACTIONS,
    ServiceType
)


class PermissionsBoundaryConfig:
    """Configuration class for permissions boundary settings."""
    
    def __init__(self, 
                 service_type: str,
                 allowed_services: List[str] = None,
                 additional_allowed_actions: List[str] = None,
                 additional_restricted_actions: List[str] = None):
        """
        Initialize permissions boundary configuration.
        
        Args:
            service_type: Type of service (from ServiceType enum)
            allowed_services: List of AWS services allowed for this boundary
            additional_allowed_actions: Additional specific actions to allow
            additional_restricted_actions: Additional specific actions to restrict
        """
        self.service_type = service_type
        self.allowed_services = allowed_services or []
        self.additional_allowed_actions = additional_allowed_actions or []
        self.additional_restricted_actions = additional_restricted_actions or []
        
        # Combine base restricted actions with additional ones
        self.restricted_actions = RESTRICTED_ACTIONS + self.additional_restricted_actions
    
    def get_allowed_actions(self) -> List[str]:
        """
        Get list of allowed actions for this boundary.
        
        Returns:
            List of allowed IAM actions
        """
        allowed_actions = []
        
        # Add service-level permissions
        for service in self.allowed_services:
            allowed_actions.append(f"{service}:*")
        
        # Add specific additional actions
        allowed_actions.extend(self.additional_allowed_actions)
        
        return allowed_actions


class BoundaryPolicyFactory:
    """Factory class for creating service-specific boundary policies."""
    
    @staticmethod
    def create_agent_service_boundary_policy() -> iam.PolicyDocument:
        """
        Create permissions boundary policy for agent services.
        
        This policy allows access to AI/ML services and basic infrastructure
        but restricts high-risk operations and administrative functions.
        
        Returns:
            IAM PolicyDocument for agent service boundary
        """
        config = PermissionsBoundaryConfig(
            service_type=ServiceType.AGENT_SERVICE,
            allowed_services=AGENT_SERVICE_ALLOWED_SERVICES,
            additional_allowed_actions=[
                # Bedrock AgentCore permissions for memory functionality
                "bedrock-agentcore:*",
                
                # Specific Bedrock AgentCore memory permissions (explicit for clarity)
                "bedrock-agentcore:RetrieveMemoryRecords",
                "bedrock-agentcore:CreateMemory",
                "bedrock-agentcore:DeleteMemory",
                "bedrock-agentcore:GetMemory",
                "bedrock-agentcore:ListMemories",
                "bedrock-agentcore:UpdateMemory",
                "bedrock-agentcore:CreateEvent",
                "bedrock-agentcore:DeleteEvent",
                "bedrock-agentcore:GetEvent",
                "bedrock-agentcore:ListEvents",
                "bedrock-agentcore:RetrieveMemories",
                
                # Allow ECS task management for self-discovery
                "ecs:DescribeServices",
                "ecs:DescribeTasks",
                "ecs:ListTasks",
                
                # Allow limited EC2 network discovery
                "ec2:DescribeNetworkInterfaces",
                "ec2:DescribeSubnets",
                "ec2:DescribeVpcs",
                "ec2:DescribeSecurityGroups",
                
                # Allow VPC Lattice service discovery
                "vpc-lattice:GetService",
                "vpc-lattice:ListServices",
                "vpc-lattice:GetServiceNetwork",
                "vpc-lattice:ListServiceNetworks"
            ]
        )
        
        return BoundaryPolicyFactory._create_policy_document(config)
    
    @staticmethod
    def create_configuration_api_boundary_policy() -> iam.PolicyDocument:
        """
        Create permissions boundary policy for Configuration API.
        
        This policy allows infrastructure management operations needed for
        dynamic agent deployment but restricts account-level changes and
        cross-account access.
        
        Returns:
            IAM PolicyDocument for Configuration API boundary
        """
        config = PermissionsBoundaryConfig(
            service_type=ServiceType.CONFIGURATION_API,
            allowed_services=CONFIGURATION_API_ALLOWED_SERVICES,
            additional_allowed_actions=[
                # Allow broad CloudFormation operations for stack management
                "cloudformation:*",
                
                # Allow IAM operations needed for role management in stacks
                "iam:CreateRole",
                "iam:DeleteRole",
                "iam:GetRole",
                "iam:ListRoles",
                "iam:PassRole",
                "iam:UpdateRole",
                "iam:TagRole",
                "iam:UntagRole",
                "iam:AttachRolePolicy",
                "iam:DetachRolePolicy",
                "iam:CreatePolicy",
                "iam:DeletePolicy",
                "iam:GetPolicy",
                "iam:ListPolicies",
                "iam:PutRolePolicy",
                "iam:DeleteRolePolicy",
                "iam:GetRolePolicy",
                
                # Allow ECS management for agent services
                "ecs:*",
                
                # Allow Load Balancer management for ALB-VPC Lattice hybrid
                "elasticloadbalancing:*",
                
                # Allow VPC Lattice management for service network
                "vpc-lattice:*",
                
                # Allow CloudWatch Logs management for stack logging
                "logs:*",
                
                # Allow EC2 security group and network interface management
                "ec2:CreateSecurityGroup",
                "ec2:DeleteSecurityGroup",
                "ec2:AuthorizeSecurityGroupIngress",
                "ec2:AuthorizeSecurityGroupEgress", 
                "ec2:RevokeSecurityGroupIngress",
                "ec2:RevokeSecurityGroupEgress",
                "ec2:CreateNetworkInterface",
                "ec2:DeleteNetworkInterface",
                "ec2:AttachNetworkInterface",
                "ec2:DetachNetworkInterface",
                "ec2:CreateTags",
                "ec2:DeleteTags",
                "ec2:DescribeAvailabilityZones",
                
                # Allow Bedrock inference profile operations for cross-region model discovery
                "bedrock:ListInferenceProfiles",
                "bedrock:GetInferenceProfile"
            ],
            additional_restricted_actions=[
                # Restrict high-risk IAM operations even for Configuration API
                "iam:CreateUser",
                "iam:DeleteUser",
                "iam:CreateGroup",
                "iam:DeleteGroup",
                "iam:AttachUserPolicy",
                "iam:DetachUserPolicy",
                "iam:PutUserPolicy",
                "iam:DeleteUserPolicy",
                
                # Restrict VPC-level network changes
                "ec2:CreateVpc",
                "ec2:DeleteVpc",
                "ec2:CreateSubnet",
                "ec2:DeleteSubnet",
                "ec2:CreateRouteTable",
                "ec2:DeleteRouteTable",
                "ec2:CreateInternetGateway",
                "ec2:DeleteInternetGateway"
            ]
        )
        
        return BoundaryPolicyFactory._create_policy_document(config)
    
    @staticmethod
    def create_supervisor_agent_boundary_policy() -> iam.PolicyDocument:
        """
        Create permissions boundary policy for supervisor agent.
        
        This policy allows coordination functions and basic AI/ML services
        but restricts infrastructure management and high-risk operations.
        
        Returns:
            IAM PolicyDocument for supervisor agent boundary
        """
        config = PermissionsBoundaryConfig(
            service_type=ServiceType.SUPERVISOR_AGENT,
            allowed_services=SUPERVISOR_AGENT_ALLOWED_SERVICES,
            additional_allowed_actions=[
                # Allow ECS service discovery for agent coordination
                "ecs:DescribeServices",
                "ecs:DescribeTasks",
                "ecs:ListTasks",
                "ecs:DescribeTaskDefinition",
                
                # Allow limited EC2 network discovery
                "ec2:DescribeNetworkInterfaces",
                "ec2:DescribeSubnets",
                "ec2:DescribeVpcs",
                "ec2:DescribeSecurityGroups"
            ]
        )
        
        return BoundaryPolicyFactory._create_policy_document(config)
    
    @staticmethod
    def _create_policy_document(config: PermissionsBoundaryConfig) -> iam.PolicyDocument:
        """
        Create IAM policy document from boundary configuration.
        
        Args:
            config: Permissions boundary configuration
            
        Returns:
            IAM PolicyDocument with allow and deny statements
        """
        statements = []
        
        # Allow statement for permitted actions
        if config.get_allowed_actions():
            allow_statement = iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=config.get_allowed_actions(),
                resources=["*"]
            )
            statements.append(allow_statement)
        
        # Explicit deny statement for restricted actions
        if config.restricted_actions:
            deny_statement = iam.PolicyStatement(
                effect=iam.Effect.DENY,
                actions=config.restricted_actions,
                resources=["*"]
            )
            statements.append(deny_statement)
        
        # Additional deny statement for cross-account access
        # Allow Bedrock cross-region access for model availability
        cross_account_deny = iam.PolicyStatement(
            effect=iam.Effect.DENY,
            actions=["*"],
            resources=["*"],
            conditions={
                "StringNotEquals": {
                    "aws:RequestedRegion": [cdk.Aws.REGION, "us-east-1", "us-west-2"]
                },
                "Bool": {
                    "aws:via-bedrock": "false"
                }
            }
        )
        statements.append(cross_account_deny)
        
        # Allow Bedrock cross-region access for foundation models
        bedrock_cross_region_allow = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:GetFoundationModel",
                "bedrock:ListFoundationModels",
                "bedrock:GetInferenceProfile",
                "bedrock:ListInferenceProfiles"
            ],
            resources=["*"]
        )
        statements.append(bedrock_cross_region_allow)
        
        return iam.PolicyDocument(statements=statements)
    
    @staticmethod
    def get_boundary_policy_for_service_type(service_type: str) -> iam.PolicyDocument:
        """
        Get the appropriate boundary policy for a service type.
        
        Args:
            service_type: Service type from ServiceType enum
            
        Returns:
            IAM PolicyDocument for the service type
            
        Raises:
            ValueError: If service type is not recognized
        """
        if service_type == ServiceType.AGENT_SERVICE:
            return BoundaryPolicyFactory.create_agent_service_boundary_policy()
        elif service_type == ServiceType.CONFIGURATION_API:
            return BoundaryPolicyFactory.create_configuration_api_boundary_policy()
        elif service_type == ServiceType.SUPERVISOR_AGENT:
            return BoundaryPolicyFactory.create_supervisor_agent_boundary_policy()
        else:
            raise ValueError(f"Unknown service type: {service_type}")
