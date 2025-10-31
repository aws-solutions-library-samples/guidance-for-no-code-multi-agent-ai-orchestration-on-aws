"""
Template Storage Stack.

Creates S3 bucket for storing CloudFormation templates that are used
by the Configuration API to deploy agent stacks dynamically.
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_iam as iam,
    aws_s3_deployment as s3_deployment,
)
from constructs import Construct


class TemplateStorageStack(Stack):
    """Stack for CloudFormation template storage."""
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        **kwargs
    ) -> None:
        """
        Initialize Template Storage Stack.
        
        Args:
            scope: CDK scope
            construct_id: Stack ID
            project_name: Project name for resource naming
            **kwargs: Additional stack arguments
        """
        super().__init__(scope, construct_id, **kwargs)
        
        # Create S3 bucket for CloudFormation templates
        self.template_bucket = s3.Bucket(
            self,
            "TemplateBucket",
            bucket_name=f"{project_name}-templates-{self.account}-{self.region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,  # Delete bucket on stack destroy
            auto_delete_objects=True,  # Automatically delete all objects before bucket deletion
            enforce_ssl=True,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="DeleteOldVersions",
                    noncurrent_version_expiration=Duration.days(30),
                    enabled=True
                )
            ]
        )
        
        # Deploy generated CloudFormation template from CDK output directory to S3
        # This automatically uploads the GenericAgentTemplate.json after synthesis
        # Get the CDK output directory dynamically from the app
        app = self.node.root
        outdir = app.outdir if hasattr(app, 'outdir') else 'cdk.out'
        
        s3_deployment.BucketDeployment(
            self,
            "TemplateDeployment",
            sources=[s3_deployment.Source.asset(outdir, exclude=["**", "!GenericAgentTemplate.json"])],
            destination_bucket=self.template_bucket,
            prune=False,  # Keep old versions for rollback capability
            retain_on_delete=False,  # Delete templates when stack is destroyed
        )
        
        # Grant read access to Configuration API task role (will be added later)
        # This is a placeholder - actual permissions added in Configuration API stack
        
    def grant_read_access(self, grantee: iam.IGrantable) -> None:
        """
        Grant read access to the template bucket.
        
        Args:
            grantee: IAM role or principal to grant access to
        """
        self.template_bucket.grant_read(grantee)
