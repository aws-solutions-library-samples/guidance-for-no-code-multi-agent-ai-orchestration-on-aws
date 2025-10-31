"""IAM policy mixin for CDK stacks."""

from typing import List, Optional

import aws_cdk
from aws_cdk import aws_iam as iam


class IAMPolicyMixin:
    """
    Mixin class providing common IAM policy functionality.
    
    This mixin provides reusable methods for adding common IAM permissions
    to roles, following the principle of least privilege.
    """
    
    def add_bedrock_permissions(self, role: iam.Role, 
                                model_arns: List[str] = None) -> None:
        """
        Add Bedrock permissions to a role, including inference profiles for cross-region support.
        
        Args:
            role: The IAM role to add permissions to
            model_arns: Optional list of specific model ARNs to restrict access
        """
        resources = model_arns if model_arns else ["*"]
        
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=resources,
            actions=[
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ListFoundationModels",
                "bedrock:GetFoundationModel",
                # Add inference profile permissions for cross-region model discovery
                "bedrock:ListInferenceProfiles",
                "bedrock:GetInferenceProfile"
            ]
        ))
    
    def add_ssm_permissions(self, role: iam.Role, 
                           parameter_arns: List[str] = None,
                           kms_key_arn: str = None,
                           allow_write: bool = False,
                           allow_delete: bool = False) -> None:
        """
        Add scoped SSM Parameter Store permissions to a role with SecureString support.
        
        This method now applies least-privilege access by default:
        - Read-only access by default (allow_write=False, allow_delete=False)
        - Scoped to project parameters when parameter_arns not provided
        - Explicit opt-in required for write and delete operations
        
        Args:
            role: The IAM role to add permissions to
            parameter_arns: Optional list of specific parameter ARNs. If not provided,
                          defaults to project-scoped parameters (/{ProjectName}/*)
            kms_key_arn: KMS key ARN for SecureString parameter encryption/decryption
            allow_write: Whether to allow PutParameter and tag operations (default: False)
            allow_delete: Whether to allow DeleteParameter operations (default: False)
        """
        # Default to project-scoped parameters if not specified
        if parameter_arns is None:
            # SECURITY: Require ProjectName for scoping - no fallback to wildcard
            # This enforces least-privilege access and prevents accidental overly-broad permissions
            project_name = self.get_required_config('ProjectName')
            # Allow access to:
            # 1. Project infrastructure parameters (/{ProjectName}/*)
            # 2. Agent configuration parameters (/agent/*)
            # 3. CDK bootstrap parameters (/cdk-bootstrap/*) - Required for CloudFormation operations
            # 4. Prompt library parameters (/prompts/*) - For system prompt templates
            # 5. Global system parameters (/system/*) - For global template library
            resources = [
                f"arn:aws:ssm:{aws_cdk.Aws.REGION}:{aws_cdk.Aws.ACCOUNT_ID}:parameter/{project_name}/*",
                f"arn:aws:ssm:{aws_cdk.Aws.REGION}:{aws_cdk.Aws.ACCOUNT_ID}:parameter/agent/*",
                f"arn:aws:ssm:{aws_cdk.Aws.REGION}:{aws_cdk.Aws.ACCOUNT_ID}:parameter/cdk-bootstrap/*",
                f"arn:aws:ssm:{aws_cdk.Aws.REGION}:{aws_cdk.Aws.ACCOUNT_ID}:parameter/prompts/*",
                f"arn:aws:ssm:{aws_cdk.Aws.REGION}:{aws_cdk.Aws.ACCOUNT_ID}:parameter/system/*"
            ]
        else:
            resources = parameter_arns
        
        # Core SSM read permissions for SecureString parameters (scoped to resources)
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=resources,
            actions=[
                "ssm:GetParameter",
                "ssm:GetParameters",
                "ssm:GetParametersByPath"
            ]
        ))
        
        # DescribeParameters requires * resource per AWS API design
        # This is a read-only list operation similar to ECS ListServices
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=["*"],
            actions=[
                "ssm:DescribeParameters"
            ]
        ))
        
        # KMS permissions for SecureString parameter decryption
        if kms_key_arn:
            role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=[kms_key_arn],
                actions=[
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:GenerateDataKey"
                ],
                conditions={
                    "StringEquals": {
                        "kms:ViaService": f"ssm.{aws_cdk.Aws.REGION}.amazonaws.com"
                    }
                }
            ))
        else:
            # If no specific KMS key provided, allow access to default SSM key
            role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=[f"arn:aws:kms:{aws_cdk.Aws.REGION}:{aws_cdk.Aws.ACCOUNT_ID}:key/*"],
                actions=[
                    "kms:Decrypt",
                    "kms:DescribeKey"
                ],
                conditions={
                    "StringEquals": {
                        "kms:ViaService": f"ssm.{aws_cdk.Aws.REGION}.amazonaws.com"
                    }
                }
            ))
        
        # Optional write permissions (explicit opt-in required)
        if allow_write:
            role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=resources,
                actions=[
                    "ssm:PutParameter",
                    "ssm:AddTagsToResource",
                    "ssm:RemoveTagsFromResource"
                ]
            ))
            
            # KMS permissions for parameter creation/updates
            if kms_key_arn:
                role.add_to_policy(iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    resources=[kms_key_arn],
                    actions=[
                        "kms:Encrypt",
                        "kms:GenerateDataKey"
                    ]
                ))
        
        # Optional delete permissions (explicit opt-in required)
        if allow_delete:
            role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=resources,
                actions=[
                    "ssm:DeleteParameter",
                    "ssm:DeleteParameters"
                ]
            ))
    
    def add_logs_permissions(self, role: iam.Role, 
                            log_group_arns: List[str]) -> None:
        """
        Add CloudWatch Logs permissions to a role, including VPC Lattice access logging.
        
        Args:
            role: The IAM role to add permissions to
            log_group_arns: List of log group ARNs to grant access to
        """
        from aws_cdk import Aws
        
        # Permissions for writing to specific log groups
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=log_group_arns,
            actions=[
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "logs:DescribeLogStreams"
            ]
        ))
        
        # Permission to create log groups (if they don't exist)
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=["*"],
            actions=[
                "logs:CreateLogGroup",
                "logs:DescribeLogGroups"
            ]
        ))
        
        # Additional permissions for VPC Lattice access logging to CloudWatch
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=[
                f"arn:aws:logs:*:*:log-group:/aws/vpclattice/*:*"
            ],
            actions=[
                "logs:CreateLogStream",
                "logs:PutLogEvents",
                "logs:DescribeLogStreams",
                "logs:DescribeLogGroups"
            ]
        ))
    
    def add_vpc_lattice_permissions(self, role: iam.Role,
                                   target_group_arns: List[str] = None) -> None:
        """
        Add VPC Lattice permissions to a role.
        
        Args:
            role: The IAM role to add permissions to
            target_group_arns: Optional list of target group ARNs to restrict access
        """
        # Basic VPC Lattice permissions
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=["*"],
            actions=[
                "vpc-lattice:GetService",
                "vpc-lattice:ListServices",
                "vpc-lattice:GetServiceNetwork",
                "vpc-lattice:ListServiceNetworks",
                "vpc-lattice:ListServiceNetworkServiceAssociations",
                "vpc-lattice:GetListener",
                "vpc-lattice:ListListeners"
            ]
        ))
        
        # Target-specific permissions
        resources = target_group_arns if target_group_arns else ["*"]
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=resources,
            actions=[
                "vpc-lattice:RegisterTargets",
                "vpc-lattice:DeregisterTargets",
                "vpc-lattice:GetTargetGroup",
                "vpc-lattice:ListTargets",
                "vpc-lattice:GetTargetGroupHealth"
            ]
        ))
    
    def add_ecs_task_permissions(self, role: iam.Role) -> None:
        """
        Add ECS task execution permissions to a role.
        
        Args:
            role: The IAM role to add permissions to
        """
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=["*"],
            actions=[
                "ecs:DescribeServices",
                "ecs:DescribeTasks",
                "ecs:ListTasks",
                "ecs:DescribeTaskDefinition"
            ]
        ))
    
    def add_ecr_permissions(self, role: iam.Role, 
                           repository_arns: List[str] = None) -> None:
        """
        Add ECR (Elastic Container Registry) permissions to a role.
        
        Args:
            role: The IAM role to add permissions to
            repository_arns: Optional list of repository ARNs to restrict access
        """
        # ECR token permissions (always needed)
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=["*"],
            actions=[
                "ecr:GetAuthorizationToken"
            ]
        ))
        
        # Repository-specific permissions
        resources = repository_arns if repository_arns else ["*"]
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=resources,
            actions=[
                "ecr:BatchCheckLayerAvailability",
                "ecr:GetDownloadUrlForLayer",
                "ecr:BatchGetImage",
                "ecr:DescribeRepositories",
                "ecr:DescribeImages"
            ]
        ))
    
    def add_ec2_network_permissions(self, role: iam.Role,
                                   vpc_arns: List[str] = None) -> None:
        """
        Add EC2 network-related permissions to a role.
        
        Args:
            role: The IAM role to add permissions to
            vpc_arns: Optional list of VPC ARNs to restrict access
        """
        resources = vpc_arns if vpc_arns else ["*"]
        
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=resources,
            actions=[
                "ec2:DescribeNetworkInterfaces",
                "ec2:DescribeSubnets",
                "ec2:DescribeVpcs",
                "ec2:DescribeSecurityGroups"
            ]
        ))
    
    def add_rds_data_permissions(self, role: iam.Role, 
                                cluster_arns: List[str] = None) -> None:
        """
        Add RDS Data API permissions to a role for Aurora Serverless database access.
        
        Args:
            role: The IAM role to add permissions to
            cluster_arns: Optional list of specific Aurora cluster ARNs to restrict access
        """
        resources = cluster_arns if cluster_arns else ["*"]
        
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=resources,
            actions=[
                "rds-data:*"
            ]
        ))
    
    def add_secrets_manager_permissions(self, role: iam.Role,
                                      secret_arns: List[str] = None) -> None:
        """
        Add AWS Secrets Manager permissions to a role for retrieving database credentials.
        
        Args:
            role: The IAM role to add permissions to
            secret_arns: Optional list of specific secret ARNs to restrict access
        """
        resources = secret_arns if secret_arns else ["*"]
        
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=resources,
            actions=[
                "secretsmanager:GetSecretValue",
                "secretsmanager:DescribeSecret"
            ]
        ))
    
    def create_task_execution_role(self, role_name: str) -> iam.Role:
        """
        Create a standard ECS task execution role with common permissions.
        
        Args:
            role_name: Name for the IAM role
            
        Returns:
            The created IAM role
        """
        role = iam.Role(
            self,
            f"{role_name}-execution-role",
            role_name=f"{role_name}-execution-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description=f"ECS task execution role for {role_name}",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ]
        )
        
        return role
    
    def add_dynamodb_read_permissions(self, role: iam.Role,
                                     table_arns: List[str] = None) -> None:
        """
        Add DynamoDB read permissions to a role.
        
        Args:
            role: The IAM role to add permissions to
            table_arns: Optional list of specific table ARNs to restrict access
        """
        resources = table_arns if table_arns else ["*"]
        
        role.add_to_policy(iam.PolicyStatement(
            effect=iam.Effect.ALLOW,
            resources=resources,
            actions=[
                "dynamodb:GetItem",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:BatchGetItem",
                "dynamodb:DescribeTable",
                "dynamodb:ListTables"
            ]
        ))
        
        # If specific table ARNs are provided, also allow index access
        if table_arns:
            index_arns = [f"{table_arn}/index/*" for table_arn in table_arns]
            role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=index_arns,
                actions=[
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ]
            ))
    
    def add_s3_read_permissions(self, role: iam.Role,
                               bucket_arns: List[str] = None) -> None:
        """
        Add S3 read permissions to a role.
        
        Args:
            role: The IAM role to add permissions to
            bucket_arns: Optional list of specific bucket ARNs to restrict access
        """
        if bucket_arns:
            # Permissions for specific buckets
            role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=bucket_arns,
                actions=[
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                    "s3:GetBucketVersioning"
                ]
            ))
            
            # Permissions for objects in specific buckets
            object_arns = [f"{bucket_arn}/*" for bucket_arn in bucket_arns]
            role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=object_arns,
                actions=[
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:GetObjectVersionTagging",
                    "s3:GetObjectTagging"
                ]
            ))
        else:
            # General S3 read permissions for all buckets
            role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["*"],
                actions=[
                    "s3:ListAllMyBuckets",
                    "s3:ListBucket",
                    "s3:GetBucketLocation"
                ]
            ))
            
            # General S3 object read permissions
            role.add_to_policy(iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                resources=["arn:aws:s3:::*/*"],
                actions=[
                    "s3:GetObject",
                    "s3:GetObjectVersion",
                    "s3:GetObjectVersionTagging",
                    "s3:GetObjectTagging"
                ]
            ))

    def create_task_role(self, role_name: str, permissions_boundary_arn: str = None) -> iam.Role:
        """
        Create a standard ECS task role with optional permissions boundary.
        
        Args:
            role_name: Name for the IAM role
            permissions_boundary_arn: Optional ARN of permissions boundary policy
            
        Returns:
            The created IAM role
        """
        role_props = {
            "role_name": f"{role_name}-task-role",
            "assumed_by": iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            "description": f"ECS task role for {role_name}"
        }
        
        # Apply permissions boundary if provided
        if permissions_boundary_arn:
            role_props["permissions_boundary"] = iam.ManagedPolicy.from_managed_policy_arn(
                self, f"{role_name}-boundary-ref", permissions_boundary_arn
            )
        
        role = iam.Role(
            self,
            f"{role_name}-task-role",
            **role_props
        )
        
        return role
    
    def create_role_with_boundary(self, 
                                  role_name: str,
                                  assumed_by: iam.IPrincipal,
                                  permissions_boundary_arn: str,
                                  description: str = None) -> iam.Role:
        """
        Create an IAM role with permissions boundary applied.
        
        Args:
            role_name: Name for the IAM role
            assumed_by: Principal that can assume this role
            permissions_boundary_arn: ARN of permissions boundary policy
            description: Optional description for the role
            
        Returns:
            The created IAM role with boundary applied
        """
        role = iam.Role(
            self,
            f"{role_name}-role",
            role_name=f"{role_name}-role",
            assumed_by=assumed_by,
            description=description or f"IAM role for {role_name} with permissions boundary",
            permissions_boundary=iam.ManagedPolicy.from_managed_policy_arn(
                self, f"{role_name}-boundary-policy-ref", permissions_boundary_arn
            )
        )
        
        return role
    
    def apply_permissions_boundary(self, role: iam.Role, permissions_boundary_arn: str) -> None:
        """
        Apply permissions boundary to an existing IAM role.
        
        Args:
            role: The IAM role to apply boundary to
            permissions_boundary_arn: ARN of permissions boundary policy
        """
        # Get the underlying CfnRole to set the permissions boundary
        cfn_role = role.node.default_child
        if isinstance(cfn_role, iam.CfnRole):
            # Reference the boundary policy by ARN
            boundary_policy = iam.ManagedPolicy.from_managed_policy_arn(
                role, f"{role.role_name}-boundary-ref", permissions_boundary_arn
            )
            cfn_role.permissions_boundary = boundary_policy.managed_policy_arn
        else:
            raise ValueError(f"Expected CfnRole, got {type(cfn_role)}")
    
    def get_boundary_policy_arn_from_import(self, export_name: str) -> str:
        """
        Get permissions boundary policy ARN from CloudFormation import.
        
        Args:
            export_name: CloudFormation export name for the boundary policy ARN
            
        Returns:
            ARN of the boundary policy
        """
        return aws_cdk.Fn.import_value(export_name)
