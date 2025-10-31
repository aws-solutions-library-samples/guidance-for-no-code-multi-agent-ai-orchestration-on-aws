#!/usr/bin/env python3
"""
Lambda function to create CloudWatch Logs data protection policies.
This is deployed as a custom resource since AWS::Logs::DataProtectionPolicy 
doesn't exist in CloudFormation.
"""

import json
import boto3
import logging
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Lambda handler for data protection policy custom resource.
    
    Args:
        event: CloudFormation custom resource event
        context: Lambda context
        
    Returns:
        Response for CloudFormation
    """
    
    try:
        # Extract event details
        request_type = event['RequestType']
        resource_properties = event.get('ResourceProperties', {})
        log_group_identifier = resource_properties.get('LogGroupIdentifier')
        policy_document = resource_properties.get('PolicyDocument')
        
        logger.info(f"Request type: {request_type}")
        logger.info(f"Log group: {log_group_identifier}")
        
        # Initialize CloudWatch Logs client
        logs_client = boto3.client('logs')
        
        if request_type in ['Create', 'Update']:
            # Create or update data protection policy
            response = logs_client.put_data_protection_policy(
                logGroupIdentifier=log_group_identifier,
                policyDocument=policy_document
            )
            
            physical_resource_id = f"DataProtectionPolicy-{log_group_identifier}"
            
            logger.info(f"Successfully applied data protection policy to {log_group_identifier}")
            
            return {
                'Status': 'SUCCESS',
                'PhysicalResourceId': physical_resource_id,
                'Data': {
                    'PolicyId': response.get('policyDocument', ''),
                    'LogGroupIdentifier': log_group_identifier
                }
            }
            
        elif request_type == 'Delete':
            # Delete data protection policy
            try:
                logs_client.delete_data_protection_policy(
                    logGroupIdentifier=log_group_identifier
                )
                logger.info(f"Successfully deleted data protection policy from {log_group_identifier}")
            except logs_client.exceptions.ResourceNotFoundException:
                # Policy doesn't exist, which is fine for deletion
                logger.info(f"Data protection policy not found for {log_group_identifier}, nothing to delete")
            
            return {
                'Status': 'SUCCESS',
                'PhysicalResourceId': event.get('PhysicalResourceId', f"DataProtectionPolicy-{log_group_identifier}")
            }
        
        else:
            logger.error(f"Unknown request type: {request_type}")
            return {
                'Status': 'FAILED',
                'Reason': f'Unknown request type: {request_type}',
                'PhysicalResourceId': event.get('PhysicalResourceId', 'unknown')
            }
    
    except Exception as e:
        logger.error(f"Error in data protection policy handler: {str(e)}", exc_info=True)
        return {
            'Status': 'FAILED',
            'Reason': str(e),
            'PhysicalResourceId': event.get('PhysicalResourceId', 'unknown')
        }

# For testing locally
if __name__ == "__main__":
    # Test event structure
    test_event = {
        'RequestType': 'Create',
        'ResourceProperties': {
            'LogGroupIdentifier': 'test-log-group',
            'PolicyDocument': '{"Version":"2021-06-01","Statement":[]}'
        }
    }
    
    result = lambda_handler(test_event, None)
    print(json.dumps(result, indent=2))
