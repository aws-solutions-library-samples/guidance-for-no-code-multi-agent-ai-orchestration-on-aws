#!/usr/bin/env python3
"""
CDK app for generating agent template without deployment.
This app synthesizes the MultiAgentStack as a standalone CloudFormation template
and prepares it for upload to S3 during deployment.

The Docker image build is now handled by TemplateStorageStack during deployment,
following the same pattern as template upload to S3.

This runs as a pre-hook before 'cdk deploy' to ensure the template
is always up-to-date with the stack definition.
"""
import os
import json
import boto3
import sys
import logging
from aws_cdk import App, Fn, Environment
from stacks.multi_agent.stack import MultiAgentStack
from helper.config import Config

logger = logging.getLogger(__name__)


def main():
    """Generate the template and save to file."""
    logger.info("Generating agent template...")
    
    # Get actual AWS account and region
    try:
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
    except Exception:
        account_id = os.environ.get("CDK_DEFAULT_ACCOUNT", "123456789012")
    
    region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
    
    # Create app
    app = App()
    
    # Get configuration
    environment = app.node.try_get_context("environment") or os.environ.get("ENVIRONMENT", "development")
    conf = Config(environment=environment)
    
    # Get project name from config (should match app.py)
    project_name_from_config = conf.get('ProjectName')
    
    logger.info("Using CloudFormation exports from VPC stack...")
    
    # Import VPC ID using CloudFormation export token
    # The MultiAgentStack will handle importing the VPC and all related resources
    vpc_id_token = Fn.import_value(f"{project_name_from_config}-VpcId")
    
    # Import cluster name using CloudFormation export
    cluster_name_token = Fn.import_value(f"{project_name_from_config}-ClusterName")
    
    # Import access log bucket name using CloudFormation export
    bucket_name_token = Fn.import_value(f"{project_name_from_config}-AccessLogBucketName")
    
    # Import VPC Lattice service network ARN using CloudFormation export
    service_network_arn = Fn.import_value(f"{project_name_from_config}-vpc:ExportsOutputFnGetAttservicenetworkArnD9BDB9C7")
    
    logger.info("All infrastructure references use CloudFormation imports")
    logger.debug(f"  - VPC ID: {{Fn::ImportValue: {project_name_from_config}-VpcId}}")
    logger.debug(f"  - Cluster: {{Fn::ImportValue: {project_name_from_config}-ClusterName}}")
    logger.debug(f"  - Bucket: {{Fn::ImportValue: {project_name_from_config}-AccessLogBucketName}}")
    
    # Create the agent stack - MultiAgentStack will import all resources internally
    # Pass tokens directly - no boto3 queries needed!
    agent_stack = MultiAgentStack(
        app,
        "GenericAgentTemplate",
        vpc_id=vpc_id_token,  # MultiAgentStack imports VPC from this token
        access_log_bucket_name=bucket_name_token,  # Pass bucket name token for import
        service_network_arn=service_network_arn,
        cluster=None,  # Will be imported inside MultiAgentStack
        cluster_name=cluster_name_token,  # Pass cluster name token
        agent_name="generic-agent",
        conf=conf,
        env=Environment(account=account_id, region=region),
    )
    
    # Synthesize
    assembly = app.synth()
    
    # Get the template from cloud assembly
    template_artifact = assembly.get_stack_by_name(agent_stack.stack_name)
    template_path = template_artifact.template_full_path
    
    if os.path.exists(template_path):
        # Read the template with proper encoding
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = json.load(f)
        
        # Log that template uses ImageTag parameter (will be updated by TemplateStorageStack)
        logger.info("Template uses ImageTag parameter (default will be updated during deployment)")
        
        # Save to standard location for easy access
        output_path = "cdk.out/GenericAgentTemplate.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(template_content, f, indent=2)
        
        logger.info(f"Template generated: {output_path}")
        logger.debug(f"  Stack name: {agent_stack.stack_name}")
        logger.debug(f"  Template size: {len(json.dumps(template_content))} bytes")
        
        # List resources for reference
        if 'Resources' in template_content:
            resource_count = len(template_content['Resources'])
            resource_types = {}
            for resource in template_content['Resources'].values():
                rtype = resource.get('Type', 'Unknown')
                resource_types[rtype] = resource_types.get(rtype, 0) + 1
            
            logger.debug(f"  Total resources: {resource_count}")
            logger.debug("  Resource breakdown:")
            for rtype, count in sorted(resource_types.items()):
                logger.debug(f"    - {rtype}: {count}")
        
        logger.info("Template and Docker image will be deployed by TemplateStorageStack")
        logger.debug("  - Template: Uploaded to S3 during deployment")
        logger.debug("  - Docker Image: Built and pushed to ECR during deployment")
        
        return True
    else:
        logger.error(f"Template not found at {template_path}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
