"""KMS Stack for SSM Parameter Store encryption."""

import aws_cdk as cdk
import aws_cdk.aws_kms as kms
import aws_cdk.aws_iam as iam
from constructs import Construct
from helper.config import Config
from stacks.common.base import BaseStack


class KMSStack(BaseStack):
    """Stack for creating KMS keys used across the application."""
    
    def __init__(self, scope: Construct, construct_id: str, config: Config, **kwargs) -> None:
        # Add solution ID and description
        kwargs['description'] = "KMS encryption keys for SSM Parameter Store and secure data protection - (Solution ID - SO9637)"
        super().__init__(scope, construct_id, config, **kwargs)
        
        # Create KMS key for SSM Parameter Store encryption
        self.ssm_parameter_key = kms.Key(
            self, "SSMParameterKey",
            description="Customer managed key for SSM Parameter Store encryption",
            enable_key_rotation=True,
            key_spec=kms.KeySpec.SYMMETRIC_DEFAULT,
            key_usage=kms.KeyUsage.ENCRYPT_DECRYPT,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            policy=self._create_ssm_key_policy()
        )
        
        # Create alias for easier identification
        # Use config environment instead of self.environment to avoid invalid characters
        environment_name = self.config._environment or "development"
        self.ssm_parameter_key_alias = kms.Alias(
            self, "SSMParameterKeyAlias",
            alias_name=f"alias/{environment_name}-ssm-parameters",
            target_key=self.ssm_parameter_key
        )
        
        # Stack outputs using ProjectName for consistent naming
        # No export_name to avoid import/export dependencies - use direct stack references instead
        project_name = self.get_required_config('ProjectName')
        cdk.CfnOutput(
            self, "SSMParameterKeyId",
            value=self.ssm_parameter_key.key_id,
            description="KMS Key ID for SSM parameter encryption"
        )
        
        cdk.CfnOutput(
            self, "SSMParameterKeyArn", 
            value=self.ssm_parameter_key.key_arn,
            description="KMS Key ARN for SSM parameter encryption"
        )
        
        cdk.CfnOutput(
            self, "SSMParameterKeyAliasName",
            value=self.ssm_parameter_key_alias.alias_name,
            description="KMS Key Alias name for SSM parameter encryption"
        )
    
    def _create_ssm_key_policy(self) -> iam.PolicyDocument:
        """Create the KMS key policy for SSM Parameter Store access."""
        
        # Root account has full access (required for key management)
        root_statement = iam.PolicyStatement(
            sid="EnableRootAccess",
            effect=iam.Effect.ALLOW,
            principals=[iam.AccountRootPrincipal()],
            actions=["kms:*"],
            resources=["*"]
        )
        
        # Allow SSM service to use the key
        ssm_service_statement = iam.PolicyStatement(
            sid="AllowSSMService",
            effect=iam.Effect.ALLOW,
            principals=[iam.ServicePrincipal("ssm.amazonaws.com")],
            actions=[
                "kms:Encrypt",
                "kms:Decrypt",
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey"
            ],
            resources=["*"]
        )
        
        # Allow ECS tasks and Lambda functions to decrypt parameters
        application_decrypt_statement = iam.PolicyStatement(
            sid="AllowApplicationDecrypt",
            effect=iam.Effect.ALLOW,
            principals=[
                iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
                iam.ServicePrincipal("lambda.amazonaws.com")
            ],
            actions=[
                "kms:Decrypt",
                "kms:DescribeKey",
                "kms:GenerateDataKey"
            ],
            resources=["*"],
            conditions={
                "StringEquals": {
                    "kms:ViaService": f"ssm.{cdk.Aws.REGION}.amazonaws.com"
                }
            }
        )
        
        # Allow CloudFormation to manage the key during stack operations
        cloudformation_statement = iam.PolicyStatement(
            sid="AllowCloudFormation",
            effect=iam.Effect.ALLOW,
            principals=[iam.ServicePrincipal("cloudformation.amazonaws.com")],
            actions=[
                "kms:Encrypt",
                "kms:Decrypt", 
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:DescribeKey"
            ],
            resources=["*"]
        )
        
        return iam.PolicyDocument(
            statements=[
                root_statement,
                ssm_service_statement,
                application_decrypt_statement,
                cloudformation_statement
            ]
        )
