import aws_cdk as cdk
from typing import Dict
from constructs import Construct
from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_ecr_assets as ecr_assets
)

from helper.config import Config
from stacks.common.base import FargateServiceStack
from stacks.common.constants import (
    AGENT_PORT,
    AGENT_SUPERVISOR_PORT,
    AGENT_HEALTH_CHECK_PATH,
    DEFAULT_CPU,
    DEFAULT_MEMORY,
    DEFAULT_DESIRED_COUNT,
    AGENT_INSTANCE_IMAGE_PATH,
    AGENT_INSTANCE_DOCKERFILE_PATH,
    AGENT_SUPERVISOR_IMAGE_PATH,
    AGENT_SUPERVISOR_DOCKERFILE_PATH
)


class MultiAgentStack(FargateServiceStack):
    """
    Agent Stack for deploying multi-agent services on ECS Fargate with VPC Lattice integration (internal-only).
    
    This stack is configurable to use any ECS cluster, providing flexibility to:
    - Use a shared cluster for cost efficiency and resource optimization
    - Use dedicated clusters for isolation and specific requirements
    - Scale agents independently based on workload demands
    - Deploy via AWS CLI with agent_name as a CloudFormation parameter
    """

    def __init__(self, 
                 scope: Construct, 
                 construct_id: str,
                 access_log_bucket: s3.Bucket = None,
                 service_network_arn: str = None,
                 cluster: ecs.Cluster = None,
                 agent_name: str = None,
                 conf: Config = None,
                 vpc: ec2.Vpc = None,
                 vpc_id: str = None,
                 cluster_name: str = None,
                 access_log_bucket_name: str = None,
                 **kwargs) -> None:
        # Handle both VPC object and VPC ID token for CloudFormation imports
        # Import resources BEFORE calling super().__init__() so we can pass them
        if vpc is None and vpc_id is not None:
            # We need to create a Stack first to have a scope for imports
            # Call Stack.__init__ directly to get a Stack scope
            from aws_cdk import Stack
            Stack.__init__(self, scope, construct_id, **kwargs)
            
            # Now import VPC using vpc_id token (supports CloudFormation Fn::ImportValue)
            # Import subnet IDs and CIDR from VPC stack exports
            project_name = conf.get('ProjectName')
            vpc_cidr_token = cdk.Fn.import_value(f"{project_name}-VpcCidr")
            private_subnet_ids_csv = cdk.Fn.import_value(f"{project_name}-PrivateSubnetIds")
            
            # Split the comma-separated subnet IDs - CloudFormation will resolve this at deploy time
            private_subnet_ids = cdk.Fn.split(",", private_subnet_ids_csv)
            
            # Convert token list to Python list for from_vpc_attributes
            # We need to reference individual subnets using Fn.select
            private_subnet_list = [
                cdk.Fn.select(0, private_subnet_ids),
                cdk.Fn.select(1, private_subnet_ids)
            ]
            
            vpc = ec2.Vpc.from_vpc_attributes(
                self, "VpcImport",
                vpc_id=vpc_id,
                availability_zones=cdk.Fn.get_azs(),
                # Use actual subnet IDs and CIDR from CloudFormation exports
                private_subnet_ids=private_subnet_list,
                vpc_cidr_block=vpc_cidr_token
            )
        elif vpc is None:
            raise ValueError("Either vpc or vpc_id parameter must be provided")
        else:
            # vpc object was provided, just call parent __init__
            super().__init__(scope, construct_id, vpc, cluster, service_network_arn, conf, access_log_bucket=access_log_bucket, **kwargs)
            return  # Early return since parent __init__ handles everything
        
        # Import cluster if not provided but cluster_name is available
        if cluster is None and cluster_name is not None:
            cluster = ecs.Cluster.from_cluster_attributes(
                self, "ImportedCluster",
                cluster_name=cluster_name,
                vpc=vpc
            )
        elif cluster is None:
            raise ValueError("Either cluster or cluster_name parameter must be provided")
        
        # Import access log bucket if not provided but bucket name is available
        if access_log_bucket is None and access_log_bucket_name is not None:
            access_log_bucket = s3.Bucket.from_bucket_name(
                self, "ImportedAccessLogBucket",
                bucket_name=access_log_bucket_name
            )
        elif access_log_bucket is None:
            raise ValueError("Either access_log_bucket or access_log_bucket_name parameter must be provided")
        
        # Now manually initialize FargateServiceStack attributes since we bypassed super().__init__()
        # Replicate FargateServiceStack.__init__ logic
        self.vpc = vpc
        self.cluster = cluster
        self.access_log_bucket = access_log_bucket
        self.service_network_arn = service_network_arn
        self.config = conf
        
        # Initialize base stack properties that FargateServiceStack expects
        self._environment = conf._environment
        # Note: self.region is a read-only property from Stack, don't try to set it
        
        # Create CloudFormation parameter for agent name
        # Preserve original agent name for SSM parameters and internal references
        self.agent_name_parameter = cdk.CfnParameter(
            self, "AgentName",
            type="String",
            description="Name of the agent instance (used for SSM configuration and environment variables)",
            default=agent_name,
            allowed_pattern=r"^[a-z0-9_-]+$",
            constraint_description="Agent name must contain only lowercase letters, numbers, underscores, and hyphens"
        )

        # Get configuration values
        agent_cpu = self.get_optional_config('AgentCPU', DEFAULT_CPU)
        agent_memory = self.get_optional_config('AgentMemory', DEFAULT_MEMORY)
        agent_desired_count = self.get_optional_config('AgentDesiredCount', DEFAULT_DESIRED_COUNT)
        
        # Determine container image path, port, and dockerfile path based on agent name
        container_image_path = self._get_agent_image_path(agent_name)
        container_port = self._get_agent_port(agent_name)
        dockerfile_path = self._get_agent_dockerfile_path(agent_name)

        # Create environment variables for agent configuration using CloudFormation parameter
        environment_vars = self._get_agent_environment_vars(conf)
        
        # Create the agent service using ALB-VPC Lattice hybrid approach for extended timeout
        # This places ALB between VPC Lattice and ECS tasks to solve the 60-second timeout limitation
        # Use generic name for CDK construct IDs to make CloudFormation template reusable
        # CloudFormation parameter is used for actual AWS resource names and environment variables
        resources = self.create_alb_vpc_lattice_fargate_service(
            service_name="agent",  # Use static name for CDK construct IDs
            container_image_path=container_image_path,
            port=container_port,
            health_check_path=AGENT_HEALTH_CHECK_PATH,
            cpu=agent_cpu,
            memory=agent_memory,
            desired_count=agent_desired_count,
            environment_vars=environment_vars,
            platform=ecr_assets.Platform.LINUX_ARM64,
            dockerfile_path=dockerfile_path,
            vpc_lattice_service_name=self.agent_name_parameter.value_as_string  # Pass parameter for VPC Lattice service name
        )
        
        # Add Bedrock AgentCore Memory permissions to agent task definition
        self._add_bedrock_agentcore_memory_permissions(resources["task_definition"])
        
        # Apply agent service permissions boundary to task role
        self._apply_agent_service_permissions_boundary(resources["task_definition"])

        # Export the service properties for compatibility with existing code
        self.agent_fargate_service = resources["ecs_service"]
        self.agent_lattice_service = resources["service"]
        self.agent_lattice_target_group = resources["lattice_target_group"]  # VPC Lattice target group
        self.agent_alb_target_group = resources["target_group"]  # ALB target group (new)
        self.agent_load_balancer = resources["load_balancer"]  # ALB load balancer (new)
        self.agent_lattice_service_arn = resources["service"].attr_arn
        self.agent_fargate_service_arn = resources["ecs_service"].service_arn
        
        # Override ManagedBy tag to allow Configuration API deletion
        # This allows the Configuration API to delete these stacks via its IAM policy
        cdk.Tags.of(self).add("ManagedBy", "ConfigurationAPI", priority=300)
        
        # Note: CloudFormation output is created by base class _create_service_output method
    
    def _get_agent_image_path(self, agent_name: str) -> str:
        """
        Get the container image path based on agent name using constants.
        All agent instances use the same unified image path except supervisor.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Path to the container image
        """
        if agent_name == "agent-supervisor":
            return AGENT_SUPERVISOR_IMAGE_PATH
        else:
            # All other agents use the unified agent-instance image
            return AGENT_INSTANCE_IMAGE_PATH
    
    def _get_agent_port(self, agent_name: str) -> int:
        """
        Get the container port based on agent name using constants.
        All agent instances use the same unified port except supervisor.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Port number for the agent
        """
        if agent_name == "agent-supervisor":
            return AGENT_SUPERVISOR_PORT
        else:
            # All other agents use the unified port (8080)
            return AGENT_PORT
    
    def _get_agent_dockerfile_path(self, agent_name: str) -> str:
        """
        Get the dockerfile path based on agent name.
        All agent instances use the same unified dockerfile except supervisor.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Path to the Dockerfile relative to the build context
        """
        if agent_name == "agent-supervisor":
            return AGENT_SUPERVISOR_DOCKERFILE_PATH
        else:
            # All other agents use the unified agent-instance dockerfile
            return AGENT_INSTANCE_DOCKERFILE_PATH
    
    def _get_agent_environment_vars(self, conf: Config) -> Dict[str, str]:
        """
        Get environment variables for agent configuration.
        Sets AGENT_NAME using CloudFormation parameter and injects model configuration from config file.
        HOSTED_DNS is handled by base class _add_container_to_task(),
        and AGENT_DESCRIPTION is loaded from SSM parameters.
            
        Returns:
            Dictionary of environment variables for the agent
        """
        # Use CloudFormation parameter reference for AGENT_NAME
        # Base class will automatically set HOSTED_DNS via _add_container_to_task()
        # SSM parameters will provide AGENT_DESCRIPTION
        
        # Get project name for runtime use by components like memory and observability
        project_name = conf.get('ProjectName')
        
        # Environment variables required for agent runtime
        # These match docker-compose.yml configuration for consistency
        env_vars = {
            "AGENT_NAME": self.agent_name_parameter.value_as_string,
            "PROJECT_NAME": project_name,  # Critical for runtime components
            "AWS_REGION": self.region,
            "HOST": "0.0.0.0",  # nosec: B104 # Required for container networking - agent must bind to all interfaces
            "PYTHONPATH": "/app:/app/common"  # Required for Python imports - matches docker-compose
        }
        
        return env_vars
    
    def _add_bedrock_agentcore_memory_permissions(self, task_definition: ecs.FargateTaskDefinition) -> None:
        """
        Add Bedrock AgentCore Memory permissions for memory provider functionality.
        
        Based on AWS Service Authorization Reference for Amazon Bedrock AgentCore:
        https://docs.aws.amazon.com/service-authorization/latest/reference/list_amazonbedrockagentcore.html
        
        Args:
            task_definition: The ECS task definition to add permissions to
        """
        from aws_cdk import aws_iam as iam
        
        # Bedrock AgentCore Memory resource management permissions using CDK tokens
        bedrock_agentcore_memory_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # Memory resource management
                "bedrock-agentcore:CreateMemory",
                "bedrock-agentcore:DeleteMemory", 
                "bedrock-agentcore:GetMemory",
                "bedrock-agentcore:ListMemories",
                "bedrock-agentcore:UpdateMemory",
                
                # Memory event management
                "bedrock-agentcore:CreateEvent",
                "bedrock-agentcore:DeleteEvent",
                "bedrock-agentcore:GetEvent", 
                "bedrock-agentcore:ListEvents",
                
                # Memory record management
                "bedrock-agentcore:DeleteMemoryRecord",
                "bedrock-agentcore:GetMemoryRecord",
                "bedrock-agentcore:ListMemoryRecords",
                "bedrock-agentcore:RetrieveMemoryRecords",
                
                # Memory session and actor management
                "bedrock-agentcore:ListActors",
                "bedrock-agentcore:ListSessions",
                
                # Memory retrieval operations
                "bedrock-agentcore:RetrieveMemories"
            ],
            resources=[
                # Memory resources using CDK tokens for portability
                f"arn:aws:bedrock-agentcore:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:memory/*",
                f"arn:aws:bedrock-agentcore:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:memory-strategy/*"
            ]
        )
        
        # Bedrock AgentCore workload identity permissions using CDK tokens
        bedrock_agentcore_workload_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock-agentcore:GetWorkloadAccessToken",
                "bedrock-agentcore:GetWorkloadAccessTokenForJWT", 
                "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
            ],
            resources=[
                f"arn:aws:bedrock-agentcore:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:workload-identity-directory/default",
                f"arn:aws:bedrock-agentcore:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:workload-identity-directory/default/workload-identity/*"
            ]
        )
        
        # Bedrock model invocation permissions using CDK tokens
        bedrock_agentcore_model_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            resources=[
                # Foundation models using CDK tokens for region portability
                f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/amazon.titan-embed-text-v1",
                f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/amazon.titan-embed-text-v2",
                f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/cohere.embed-*",
                f"arn:aws:bedrock:{cdk.Aws.REGION}::foundation-model/amazon.titan-text-*"
            ]
        )
        
        # Add all policies to the task role
        task_definition.task_role.add_to_policy(bedrock_agentcore_memory_policy)
        task_definition.task_role.add_to_policy(bedrock_agentcore_workload_policy)
        task_definition.task_role.add_to_policy(bedrock_agentcore_model_policy)
        
        # Add the managed policy for Bedrock AgentCore Memory
        task_definition.task_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockAgentCoreMemoryBedrockModelInferenceExecutionRolePolicy")
        )
    
    def _apply_agent_service_permissions_boundary(self, task_definition: ecs.FargateTaskDefinition) -> None:
        """
        Apply agent service permissions boundary to task role.
        
        Args:
            task_definition: The ECS task definition with role to apply boundary to
        """
        try:
            # Import agent service boundary policy ARN from IAM boundaries stack
            boundary_arn = cdk.Fn.import_value(f"{self.config._environment}-AgentServiceBoundaryArn")
            
            # Apply boundary to the task role
            self.apply_permissions_boundary(task_definition.task_role, boundary_arn)
            
        except Exception as e:
            # Log warning but don't fail deployment if boundary import fails
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to apply agent service permissions boundary: {str(e)}")
