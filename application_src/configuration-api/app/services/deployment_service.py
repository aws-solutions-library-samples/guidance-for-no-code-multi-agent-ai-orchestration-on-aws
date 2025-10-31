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
            # Get project name from environment or use default
            self.project_name = os.environ.get('PROJECT_NAME', 'genai-box')
            logger.info(f"DeploymentService initialized for region: {self.region}, project: {self.project_name}")
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
        source_stack_name: str,
        new_agent_name: str,
        new_stack_name: str,
        model_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new agent stack from an existing template.
        
        Args:
            source_stack_name: Name of the existing stack to copy template from
            new_agent_name: Name for the new agent (AgentName parameter)
            new_stack_name: Name for the new CloudFormation stack
            model_config: Model configuration (if not provided, will read from SSM)
            
        Returns:
            Dictionary containing stack creation information
            
        Raises:
            ValueError: If source stack not found or validation fails
            Exception: If stack creation fails
        """
        try:
            logger.info(f"Creating agent stack '{new_stack_name}' from source '{source_stack_name}'")
            
            # Simplified approach: Agents read all configuration from SSM
            # No need to inject environment variables - cleaner and more reliable
            
            # Get the template from the source stack
            template_body = await self._get_stack_template(source_stack_name)
            
            # Only modify the AgentName parameter - agents read everything else from SSM
            modified_template = self._modify_agent_name_parameter(template_body, new_agent_name)
            
            logger.info(f"Agent {new_agent_name} will read all configuration from SSM parameter: /agent/{new_agent_name}/config")
            
            # Get the original stack's tags and capabilities
            source_stack_info = await self._get_stack_info(source_stack_name)
            
            # Prepare parameters for the new stack
            parameters = [
                {
                    'ParameterKey': 'AgentName',
                    'ParameterValue': new_agent_name
                }
            ]
            
            # Create the new stack
            create_params = {
                'StackName': new_stack_name,
                'TemplateBody': json.dumps(modified_template),
                'Parameters': parameters,
                'Capabilities': ['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM'],
                'Tags': [
                    {'Key': 'ManagedBy', 'Value': 'ConfigurationAPI'},
                    {'Key': 'AgentName', 'Value': new_agent_name},
                    {'Key': 'SourceStack', 'Value': source_stack_name},
                    {'Key': 'CreatedAt', 'Value': datetime.utcnow().isoformat()}
                ]
            }
            
            # Add original tags (excluding system tags)
            if source_stack_info.get('tags'):
                for tag in source_stack_info['tags']:
                    if not tag['Key'].startswith('aws:'):
                        create_params['Tags'].append(tag)
            
            response = self.cloudformation.create_stack(**create_params)
            
            stack_id = response['StackId']
            logger.info(f"Successfully created stack '{new_stack_name}' with ID: {stack_id}")
            
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
    
    def _modify_agent_name_parameter(self, template: Dict[str, Any], new_agent_name: str) -> Dict[str, Any]:
        """
        Modify the AgentName parameter default value in the template.
        
        Args:
            template: Original CloudFormation template
            new_agent_name: New agent name to set as default
            
        Returns:
            Modified CloudFormation template
        """
        try:
            # Create a copy of the template to avoid modifying the original
            modified_template = json.loads(json.dumps(template))
            
            # Update the AgentName parameter default value
            if 'Parameters' in modified_template and 'AgentName' in modified_template['Parameters']:
                modified_template['Parameters']['AgentName']['Default'] = new_agent_name
                logger.info(f"Updated AgentName parameter default to: {new_agent_name}")
            else:
                logger.warning("AgentName parameter not found in template")
            
            return modified_template
            
        except Exception as e:
            log_exception_safely(logger, e, "Error modifying template")
            raise RuntimeError("Failed to modify template")
    
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
            
            return {
                'stack_name': stack_info['stack_name'],
                'stack_id': stack_info['stack_id'],
                'status': stack_info['status'],
                'agent_name': agent_name,
                'created_at': stack_info.get('creation_time'),
                'updated_at': stack_info.get('last_updated_time'),
                'outputs': outputs if outputs else None
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
    
    async def find_agent_stack_by_name(self, agent_name: str) -> Optional[Dict[str, Any]]:
        """
        Find a CloudFormation stack for a specific agent using multiple naming patterns.
        
        This method checks multiple possible naming patterns:
        1. ai-platform-agent-{agent-name} (actual pattern used by the system)
        2. ai-platform-{agent-name}-stack (legacy pattern)
        3. {project-name}-{agent-name}-stack (fallback pattern)
        
        Args:
            agent_name: Name of the agent to find stack for
            
        Returns:
            Stack information if found, None otherwise
        """
        try:
            # Convert agent name to the expected stack format
            stack_agent_name = agent_name.replace('_', '-')
            
            # Try multiple naming patterns
            possible_stack_names = [
                f"ai-platform-agent-{stack_agent_name}",  # Actual pattern from AWS CLI output
                f"{self.project_name}-agent-{stack_agent_name}",  # Project-based agent pattern
                f"ai-platform-{stack_agent_name}-stack",  # Original expected pattern
                f"{self.project_name}-{stack_agent_name}-stack"  # Project-based legacy pattern
            ]
            
            logger.info(f"Looking for agent stack using multiple patterns: {possible_stack_names}")
            
            for expected_stack_name in possible_stack_names:
                try:
                    logger.info(f"Trying stack name pattern: {expected_stack_name}")
                    
                    # Try to get the stack directly using this pattern
                    stack_info = await self._get_stack_info(expected_stack_name)
                    
                    # Verify this stack has the correct AgentName parameter
                    stack_agent_name_param = None
                    for param in stack_info.get('parameters', []):
                        if param['ParameterKey'] == 'AgentName':
                            stack_agent_name_param = param['ParameterValue']
                            break
                    
                    if stack_agent_name_param == agent_name:
                        logger.info(f"✅ Found exact match: {expected_stack_name} with AgentName={agent_name}")
                        
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
                        continue
                        
                except ValueError:
                    # Stack not found with this pattern, try next pattern
                    logger.debug(f"No stack found with pattern: {expected_stack_name}")
                    continue
            
            # If we get here, no stack was found with any pattern
            logger.info(f"No stack found for agent '{agent_name}' using any naming pattern")
            return None
                
        except Exception as e:
            log_exception_safely(logger, e, f"Error finding agent stack for '{agent_name}'")
            return None
    
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
