#!/usr/bin/env python3
"""
Check CDK SSM API for SecureString parameter creation with KMS keys.
"""

import aws_cdk.aws_ssm as ssm

def check_ssm_apis():
    """Check available CDK SSM parameter APIs."""
    
    print("=== CDK SSM Parameter APIs ===\n")
    
    # Check StringParameter
    print("StringParameter parameters:")
    help(ssm.StringParameter.__init__)
    
    print("\n" + "="*60 + "\n")
    
    # Check if there's a SecureStringParameter class
    try:
        if hasattr(ssm, 'SecureStringParameter'):
            print("SecureStringParameter parameters:")
            help(ssm.SecureStringParameter.__init__)
        else:
            print("❌ SecureStringParameter class not found")
    except Exception as e:
        print(f"Error checking SecureStringParameter: {e}")
    
    print("\n" + "="*60 + "\n")
    
    # Check CfnParameter (lower level)
    print("CfnParameter parameters:")
    help(ssm.CfnParameter.__init__)
    
    print("\n" + "="*60 + "\n")
    
    # Check what parameter types are available
    print("Available ParameterType values:")
    try:
        if hasattr(ssm, 'ParameterType'):
            for attr_name in dir(ssm.ParameterType):
                if not attr_name.startswith('_'):
                    try:
                        attr_value = getattr(ssm.ParameterType, attr_name)
                        print(f"  - ParameterType.{attr_name} = {attr_value}")
                    except:
                        print(f"  - ParameterType.{attr_name} (property)")
        else:
            print("❌ ParameterType not found")
    except Exception as e:
        print(f"Error checking ParameterType: {e}")
    
    print("\n" + "="*60 + "\n")
    
    # Check ParameterTier
    print("Available ParameterTier values:")
    try:
        if hasattr(ssm, 'ParameterTier'):
            for attr_name in dir(ssm.ParameterTier):
                if not attr_name.startswith('_'):
                    try:
                        attr_value = getattr(ssm.ParameterTier, attr_name)
                        print(f"  - ParameterTier.{attr_name} = {attr_value}")
                    except:
                        print(f"  - ParameterTier.{attr_name} (property)")
        else:
            print("❌ ParameterTier not found")
    except Exception as e:
        print(f"Error checking ParameterTier: {e}")

if __name__ == "__main__":
    check_ssm_apis()
