import aws_cdk as cdk
from typing import Dict, Optional, List
from constructs import Construct
from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_ecr_assets as ecr_assets,
    aws_logs as logs
)

from helper.config import Config
from stacks.common.base import BaseStack, FargateServiceStack
from stacks.common.mixins import IAMPolicyMixin, SecurityGroupMixin, LoadBalancerLoggingMixin
from stacks.common.constants import (
    AGENT_SUPERVISOR_PORT,
    AGENT_SUPERVISOR_HEALTH_CHECK_PATH,
    AGENT_SUPERVISOR_DOCKERFILE_PATH,
    DEFAULT_CPU,
    DEFAULT_MEMORY,
    DEFAULT_DESIRED_COUNT,
    AGENT_SUPERVISOR_IMAGE_PATH,
    DEFAULT_MINIMUM_HEALTHY_PERCENT_BLUE_GREEN,
    DEFAULT_MAXIMUM_PERCENT_BLUE_GREEN,
    DEFAULT_HEALTHY_THRESHOLD_COUNT,
    DEFAULT_UNHEALTHY_THRESHOLD_COUNT,
    DEFAULT_HEALTH_CHECK_INTERVAL,
    DEFAULT_HEALTH_CHECK_TIMEOUT
)


class SupervisorAgentStack(FargateServiceStack, LoadBalancerLoggingMixin):
    """
    Supervisor Agent Stack for deploying agent supervisor service on ECS Fargate with ALB (internal-facing).
    
    This stack is designed to deploy the supervisor agent with an internal Application Load Balancer
    that only allows traffic from VPC CIDRs, providing secure internal access to the supervisor service.
    
    Features:
    - Termination protection enabled to prevent accidental deletion
    - Blue-green deployment strategy for zero-downtime updates
    - Internal-facing ALB for secure VPC-only access
    """

    def __init__(self, 
                 scope: Construct, 
                 construct_id: str,
                 vpc: ec2.Vpc,
                 access_log_bucket: s3.Bucket,
                 cluster: ecs.Cluster,
                 configuration_api_dns: str,
                 cognito_resources,  # CognitoResources from authentication stack
                 conf: Config,
                 **kwargs) -> None:
        # Add solution ID and description
        kwargs['description'] = "Supervisor Agent service for orchestrating and coordinating multi-agent workflows - (Solution ID - SO9637)"
        # Initialize with FargateServiceStack - use empty string for service_network_arn since we're using ALB
        super().__init__(scope, construct_id, vpc, cluster, "", conf, **kwargs)
        
        # Set additional attributes
        self.access_log_bucket = access_log_bucket
        self.cognito_resources = cognito_resources

        # Get configuration values
        supervisor_cpu = self.get_optional_config('SupervisorCPU', DEFAULT_CPU)
        supervisor_memory = self.get_optional_config('SupervisorMemory', DEFAULT_MEMORY)
        supervisor_desired_count = self.get_optional_config('SupervisorDesiredCount', DEFAULT_DESIRED_COUNT)
        
        # Prepare environment variables for supervisor agent
        environment_vars = {
            "AGENT_NAME": "supervisor_agent",
            "PROJECT_NAME": conf.get('ProjectName'),  # Critical for runtime components
            "CONFIGURATION_API_ENDPOINT": f"http://{configuration_api_dns}",
            "AWS_REGION": self.region,
            "SECRETS_MANAGER_ARN": cognito_resources.secret_arn,  # Use cognito resources directly
            "AUTH_PROVIDER_TYPE": self.get_optional_config('AuthProviderType', 'cognito'),  # Configurable auth provider
            # Model configuration from config file using generic environment variables
            "MODEL_ID": self.get_optional_config('SupervisorModelId', 'us.anthropic.claude-opus-4-1-20250805-v1:0'),
            "JUDGE_MODEL_ID": self.get_optional_config('SupervisorJudgeModelId', 'us.anthropic.claude-opus-4-1-20250805-v1:0'),
            "EMBEDDING_MODEL_ID": self.get_optional_config('SupervisorEmbeddingModelId', 'amazon.titan-embed-text-v2:0'),
            "TEMPERATURE": str(self.get_optional_config('SupervisorTemperature', 0.7)),
            "TOP_P": str(self.get_optional_config('SupervisorTopP', 0.9)),
            "STREAMING": str(self.get_optional_config('SupervisorStreaming', 'True'))
        }
        
        # Create the supervisor agent service using native blue-green ALB deployment
        resources = self.create_blue_green_alb_fargate_service(
            service_name="agent-supervisor",
            container_image_path=AGENT_SUPERVISOR_IMAGE_PATH,
            port=AGENT_SUPERVISOR_PORT,
            health_check_path=AGENT_SUPERVISOR_HEALTH_CHECK_PATH,
            cpu=supervisor_cpu,
            memory=supervisor_memory,
            desired_count=supervisor_desired_count,
            environment_vars=environment_vars,
            platform=ecr_assets.Platform.LINUX_ARM64,
            dockerfile_path=AGENT_SUPERVISOR_DOCKERFILE_PATH
        )
        
        # Configure ALB logging using the mixin with AWS documentation best practices
        # This ensures proper region-aware service account permissions and consistent naming
        self.configure_alb_logging(
            load_balancer=resources["load_balancer"],
            access_logs_bucket=self.access_log_bucket,
            prefix="supervisor-agent-alb"
        )
        
        # Grant read access to Cognito secret from authentication stack
        self.cognito_resources.secrets_manager_secret.grant_read(resources["task_definition"].task_role)
        
        # Add explicit Secrets Manager permissions for Cognito secret access
        from aws_cdk import aws_iam as iam
        task_definition_task_role = resources["task_definition"].task_role
        task_definition_task_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "secretsmanager:GetSecretValue",
                    "secretsmanager:DescribeSecret"
                ],
                resources=[self.cognito_resources.secret_arn]
            )
        )
        
        # Add Cognito User Pool permissions for token validation
        self._add_authentication_permissions(resources["task_definition"])
        
        # Add core service permissions for supervisor agent functionality
        self._add_supervisor_core_permissions(resources["task_definition"])
        
        # Apply supervisor agent permissions boundary to task role
        self._apply_supervisor_agent_permissions_boundary(resources["task_definition"])

        # Export the service properties for compatibility with existing code
        self.supervisor_fargate_service = resources["ecs_service"]
        self.supervisor_load_balancer = resources["load_balancer"]
        self.supervisor_target_group = resources["target_groups"]["primary"]  # Use primary target group for blue-green
        self.supervisor_alb_dns = resources["load_balancer"].load_balancer_dns_name
        
        # Construct service ARN manually since CfnService doesn't have service_arn attribute
        self.supervisor_fargate_service_arn = cdk.Arn.format(
            components=cdk.ArnComponents(
                service="ecs",
                resource="service",
                resource_name=f"{cluster.cluster_name}/{resources['ecs_service'].service_name}",
                region=cdk.Stack.of(self).region,
                account=cdk.Stack.of(self).account
            ),
            stack=self
        )
    
    def _add_authentication_permissions(self, task_definition: ecs.FargateTaskDefinition) -> None:
        """
        Add Cognito User Pool permissions for JWT token validation.
        
        The Supervisor Agent needs these permissions to validate JWT tokens
        and extract user information for authentication.
        
        Args:
            task_definition: ECS task definition to grant permissions to
        """
        from aws_cdk import aws_iam as iam
        
        # Cognito User Pool permissions for token validation
        cognito_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # User operations for authentication and token validation
                "cognito-idp:AdminGetUser",
                "cognito-idp:GetUser",
                "cognito-idp:AdminListGroupsForUser",
                "cognito-idp:ListUsersInGroup",
                "cognito-idp:GetGroup",
                "cognito-idp:ListGroups"
            ],
            resources=[
                # Access the Cognito User Pool from authentication stack
                self.cognito_resources.user_pool.user_pool_arn
            ]
        )
        
        task_definition.task_role.add_to_policy(cognito_policy)

    def _add_supervisor_core_permissions(self, task_definition: ecs.FargateTaskDefinition) -> None:
        """
        Add supervisor-specific permissions beyond what base class provides.
        
        Note: Base class create_blue_green_alb_fargate_service() already adds:
        - Bedrock permissions
        - SSM permissions  
        - CloudWatch Logs permissions
        - ECS task permissions
        - ECR permissions
        - EC2 network permissions
        
        Args:
            task_definition: ECS task definition to grant permissions to
        """
        from aws_cdk import aws_iam as iam
        
        # Add ECS service discovery permissions for agent coordination (not in base class)
        ecs_discovery_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ecs:DescribeServices",
                "ecs:DescribeTasks", 
                "ecs:ListTasks",
                "ecs:DescribeTaskDefinition"
            ],
            resources=["*"]  # ECS discovery operations require * resource
        )
        
        task_definition.task_role.add_to_policy(ecs_discovery_policy)

    def _apply_supervisor_agent_permissions_boundary(self, task_definition: ecs.FargateTaskDefinition) -> None:
        """
        Apply supervisor agent permissions boundary to task role.
        
        Args:
            task_definition: The ECS task definition with role to apply boundary to
        """
        try:
            # Import supervisor agent boundary policy ARN from IAM boundaries stack
            boundary_arn = cdk.Fn.import_value(f"{self.config._environment}-SupervisorAgentBoundaryArn")
            
            # Apply boundary to the task role
            self.apply_permissions_boundary(task_definition.task_role, boundary_arn)
            
        except Exception as e:
            # Log warning but don't fail deployment if boundary import fails
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to apply supervisor agent permissions boundary: {str(e)}")
