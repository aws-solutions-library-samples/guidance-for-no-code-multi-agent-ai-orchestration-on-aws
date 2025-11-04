"""
IAM Permissions Boundaries Stack.

This stack creates IAM managed policies that serve as permissions boundaries
for different compute resource types in the generative AI platform.
"""

from typing import Dict, Any
import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from constructs import Construct

from helper.config import Config
from stacks.common.base import BaseStack
from .policies import BoundaryPolicyFactory
from .constants import (
    FULL_AGENT_SERVICE_BOUNDARY_POLICY_NAME,
    FULL_CONFIGURATION_API_BOUNDARY_POLICY_NAME,
    FULL_SUPERVISOR_AGENT_BOUNDARY_POLICY_NAME,
    ServiceType
)


class IAMBoundariesStack(BaseStack):
    """
    Stack for creating IAM permissions boundary policies.
    
    This stack must be deployed before any compute resource stacks that
    reference these boundary policies. It creates managed policies that
    limit the maximum permissions that can be granted to IAM roles.
    """

    def __init__(self, 
                 scope: Construct, 
                 construct_id: str,
                 config: Config,
                 **kwargs) -> None:
        """
        Initialize the IAM boundaries stack.
        
        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            config: Configuration object
            **kwargs: Additional keyword arguments for Stack
        """
        # Add solution ID and description
        kwargs['description'] = "IAM permissions boundary policies for secure role-based access control - (Solution ID - SO9637)"
        super().__init__(scope, construct_id, config, **kwargs)
        
        # Store boundary policies for cross-stack references
        self.boundary_policies = {}
        
        # Create permissions boundary policies
        self._create_boundary_policies()
        
        # Create CloudFormation outputs for policy ARNs
        self._create_policy_outputs()
    
    def _create_boundary_policies(self) -> None:
        """Create all permissions boundary policies."""
        # Create agent service boundary policy
        self.boundary_policies[ServiceType.AGENT_SERVICE] = self._create_agent_service_boundary()
        
        # Create configuration API boundary policy
        self.boundary_policies[ServiceType.CONFIGURATION_API] = self._create_configuration_api_boundary()
        
        # Create supervisor agent boundary policy
        self.boundary_policies[ServiceType.SUPERVISOR_AGENT] = self._create_supervisor_agent_boundary()
    
    def _create_agent_service_boundary(self) -> iam.ManagedPolicy:
        """
        Create permissions boundary policy for agent services.
        
        Returns:
            IAM ManagedPolicy for agent service boundary
        """
        policy_doc = BoundaryPolicyFactory.create_agent_service_boundary_policy()
        
        policy = iam.ManagedPolicy(
            self,
            "agent-service-boundary-policy",
            description=(
                "Permissions boundary for AI agent services. Allows access to "
                "Bedrock, SSM, CloudWatch, S3, DynamoDB, and basic infrastructure "
                "services while restricting high-risk operations."
            ),
            document=policy_doc
        )
        
        # Add tags for identification and management
        cdk.Tags.of(policy).add("BoundaryType", "AgentService")
        cdk.Tags.of(policy).add("Purpose", "PermissionsBoundary")
        cdk.Tags.of(policy).add("RestrictPrivilegeEscalation", "true")
        
        return policy
    
    def _create_configuration_api_boundary(self) -> iam.ManagedPolicy:
        """
        Create permissions boundary policy for Configuration API.
        
        Returns:
            IAM ManagedPolicy for Configuration API boundary
        """
        policy_doc = BoundaryPolicyFactory.create_configuration_api_boundary_policy()
        
        policy = iam.ManagedPolicy(
            self,
            "configuration-api-boundary-policy",
            description=(
                "Permissions boundary for Configuration API service. Allows "
                "infrastructure management operations for dynamic agent deployment "
                "while restricting account-level changes and cross-account access."
            ),
            document=policy_doc
        )
        
        # Add tags for identification and management
        cdk.Tags.of(policy).add("BoundaryType", "ConfigurationAPI")
        cdk.Tags.of(policy).add("Purpose", "PermissionsBoundary")
        cdk.Tags.of(policy).add("RestrictPrivilegeEscalation", "true")
        
        return policy
    
    def _create_supervisor_agent_boundary(self) -> iam.ManagedPolicy:
        """
        Create permissions boundary policy for supervisor agent.
        
        Returns:
            IAM ManagedPolicy for supervisor agent boundary
        """
        policy_doc = BoundaryPolicyFactory.create_supervisor_agent_boundary_policy()
        
        policy = iam.ManagedPolicy(
            self,
            "supervisor-agent-boundary-policy",
            description=(
                "Permissions boundary for supervisor agent service. Allows "
                "coordination functions and basic AI/ML services while "
                "restricting infrastructure management and high-risk operations."
            ),
            document=policy_doc
        )
        
        # Add tags for identification and management
        cdk.Tags.of(policy).add("BoundaryType", "SupervisorAgent")
        cdk.Tags.of(policy).add("Purpose", "PermissionsBoundary")
        cdk.Tags.of(policy).add("RestrictPrivilegeEscalation", "true")
        
        return policy
    
    def _create_policy_outputs(self) -> None:
        """Create CloudFormation outputs for boundary policy ARNs."""
        # Export agent service boundary policy ARN
        cdk.CfnOutput(
            self,
            "agent-service-boundary-arn",
            description="ARN of the Agent Service permissions boundary policy",
            value=self.boundary_policies[ServiceType.AGENT_SERVICE].managed_policy_arn,
            export_name=f"{self.config._environment}-AgentServiceBoundaryArn"
        )
        
        # Export configuration API boundary policy ARN
        cdk.CfnOutput(
            self,
            "configuration-api-boundary-arn",
            description="ARN of the Configuration API permissions boundary policy",
            value=self.boundary_policies[ServiceType.CONFIGURATION_API].managed_policy_arn,
            export_name=f"{self.config._environment}-ConfigurationApiBoundaryArn"
        )
        
        # Export supervisor agent boundary policy ARN
        cdk.CfnOutput(
            self,
            "supervisor-agent-boundary-arn",
            description="ARN of the Supervisor Agent permissions boundary policy",
            value=self.boundary_policies[ServiceType.SUPERVISOR_AGENT].managed_policy_arn,
            export_name=f"{self.config._environment}-SupervisorAgentBoundaryArn"
        )
    
    def get_boundary_policy_arn(self, service_type: str) -> str:
        """
        Get the ARN of a boundary policy for a specific service type.
        
        Args:
            service_type: Service type from ServiceType enum
            
        Returns:
            ARN of the boundary policy
            
        Raises:
            ValueError: If service type is not recognized
        """
        if service_type not in self.boundary_policies:
            raise ValueError(f"Unknown service type: {service_type}")
        
        return self.boundary_policies[service_type].managed_policy_arn
    
    def get_boundary_policy(self, service_type: str) -> iam.ManagedPolicy:
        """
        Get the boundary policy object for a specific service type.
        
        Args:
            service_type: Service type from ServiceType enum
            
        Returns:
            IAM ManagedPolicy object
            
        Raises:
            ValueError: If service type is not recognized
        """
        if service_type not in self.boundary_policies:
            raise ValueError(f"Unknown service type: {service_type}")
        
        return self.boundary_policies[service_type]
