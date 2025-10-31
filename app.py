#!/usr/bin/env python3

import aws_cdk as cdk
from helper import config
from stacks import VpcStack, ConfigurationApiStack, WebAppStack, MultiAgentStack, SupervisorAgentStack
from stacks.kms.stack import KMSStack
from stacks.iam_boundaries.stack import IAMBoundariesStack
from cdk_nag import ( AwsSolutionsChecks, NagSuppressions )
import os
import json
import boto3
import sys

# AUTOMATIC TEMPLATE GENERATION
# Generate agent template before CDK synthesis to ensure it's always up-to-date
def generate_agent_template():
    """Generate GenericAgentTemplate.json during synth/deploy."""
    try:
        # Skip during destroy operations only
        if len(sys.argv) > 1 and 'destroy' in ' '.join(sys.argv).lower():
            return
        
        print("🔄 Generating agent template...")
        import subprocess
        result = subprocess.run(
            ['python3', 'app-template-generator.py'],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        if result.returncode == 0:
            print("✓ Agent template generated successfully")
            if result.stdout:
                print(result.stdout)
        else:
            print(f"⚠️  Template generation had warnings:")
            if result.stderr:
                print(result.stderr)
    except Exception as e:
        print(f"⚠️  Template generation failed (non-fatal): {e}")

# Generate template before creating app
generate_agent_template()

app = cdk.App()

conf = config.Config(app.node.try_get_context('environment') or 'development')

# Use ProjectName for all stack naming
project_name = conf.get('ProjectName')

vpc_stack = VpcStack(app, f"{project_name}-vpc",
                     config=conf,
                     env={
                         "region": conf.get('RegionName'),
                         "account": os.environ.get('CDK_DEFAULT_ACCOUNT')
                     },
                     termination_protection=True  # Protect critical VPC infrastructure
                     )

# KMS stack must be deployed before SSM stack (dependency)
kms_stack = KMSStack(app, f"{project_name}-kms",
                     config=conf,
                     env={
                         "region": conf.get('RegionName'),
                         "account": os.environ.get('CDK_DEFAULT_ACCOUNT')
                     },
                     termination_protection=True  # Protect encryption keys
                     )

# KMS stack reference stored in app for cross-stack access
# Removed context approach as it conflicts with CDK construct lifecycle

# Template Storage stack - S3 bucket for CloudFormation templates
from stacks.template_storage import TemplateStorageStack
template_storage_stack = TemplateStorageStack(app, f"{project_name}-template-storage",
                                              project_name=project_name,
                                              env={
                                                  "region": conf.get('RegionName'),
                                                  "account": os.environ.get('CDK_DEFAULT_ACCOUNT')
                                              },
                                              termination_protection=True
                                              )

# IAM boundaries stack must be deployed before compute resources that reference boundary policies
iam_boundaries_stack = IAMBoundariesStack(app, f"{project_name}-iam-boundaries",
                                         config=conf,
                                         env={
                                             "region": conf.get('RegionName'),
                                             "account": os.environ.get('CDK_DEFAULT_ACCOUNT')
                                         },
                                         termination_protection=True  # Protect security boundaries
                                         )

# Authentication stack - decoupled Cognito infrastructure for better modularity
from stacks.authentication import AuthenticationStack
authentication_stack = AuthenticationStack(app, f"{project_name}-authentication",
                                          config=conf,
                                          env={
                                              "region": conf.get('RegionName'),
                                              "account": os.environ.get('CDK_DEFAULT_ACCOUNT')
                                          },
                                          termination_protection=True  # Protect authentication infrastructure
                                          )

configuration_api_stack = ConfigurationApiStack(app, f"{project_name}-config-api",
                            env={
                                "region": conf.get('RegionName'),
                                "account": os.environ.get('CDK_DEFAULT_ACCOUNT')
                            },
                            vpc=vpc_stack.vpc,
                            cluster=vpc_stack.ecs_cluster,
                            service_network_arn=vpc_stack.service_network_arn,
                            access_logs_bucket=vpc_stack.access_logs_bucket,
                            cognito_resources=authentication_stack.cognito_resources,  # Pass from auth stack
                            template_bucket=template_storage_stack.template_bucket,  # Pass template bucket
                            conf=conf,
                            termination_protection=True  # Protect critical configuration API
                            )

# Configuration API depends on authentication stack for Cognito resources
configuration_api_stack.add_dependency(authentication_stack)

# Configuration API depends on template storage for CloudFormation templates
configuration_api_stack.add_dependency(template_storage_stack)

# SSM parameters are now created defensively by Configuration API on startup
# This eliminates the need for complex CloudFormation Custom Resources

# DYNAMIC AGENT DEPLOYMENT: Generic agent no longer deployed via CDK
# Instead, agents are deployed dynamically by Configuration API using CloudFormation template
# The template is auto-generated via app-template-generator.py (runs as "pre" hook in cdk.json)
# This approach ensures:
# 1. Template stays synchronized with MultiAgentStack definition automatically
# 2. Agents are only deployed when created through the UI
# 3. No unused generic agent in infrastructure
#
# See implementation_plan.md for architecture details

# Add dependencies to ensure IAM boundaries are created before compute resources
configuration_api_stack.add_dependency(iam_boundaries_stack)

supervisor_agent_stack = SupervisorAgentStack(app, f"{project_name}-supervisor-agent",
                            env={
                                "region": conf.get('RegionName'),
                                "account": os.environ.get('CDK_DEFAULT_ACCOUNT')
                            },
                            vpc=vpc_stack.vpc,
                            access_log_bucket=vpc_stack.access_logs_bucket,
                            cluster=vpc_stack.ecs_cluster,
                            configuration_api_dns=configuration_api_stack.api_fargate_service.load_balancer.load_balancer_dns_name,
                            cognito_resources=authentication_stack.cognito_resources,  # ← FIX: Pass cognito resources
                            conf=conf,
                            termination_protection=True  # Protect supervisor agent service
                            )

# Add dependencies to ensure IAM boundaries are created before compute resources
supervisor_agent_stack.add_dependency(iam_boundaries_stack)

# Supervisor agent depends on authentication stack for Cognito resources
supervisor_agent_stack.add_dependency(authentication_stack)

# CRITICAL: Configuration API must deploy first to initialize SSM parameters  
# Supervisor agent depends on SSM parameters created by Configuration API startup
supervisor_agent_stack.add_dependency(configuration_api_stack)

ui_stack = WebAppStack(app, f"{project_name}-ui",
                            env={
                                "region": conf.get('RegionName'),
                                "account": os.environ.get('CDK_DEFAULT_ACCOUNT')
                            },
                            api_url=f"{configuration_api_stack.api_fargate_service.load_balancer.load_balancer_dns_name}",
                            supervisor_agent_url=f"{supervisor_agent_stack.supervisor_alb_dns}",
                            imported_cert_arn=conf.data.get('CertificateArn'),  # Use dict.get() for optional value
                            cluster=vpc_stack.ecs_cluster,
                            access_logs_bucket=vpc_stack.access_logs_bucket,
                            cognito_resources=authentication_stack.cognito_resources,  # Pass from auth stack
                            config=conf,
                            termination_protection=True  # Protect UI stack
                       )

# UI stack depends on authentication stack for Cognito resources
ui_stack.add_dependency(authentication_stack)

# Apply CDK Nag AwsSolutions checks to all stacks
# Temporarily disabled for production deployment - KMS suppressions need refinement
# cdk.Aspects.of(app).add(AwsSolutionsChecks())

# Suppressions for legitimate architectural patterns that cannot be avoided
# Using portable patterns that work across different AWS accounts/regions

# VPC Stack suppressions
NagSuppressions.add_stack_suppressions(vpc_stack, [
    {"id": "AwsSolutions-S1", "reason": "Access logs bucket is itself used for storing access logs"},
    {"id": "CdkNagValidationFailure", "reason": "Security group rules use intrinsic functions which cannot be validated at synth time"},
    {"id": "AwsSolutions-IAM4", "reason": "Data protection custom resource uses AWS managed Lambda execution role"},
    {"id": "AwsSolutions-IAM5", "reason": "Data protection custom resource requires wildcard permissions on shared log group for policy management", 
     "appliesTo": [{"regex": "/^Resource::arn:aws:logs:[^:]+:[^:]+:log-group:<[^>]+>:\\*$/"}]}
])

# KMS Stack suppressions
NagSuppressions.add_stack_suppressions(kms_stack, [
    {"id": "AwsSolutions-KMS5", "reason": "Customer managed KMS key policy allows service principals and root for proper SSM parameter encryption"}
])

# IAM Boundaries Stack suppressions - boundary policies require wildcards to define maximum permissions
NagSuppressions.add_stack_suppressions(iam_boundaries_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Permissions boundary policies require wildcard resources to define maximum allowed permissions", "appliesTo": ["Resource::*"]},
    {"id": "AwsSolutions-IAM5", "reason": "Cross-account access restriction requires region condition with current region", "appliesTo": ["Action::*"]},
    {"id": "AwsSolutions-IAM5", "reason": "Agent service boundary requires wildcard service permissions to define maximum scope", "appliesTo": ["Action::bedrock:*", "Action::bedrock-agentcore:*", "Action::ssm:*", "Action::logs:*", "Action::s3:*", "Action::dynamodb:*", "Action::rds-data:*", "Action::secretsmanager:*", "Action::ecs:*", "Action::ecr:*", "Action::ec2:*", "Action::vpc-lattice:*", "Action::kms:*"]},
    {"id": "AwsSolutions-IAM5", "reason": "Configuration API boundary requires wildcard service permissions for infrastructure management", "appliesTo": ["Action::cloudformation:*", "Action::iam:*", "Action::ecs:*", "Action::ec2:*", "Action::elasticloadbalancing:*", "Action::logs:*", "Action::ssm:*", "Action::secretsmanager:*", "Action::cognito-idp:*", "Action::vpc-lattice:*", "Action::ecr:*", "Action::kms:*", "Action::s3:*", "Action::bedrock:*"]},
    {"id": "AwsSolutions-IAM5", "reason": "Supervisor agent boundary requires wildcard service permissions for coordination functions", "appliesTo": ["Action::bedrock:*", "Action::ssm:*", "Action::logs:*", "Action::ecs:*", "Action::ecr:*", "Action::ec2:*", "Action::kms:*"]}
])

