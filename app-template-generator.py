#!/usr/bin/env python3
"""
CDK app for generating agent template without deployment.
This app synthesizes the MultiAgentStack as a standalone CloudFormation template,
builds and pushes the Docker image to ECR, and uploads everything to S3.

This runs as a pre-hook before 'cdk deploy' to ensure the template
is always up-to-date with the stack definition and available in S3.
"""
import os
import json
import boto3
import sys
import shlex
import subprocess
from aws_cdk import App, Fn, Environment, Stack
from aws_cdk import aws_ec2 as ec2, aws_ecs as ecs, aws_s3 as s3, aws_ecr_assets as ecr_assets
from stacks.multi_agent.stack import MultiAgentStack
from helper.config import Config


def build_and_push_agent_image(app: App, account_id: str, region: str) -> str:
    """
    Build and push the agent Docker image to ECR using direct Docker commands.
    
    Args:
        app: CDK app instance  
        account_id: AWS account ID
        region: AWS region
        
    Returns:
        ECR image URI with stable tag
    """
    print("\n🐳 Building and pushing agent Docker image to ECR...")
    
    import hashlib
    
    # Use stable tag based on directory content hash
    ecr_repo = f"{account_id}.dkr.ecr.{region}.amazonaws.com/cdk-hnb659fds-container-assets-{account_id}-{region}"
    stable_tag = "agent-instance-latest"
    image_uri = f"{ecr_repo}:{stable_tag}"
    
    # Check if Docker/Podman is available - use safe validated default
    docker_executable = os.environ.get('CDK_DOCKER', 'docker')
    
    # SECURITY: Validate docker executable to prevent command injection
    allowed_executables = ['docker', 'podman']
    if docker_executable not in allowed_executables:
        raise ValueError(f"Invalid container runtime specified: {docker_executable}. Allowed: {allowed_executables}")
    
    try:
        # 1. Login to ECR - separate password retrieval and login for security
        print(f"  Logging in to ECR...")
        
        # Get ECR password securely - validate region parameter
        if not region or not region.replace('-', '').replace('_', '').isalnum():
            raise ValueError(f"Invalid AWS region: {region}")
            
        password_result = subprocess.run(
            ['aws', 'ecr', 'get-login-password', '--region', region],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Login to ECR with password from stdin - validate parameters
        if not account_id or not account_id.isdigit() or len(account_id) != 12:
            raise ValueError(f"Invalid AWS account ID: {account_id}")
            
        ecr_endpoint = f"{account_id}.dkr.ecr.{region}.amazonaws.com"
            
        subprocess.run(
            [docker_executable, 'login', '--username', 'AWS', '--password-stdin', ecr_endpoint],
            input=password_result.stdout,
            check=True,
            capture_output=True,
            text=True
        )
        
        # 2. Build image - validate parameters
        print(f"  Building Docker image...")
        if not image_uri or '://' in image_uri.split(':')[0]:  # Basic URI validation
            raise ValueError(f"Invalid image URI: {image_uri}")
            
        subprocess.run(
            [docker_executable, 'build',
             '-t', image_uri,
             '--platform', 'linux/arm64',
             '-f', 'application_src/multi-agent/agent-instance/Dockerfile',
             'application_src'],
            check=True,
            capture_output=True
        )
        
        # 3. Push to ECR
        print(f"  Pushing image to ECR...")
        subprocess.run(
            [docker_executable, 'push', image_uri],
            check=True,
            capture_output=True
        )
        
        print(f"✓ Docker image built and pushed to ECR: {image_uri}")
        return image_uri
        
    except subprocess.CalledProcessError as e:
        print(f"⚠️  Warning: Failed to build/push Docker image: {e}")
        print(f"  Using placeholder - manual push required")
        return image_uri




def main():
    """Generate the template and save to file."""
    # Get actual AWS account and region
    try:
        sts = boto3.client('sts')
        account_id = sts.get_caller_identity()['Account']
    except Exception:
        account_id = os.environ.get("CDK_DEFAULT_ACCOUNT", "123456789012")
    
    region = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
    
    # Create app
    app = App()
    
    # Step 1: Build and push Docker image to ECR BEFORE creating the stack
    # This ensures the image exists in ECR before the CloudFormation template references it
    agent_image_uri = build_and_push_agent_image(app, account_id, region)
    
    # Get configuration
    environment = app.node.try_get_context("environment") or os.environ.get("ENVIRONMENT", "development")
    conf = Config(environment=environment)
    
    # Get project name from config (should match app.py)
    project_name_from_config = conf.get('ProjectName')
    
    print(f"\n📦 Using CloudFormation exports from VPC stack...")
    
    # Import VPC ID using CloudFormation export token
    # The MultiAgentStack will handle importing the VPC and all related resources
    vpc_id_token = Fn.import_value(f"{project_name_from_config}-VpcId")
    
    # Import cluster name using CloudFormation export
    cluster_name_token = Fn.import_value(f"{project_name_from_config}-ClusterName")
    
    # Import access log bucket name using CloudFormation export
    bucket_name_token = Fn.import_value(f"{project_name_from_config}-AccessLogBucketName")
    
    # Import VPC Lattice service network ARN using CloudFormation export
    service_network_arn = Fn.import_value(f"{project_name_from_config}-vpc:ExportsOutputFnGetAttservicenetworkArnD9BDB9C7")
    
    print(f"✓ All infrastructure references use CloudFormation imports")
    print(f"  - VPC ID: {{Fn::ImportValue: {project_name_from_config}-VpcId}}")
    print(f"  - Cluster: {{Fn::ImportValue: {project_name_from_config}-ClusterName}}")
    print(f"  - Bucket: {{Fn::ImportValue: {project_name_from_config}-AccessLogBucketName}}")
    
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
        
        # Replace Docker image reference with stable tag
        task_def = template_content['Resources']['agenttaskdefinitionF56FAA50']
        container = task_def['Properties']['ContainerDefinitions'][0]
        
        # Update image to use stable tag
        container['Image'] = {
            'Fn::Sub': f"{account_id}.dkr.ecr.{region}.${{AWS::URLSuffix}}/cdk-hnb659fds-container-assets-{account_id}-{region}:agent-instance-latest"
        }
        
        print(f"✓ Updated template to use stable Docker image tag: agent-instance-latest")
        
        # Save to standard location for easy access
        output_path = "cdk.out/GenericAgentTemplate.json"
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(template_content, f, indent=2)
        
        print(f"✓ Template generated: {output_path}")
        print(f"  Stack name: {agent_stack.stack_name}")
        print(f"  Template size: {len(json.dumps(template_content))} bytes")
        
        # List resources for reference
        if 'Resources' in template_content:
            resource_count = len(template_content['Resources'])
            resource_types = {}
            for resource in template_content['Resources'].values():
                rtype = resource.get('Type', 'Unknown')
                resource_types[rtype] = resource_types.get(rtype, 0) + 1
            
            print(f"  Total resources: {resource_count}")
            print(f"  Resource breakdown:")
            for rtype, count in sorted(resource_types.items()):
                print(f"    - {rtype}: {count}")
        
        # Note: Template will be automatically uploaded to S3 by TemplateStorageStack
        # using CDK's BucketDeployment construct during 'cdk deploy'
        print(f"\n📤 Template will be uploaded to S3 by TemplateStorageStack during deployment")
        
        return True
    else:
        print(f"Error: Template not found at {template_path}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
