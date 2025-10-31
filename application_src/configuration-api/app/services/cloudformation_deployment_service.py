"""
CloudFormation Deployment Service

Manages dynamic agent stack deployment using CloudFormation API directly.
Replaces subprocess-based CDK deployment with native CloudFormation operations.

Key Features:
- Downloads CloudFormation templates from S3
- Creates/updates/deletes agent stacks with proper tagging
- Monitors deployment status with comprehensive error handling
- Provides deployment metadata and outputs
"""

import logging
import time
import json
from typing import Any
from datetime import datetime, timezone

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../'))
from common.secure_logging_utils import log_exception_safely

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class CloudFormationDeploymentService:
    """Service for managing CloudFormation stack deployments."""
    
    def __init__(
        self,
        region: str,
        project_name: str,
        template_bucket: str
    ):
        """
        Initialize CloudFormation deployment service.
        
        Args:
            region: AWS region for deployments
            project_name: Project name for stack naming
            template_bucket: S3 bucket containing CloudFormation templates
        """
        self.region = region
        self.project_name = project_name
        self.template_bucket = template_bucket
        
        # Initialize AWS clients
        self.cfn_client = boto3.client('cloudformation', region_name=region)
        self.s3_client = boto3.client('s3', region_name=region)
        
        logger.info(
            f"Initialized CloudFormation service: region={region}, "
            f"project={project_name}, bucket={template_bucket}"
        )
    
    def deploy_agent_stack(
        self,
        agent_name: str,
        parameters: dict[str, Any],
        timeout_minutes: int = 30
    ) -> dict[str, Any]:
        """
        Deploy a new agent stack using CloudFormation.
        
        Args:
            agent_name: Name of the agent
            parameters: CloudFormation parameters for the stack
            timeout_minutes: Maximum time to wait for deployment
            
        Returns:
            Deployment result with stack outputs and metadata
            
        Raises:
            RuntimeError: If deployment fails
        """
        stack_name = self._get_stack_name(agent_name)
        template_key = "GenericAgentTemplate.json"
        
        logger.info(f"Starting deployment of agent stack: {stack_name}")
        
        try:
            # Download template from S3
            template_body = self._download_template(template_key)
            
            # Prepare CloudFormation parameters
            cfn_parameters = self._convert_parameters(parameters)
            
            # Create stack with proper tags
            self.cfn_client.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cfn_parameters,
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM'],
                Tags=[
                    {'Key': 'ManagedBy', 'Value': 'ConfigurationAPI'},
                    {'Key': 'ProjectName', 'Value': self.project_name},
                    {'Key': 'AgentName', 'Value': agent_name},
                    {'Key': 'DeployedAt', 'Value': datetime.now(timezone.utc).isoformat()}
                ],
                TimeoutInMinutes=timeout_minutes
            )
            
            logger.info(f"CloudFormation stack creation initiated: {stack_name}")
            
            # Wait for stack creation to complete
            result = self._wait_for_stack_complete(stack_name, 'CREATE_COMPLETE', timeout_minutes)
            
            logger.info(f"Agent stack deployed successfully: {stack_name}")
            return result
            
        except ClientError as e:
            log_exception_safely(logger, e, f"Failed to deploy agent stack {stack_name}")
            raise RuntimeError(f"Failed to deploy agent stack {stack_name}") from e
    
    def update_agent_stack(
        self,
        agent_name: str,
        parameters: dict[str, Any],
        timeout_minutes: int = 30
    ) -> dict[str, Any]:
        """
        Update an existing agent stack.
        
        Args:
            agent_name: Name of the agent
            parameters: CloudFormation parameters for the stack
            timeout_minutes: Maximum time to wait for update
            
        Returns:
            Update result with stack outputs and metadata
            
        Raises:
            RuntimeError: If update fails
        """
        stack_name = self._get_stack_name(agent_name)
        template_key = "GenericAgentTemplate.json"
        
        logger.info(f"Starting update of agent stack: {stack_name}")
        
        try:
            # Download template from S3
            template_body = self._download_template(template_key)
            
            # Prepare CloudFormation parameters
            cfn_parameters = self._convert_parameters(parameters)
            
            # Update stack
            self.cfn_client.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cfn_parameters,
                Capabilities=['CAPABILITY_IAM', 'CAPABILITY_NAMED_IAM']
            )
            
            logger.info(f"CloudFormation stack update initiated: {stack_name}")
            
            # Wait for stack update to complete
            result = self._wait_for_stack_complete(stack_name, 'UPDATE_COMPLETE', timeout_minutes)
            
            logger.info(f"Agent stack updated successfully: {stack_name}")
            return result
            
        except ClientError as e:
            if 'No updates are to be performed' in str(e):
                logger.info(f"No updates needed for stack: {stack_name}")
                return self.get_stack_info(agent_name)
            
            log_exception_safely(logger, e, f"Failed to update agent stack {stack_name}")
            raise RuntimeError(f"Failed to update agent stack {stack_name}") from e
    
    def delete_agent_stack(
        self,
        agent_name: str,
        timeout_minutes: int = 30
    ) -> dict[str, Any]:
        """
        Delete an agent stack.
        
        Args:
            agent_name: Name of the agent
            timeout_minutes: Maximum time to wait for deletion
            
        Returns:
            Deletion result with metadata
            
        Raises:
            RuntimeError: If deletion fails
        """
        stack_name = self._get_stack_name(agent_name)
        
        logger.info(f"Starting deletion of agent stack: {stack_name}")
        
        try:
            # Delete stack
            self.cfn_client.delete_stack(StackName=stack_name)
            
            logger.info(f"CloudFormation stack deletion initiated: {stack_name}")
            
            # Wait for stack deletion to complete
            self._wait_for_stack_delete(stack_name, timeout_minutes)
            
            logger.info(f"Agent stack deleted successfully: {stack_name}")
            
            return {
                'stack_name': stack_name,
                'agent_name': agent_name,
                'status': 'DELETE_COMPLETE',
                'deleted_at': datetime.now(timezone.utc).isoformat()
            }
            
        except ClientError as e:
            log_exception_safely(logger, e, f"Failed to delete agent stack {stack_name}")
            raise RuntimeError(f"Failed to delete agent stack {stack_name}") from e
    
    def get_stack_info(self, agent_name: str) -> dict[str, Any]:
        """
        Get information about an agent stack.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Stack information with outputs and metadata
            
        Raises:
            RuntimeError: If stack not found or error occurs
        """
        stack_name = self._get_stack_name(agent_name)
        
        try:
            response = self.cfn_client.describe_stacks(StackName=stack_name)
            
            if not response.get('Stacks'):
                raise RuntimeError(f"Stack not found: {stack_name}")
            
            stack = response['Stacks'][0]
            
            return {
                'stack_name': stack_name,
                'agent_name': agent_name,
                'stack_id': stack.get('StackId'),
                'status': stack.get('StackStatus'),
                'creation_time': stack.get('CreationTime').isoformat() if stack.get('CreationTime') else None,
                'last_updated_time': stack.get('LastUpdatedTime').isoformat() if stack.get('LastUpdatedTime') else None,
                'outputs': self._parse_stack_outputs(stack.get('Outputs', []))
            }
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'ValidationError':
                raise RuntimeError(f"Stack not found: {stack_name}") from e
            
            log_exception_safely(logger, e, f"Failed to get stack info for {stack_name}")
            raise RuntimeError(f"Failed to get stack info for {stack_name}") from e
    
    def list_agent_stacks(self) -> list[dict[str, Any]]:
        """
        List all agent stacks managed by this service.
        
        Returns:
            List of stack summaries
        """
        try:
            stacks = []
            paginator = self.cfn_client.get_paginator('list_stacks')
            
            for page in paginator.paginate(
                StackStatusFilter=[
                    'CREATE_COMPLETE',
                    'UPDATE_COMPLETE',
                    'UPDATE_ROLLBACK_COMPLETE'
                ]
            ):
                for stack in page['StackSummaries']:
                    stack_name = stack['StackName']
                    
                    # Only include stacks managed by this project
                    if stack_name.startswith(f"{self.project_name}-agent-"):
                        stacks.append({
                            'stack_name': stack_name,
                            'agent_name': self._extract_agent_name(stack_name),
                            'status': stack['StackStatus'],
                            'creation_time': stack['CreationTime'].isoformat() if stack.get('CreationTime') else None,
                            'last_updated_time': stack.get('LastUpdatedTime').isoformat() if stack.get('LastUpdatedTime') else None
                        })
            
            return stacks
            
        except ClientError as e:
            log_exception_safely(logger, e, "Failed to list agent stacks")
            raise RuntimeError("Failed to list agent stacks") from e
    
    def _get_stack_name(self, agent_name: str) -> str:
        """Generate CloudFormation stack name for agent."""
        return f"{self.project_name}-agent-{agent_name}"
    
    def _extract_agent_name(self, stack_name: str) -> str:
        """Extract agent name from stack name."""
        prefix = f"{self.project_name}-agent-"
        if stack_name.startswith(prefix):
            return stack_name[len(prefix):]
        return stack_name
    
    def _download_template(self, template_key: str) -> str:
        """
        Download CloudFormation template from S3.
        
        Args:
            template_key: S3 object key for template
            
        Returns:
            Template body as string
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.template_bucket,
                Key=template_key
            )
            
            template_body = response['Body'].read().decode('utf-8')
            logger.info(f"Downloaded template: {template_key}")
            
            return template_body
            
        except ClientError as e:
            log_exception_safely(logger, e, f"Failed to download template {template_key}")
            raise RuntimeError(f"Failed to download template {template_key}") from e
    
    def _convert_parameters(self, parameters: dict[str, Any]) -> list[dict[str, str]]:
        """
        Convert dictionary parameters to CloudFormation format.
        
        Args:
            parameters: Dictionary of parameter name -> value
            
        Returns:
            List of CloudFormation parameter dicts
        """
        cfn_parameters = []
        
        for key, value in parameters.items():
            cfn_parameters.append({
                'ParameterKey': key,
                'ParameterValue': str(value)
            })
        
        return cfn_parameters
    
    def _parse_stack_outputs(self, outputs: list[dict[str, str]]) -> dict[str, str]:
        """
        Parse CloudFormation stack outputs into a dictionary.
        
        Args:
            outputs: List of output dicts from CloudFormation
            
        Returns:
            Dictionary of output key -> value
        """
        return {
            output['OutputKey']: output['OutputValue']
            for output in outputs
        }
    
    def _wait_for_stack_complete(
        self,
        stack_name: str,
        expected_status: str,
        timeout_minutes: int
    ) -> dict[str, Any]:
        """
        Wait for stack operation to complete.
        
        Args:
            stack_name: Name of the stack
            expected_status: Expected completion status
            timeout_minutes: Maximum time to wait
            
        Returns:
            Stack information after completion
            
        Raises:
            RuntimeError: If operation fails or times out
        """
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        check_interval = 10  # seconds
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout_seconds:
                raise RuntimeError(
                    f"Stack operation timed out after {timeout_minutes} minutes: {stack_name}"
                )
            
            try:
                response = self.cfn_client.describe_stacks(StackName=stack_name)
                
                if not response.get('Stacks'):
                    raise RuntimeError(f"Stack not found: {stack_name}")
                
                stack = response['Stacks'][0]
                status = stack['StackStatus']
                
                logger.info(f"Stack {stack_name} status: {status}")
                
                # Check if completed successfully
                if status == expected_status:
                    return {
                        'stack_name': stack_name,
                        'agent_name': self._extract_agent_name(stack_name),
                        'status': status,
                        'outputs': self._parse_stack_outputs(stack.get('Outputs', []))
                    }
                
                # Check for failure states (including ROLLBACK_COMPLETE)
                if (status.endswith('_FAILED') or 
                    status == 'ROLLBACK_COMPLETE' or 
                    status == 'ROLLBACK_FAILED' or
                    status == 'DELETE_FAILED'):
                    error_msg = self._get_stack_error_reason(stack_name)
                    logger.error(f"Stack {stack_name} failed with status {status}: {error_msg}")
                    raise RuntimeError(
                        f"Stack operation failed with status {status}: {error_msg}"
                    )
                
                # Still in progress, wait before checking again
                time.sleep(check_interval)
                
            except ClientError as e:
                log_exception_safely(logger, e, "Error checking stack status")
                raise RuntimeError("Error checking stack status") from e
    
    def _wait_for_stack_delete(self, stack_name: str, timeout_minutes: int) -> None:
        """
        Wait for stack deletion to complete.
        
        Args:
            stack_name: Name of the stack
            timeout_minutes: Maximum time to wait
            
        Raises:
            RuntimeError: If deletion fails or times out
        """
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        check_interval = 10  # seconds
        
        while True:
            elapsed = time.time() - start_time
            
            if elapsed > timeout_seconds:
                raise RuntimeError(
                    f"Stack deletion timed out after {timeout_minutes} minutes: {stack_name}"
                )
            
            try:
                response = self.cfn_client.describe_stacks(StackName=stack_name)
                
                if not response.get('Stacks'):
                    # Stack no longer exists - deletion complete
                    logger.info(f"Stack deleted successfully: {stack_name}")
                    return
                
                stack = response['Stacks'][0]
                status = stack['StackStatus']
                
                logger.info(f"Stack {stack_name} deletion status: {status}")
                
                # Check for failure states
                if status == 'DELETE_FAILED':
                    error_msg = self._get_stack_error_reason(stack_name)
                    raise RuntimeError(
                        f"Stack deletion failed: {error_msg}"
                    )
                
                # Still deleting, wait before checking again
                time.sleep(check_interval)
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ValidationError':
                    # Stack no longer exists - deletion complete
                    logger.info(f"Stack deleted successfully: {stack_name}")
                    return
                
                log_exception_safely(logger, e, "Error checking stack deletion status")
                raise RuntimeError("Error checking stack deletion status") from e
    
    def _get_stack_error_reason(self, stack_name: str) -> str:
        """
        Get detailed error reason for stack operation failure.
        
        Args:
            stack_name: Name of the stack
            
        Returns:
            Error message describing the failure
        """
        try:
            response = self.cfn_client.describe_stack_events(StackName=stack_name)
            
            # Find failed events
            for event in response['StackEvents']:
                if event['ResourceStatus'].endswith('_FAILED'):
                    return event.get('ResourceStatusReason', 'Unknown error')
            
            return "No detailed error information available"
            
        except ClientError:
            return "Failed to retrieve error details"