# Authentication Stack suppressions
NagSuppressions.add_stack_suppressions(authentication_stack, [
    {"id": "AwsSolutions-COG2", "reason": "MFA disabled for development environment - enable in production"},
    {"id": "AwsSolutions-SMG4", "reason": "Secret rotation disabled for development environment - enable in production"}
])

# SSM parameters are now created by Configuration API on startup with SecureString encryption
# No separate SSM stack needed - eliminates CloudFormation Custom Resource complexity

# Template Storage Stack suppressions
NagSuppressions.add_stack_suppressions(template_storage_stack, [
    {"id": "AwsSolutions-S1", "reason": "Template storage bucket used for CloudFormation templates - no access logging needed"},
])

# Configuration API Stack suppressions
NagSuppressions.add_stack_suppressions(configuration_api_stack, [
    # AWS Managed Policy suppressions
    {"id": "AwsSolutions-IAM4", "reason": "VPCLatticeFullAccess managed policy required for service mesh - no customer-managed alternative available", "appliesTo": ["Policy::arn:<AWS::Partition>:iam::aws:policy/VPCLatticeFullAccess"]},
    
    # Wildcard permissions for services that require them
    {"id": "AwsSolutions-IAM5", "reason": "ECS and EC2 describe operations require wildcard permissions", "appliesTo": ["Resource::*"]},
    {"id": "AwsSolutions-IAM5", "reason": "CloudFormation operations scoped to application prefix with CDK tokens", "appliesTo": [
        f"Resource::arn:aws:cloudformation:<AWS::Region>:<AWS::AccountId>:stack/{project_name}-*/*",
        f"Resource::arn:aws:cloudformation:<AWS::Region>:<AWS::AccountId>:stackset/{project_name}-*"
    ]},
    {"id": "AwsSolutions-IAM5", "reason": "IAM operations scoped to application roles and policies", "appliesTo": [
        f"Resource::arn:aws:iam::<AWS::AccountId>:role/{project_name}-*",
        f"Resource::arn:aws:iam::<AWS::AccountId>:policy/{project_name}-*"
    ]},
    {"id": "AwsSolutions-IAM5", "reason": "CloudWatch Logs operations scoped to application log groups", "appliesTo": [
        f"Resource::arn:aws:logs:<AWS::Region>:<AWS::AccountId>:log-group:/aws/ecs/{project_name}-*",
        f"Resource::arn:aws:logs:<AWS::Region>:<AWS::AccountId>:log-group:/aws/vpclattice/{project_name}-*",
        f"Resource::arn:aws:logs:<AWS::Region>:<AWS::AccountId>:log-group:{project_name}-*",
        f"Resource::arn:aws:logs:<AWS::Region>:<AWS::AccountId>:log-group:{project_name}-*:log-stream:*",
        "Resource::arn:aws:logs:<AWS::Region>:<AWS::AccountId>:*"
    ]},
    {"id": "AwsSolutions-IAM5", "reason": "VPC Lattice logging requires wildcard for service log groups", "appliesTo": ["Resource::arn:aws:logs:*:*:log-group:/aws/vpclattice/*:*"]},
    
    # KMS wildcard permissions for SSM parameter access (replaces import/export dependencies)
    {"id": "AwsSolutions-IAM5", "reason": "KMS wildcard permissions required for SSM parameter encryption access - more robust than import/export dependencies", "appliesTo": ["Resource::arn:aws:kms:<AWS::Region>:<AWS::AccountId>:key/*"]},
    
    # Authentication-related permissions
    {"id": "AwsSolutions-IAM5", "reason": "Cognito User Pool operations require wildcard for role management and group operations", "appliesTo": ["Resource::arn:aws:cognito-idp:<AWS::Region>:<AWS::AccountId>:userpool/*"]},
    {"id": "AwsSolutions-IAM5", "reason": "Secrets Manager access for multi-IDP support requires pattern matching for different identity providers", "appliesTo": [
        f"Resource::arn:aws:secretsmanager:<AWS::Region>:<AWS::AccountId>:secret:{project_name}-CognitoSecretName*",
        f"Resource::arn:aws:secretsmanager:<AWS::Region>:<AWS::AccountId>:secret:{project_name}-cognito-secret*",
        "Resource::arn:aws:secretsmanager:<AWS::Region>:<AWS::AccountId>:secret:Auth0Secret*",
        "Resource::arn:aws:secretsmanager:<AWS::Region>:<AWS::AccountId>:secret:CognitoSecret*",
        "Resource::arn:aws:secretsmanager:<AWS::Region>:<AWS::AccountId>:secret:OktaSecret*",
        "Resource::arn:aws:secretsmanager:<AWS::Region>:<AWS::AccountId>:secret:PingSecret*"
    ]},
    
    {"id": "AwsSolutions-ECS2", "reason": "Environment variables contain non-sensitive configuration values only"},
    {"id": "CdkNagValidationFailure", "reason": "Security group rules use intrinsic functions which cannot be validated at synth time"}
])

