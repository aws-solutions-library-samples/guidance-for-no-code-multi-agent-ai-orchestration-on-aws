#!/usr/bin/env python3
"""
Debug script for data protection policy creation.
"""

import json
import sys
import os
from helper.config import Config
from stacks.data_protection import (
    ManagedDataIdentifierRegistry,
    get_custom_platform_identifiers
)

def debug_data_protection():
    """Debug data protection policy creation logic."""
    print("=== Data Protection Policy Debug ===\n")
    
    try:
        # Initialize config
        config = Config('development')
        region = 'us-east-1'
        account = '594154372526'  # From the deployment outputs
        
        print("✅ Config loaded")
        print(f"✅ Data protection enabled: {config.is_data_protection_enabled()}")
        print(f"✅ Managed identifiers: {config.get_data_protection_managed_identifiers()}")
        print(f"✅ Custom identifiers: {config.get_data_protection_custom_identifiers()}")
        print(f"✅ Audit log group: {config.get_audit_findings_log_group_name()}\n")
        
        # Test managed identifiers
        managed_identifier_names = config.get_data_protection_managed_identifiers()
        managed_identifiers = []
        
        print("=== Processing Managed Identifiers ===")
        for identifier_name in managed_identifier_names:
            identifier = ManagedDataIdentifierRegistry.get_identifier_by_name(
                identifier_name, region
            )
            if identifier:
                managed_identifiers.append({
                    "Name": identifier_name,
                    "Arn": identifier.arn
                })
                print(f"✅ {identifier_name}: {identifier.arn}")
            else:
                print(f"❌ Failed to get identifier: {identifier_name}")
        
        print(f"\n✅ Managed identifiers processed: {len(managed_identifiers)}")
        
        # Test custom identifiers
        custom_identifier_names = config.get_data_protection_custom_identifiers()
        custom_identifiers = []
        platform_identifiers = get_custom_platform_identifiers()
        
        print("\n=== Processing Custom Identifiers ===")
        for custom_name in custom_identifier_names:
            found = False
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
                    print(f"✅ {custom_name}: regex pattern defined")
                    found = True
                    break
            
            if not found:
                print(f"❌ Custom identifier not found: {custom_name}")
        
        print(f"\n✅ Custom identifiers processed: {len(custom_identifiers)}")
        
        # Build complete policy
        all_data_identifiers = managed_identifiers + custom_identifiers
        
        if not all_data_identifiers:
            print("❌ No data identifiers found - policy creation would be skipped")
            return False
        
        print(f"\n=== Creating Data Protection Policy ===")
        print(f"✅ Total identifiers: {len(all_data_identifiers)}")
        
        # Create audit findings log group ARN
        audit_log_group_name = config.get_audit_findings_log_group_name()
        audit_log_group_arn = f"arn:aws:logs:{region}:{account}:log-group:{audit_log_group_name}"
        
        # Create the data protection policy document
        policy_document = {
            "Name": "PlatformDataProtectionPolicy-test",
            "Description": "Data protection policy for multi-agent AI platform log group",
            "Version": "2021-06-01", 
            "Statement": [
                {
                    "Sid": "audit-policy",
                    "DataIdentifier": all_data_identifiers,
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
        
        # Test JSON serialization
        policy_json = json.dumps(policy_document, indent=2)
        print(f"✅ Policy JSON created successfully")
        print(f"✅ Policy size: {len(policy_json)} bytes")
        
        # Save policy to file for inspection
        with open('data_protection_policy.json', 'w') as f:
            f.write(policy_json)
        print("✅ Policy saved to data_protection_policy.json")
        
        # Test CloudFormation resource properties
        cfn_properties = {
            "LogGroupIdentifier": "agentic-ai-platform-logs",  # The main shared log group
            "PolicyDocument": policy_json
        }
        
        print(f"\n=== CloudFormation Resource Properties ===")
        print(f"✅ LogGroupIdentifier: {cfn_properties['LogGroupIdentifier']}")
        print(f"✅ PolicyDocument size: {len(cfn_properties['PolicyDocument'])} bytes")
        
        print("\n🎯 Data protection policy creation logic is working correctly!")
        print("🔍 Issue might be in CDK resource creation or CloudFormation deployment")
        
        return True
        
    except Exception as e:
        print(f"❌ Error in data protection debug: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = debug_data_protection()
    sys.exit(0 if success else 1)
