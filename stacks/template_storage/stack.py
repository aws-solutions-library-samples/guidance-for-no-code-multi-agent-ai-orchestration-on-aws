"""
Template Storage Stack.

Creates S3 bucket for storing CloudFormation templates that are used
by the Configuration API to deploy agent stacks dynamically.

Also manages the Docker image asset for the generic agent, ensuring both
the template and the Docker image follow the same deployment pattern.
"""

import json
import logging
import os
from datetime import datetime, timezone

from aws_cdk import (
    Stack,
    RemovalPolicy,
    Duration,
    aws_s3 as s3,
    aws_iam as iam,
    aws_s3_deployment as s3_deployment,
    aws_ecr_assets as ecr_assets,
    aws_ssm as ssm,
)
from constructs import Construct

logger = logging.getLogger(__name__)


class TemplateStorageStack(Stack):
    """Stack for CloudFormation template storage and agent image management."""
    
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        build_agent_image: bool = True,
        **kwargs
    ) -> None:
        """
        Initialize Template Storage Stack.
        
        Args:
            scope: CDK scope
            construct_id: Stack ID
            project_name: Project name for resource naming
            build_agent_image: Whether to build and push agent Docker image
            **kwargs: Additional stack arguments
        """
        # Add solution ID and description
        kwargs['description'] = "S3 bucket for storing CloudFormation templates used for dynamic agent deployment - (Solution ID - SO9637)"
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
        
        # Build and push agent Docker image during deployment (if enabled)
        if build_agent_image:
            # Create the Docker image asset - CDK will build and push to bootstrap ECR repo with SHA256 hash
            self.agent_image_asset = self._create_agent_image_asset()
            
            # Get the ACTUAL CDK-generated image URI including:
            # - Bootstrap ECR repository (cdk-hnb659fds-container-assets-ACCOUNT-REGION)
            # - SHA256 hash tag (e.g., 9f846af5ece47ba5acecb3e381d65441b31f7f0fbd03f513e4f9aabd427c8659)
            # This ensures each rebuild gets a unique hash, forcing ECS to pull the new image
            docker_image_uri = self.agent_image_asset.image_uri
            
            logger.info(f"Docker image will be deployed to: {docker_image_uri}")
            
            # Store image URI in SSM Parameter Store for runtime use by Configuration API
            # The deployment service will retrieve this at runtime, so we don't need to modify templates
            ssm.StringParameter(
                self,
                "agent-image-uri-parameter",
                parameter_name=f"/{project_name}/agent/image-uri",
                string_value=docker_image_uri,
                description="Docker image URI for agent containers (includes content hash for versioning)",
                tier=ssm.ParameterTier.STANDARD
            )
        
        # Deploy CloudFormation template to S3 (unmodified)
        # The deployment service retrieves the image URI from SSM at runtime
        self._deploy_template()
    
    def _deploy_template(self) -> s3_deployment.BucketDeployment:
        """
        Deploy the unmodified CloudFormation template to S3.
        
        The deployment service retrieves the actual image URI from SSM at runtime,
        so we don't need to modify the template's ImageTag default value.
        
        Returns:
            BucketDeployment for the template
        """
        # Get template path from CDK output directory
        app = self.node.root
        outdir = app.outdir if hasattr(app, 'outdir') else 'cdk.out'
        
        logger.info(f"Deploying CloudFormation template from: {outdir}")
        
        # Deploy unmodified template to S3
        return s3_deployment.BucketDeployment(
            self,
            "TemplateDeployment",
            sources=[s3_deployment.Source.asset(outdir, exclude=["*", "!GenericAgentTemplate.json"])],
            destination_bucket=self.template_bucket,
            prune=False,  # Don't delete other objects in bucket
            retain_on_delete=False  # Clean up on stack deletion
        )
        
    def _create_agent_image_asset(self) -> ecr_assets.DockerImageAsset:
        """
        Create Docker image asset for the generic agent.
        
        CDK builds the image and pushes it to the bootstrap ECR repository
        (cdk-hnb659fds-container-assets-ACCOUNT-REGION) with a SHA256 content hash as the tag.
        
        This SHA256 hash changes with every code change, ensuring:
        - Each rebuild gets a unique image identifier
        - ECS tasks are forced to pull the new image on stack updates
        - No manual tagging or versioning needed
        
        Returns:
            DockerImageAsset for the agent image with CDK-generated SHA256 tag
        """
        return ecr_assets.DockerImageAsset(
            self,
            "AgentImageAsset",
            directory="application_src",
            file="multi-agent/agent-instance/Dockerfile",
            platform=ecr_assets.Platform.LINUX_ARM64,
            build_args={
                "BUILD_TARGET": "production"
            },
            target="production"
            # No explicit asset_name needed - CDK will use content hash
        )
    
    
    def grant_read_access(self, grantee: iam.IGrantable) -> None:
        """
        Grant read access to the template bucket.
        
        Args:
            grantee: IAM role or principal to grant access to
        """
        self.template_bucket.grant_read(grantee)