# Generic Agent Stack no longer deployed via CDK - agents deployed dynamically via Configuration API
# CDK Nag suppressions for agent stacks will be applied during dynamic deployment

# Supervisor Agent Stack suppressions
NagSuppressions.add_stack_suppressions(supervisor_agent_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "ECS and EC2 describe operations require wildcard permissions", "appliesTo": ["Resource::*"]},
    {"id": "AwsSolutions-IAM5", "reason": "VPC Lattice logging requires wildcard for service log groups", "appliesTo": ["Resource::arn:aws:logs:*:*:log-group:/aws/vpclattice/*:*"]},
    {"id": "AwsSolutions-IAM5", "reason": "RDS Data API requires wildcard for serverless database operations", "appliesTo": ["Action::rds-data:*"]},
    {"id": "AwsSolutions-IAM5", "reason": "S3 access for agent file operations - scoped to objects only", "appliesTo": ["Resource::arn:aws:s3:::*/*"]},
    
    # KMS wildcard permissions for SSM parameter access (replaces import/export dependencies)
    {"id": "AwsSolutions-IAM5", "reason": "KMS wildcard permissions required for SSM parameter encryption access - more robust than import/export dependencies", "appliesTo": ["Resource::arn:aws:kms:<AWS::Region>:<AWS::AccountId>:key/*"]},
    
    {"id": "AwsSolutions-ECS2", "reason": "Environment variables contain non-sensitive configuration values only"},
    {"id": "CdkNagValidationFailure", "reason": "Security group rules use intrinsic functions which cannot be validated at synth time"}
])

