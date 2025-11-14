"""
Deployment service for dynamic agent stack management.

This service handles CloudFormation stack operations for creating,
monitoring, and managing agent instances dynamically.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../'))
from common.secure_logging_utils import log_exception_safely

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

logger = logging.getLogger(__name__)


class DeploymentService:
    """
    Service for managing CloudFormation stack deployments.
    
    This service provides functionality to:
    - Read existing CloudFormation templates
    - Create new stacks with modified parameters
    - Monitor stack status and outputs
    - List and manage agent stacks
    """
    
    def __init__(self):
        """Initialize the deployment service with AWS clients."""
        try:
            import os
            # Get region from environment variable with fallback
            self.region = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
            self.cloudformation = boto3.client('cloudformation', region_name=self.region)
            self.s3 = boto3.client('s3', region_name=self.region)
            
            # Get project name and account for S3 bucket construction
            self.project_name = os.environ.get('PROJECT_NAME', 'ai-platform')
            sts = boto3.client('sts')
            self.account_id = sts.get_caller_identity()['Account']
            self.template_bucket_name = f"{self.project_name}-templates-{self.account_id}-{self.region}"
            
            logger.info(f"DeploymentService initialized for region: {self.region}, project: {self.project_name}")
            logger.info(f"Template bucket: {self.template_bucket_name}")
        except NoCredentialsError:
            logger.error("AWS credentials not found")
            raise ValueError("AWS credentials not configured")
        except Exception as e:
            log_exception_safely(logger, e, "Failed to initialize AWS clients")
            raise
    
    async def get_project_name(self) -> str:
        """
        Get the project name for stack naming patterns.
        
        Returns:
            Project name from configuration
        """
        return self.project_name
    
    async def create_agent_stack(
        self,
        new_agent_name: str,
        new_stack_name: str,
        model_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new agent stack using the template from S3.
        
        Args:
            new_agent_name: Name for the new agent (AgentName parameter)
            new_stack_name: Name for the new CloudFormation stack
            model_config: Model configuration (if not provided, will read from SSM)
            
        Returns:
            Dictionary containing stack creation information
            
        Raises:
            ValueError: If template not found or validation fails
            Exception: If stack creation fails
        """
        try:
            logger.info(f"Creating agent stack '{new_stack_name}' for agent '{new_agent_name}'")
            
            # Simplified approach: Agents read all configuration from SSM
            # No need to inject environment variables - cleaner and more reliable
            
            # Get the template from S3 (deployed by CDK template-storage stack)
            template_body = await self._get_template_from_s3("GenericAgentTemplate.json")
            
            # No template modification needed - parameters are explicitly required
            # AgentName and ImageTag must be provided as CloudFormation parameters
            
            logger.info(f"Agent {new_agent_name} will read all configuration from SSM parameter: /agent/{new_agent_name}/config")
            
            # Prepare parameters for the new stack
            logger.debug(f"Building CloudFormation parameters for agent: {new_agent_name}")
            
            parameters = [
                {
                    'ParameterKey': 'AgentName',
                    'ParameterValue': new_agent_name
                }
            ]
            logger.debug(f"Set AgentName parameter: {new_agent_name}")
            
            # CRITICAL: Retrieve and set ImageTag from SSM to ensure correct image version
            # ImageTag parameter is required - no default value in template
            logger.info("IMAGE TAG RETRIEVAL FOR AGENT CREATION")
            
            image_uri = None
            try:
                logger.info(f"Retrieving image URI from SSM Parameter Store: /{self.project_name}/agent/image-uri")
                
                image_uri = self._get_image_uri_from_ssm()
                
                logger.info(f"Successfully retrieved image URI from SSM: {image_uri}")
                
                # Extract and log the tag portion
                if ':' in image_uri:
                    tag_portion = image_uri.split(':')[-1]
                    logger.debug(f"Extracted tag: {tag_portion}")
                    
                    # Validate that we don't have "latest" in the image URI
                    if tag_portion.lower() == 'latest':
                        logger.error("SSM parameter contains 'latest' tag!")
                        logger.error("This indicates the ECR image was not properly tagged with SHA256")
                        logger.error("The CDK deployment may not have completed successfully")
                        raise ValueError("SSM parameter contains 'latest' tag instead of SHA256 hash")
                else:
                    logger.error("No ':' found in image URI from SSM")
                    logger.error(f"Invalid image URI format: {image_uri}")
                    raise ValueError("Invalid image URI format - missing tag separator")
                
                # IMPORTANT: Pass the FULL image URI, not just the tag
                # The CloudFormation template expects the complete URI with repository and SHA256 tag
                parameters.append({
                    'ParameterKey': 'ImageTag',
                    'ParameterValue': image_uri
                })
                
                logger.info("Successfully added ImageTag to CloudFormation parameters")
                logger.debug(f"CloudFormation ImageTag parameter value: {image_uri}")
                
            except Exception as e:
                logger.error(f"Failed to retrieve ImageTag from SSM: {e}")
                logger.error(f"Error type: {type(e).__name__}")
                
                # CRITICAL: Do not proceed without a valid ImageTag - this would cause "latest" to be used
                if image_uri and 'latest' in image_uri.lower():
                    logger.error("Refusing to create agent with 'latest' image tag!")
                    logger.error("This would create an unstable deployment")
                    raise ValueError("Cannot create agent with 'latest' image tag - please ensure CDK deployment completed successfully")
                
                logger.error("Refusing to create agent WITHOUT ImageTag parameter")
                logger.error("ImageTag parameter is required - no default value in template")
                logger.error("Agent creation aborted to prevent deployment failure!")
                
                # Re-raise the exception to prevent agent creation with wrong image
                raise ValueError(f"ImageTag retrieval failed: {e}. Cannot create agent without proper image tag.")
            
            # Log final parameters before CloudFormation call
            logger.info("Final CloudFormation parameters for create_stack")
            logger.info(f"Stack Name: {new_stack_name}")
            logger.info(f"Total parameters: {len(parameters)}")
            for i, param in enumerate(parameters, 1):
                logger.debug(f"  {i}. {param['ParameterKey']} = {param['ParameterValue'][:100]}...")  # Truncate long values
            
            # Create the new stack
            create_params = {
                'StackName': new_stack_name,
                'TemplateBody': json.dumps(template_body),
                'Parameters': parameters,
                'Capabilities': ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM'],
                'Tags': [
                    {'Key': 'ManagedBy', 'Value': 'ConfigurationAPI'},
                    {'Key': 'AgentName', 'Value': new_agent_name},
                    {'Key': 'TemplateSource', 'Value': 'S3'},
                    {'Key': 'CreatedAt', 'Value': datetime.utcnow().isoformat()}
                ]
            }
            
            logger.info("Calling CloudFormation CreateStack API...")
            response = self.cloudformation.create_stack(**create_params)
            
            stack_id = response['StackId']
            logger.info("Stack creation initiated successfully")
            logger.info(f"Stack Name: {new_stack_name}")
            logger.info(f"Stack ID: {stack_id}")
            logger.info(f"Agent Name: {new_agent_name}")
            logger.info(f"Status: CREATE_IN_PROGRESS")
            
            return {
                'stack_name': new_stack_name,
                'stack_id': stack_id,
                'status': 'CREATE_IN_PROGRESS',
                'agent_name': new_agent_name
            }
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AlreadyExistsException':
                raise ValueError(f"Stack '{new_stack_name}' already exists")
            else:
                logger.error(f"CloudFormation error: {error_code} - {e.response['Error']['Message']}")
                raise Exception(f"Failed to create stack: {e.response['Error']['Message']}")
        except Exception as e:
            log_exception_safely(logger, e, "Error creating agent stack")
            raise
    
    async def _get_stack_template(self, stack_name: str) -> Dict[str, Any]:
        """
        Get the CloudFormation template from an existing stack.
        
        Args:
            stack_name: Name of the stack to get template from
            
        Returns:
            CloudFormation template as a dictionary
            
        Raises:
            ValueError: If stack not found
            Exception: If unable to retrieve template
        """
        try:
            logger.info(f"Retrieving template from stack: {stack_name}")
            
            response = self.cloudformation.get_template(StackName=stack_name)
            template = response['TemplateBody']
            
            logger.info(f"Successfully retrieved template from stack: {stack_name}")
            return template
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['ValidationError', 'StackNotFoundException']:
                raise ValueError(f"Stack '{stack_name}' not found")
            else:
                logger.error(f"Error retrieving template: {error_code}")
                raise Exception(f"Failed to retrieve template: {e.response['Error']['Message']}")
        except Exception as e:
            log_exception_safely(logger, e, "Error getting stack template")
            raise
    
    async def _get_template_from_s3(self, template_key: str = "GenericAgentTemplate.json") -> Dict[str, Any]:
        """
        Get the latest CloudFormation template from S3.
        
        This fetches the template that was deployed by CDK to the template storage bucket.
        This ensures stack updates pick up the latest CDK-generated template changes.
        
        Args:
            template_key: S3 key for the template file
            
        Returns:
            CloudFormation template as a dictionary
            
        Raises:
            ValueError: If template not found in S3
            Exception: If unable to retrieve template
        """
        try:
            logger.info(f"Retrieving template from S3: s3://{self.template_bucket_name}/{template_key}")
            
            response = self.s3.get_object(
                Bucket=self.template_bucket_name,
                Key=template_key
            )
            
            template_body = response['Body'].read().decode('utf-8')
            template = json.loads(template_body)
            
            logger.info(f"Successfully retrieved template from S3: {template_key}")
            return template
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code in ['NoSuchKey', 'NoSuchBucket']:
                raise ValueError(f"Template '{template_key}' not found in S3 bucket '{self.template_bucket_name}'")
            else:
                logger.error(f"S3 error retrieving template: {error_code}")
                raise Exception(f"Failed to retrieve template from S3: {e.response['Error']['Message']}")
        except Exception as e:
            log_exception_safely(logger, e, "Error getting template from S3")
            raise
    
    
    def _inject_model_environment_variables(
        self, 
        template: Dict[str, Any], 
        agent_name: str, 
        model_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Inject model configuration as environment variables into the CloudFormation template.
        
        This method modifies the ECS task definition containers to include environment variables
        that override SSM parameters with UI-selected model configuration.
        
        Args:
            template: CloudFormation template to modify
            agent_name: Name of the agent (used for environment variable naming)
            model_config: Model configuration from UI
            
        Returns:
            Modified CloudFormation template with environment variables
        """
        try:
            # Create a copy of the template
            modified_template = json.loads(json.dumps(template))
            
            # Create environment variable prefix from agent name
            agent_name_upper = agent_name.upper().replace('-', '_')
            
            # Build environment variables from model config (only include non-None values)
            env_vars = {}
            if model_config.get("model_id"):
                env_vars[f"{agent_name_upper}_MODEL_ID"] = str(model_config["model_id"])
            if model_config.get("judge_model_id"):
                env_vars[f"{agent_name_upper}_JUDGE_MODEL_ID"] = str(model_config["judge_model_id"])
            if model_config.get("embedding_model_id"):
                env_vars[f"{agent_name_upper}_EMBEDDING_MODEL_ID"] = str(model_config["embedding_model_id"])
            if model_config.get("temperature") is not None:
                env_vars[f"{agent_name_upper}_TEMPERATURE"] = str(model_config["temperature"])
            if model_config.get("top_p") is not None:
                env_vars[f"{agent_name_upper}_TOP_P"] = str(model_config["top_p"])
            if model_config.get("streaming") is not None:
                env_vars[f"{agent_name_upper}_STREAMING"] = str(model_config["streaming"]).lower()
            
            if not env_vars:
                logger.info("No model configuration provided, skipping environment variable injection")
                return modified_template
            
            logger.info(f"Injecting {len(env_vars)} model environment variables for agent: {agent_name}")
            
            # Navigate through CloudFormation template to find ECS container definitions
            resources = modified_template.get("Resources", {})
            
            for resource_name, resource in resources.items():
                if resource.get("Type") == "AWS::ECS::TaskDefinition":
                    # Found an ECS task definition
                    properties = resource.get("Properties", {})
                    container_definitions = properties.get("ContainerDefinitions", [])
                    
                    for container_def in container_definitions:
                        # Get existing environment variables or create empty list
                        existing_env = container_def.get("Environment", [])
                        
                        # Convert existing env list to dict for easier processing
                        existing_env_dict = {
                            env["Name"]: env["Value"] for env in existing_env
                        }
                        
                        # Add/update with new model configuration
                        existing_env_dict.update(env_vars)
                        
                        # Convert back to CloudFormation format
                        container_def["Environment"] = [
                            {"Name": name, "Value": value}
                            for name, value in existing_env_dict.items()
                        ]
                        
                        logger.info(f"Added model environment variables to container in resource: {resource_name}")
            
            logger.info(f"Successfully injected model environment variables for agent: {agent_name}")
            return modified_template
            
        except Exception as e:
            log_exception_safely(logger, e, "Error injecting model environment variables")
            raise RuntimeError("Failed to inject environment variables")
    
    async def _get_stack_info(self, stack_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a CloudFormation stack.
        
        Args:
            stack_name: Name of the stack
            
        Returns:
            Dictionary containing stack information
        """
        try:
            response = self.cloudformation.describe_stacks(StackName=stack_name)
            
            if not response['Stacks']:
                raise ValueError(f"Stack '{stack_name}' not found")
                
            stack = response['Stacks'][0]
            
            return {
                'stack_name': stack['StackName'],
                'stack_id': stack['StackId'],
                'status': stack['StackStatus'],
                'creation_time': stack.get('CreationTime'),
                'last_updated_time': stack.get('LastUpdatedTime'),
                'parameters': stack.get('Parameters', []),
                'outputs': stack.get('Outputs', []),
                'tags': stack.get('Tags', [])
            }
            
        except ClientError as e:
            if e.response['Error']['Code'] in ['ValidationError', 'StackNotFoundException']:
                raise ValueError(f"Stack '{stack_name}' not found")
            raise
    
    async def get_stack_status(self, stack_name: str) -> Dict[str, Any]:
        """
        Get the current status of a CloudFormation stack.
        
        Args:
            stack_name: Name of the stack
            
        Returns:
            Dictionary containing stack status information
        """
        try:
            stack_info = await self._get_stack_info(stack_name)
            
            # Extract agent name from parameters
            agent_name = None
            for param in stack_info.get('parameters', []):
                if param['ParameterKey'] == 'AgentName':
                    agent_name = param['ParameterValue']
                    break
            
            # Process outputs
            outputs = {}
            for output in stack_info.get('outputs', []):
                outputs[output['OutputKey']] = output['OutputValue']
            
            # Convert datetime objects to ISO format strings for JSON serialization
            creation_time = None
            if stack_info.get('creation_time'):
                creation_time = stack_info['creation_time'].isoformat() if hasattr(stack_info['creation_time'], 'isoformat') else str(stack_info['creation_time'])
            
            last_updated_time = None
            if stack_info.get('last_updated_time'):
                last_updated_time = stack_info['last_updated_time'].isoformat() if hasattr(stack_info['last_updated_time'], 'isoformat') else str(stack_info['last_updated_time'])
            
            return {
                'stack_name': stack_info['stack_name'],
                'stack_id': stack_info['stack_id'],
                'status': stack_info['status'],
                'creation_time': creation_time,
                'last_updated_time': last_updated_time,
                'outputs': outputs if outputs else {}
            }
            
        except Exception as e:
            log_exception_safely(logger, e, "Error getting stack status")
            raise
    
    async def list_agent_stacks(self) -> List[Dict[str, Any]]:
        """
        List all agent stacks with their status using strict pattern matching.
        
        Returns:
            List of agent stacks with status information
        """
        try:
            logger.info("Listing all agent stacks with strict pattern matching")
            
            # Get all stacks
            paginator = self.cloudformation.get_paginator('list_stacks')
            
            # Only get stacks that are not deleted
            stack_statuses = [
                'CREATE_IN_PROGRESS', 'CREATE_FAILED', 'CREATE_COMPLETE',
                'ROLLBACK_IN_PROGRESS', 'ROLLBACK_FAILED', 'ROLLBACK_COMPLETE',
                'DELETE_IN_PROGRESS', 'DELETE_FAILED',
                'UPDATE_IN_PROGRESS', 'UPDATE_COMPLETE_CLEANUP_IN_PROGRESS',
                'UPDATE_COMPLETE', 'UPDATE_ROLLBACK_IN_PROGRESS',
                'UPDATE_ROLLBACK_FAILED', 'UPDATE_ROLLBACK_COMPLETE_CLEANUP_IN_PROGRESS',
                'UPDATE_ROLLBACK_COMPLETE', 'REVIEW_IN_PROGRESS'
            ]
            
            agent_stacks = []
            
            for page in paginator.paginate(StackStatusFilter=stack_statuses):
                for stack_summary in page['StackSummaries']:
                    stack_name = stack_summary['StackName']
                    
                    # Strict filtering for agent stacks - only exact patterns to avoid accidental matches
                    is_agent_stack = (
                        # Configuration API pattern: {project-name}-{agent-name}-api
                        (stack_name.startswith(f'{self.project_name}-') and stack_name.endswith('-api')) or
                        # Manual deployment pattern: {project-name}-{agent-name}-stack
                        (stack_name.startswith(f'{self.project_name}-') and stack_name.endswith('-stack')) or
                        # Known system stacks that have AgentName parameter
                        stack_name in [f'{self.project_name}-generic-agent-api', f'{self.project_name}-supervisor-agent']
                    )
                    
                    if is_agent_stack:
                        try:
                            # Get detailed stack info to check for agent parameters
                            stack_info = await self._get_stack_info(stack_name)
                            
                            # Extract agent name from parameters
                            agent_name = None
                            for param in stack_info.get('parameters', []):
                                if param['ParameterKey'] == 'AgentName':
                                    agent_name = param['ParameterValue']
                                    break
                            
                            # Only include stacks that have AgentName parameter
                            if agent_name:
                                # Check if it's managed by our API
                                managed_by_api = False
                                for tag in stack_info.get('tags', []):
                                    if tag['Key'] == 'ManagedBy' and tag['Value'] == 'ConfigurationAPI':
                                        managed_by_api = True
                                        break
                                
                                agent_stacks.append({
                                    'stack_name': stack_info['stack_name'],
                                    'stack_id': stack_info['stack_id'],
                                    'status': stack_info['status'],
                                    'agent_name': agent_name,
                                    'managed_by_api': managed_by_api,
                                    'parameters': stack_info.get('parameters', []),  # Include parameters for matching
                                    'created_at': stack_info.get('creation_time'),
                                    'updated_at': stack_info.get('last_updated_time')
                                })
                                
                        except Exception as e:
                            log_exception_safely(logger, e, f"Could not get details for stack {stack_name}")
                            continue
            
            logger.info(f"Found {len(agent_stacks)} agent stacks")
            return agent_stacks
            
        except Exception as e:
            log_exception_safely(logger, e, "Error listing agent stacks")
            raise
    
    def get_stack_name_from_agent(self, agent_name: str) -> str:
        """
        Get CloudFormation stack name from agent name using consistent naming pattern.
        
        Standard pattern: {project_name}-agent-{agent_name}
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            CloudFormation stack name
        """
        # Convert underscores to hyphens for stack naming consistency
        stack_agent_name = agent_name.replace('_', '-')
        return f"{self.project_name}-agent-{stack_agent_name}"
    
    async def find_agent_stack_by_name(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        Find a CloudFormation stack for a specific agent using standard naming pattern.
        
        Args:
            agent_name: Name of the agent to find stack for
            
        Returns:
            Stack information if found, None otherwise
        """
        try:
            # Use consistent naming pattern
            expected_stack_name = self.get_stack_name_from_agent(agent_name)
            
            logger.info(f"Looking for agent stack: {expected_stack_name}")
            
            try:
                # Get the stack directly using standard pattern
                stack_info = await self._get_stack_info(expected_stack_name)
                
                # Verify this stack has the correct AgentName parameter
                stack_agent_name_param = None
                for param in stack_info.get('parameters', []):
                    if param['ParameterKey'] == 'AgentName':
                        stack_agent_name_param = param['ParameterValue']
                        break
                
                if stack_agent_name_param == agent_name:
                    logger.info(f"Found agent stack: {expected_stack_name} with AgentName={agent_name}")
                    
                    # Check if it's managed by our API
                    managed_by_api = False
                    for tag in stack_info.get('tags', []):
                        if tag['Key'] == 'ManagedBy' and tag['Value'] == 'ConfigurationAPI':
                            managed_by_api = True
                            break
                    
                    return {
                        'stack_name': stack_info['stack_name'],
                        'stack_id': stack_info['stack_id'],
                        'status': stack_info['status'],
                        'agent_name': stack_agent_name_param,
                        'managed_by_api': managed_by_api,
                        'parameters': stack_info.get('parameters', []),
                        'created_at': stack_info.get('creation_time'),
                        'updated_at': stack_info.get('last_updated_time')
                    }
                else:
                    logger.warning(f"Stack {expected_stack_name} found but AgentName parameter mismatch: expected '{agent_name}', got '{stack_agent_name_param}'")
                    return None
                    
            except ValueError:
                # Stack not found with standard pattern
                logger.info(f"No stack found for agent '{agent_name}' using pattern: {expected_stack_name}")
                return None
                
        except Exception as e:
            log_exception_safely(logger, e, f"Error finding agent stack for '{agent_name}'")
            return None
    
    async def update_agent_stack(
        self,
        agent_name: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Update an existing agent stack with new parameters or template changes.
        
        This method:
        1. Finds the CloudFormation stack for the agent
        2. Retrieves the current template
        3. Updates the stack with new parameters (if provided)
        
        Args:
            agent_name: Name of the agent whose stack to update
            parameters: Optional dictionary of CloudFormation parameters to update
            
        Returns:
            Dictionary containing update information
            
        Raises:
            ValueError: If agent stack not found
            Exception: If stack update fails
        """
        try:
            logger.info(f"Updating agent stack for: {agent_name}")
            
            # Find the stack for this agent
            stack_info = await self.find_agent_stack_by_name(agent_name)
            
            if not stack_info:
                raise ValueError(f"No CloudFormation stack found for agent '{agent_name}'")
            
            stack_name = stack_info['stack_name']
            logger.info(f"Found stack '{stack_name}' for agent '{agent_name}'")
            
            # Fetch the latest template from S3 to pick up any CDK template changes
            # This ensures updates include latest infrastructure improvements
            logger.info("Fetching latest template from S3 for stack update")
            template_from_s3 = await self._get_template_from_s3("GenericAgentTemplate.json")
            
            # No template modification - parameters must be explicitly provided
            # AgentName and ImageTag are required parameters with no defaults
            logger.info("Using template as-is - no defaults to modify")
            
            # Prepare update parameters with unmodified template
            update_params = {
                'StackName': stack_name,
                'TemplateBody': json.dumps(template_from_s3),
                'Capabilities': ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
            }
            
            # Build parameters list, preserving existing parameters and merging with new ones
            # CRITICAL: AgentName must ALWAYS be explicitly set to prevent CloudFormation from using template default
            
            # Get existing parameters from stack
            existing_params = {
                param['ParameterKey']: param['ParameterValue']
                for param in stack_info.get('parameters', [])
            }
            
            logger.info(f"Existing parameters from stack: {existing_params}")
            
            # If new parameters provided, merge them with existing ones
            if parameters:
                existing_params.update(parameters)
                logger.info(f"Merged {len(parameters)} new parameters with existing parameters")
            
            # CRITICAL: Always ensure AgentName is set to the correct agent name
            # This is the most important parameter and must never revert to template default
            existing_params['AgentName'] = agent_name
            logger.info(f"Explicitly set AgentName parameter to: {agent_name}")
            
            # CRITICAL: Retrieve and set ImageTag from SSM to ensure ECS updates
            # The existing parameter may contain a CDK token like ${Token[TOKEN.262]}
            # which must be replaced with the actual full image URI with SHA256 tag from SSM
            logger.debug(f"Current ImageTag parameter value before SSM retrieval: {existing_params.get('ImageTag', 'NOT SET')}")
            try:
                logger.info("Retrieving image URI from SSM for ImageTag parameter...")
                image_uri = self._get_image_uri_from_ssm()
                logger.debug(f"Full image URI from SSM: {image_uri}")
                
                # IMPORTANT: Pass the FULL image URI, not just the tag
                # The CloudFormation template expects the complete URI with repository and SHA256 tag
                logger.debug(f"Replacing ImageTag parameter: '{existing_params.get('ImageTag')}' -> '{image_uri}'")
                existing_params['ImageTag'] = image_uri
                logger.info(f"Successfully updated ImageTag parameter from SSM: {image_uri}")
            except Exception as e:
                logger.error(f"Failed to retrieve ImageTag from SSM: {e}")
                logger.warning(f"Proceeding with existing ImageTag value: {existing_params.get('ImageTag', 'NOT SET')}")
                logger.warning("ECS may not update if ImageTag hasn't changed")
            
            # Build CloudFormation parameter list from merged parameters
            # Put AgentName FIRST to emphasize its importance
            cfn_parameters = [
                {
                    'ParameterKey': 'AgentName',
                    'ParameterValue': agent_name
                }
            ]
            
            # Add all other parameters
            for key, value in existing_params.items():
                if key != 'AgentName':  # Skip AgentName since we already added it first
                    cfn_parameters.append({
                        'ParameterKey': key,
                        'ParameterValue': str(value)
                    })
            
            update_params['Parameters'] = cfn_parameters
            logger.info(f"Final parameters for CloudFormation update (AgentName={agent_name} is first): {[p['ParameterKey'] for p in cfn_parameters]}")
            
            # Add update tags - ensure ManagedBy tag is always present
            existing_tags = stack_info.get('tags', [])
            update_tags = [tag for tag in existing_tags if not tag['Key'].startswith('aws:')]
            
            # Ensure ManagedBy tag is present (required for deletion permission)
            has_managed_by_tag = any(tag['Key'] == 'ManagedBy' and tag['Value'] == 'ConfigurationAPI' 
                                   for tag in update_tags)
            
            if not has_managed_by_tag:
                logger.info(f"Adding missing ManagedBy tag to stack: {stack_name}")
                update_tags.append({
                    'Key': 'ManagedBy',
                    'Value': 'ConfigurationAPI'
                })
            
            # Ensure AgentName tag is present and matches the agent
            agent_name_tag_index = None
            for i, tag in enumerate(update_tags):
                if tag['Key'] == 'AgentName':
                    agent_name_tag_index = i
                    break
            
            if agent_name_tag_index is not None:
                update_tags[agent_name_tag_index]['Value'] = agent_name
            else:
                update_tags.append({
                    'Key': 'AgentName',
                    'Value': agent_name
                })
            
            update_tags.append({
                'Key': 'LastUpdatedBy',
                'Value': 'ConfigurationAPI'
            })
            update_tags.append({
                'Key': 'LastUpdatedAt',
                'Value': datetime.utcnow().isoformat()
            })
            update_params['Tags'] = update_tags
            
            # Execute stack update
            # Note: EnableTerminationProtection is only valid for create_stack, not update_stack
            try:
                response = self.cloudformation.update_stack(**update_params)
                stack_id = response['StackId']
                
                logger.info(f"Successfully initiated stack update for '{stack_name}' (with ForceNewDeployment)")
                
                return {
                    'stack_name': stack_name,
                    'stack_id': stack_id,
                    'status': 'UPDATE_IN_PROGRESS',
                    'agent_name': agent_name,
                    'message': f'Stack update initiated for agent {agent_name} - ECS service will force new deployment'
                }
                
            except ClientError as e:
                error_code = e.response['Error']['Code']
                error_message = e.response['Error']['Message']
                
                # Handle "No updates are to be performed" case gracefully
                if error_code == 'ValidationError' and 'No updates are to be performed' in error_message:
                    logger.info(f"No updates needed for stack '{stack_name}'")
                    return {
                        'stack_name': stack_name,
                        'stack_id': stack_info['stack_id'],
                        'status': stack_info['status'],
                        'agent_name': agent_name,
                        'message': 'Stack is already up to date - no changes needed'
                    }
                else:
                    logger.error(f"CloudFormation error: {error_code} - {error_message}")
                    raise Exception(f"Failed to update stack: {error_message}")
            
        except ValueError:
            # Re-raise ValueError for agent not found
            raise
        except Exception as e:
            log_exception_safely(logger, e, f"Error updating agent stack for '{agent_name}'")
            raise
    
    def _get_image_uri_from_ssm(self) -> str:
        """
        Retrieve the agent image URI from SSM Parameter Store.
        
        This retrieves the SHA256-tagged image URI that was stored during
        the CDK deployment, ensuring ECS tasks always pull the correct image version.
        
        Returns:
            Image URI with SHA256 tag (e.g., "123456789.dkr.ecr.us-east-1.amazonaws.com/repo:sha256tag")
            
        Raises:
            Exception: If parameter not found or retrieval fails
        """
        try:
            # Get SSM client
            ssm = boto3.client('ssm', region_name=self.region)
            
            # Parameter name where CDK stores the image URI
            # This matches the actual parameter created by template_storage stack:
            # ssm.StringParameter(parameter_name=f"/{project_name}/agent/image-uri", ...)
            parameter_name = f"/{self.project_name}/agent/image-uri"
            
            logger.debug(f"Fetching SSM parameter: {parameter_name}")
            response = ssm.get_parameter(Name=parameter_name)
            image_uri = response['Parameter']['Value']
            
            logger.info(f"Successfully retrieved image URI from SSM: {image_uri}")
            
            # Log the expected tag extraction for debugging
            if ':' in image_uri:
                expected_tag = image_uri.split(':')[-1]
                logger.debug(f"Expected tag after extraction: {expected_tag}")
            else:
                logger.warning("Image URI doesn't contain ':' separator - will default to 'latest'")
            
            return image_uri
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ParameterNotFound':
                logger.error(f"SSM parameter not found: {parameter_name}")
                logger.error("Ensure CDK deployment completed successfully and created this parameter")
                logger.error(f"Check if parameter exists with: aws ssm get-parameter --name {parameter_name}")
            else:
                logger.error(f"AWS error retrieving SSM parameter: {error_code}")
            raise Exception(f"Failed to retrieve image URI from SSM: {e.response['Error']['Message']}")
        except Exception as e:
            logger.error("Unexpected error retrieving image URI from SSM")
            log_exception_safely(logger, e, "Error retrieving image URI from SSM")
            raise
    
    async def delete_stack(self, stack_name: str) -> Dict[str, Any]:
        """
        Delete a CloudFormation stack.
        
        Args:
            stack_name: Name of the stack to delete
            
        Returns:
            Dictionary containing deletion information
        """
        try:
            logger.info(f"Deleting stack: {stack_name}")
            
            # Verify stack exists before attempting deletion
            await self._get_stack_info(stack_name)
            
            # Delete the stack
            self.cloudformation.delete_stack(StackName=stack_name)
            
            logger.info(f"Successfully initiated deletion of stack: {stack_name}")
            
            return {
                'stack_name': stack_name,
                'status': 'DELETE_IN_PROGRESS'
            }
            
        except ValueError as e:
            # Stack not found
            raise
        except ClientError as e:
            logger.error(f"CloudFormation error deleting stack: {e.response['Error']['Message']}")
            raise Exception(f"Failed to delete stack: {e.response['Error']['Message']}")
        except Exception as e:
            log_exception_safely(logger, e, "Error deleting stack")
            raise
