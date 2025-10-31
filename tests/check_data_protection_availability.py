#!/usr/bin/env python3
"""
Check data protection availability and identifiers in the region.
"""

import json
import boto3

def check_data_protection_availability():
    """Check what data protection features are available."""
    
    try:
        logs_client = boto3.client('logs', region_name='us-east-1')
        
        # Check if we can list data identifiers (this API might not exist)
        print("=== Checking Data Protection Availability ===")
        
        # Try to see if there are any existing data protection policies
        try:
            print("\n=== Checking existing log groups with data protection ===")
            response = logs_client.describe_log_groups()
            
            for lg in response.get('logGroups', []):
                dp_status = lg.get('dataProtectionStatus')
                if dp_status:
                    print(f"Log group {lg['logGroupName']}: {dp_status}")
                    
        except Exception as e:
            print(f"❌ Error checking log groups: {str(e)}")
        
        # Try a very basic policy without audit destination
        print("\n=== Testing basic policy without audit destination ===")
        basic_policy = {
            "Name": "BasicTestPolicy",
            "Description": "Basic test policy",
            "Version": "2021-06-01",
            "Statement": [
                {
                    "Sid": "basic-audit",
                    "DataIdentifier": ["EmailAddress"],
                    "Operation": {
                        "Audit": {
                            "FindingsDestination": {}
                        }
                    }
                }
            ]
        }
        
        policy_json = json.dumps(basic_policy, indent=2)
        print("Basic policy JSON:")
        print(policy_json)
        
        log_group_name = "agentic-ai-platform-logs"
        
        try:
            response = logs_client.put_data_protection_policy(
                logGroupIdentifier=log_group_name,
                policyDocument=policy_json
            )
            print("✅ Basic policy applied successfully!")
            
            # Check status
            describe_response = logs_client.describe_log_groups(
                logGroupNamePrefix=log_group_name
            )
            
            for lg in describe_response.get('logGroups', []):
                if lg['logGroupName'] == log_group_name:
                    print(f"✅ Data protection status: {lg.get('dataProtectionStatus', 'None')}")
            
            return True
            
        except Exception as e:
            print(f"❌ Basic policy failed: {str(e)}")
            
            # Check if the error gives us more info about valid identifiers
            error_message = str(e)
            if "not a valid Data Identifier" in error_message:
                print("\n=== Data identifiers might not be available in this region ===")
                print("This could mean:")
                print("1. Data protection feature is not enabled for this account")
                print("2. Region doesn't support data protection")
                print("3. Additional setup is required")
                
                # Check region support
                print(f"\nCurrent region: us-east-1")
                print("Data protection should be supported in us-east-1")
                
            return False
            
    except Exception as e:
        print(f"❌ Script error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    check_data_protection_availability()
