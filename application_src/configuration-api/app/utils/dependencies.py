"""
Dependency injection setup for FastAPI.

This module provides dependency injection functions for services,
following the dependency inversion principle for better testability.
"""

import os
from functools import lru_cache

from ..services import SSMService, DiscoveryService, AgentConfigService
from ..services.deployment_service import DeploymentService
from ..services.cloudformation_deployment_service import CloudFormationDeploymentService


@lru_cache()
def get_aws_region() -> str:
    """
    Get AWS region from environment variables.
    
    Returns:
        AWS region name
    """
    return os.environ.get('AWS_REGION', 'us-east-1')


@lru_cache()
def get_ssm_service() -> SSMService:
    """
    Get SSM service instance.
    
    Returns:
        Configured SSM service instance
    """
    return SSMService(region_name=get_aws_region())


@lru_cache()
def get_discovery_service() -> DiscoveryService:
    """
    Get Discovery service instance.
    
    Returns:
        Configured Discovery service instance
    """
    return DiscoveryService(region_name=get_aws_region())


@lru_cache()
def get_agent_config_service() -> AgentConfigService:
    """
    Get Agent Configuration service instance.
    
    Returns:
        Configured Agent Configuration service instance
    """
    ssm_service = get_ssm_service()
    return AgentConfigService(ssm_service=ssm_service)


@lru_cache()
def get_deployment_service() -> DeploymentService:
    """
    Get Deployment service instance.
    
    Returns:
        Configured Deployment service instance
    """
    return DeploymentService()


@lru_cache()
def get_cloudformation_deployment_service() -> CloudFormationDeploymentService:
    """
    Get CloudFormation Deployment service instance.
    
    Returns:
        Configured CloudFormation Deployment service instance
    """
    region = os.environ.get('AWS_REGION', 'us-east-1')
    # Use ai-platform as project name to match CDK stack naming convention
    project_name = os.environ.get('PROJECT_NAME', 'ai-platform')
    template_bucket = os.environ.get('S3_TEMPLATE_BUCKET')

    if not template_bucket:
        raise ValueError("S3_TEMPLATE_BUCKET environment variable is required")
    
    return CloudFormationDeploymentService(
        region=region,
        project_name=project_name,
        template_bucket=template_bucket
    )
