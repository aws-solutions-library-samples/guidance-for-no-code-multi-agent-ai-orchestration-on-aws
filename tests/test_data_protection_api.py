#!/usr/bin/env python3
"""
Test script to validate data protection policy with AWS API.
"""

import json
import boto3
from helper.config import Config
from stacks.data_protection import (
    ManagedDataIdentifierRegistry,
    get_custom_platform_identifiers
)

def test_data_protection_policy():
    """Test data protection policy creation with actual AWS API."""
    
    try:
        config = Config('development')
        region = 'us-east-1'
        account = '594154372526'
        
        # Build the policy exactly as the CDK code does
        managed_identifier_names = config.get_data_protection_managed_identifiers()
        managed_identifiers = []
        
        for identifier_name in managed_identifier_names:
            identifier = ManagedDataIdentifierRegistry.get_identifier_by_name(
                identifier_name, region
            )
            if identifier:
                managed_identifiers.append({
                    "Name": identifier_name,
                    "Arn": identifier.arn
                })
        
        # Get custom identifiers
        custom_identifier_names = config.get_data_protection_custom_identifiers()
        custom_identifiers = []
        platform_identifiers = get_custom_platform_identifiers()
        
        for custom_name in custom_identifier_names:
            for custom_id in platform_identifiers:
                if custom_id.name == custom_name:
                    custom_identifiers.append({
                        "Name": custom_id.name,
                        "DataIdentifier": {
                            "Regex": custom_id.regex,
                            "Keywords": custom_id.keywords or [],
                            "IgnoreWords": custom_id.ignore_words or [],
                            "MaximumMatchDistance": custom_id.maximum_match_distance or 50
                        }
                    })
                    break
        
        all_data_identifiers = managed_identifiers + custom_identifiers
        
        # Create audit log group ARN
        audit_log_group_name = config.get_audit_findings_log_group_name()
        audit_log_group_arn = f"arn:aws:logs:{region}:{account}:log-group:{audit_log_group_name}"
        
        # Create simplified policy - just with managed identifiers first
        simple_policy_document = {
            "Name": "SimplePlatformDataProtectionPolicy",
            "Description": "Simplified data protection policy for testing",
            "Version": "2021-06-01",
            "Statement": [
                {
                    "Sid": "audit-policy",
                    "DataIdentifier": managed_identifiers[:3],  # Only first 3 managed identifiers
                    "Operation": {
                        "Audit": {
                            "FindingsDestination": {
                                "CloudWatchLogs": {
                                    "LogGroup": audit_log_group_arn
                                }
                            }
                        }
                    }
                }
            ]
        }
        
        policy_json = json.dumps(simple_policy_document, indent=2)
        
        print("=== Testing Simple Policy ===")
        print(f"Policy size: {len(policy_json)} bytes")
        print("Policy JSON:")
        print(policy_json)
        
        # Try to validate with AWS API (dry run)
        print("\n=== Testing AWS API Call ===")
        logs_client = boto3.client('logs', region_name=region)
        
        # Test if the log group exists
        try:
            response = logs_client.describe_log_groups(
                logGroupNamePrefix="agentic-ai-platform-logs"
            )
            log_groups = response.get('logGroups', [])
            if log_groups:
                print(f"✅ Log group exists: {log_groups[0]['logGroupName']}")
                log_group_identifier = log_groups[0]['logGroupName']
            else:
                print("❌ Log group does not exist")
                return False
                
        except Exception as e:
            print(f"❌ Error checking log group: {str(e)}")
            return False
        
        # Test the policy format with AWS
        try:
            print(f"\n=== Attempting to apply policy to {log_group_identifier} ===")
            response = logs_client.put_data_protection_policy(
                logGroupIdentifier=log_group_identifier,
                policyDocument=policy_json
            )
            print("✅ Data protection policy applied successfully!")
            print(f"Response: {response}")
            
            # Clean up - delete the test policy
            print("\n=== Cleaning up test policy ===")
            logs_client.delete_data_protection_policy(
                logGroupIdentifier=log_group_identifier
            )
            print("✅ Test policy deleted successfully")
            return True
            
        except Exception as e:
            print(f"❌ Error applying policy: {str(e)}")
            print("This shows the exact API error that CDK is encountering")
            
            # Try an even simpler policy
            print("\n=== Trying minimal policy ===")
            minimal_policy = {
                "Name": "MinimalTestPolicy",
                "Description": "Minimal policy for testing",
                "Version": "2021-06-01",
                "Statement": [
                    {
                        "Sid": "audit-policy",
                        "DataIdentifier": [managed_identifiers[0]],  # Just one identifier
                        "Operation": {
                            "Audit": {
                                "FindingsDestination": {}
                            }
                        }
                    }
                ]
            }
            
            minimal_json = json.dumps(minimal_policy, indent=2)
            print("Minimal policy:")
            print(minimal_json)
            
            try:
                response = logs_client.put_data_protection_policy(
                    logGroupIdentifier=log_group_identifier,
                    policyDocument=minimal_json
                )
                print("✅ Minimal policy worked!")
                
                # Clean up
                logs_client.delete_data_protection_policy(
                    logGroupIdentifier=log_group_identifier
                )
                print("✅ Minimal policy cleaned up")
                return True
                
            except Exception as e2:
                print(f"❌ Even minimal policy failed: {str(e2)}")
                return False
            
    except Exception as e:
        print(f"❌ Script error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_data_protection_policy()
