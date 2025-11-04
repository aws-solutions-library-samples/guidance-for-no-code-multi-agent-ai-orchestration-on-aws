import aws_cdk as cdk
from constructs import Construct
from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_ecr_assets as ecr_assets
)

from helper.config import Config
from stacks.common.base import FargateServiceStack
from stacks.common.mixins import LoadBalancerLoggingMixin
from stacks.common.constants import (
    API_PORT,
    API_HEALTH_CHECK_PATH,
    DEFAULT_CPU,
    DEFAULT_MEMORY,
    DEFAULT_DESIRED_COUNT,
    DEFAULT_API_SERVICE_SUFFIX,
    CONFIGURATION_API_IMAGE_PATH
)


class ConfigurationApiStack(FargateServiceStack, LoadBalancerLoggingMixin):
    """
    Configuration API Stack for deploying the configuration API service on ECS Fargate with Application Load Balancer.
    
    This stack creates a containerized configuration API service that can be accessed via an Application Load Balancer
    for efficient external and internal communication.
    """

    def __init__(self, 
                 scope: Construct, 
                 construct_id: str,
                 vpc: ec2.Vpc,
                 cluster: ecs.Cluster,
                 service_network_arn: str,
                 access_logs_bucket: s3.Bucket,
                 cognito_resources,  # CognitoResources from authentication stack
                 template_bucket: s3.IBucket,  # S3 bucket for CloudFormation templates
                 conf: Config,
                 **kwargs) -> None:
        # Add solution ID and description
        kwargs['description'] = "Configuration API service for managing multi-agent AI deployments and configurations - (Solution ID - SO9637)"
        # Pass service_network_arn for environment variable but use ALB for access
        super().__init__(scope, construct_id, vpc, cluster, service_network_arn, conf, **kwargs)
        
        # Store dependencies for use in configuration
        self.access_logs_bucket = access_logs_bucket
        self.cognito_resources = cognito_resources
        self.template_bucket = template_bucket

        # Get configuration values
        project_name = self.get_required_config('ProjectName')
        api_service_name = f"{project_name}-{DEFAULT_API_SERVICE_SUFFIX}"
        api_cpu = self.get_optional_config('ApiCPU', DEFAULT_CPU)
        api_memory = self.get_optional_config('ApiMemory', DEFAULT_MEMORY)
        api_desired_count = self.get_optional_config('ApiDesiredCount', DEFAULT_DESIRED_COUNT)
        
        # Environment variables for the API service
        api_environment_vars = {
            'VPC_LATTICE_SERVICE_NETWORK_ARN': service_network_arn,
            'AWS_REGION': self.region,
            'PROJECT_NAME': project_name,  # Add project name for deployment service
            'S3_TEMPLATE_BUCKET': template_bucket.bucket_name,  # S3 bucket for CloudFormation templates
            
            # Authentication configuration - use Cognito secret from authentication stack
            'SECRETS_MANAGER_ARN': cognito_resources.secret_arn,
            'AUTH_PROVIDER_TYPE': 'cognito',
            
            # Model configuration environment variables (used when helper module not available)
            'GENERIC_AGENT_MODEL_ID': self.get_optional_config('GenericAgentModelId', 'us.amazon.nova-lite-v1:0'),
            'GENERIC_AGENT_JUDGE_MODEL_ID': self.get_optional_config('GenericAgentJudgeModelId', ''),
            'GENERIC_AGENT_EMBEDDING_MODEL_ID': self.get_optional_config('GenericAgentEmbeddingModelId', 'amazon.titan-embed-text-v2:0'),
            'GENERIC_AGENT_TEMPERATURE': str(self.get_optional_config('GenericAgentTemperature', 0.3)),
            'GENERIC_AGENT_TOP_P': str(self.get_optional_config('GenericAgentTopP', 0.8)),
            'SUPERVISOR_MODEL_ID': self.get_optional_config('SupervisorModelId', 'us.anthropic.claude-opus-4-1-20250805-v1:0'),
            'SUPERVISOR_JUDGE_MODEL_ID': self.get_optional_config('SupervisorJudgeModelId', 'us.anthropic.claude-opus-4-1-20250805-v1:0'),
            'SUPERVISOR_EMBEDDING_MODEL_ID': self.get_optional_config('SupervisorEmbeddingModelId', 'amazon.titan-embed-text-v2:0'),
            'SUPERVISOR_TEMPERATURE': str(self.get_optional_config('SupervisorTemperature', 0.7)),
            'SUPERVISOR_TOP_P': str(self.get_optional_config('SupervisorTopP', 0.9))
        }
        
        # Create the configuration API service with native blue-green ALB deployment
        # ✅ HYBRID APPROACH: Shared context with .dockerignore optimization
        resources = self.create_blue_green_alb_fargate_service(
            service_name=api_service_name,
            container_image_path=CONFIGURATION_API_IMAGE_PATH,  # Shared context with optimized .dockerignore
            port=API_PORT,
            health_check_path=API_HEALTH_CHECK_PATH,
            cpu=api_cpu,
            memory=api_memory,
            desired_count=api_desired_count,
            environment_vars=api_environment_vars,
            platform=ecr_assets.Platform.LINUX_ARM64,
            dockerfile_path="configuration-api/Dockerfile"  # ✅ RESTORED: Shared context path
        )

        # Configure ALB logging using the mixin with AWS documentation best practices
        # This ensures proper region-aware service account permissions and consistent naming
        self.configure_alb_logging(
            load_balancer=resources["load_balancer"],
            access_logs_bucket=self.access_logs_bucket,
            prefix="config-api-alb"
        )

        # Add CloudFormation permissions for dynamic agent deployment
        self._add_cloudformation_permissions(resources["task_definition"])
        
        # Grant read/write access to template bucket for CloudFormation deployments
        # Write access needed for app-template-generator.py to upload templates
        # Read access needed for CloudFormation service to download templates
        template_bucket.grant_read_write(resources["task_definition"].task_role)
        
        # Add Cognito User Pool permissions for role management
        self._add_authentication_permissions(resources["task_definition"])
        
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
        
        # Apply configuration API permissions boundary to task role
        self._apply_configuration_api_permissions_boundary(resources["task_definition"])

        # Export the service properties for compatibility with existing code
        self.api_fargate_service = resources["ecs_service"]
        self.load_balancer = resources["load_balancer"]
        self.target_group = resources["target_groups"]["primary"]  # Use primary target group for blue-green
        self.alb_dns_name = resources["load_balancer"].load_balancer_dns_name

        # Create a compatibility object to maintain interface with UI stack
        class CompatibilityLoadBalancer:
            def __init__(self, dns_name):
                self._dns_name = dns_name
            
            @property
            def load_balancer_dns_name(self):
                return self._dns_name

        # Provide backwards compatibility for UI stack
        self.api_fargate_service.load_balancer = CompatibilityLoadBalancer(
            self.alb_dns_name
        )
        
        # Maintain legacy property name for backwards compatibility
        self.genai_box_api_fargate_service = self.api_fargate_service

    def _configure_alb_task_permissions(self, task_definition: ecs.FargateTaskDefinition, log_group_arns: list) -> None:
        """
        Override the base class method to exclude inline VPC Lattice permissions.
        We only want the VPCLatticeFullAccess managed policy, not additional inline permissions.
        
        Configuration API requires write and delete permissions for managing agent configurations.
        """
        from aws_cdk import aws_iam as iam
        
        # Get KMS key ARN using direct reference instead of import/export  
        kms_key_arn = self._get_kms_key_arn()
        
        # Add standard permissions (excluding VPC Lattice inline permissions)
        self.add_bedrock_permissions(task_definition.task_role)
        # Configuration API needs write and delete permissions for agent configuration management
        self.add_ssm_permissions(
            task_definition.task_role, 
            kms_key_arn=kms_key_arn,
            allow_write=True,
            allow_delete=True
        )
        self.add_logs_permissions(task_definition.task_role, log_group_arns)
        # Removed: self.add_vpc_lattice_permissions(task_definition.task_role)  # Skip inline VPC Lattice permissions
        self.add_ecs_task_permissions(task_definition.task_role)
        self.add_ecr_permissions(task_definition.task_role)
        self.add_ec2_network_permissions(task_definition.task_role)

    def _add_cloudformation_permissions(self, task_definition: ecs.FargateTaskDefinition) -> None:
        """
        Add CloudFormation permissions for dynamic agent stack deployment.
        
        This grants the Configuration API service the permissions needed to:
        - Read existing CloudFormation templates
        - Create new stacks with modified parameters
        - Monitor stack status and outputs
        - Delete stacks
        - Manage IAM roles and policies for created stacks
        
        Args:
            task_definition: The ECS task definition to add permissions to
        """
        from aws_cdk import aws_iam as iam
        
        # Get project name for resource patterns
        project_name = self.get_required_config('ProjectName')
        
        # CloudFormation read permissions (no tag restrictions for read operations)
        cloudformation_read_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # Read operations - allow on all stacks for template retrieval
                "cloudformation:DescribeStacks",
                "cloudformation:DescribeStackEvents",
                "cloudformation:DescribeStackResources", 
                "cloudformation:ListStackResources",
                "cloudformation:GetTemplate",
                "cloudformation:ValidateTemplate",
                "cloudformation:ListStackSets",
                "cloudformation:DescribeStackSet",
                "cloudformation:DescribeChangeSet",
                "cloudformation:ListChangeSets"
            ],
            resources=[
                # Use CDK tokens for portable deployment across regions/accounts
                f"arn:aws:cloudformation:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:stack/{project_name}-*/*",
                f"arn:aws:cloudformation:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:stackset/{project_name}-*"
            ]
        )
        
        # CloudFormation list operations (require * resource access)
        cloudformation_list_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # List operations need access to all stacks to enumerate them
                "cloudformation:ListStacks"
            ],
            resources=["*"]  # ListStacks requires access to all stacks
        )
        
        # CloudFormation create permissions (no tag restrictions since stack doesn't exist yet)
        cloudformation_create_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "cloudformation:CreateStack",
                "cloudformation:CreateChangeSet",
                "cloudformation:ValidateTemplate"
            ],
            resources=[
                # Use CDK tokens for portable deployment across regions/accounts
                f"arn:aws:cloudformation:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:stack/{project_name}-*/*"
            ]
        )
        
        # CloudFormation modify permissions (with tag restrictions for existing stacks)  
        cloudformation_modify_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "cloudformation:UpdateStack", 
                "cloudformation:DeleteStack",
                "cloudformation:ExecuteChangeSet",
                "cloudformation:DeleteChangeSet"
            ],
            resources=[
                f"arn:aws:cloudformation:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:stack/{project_name}-*/*"
            ],
            conditions={
                "StringEquals": {
                    "cloudformation:ResourceTag/ManagedBy": "ConfigurationAPI"
                }
            }
        )
        
        # IAM permissions for managing roles and policies in created stacks
        iam_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # Role operations
                "iam:CreateRole",
                "iam:DeleteRole",
                "iam:GetRole",
                "iam:ListRoles",
                "iam:PassRole",
                "iam:UpdateRole",
                "iam:TagRole",
                "iam:UntagRole",
                "iam:ListRoleTags",
                
                # Policy operations
                "iam:AttachRolePolicy",
                "iam:DetachRolePolicy",
                "iam:CreatePolicy",
                "iam:DeletePolicy",
                "iam:GetPolicy",
                "iam:GetPolicyVersion",
                "iam:ListPolicies",
                "iam:ListPolicyVersions",
                "iam:ListAttachedRolePolicies",
                "iam:ListRolePolicies",
                "iam:PutRolePolicy",
                "iam:DeleteRolePolicy",
                "iam:GetRolePolicy"
            ],
            resources=[
                # Use CDK tokens for portable deployment across accounts
                f"arn:aws:iam::{cdk.Aws.ACCOUNT_ID}:role/{project_name}-*",
                f"arn:aws:iam::{cdk.Aws.ACCOUNT_ID}:policy/{project_name}-*"
            ]
        )
        
        # ECS service operations (scoped to project resources)
        ecs_service_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ecs:CreateService",
                "ecs:UpdateService",
                "ecs:DeleteService",
                "ecs:DescribeServices"
            ],
            resources=[
                # Services in the cluster with project name prefix AND agent services
                f"arn:aws:ecs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:service/{self.cluster.cluster_name}/{project_name}-*",
                f"arn:aws:ecs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:service/{self.cluster.cluster_name}/agent-*"
            ]
        )
        
        # ECS task definition register/describe operations (scoped to project resources)
        ecs_task_def_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ecs:RegisterTaskDefinition",
                "ecs:DescribeTaskDefinition"
            ],
            resources=[
                # Task definitions with project name prefix AND agent task definitions
                f"arn:aws:ecs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:task-definition/{project_name}-*:*",
                f"arn:aws:ecs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:task-definition/agent-*:*"
            ]
        )
        
        # ECS task definition deregister operation (requires * resource per AWS API)
        ecs_deregister_task_def_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ecs:DeregisterTaskDefinition"
            ],
            resources=["*"]  # DeregisterTaskDefinition requires * per AWS API
        )
        
        # ECS cluster operations (scoped to specific cluster)
        ecs_cluster_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ecs:DescribeClusters"
            ],
            resources=[
                # Only the cluster being used
                self.cluster.cluster_arn
            ]
        )
        
        # ECS tagging operations (scoped to project resources)
        ecs_tagging_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ecs:TagResource",
                "ecs:UntagResource",
                "ecs:ListTagsForResource"
            ],
            resources=[
                # Services and task definitions with project name prefix AND agent resources
                f"arn:aws:ecs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:service/{self.cluster.cluster_name}/{project_name}-*",
                f"arn:aws:ecs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:service/{self.cluster.cluster_name}/agent-*",
                f"arn:aws:ecs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:task-definition/{project_name}-*:*",
                f"arn:aws:ecs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:task-definition/agent-*:*"
            ]
        )
        
        # ECS list operations (require * resource per AWS API requirements)
        ecs_list_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "ecs:ListServices",
                "ecs:ListTaskDefinitions",
                "ecs:ListClusters"
            ],
            resources=["*"]  # List operations require * per AWS API
        )
        
        
        # CloudWatch Logs permissions for stack logging (broader access for resource policies)
        logs_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "logs:CreateLogGroup",
                "logs:DeleteLogGroup",
                "logs:DescribeLogGroups",
                "logs:ListTagsLogGroup",
                "logs:TagLogGroup",
                "logs:UntagLogGroup",
                "logs:PutRetentionPolicy",
                "logs:DeleteRetentionPolicy"
            ],
            resources=[
                # Use CDK tokens for portable deployment - Standard AWS service log groups
                f"arn:aws:logs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:log-group:/aws/ecs/{project_name}-*",
                f"arn:aws:logs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:log-group:/aws/vpclattice/{project_name}-*",
                # Agent stack log groups (can have various naming patterns)
                f"arn:aws:logs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:log-group:{project_name}-*",
                # Log streams within those log groups
                f"arn:aws:logs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:log-group:{project_name}-*:log-stream:*"
            ]
        )
        
        # CloudWatch Logs resource policy permissions (requires broader resource access)
        logs_resource_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "logs:PutResourcePolicy",
                "logs:DeleteResourcePolicy",
                "logs:DescribeResourcePolicies"
            ],
            resources=["*"]  # Resource policies require broad access
        )
        
        # CloudWatch Logs tagging permissions (requires broader resource access)
        logs_tagging_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "logs:TagResource",
                "logs:UntagResource"
            ],
            resources=[
                f"arn:aws:logs:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:*"
            ]
        )
        
        # EC2 permissions for networking (VPC, subnets, security groups)
        ec2_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # Security group operations
                "ec2:CreateSecurityGroup",
                "ec2:DeleteSecurityGroup",
                "ec2:DescribeSecurityGroups",
                "ec2:AuthorizeSecurityGroupIngress",
                "ec2:AuthorizeSecurityGroupEgress",
                "ec2:RevokeSecurityGroupIngress",
                "ec2:RevokeSecurityGroupEgress",
                "ec2:CreateTags",
                "ec2:DeleteTags",
                
                # Network interface operations (for ECS tasks)
                "ec2:CreateNetworkInterface",
                "ec2:DeleteNetworkInterface",
                "ec2:DescribeNetworkInterfaces",
                "ec2:AttachNetworkInterface",
                "ec2:DetachNetworkInterface",
                
                # VPC and subnet operations (read-only)
                "ec2:DescribeVpcs",
                "ec2:DescribeSubnets",
                "ec2:DescribeAvailabilityZones"
            ],
            resources=["*"]
        )
        
        # VPC Lattice access log permissions (additional to managed policy)
        vpc_lattice_access_logs_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "vpc-lattice:CreateAccessLogSubscription",
                "vpc-lattice:DeleteAccessLogSubscription",
                "vpc-lattice:GetAccessLogSubscription",
                "vpc-lattice:ListAccessLogSubscriptions",
                "vpc-lattice:UpdateAccessLogSubscription"
            ],
            resources=["*"]  # VPC Lattice access logs require * resource
        )
        
        # ELB load balancer operations (scoped to VPC)
        elb_loadbalancer_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "elasticloadbalancing:CreateLoadBalancer",
                "elasticloadbalancing:ModifyLoadBalancerAttributes",
                "elasticloadbalancing:SetLoadBalancerPoliciesOfListener"
            ],
            resources=[
                f"arn:aws:elasticloadbalancing:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:loadbalancer/app/*"
            ],
            conditions={
                "StringEquals": {
                    "aws:RequestedRegion": cdk.Aws.REGION,
                    "elasticloadbalancing:ResourceTag/ManagedBy": "ConfigurationAPI"
                }
            }
        )
        
        # ELB delete operations (scoped with tag condition on existing resources)
        elb_delete_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "elasticloadbalancing:DeleteLoadBalancer"
            ],
            resources=[
                f"arn:aws:elasticloadbalancing:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:loadbalancer/app/*"
            ],
            conditions={
                "StringEquals": {
                    "elasticloadbalancing:ResourceTag/ManagedBy": "ConfigurationAPI"
                }
            }
        )
        
        # ELB target group operations (scoped to VPC)
        elb_targetgroup_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "elasticloadbalancing:CreateTargetGroup",
                "elasticloadbalancing:ModifyTargetGroup",
                "elasticloadbalancing:ModifyTargetGroupAttributes",
                "elasticloadbalancing:RegisterTargets",
                "elasticloadbalancing:DeregisterTargets"
            ],
            resources=[
                f"arn:aws:elasticloadbalancing:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:targetgroup/*"
            ],
            conditions={
                "StringEquals": {
                    "aws:RequestedRegion": cdk.Aws.REGION,
                    "elasticloadbalancing:ResourceTag/ManagedBy": "ConfigurationAPI"
                }
            }
        )
        
        # ELB delete target group (scoped with tag condition)
        elb_delete_targetgroup_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "elasticloadbalancing:DeleteTargetGroup"
            ],
            resources=[
                f"arn:aws:elasticloadbalancing:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:targetgroup/*"
            ],
            conditions={
                "StringEquals": {
                    "elasticloadbalancing:ResourceTag/ManagedBy": "ConfigurationAPI"
                }
            }
        )
        
        # ELB listener operations (CreateListener requires load balancer resource)
        elb_listener_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "elasticloadbalancing:CreateListener",
                "elasticloadbalancing:DeleteListener",
                "elasticloadbalancing:ModifyListener",
                "elasticloadbalancing:CreateRule",
                "elasticloadbalancing:DeleteRule",
                "elasticloadbalancing:ModifyRule"
            ],
            resources=[
                f"arn:aws:elasticloadbalancing:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:loadbalancer/app/*",
                f"arn:aws:elasticloadbalancing:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:listener/app/*",
                f"arn:aws:elasticloadbalancing:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:listener-rule/app/*"
            ]
        )
        
        # ELB describe operations (require * resource per AWS API)
        elb_describe_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "elasticloadbalancing:DescribeLoadBalancers",
                "elasticloadbalancing:DescribeTargetGroups",
                "elasticloadbalancing:DescribeTargetHealth",
                "elasticloadbalancing:DescribeListeners",
                "elasticloadbalancing:DescribeRules",
                "elasticloadbalancing:DescribeTags"
            ],
            resources=["*"]  # Describe operations require * per AWS API
        )
        
        # ELB tagging operations (scoped to region and tagged resources)
        elb_tagging_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                "elasticloadbalancing:AddTags",
                "elasticloadbalancing:RemoveTags"
            ],
            resources=[
                f"arn:aws:elasticloadbalancing:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:loadbalancer/app/*",
                f"arn:aws:elasticloadbalancing:{cdk.Aws.REGION}:{cdk.Aws.ACCOUNT_ID}:targetgroup/*"
            ],
            conditions={
                "StringEquals": {
                    "elasticloadbalancing:ResourceTag/ManagedBy": "ConfigurationAPI"
                }
            }
        )
        
        # Add all policies to the task role
        task_definition.task_role.add_to_policy(cloudformation_read_policy)
        task_definition.task_role.add_to_policy(cloudformation_list_policy)
        task_definition.task_role.add_to_policy(cloudformation_create_policy)
        task_definition.task_role.add_to_policy(cloudformation_modify_policy)
        task_definition.task_role.add_to_policy(iam_policy)
        # Add scoped ECS policies
        task_definition.task_role.add_to_policy(ecs_service_policy)
        task_definition.task_role.add_to_policy(ecs_task_def_policy)
        task_definition.task_role.add_to_policy(ecs_deregister_task_def_policy)
        task_definition.task_role.add_to_policy(ecs_cluster_policy)
        task_definition.task_role.add_to_policy(ecs_tagging_policy)
        task_definition.task_role.add_to_policy(ecs_list_policy)
        task_definition.task_role.add_to_policy(logs_policy)
        task_definition.task_role.add_to_policy(logs_resource_policy)
        task_definition.task_role.add_to_policy(logs_tagging_policy)
        task_definition.task_role.add_to_policy(ec2_policy)
        task_definition.task_role.add_to_policy(vpc_lattice_access_logs_policy)
        # Add scoped ELB policies
        task_definition.task_role.add_to_policy(elb_loadbalancer_policy)
        task_definition.task_role.add_to_policy(elb_delete_policy)
        task_definition.task_role.add_to_policy(elb_targetgroup_policy)
        task_definition.task_role.add_to_policy(elb_delete_targetgroup_policy)
        task_definition.task_role.add_to_policy(elb_listener_policy)
        task_definition.task_role.add_to_policy(elb_describe_policy)
        task_definition.task_role.add_to_policy(elb_tagging_policy)
        task_definition.task_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("VPCLatticeFullAccess")
        )
    
    def _apply_configuration_api_permissions_boundary(self, task_definition: ecs.FargateTaskDefinition) -> None:
        """
        Apply configuration API permissions boundary to task role.
        
        Args:
            task_definition: The ECS task definition with role to apply boundary to
        """
        try:
            # Import configuration API boundary policy ARN from IAM boundaries stack
            boundary_arn = cdk.Fn.import_value(f"{self.config._environment}-ConfigurationApiBoundaryArn")
            
            # Apply boundary to the task role
            self.apply_permissions_boundary(task_definition.task_role, boundary_arn)
            
        except Exception as e:
            # Log warning but don't fail deployment if boundary import fails
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to apply configuration API permissions boundary: {str(e)}")

    def _auto_discover_auth_secret(self, auth_provider_type: str) -> str:
        """
        Automatically discover authentication secret based on provider type.
        
        For Cognito, use the configurable project name pattern that matches the Cognito mixin.
        
        Args:
            auth_provider_type: The authentication provider type from config
            
        Returns:
            str: Secret name for authentication configuration
        """
        project_name = self.get_required_config('ProjectName')
        
        if auth_provider_type == 'cognito':
            # Use configurable project name pattern
            # This matches the secret created by CognitoMixin
            return f"{project_name}-cognito-secret"
                
        elif auth_provider_type == 'okta':
            # Auto-discover Okta secret using standard naming pattern
            return f"OktaSecret-{self.config._environment}"
            
        elif auth_provider_type == 'ping':
            # Auto-discover Ping secret using standard naming pattern  
            return f"PingSecret-{self.config._environment}"
            
        elif auth_provider_type == 'auth0':
            # Auto-discover Auth0 secret using standard naming pattern
            return f"Auth0Secret-{self.config._environment}"
            
        else:
            raise ValueError(f"Unsupported auth provider type: {auth_provider_type}")

    def _add_authentication_permissions(self, task_definition: ecs.FargateTaskDefinition) -> None:
        """
        Add Cognito User Pool permissions for role management.
        
        The Configuration API needs these permissions to dynamically create and manage
        user groups for role-based access control.
        
        Args:
            task_definition: ECS task definition to grant permissions to
        """
        from aws_cdk import aws_iam as iam
        
        # Cognito User Pool permissions for role management
        cognito_policy = iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            actions=[
                # User Pool Group operations for role management
                "cognito-idp:CreateGroup",
                "cognito-idp:UpdateGroup", 
                "cognito-idp:DeleteGroup",
                "cognito-idp:GetGroup",
                "cognito-idp:ListGroups",
                
                # User group membership operations
                "cognito-idp:AdminAddUserToGroup",
                "cognito-idp:AdminRemoveUserFromGroup", 
                "cognito-idp:AdminListGroupsForUser",
                "cognito-idp:ListUsersInGroup",
                
                # User operations for authentication
                "cognito-idp:AdminGetUser",
                "cognito-idp:AdminInitiateAuth",
                "cognito-idp:AdminUserGlobalSignOut"
            ],
            resources=[
                # Access the Cognito User Pool from authentication stack
                self.cognito_resources.user_pool.user_pool_arn
            ]
        )
        
        task_definition.task_role.add_to_policy(cognito_policy)