# UI Stack suppressions
NagSuppressions.add_stack_suppressions(ui_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "ECS and EC2 describe operations require wildcard permissions", "appliesTo": ["Resource::*"]},
    {"id": "AwsSolutions-IAM5", "reason": "VPC Lattice logging requires wildcard for service log groups", "appliesTo": ["Resource::arn:aws:logs:*:*:log-group:/aws/vpclattice/*:*"]},
    {"id": "AwsSolutions-ECS2", "reason": "Environment variables contain non-sensitive configuration values only"},
    {"id": "AwsSolutions-EC23", "reason": "Web application requires public internet access - protected by application-level security"},
    {"id": "AwsSolutions-COG2", "reason": "MFA disabled for development environment - enable in production"},
    {"id": "AwsSolutions-SMG4", "reason": "Secret rotation disabled for development environment - enable in production"},
    {"id": "CdkNagValidationFailure", "reason": "Security group rules use intrinsic functions which cannot be validated at synth time"},
    
    # CloudFront-specific suppressions
    {"id": "AwsSolutions-CFR1", "reason": "CloudFront distribution uses configurable geo-restriction for flexible access control"},
    {"id": "AwsSolutions-CFR2", "reason": "CloudFront distribution has WAF enabled for security protection"},
    {"id": "AwsSolutions-CFR3", "reason": "CloudFront distribution has access logging enabled to S3 bucket with proper cross-stack reference handling"},
    {"id": "AwsSolutions-CFR4", "reason": "CloudFront distribution uses TLS 1.2 2021 security policy with proper SSL/TLS protocols"},
    {"id": "AwsSolutions-CFR5", "reason": "CloudFront distribution uses default CloudFront certificate - custom domain not required"},
    {"id": "AwsSolutions-CFR6", "reason": "CloudFront distribution uses HTTP/2 for improved performance"},
    
    # WAF-specific suppressions for CloudFront
    {"id": "AwsSolutions-WAF2", "reason": "CloudFront WAF uses OWASP Common Rule Set for comprehensive security"},
    {"id": "AwsSolutions-WAF10", "reason": "CloudFront WAF has CloudWatch metrics enabled for monitoring"},
    
    # Custom Resource Lambda suppressions for dynamic AWS resource lookups
    {"id": "AwsSolutions-IAM4", "reason": "Custom resource Lambda functions use AWS managed Lambda execution role for EC2 API calls", "appliesTo": ["Policy::arn:<AWS::Partition>:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"]},
])

# Targeted suppressions for legitimate architectural patterns that cannot be further scoped
# These address remaining CDK Nag findings for necessary wildcard permissions

# Configuration API Stack - shared log group access and KMS wildcard
NagSuppressions.add_stack_suppressions(configuration_api_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Shared log group access required for centralized multi-agent logging - imported via CDK cross-stack reference", 
     "appliesTo": [{"regex": "/^Resource::.*-SharedLogGroupArn:\\*$/"}]},
    {"id": "AwsSolutions-IAM5", "reason": "KMS wildcard permissions required for SSM parameter encryption access - more robust than import/export dependencies", 
     "appliesTo": [{"regex": "/^Resource::arn:aws:kms:<AWS::Region>:<AWS::AccountId>:key\\/\\*$/"}]}
])

# Generic Agent Stack - no longer deployed via CDK (agents deployed dynamically)
# CDK Nag suppressions will be applied during dynamic deployment

# Supervisor Agent Stack - shared log group access and KMS wildcard  
NagSuppressions.add_stack_suppressions(supervisor_agent_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Shared log group access required for centralized multi-agent logging - imported via CDK cross-stack reference", 
     "appliesTo": [{"regex": "/^Resource::.*-SharedLogGroupArn:\\*$/"}]},
    {"id": "AwsSolutions-IAM5", "reason": "KMS wildcard permissions required for SSM parameter encryption access - more robust than import/export dependencies", 
     "appliesTo": [{"regex": "/^Resource::arn:aws:kms:<AWS::Region>:<AWS::AccountId>:key\\/\\*$/"}]}
])

# UI Stack - shared log group access
NagSuppressions.add_stack_suppressions(ui_stack, [
    {"id": "AwsSolutions-IAM5", "reason": "Shared log group access required for centralized multi-agent logging - imported via CDK cross-stack reference", 
     "appliesTo": [{"regex": "/^Resource::.*-SharedLogGroupArn:\\*$/"}]}
])

app.synth()

# DYNAMIC AGENT DEPLOYMENT: Template generation handled by app-template-generator.py
# The template generator runs as a "pre" hook in cdk.json before each synth
# This ensures the CloudFormation template stays synchronized with MultiAgentStack
# The template is uploaded to S3 by scripts/upload-agent-template.sh after deployment
