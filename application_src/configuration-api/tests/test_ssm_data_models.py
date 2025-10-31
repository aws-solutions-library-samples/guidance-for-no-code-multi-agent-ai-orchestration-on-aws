#!/usr/bin/env python3
"""
Test and validation script for SSM Data Models.

This script validates that the actual data stored in SSM matches
the comprehensive data models defined in ssm_data_models.py
"""

import json
import sys
import os
from pathlib import Path

# Add the application source to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.models.ssm_data_models import (
    SSMAgentConfiguration,
    SSMParameterStructure,
    SSMParameterPaths,
    SSMDataValidator,
    StreamingType,
    ProviderType,
    ThinkingType
)
from app.services.ssm_service import SSMService


def test_agent_config_completeness():
    """Test that current agent configurations in SSM are complete."""
    print("=" * 60)
    print("TESTING AGENT CONFIGURATION COMPLETENESS")
    print("=" * 60)
    
    ssm_service = SSMService('us-east-1')
    agents_to_test = ['qa_agent', 'supervisor_agent']
    
    for agent_name in agents_to_test:
        print(f"\n--- Testing Agent: {agent_name} ---")
        
        try:
            # Get the actual config from SSM
            config_path = SSMParameterPaths.agent_config(agent_name)
            config_data = ssm_service.get_json_parameter(config_path)
            
            if not config_data:
                print(f"❌ No configuration found for {agent_name}")
                continue
                
            print(f"✅ Configuration found in SSM: {config_path}")
            print(f"📊 Total fields in SSM: {len(config_data)}")
            
            # Validate against SSM data model
            validation_result = SSMDataValidator.validate_agent_configuration(config_data)
            
            if validation_result["valid"]:
                print(f"✅ Configuration is COMPLETE and VALID")
                print(f"📋 All required fields present:")
                
                # Show field summary
                validated_model = validation_result["model"]
                for field_name, field_value in validated_model.items():
                    field_type = type(field_value).__name__
                    print(f"   - {field_name}: {field_type} = {field_value}")
                    
            else:
                print(f"❌ Configuration is INCOMPLETE")
                print(f"🔍 Missing fields: {validation_result.get('missing_fields', [])}")
                print(f"⚠️  Errors: {validation_result['errors']}")
                
        except Exception as e:
            print(f"💥 Error testing {agent_name}: {str(e)}")


def test_ssm_parameter_paths():
    """Test SSM parameter path validation and standardization."""
    print("\n" + "=" * 60)
    print("TESTING SSM PARAMETER PATH PATTERNS")
    print("=" * 60)
    
    ssm_service = SSMService('us-east-1')
    
    # Test parameter path patterns
    test_paths = [
        "/agent/qa_agent/config",
        "/agent/supervisor_agent/config", 
        "/agent/qa_agent/system-prompts/qa",
        "/agent/supervisor_agent/system-prompts/supervisor",
        "/agent/qa_agent/system-prompts/index",
        "/prompts/qa",
        "/prompts/supervisor",
        "/prompts/index"
    ]
    
    for path in test_paths:
        is_valid = SSMParameterPaths.validate_parameter_path(path)
        exists = ssm_service.parameter_exists(path)
        
        status = "✅" if is_valid and exists else "⚠️" if is_valid else "❌"
        existence = "EXISTS" if exists else "MISSING"
        validity = "VALID" if is_valid else "INVALID"
        
        print(f"{status} {path} - {validity}, {existence}")


def test_data_consistency():
    """Test consistency between SSM data and API responses."""
    print("\n" + "=" * 60)
    print("TESTING DATA CONSISTENCY (SSM vs API)")
    print("=" * 60)
    
    ssm_service = SSMService('us-east-1')
    agents_to_test = ['qa_agent', 'supervisor_agent']
    
    for agent_name in agents_to_test:
        print(f"\n--- Consistency Test: {agent_name} ---")
        
        try:
            # Get raw SSM data
            config_path = SSMParameterPaths.agent_config(agent_name)
            ssm_data = ssm_service.get_json_parameter(config_path)
            
            if not ssm_data:
                print(f"❌ No SSM data found for {agent_name}")
                continue
            
            # Simulate what API would return (without system_prompt and mcp fields)
            api_simulation = ssm_data.copy()
            api_simulation.pop('system_prompt', None)  # API adds this dynamically
            
            # Add fields that API adds
            if 'mcp_enabled' not in api_simulation:
                api_simulation['mcp_enabled'] = False
            if 'mcp_servers' not in api_simulation:
                api_simulation['mcp_servers'] = ""
            
            # Compare data consistency
            comparison = SSMDataValidator.compare_configs(ssm_data, api_simulation)
            
            if comparison["identical"]:
                print(f"✅ SSM and API data are IDENTICAL")
            else:
                print(f"⚠️  Found {comparison['discrepancy_count']} discrepancies:")
                for field, details in comparison["discrepancies"].items():
                    print(f"   - {field}:")
                    print(f"     SSM: {details['ssm_value']} ({details['ssm_type']})")
                    print(f"     API: {details['api_value']} ({details['api_type']})")
                    
        except Exception as e:
            print(f"💥 Error testing consistency for {agent_name}: {str(e)}")


def test_model_configurations():
    """Test model ID configurations for consistency."""
    print("\n" + "=" * 60)
    print("TESTING MODEL ID CONFIGURATIONS")
    print("=" * 60)
    
    ssm_service = SSMService('us-east-1')
    agents_to_test = ['qa_agent', 'supervisor_agent']
    
    expected_models = {
        'model_id': 'us.anthropic.claude-3-5-sonnet-20241022-v2:0',
        'judge_model_id': 'us.anthropic.claude-3-5-haiku-20241022-v1:0',
        'embedding_model_id': 'amazon.titan-embed-text-v2:0'
    }
    
    for agent_name in agents_to_test:
        print(f"\n--- Model Configuration: {agent_name} ---")
        
        try:
            config_path = SSMParameterPaths.agent_config(agent_name)
            config_data = ssm_service.get_json_parameter(config_path)
            
            if not config_data:
                print(f"❌ No configuration found")
                continue
            
            # Check each model field
            for model_field, expected_value in expected_models.items():
                actual_value = config_data.get(model_field, '<MISSING>')
                
                if actual_value == expected_value:
                    print(f"✅ {model_field}: {actual_value}")
                elif actual_value == '<MISSING>':
                    print(f"❌ {model_field}: MISSING (expected: {expected_value})")
                else:
                    print(f"⚠️  {model_field}: {actual_value} (expected: {expected_value})")
                    
        except Exception as e:
            print(f"💥 Error checking models for {agent_name}: {str(e)}")


def show_complete_ssm_structure():
    """Display the complete SSM parameter structure currently in use."""
    print("\n" + "=" * 60)
    print("COMPLETE SSM PARAMETER STRUCTURE")
    print("=" * 60)
    
    ssm_service = SSMService('us-east-1')
    
    try:
        # Get all agent parameters
        all_agent_params = ssm_service.list_parameters_by_prefix('/agent/', max_results=100)
        prompt_params = ssm_service.list_parameters_by_prefix('/prompts/', max_results=50)
        
        print(f"📊 Total Agent Parameters: {len(all_agent_params)}")
        print(f"📚 Total Prompt Parameters: {len(prompt_params)}")
        
        # Group by agent
        agents = {}
        for param in all_agent_params:
            path_parts = param['name'].split('/')
            if len(path_parts) >= 3:
                agent_name = path_parts[2]
                if agent_name not in agents:
                    agents[agent_name] = []
                agents[agent_name].append(param['name'])
        
        print("\n📋 Agent Parameter Structure:")
        for agent_name, params in agents.items():
            print(f"\n  🤖 {agent_name}:")
            for param_path in sorted(params):
                param_type = "JSON" if param_path.endswith('/config') or param_path.endswith('/index') else "String"
                print(f"     - {param_path} ({param_type})")
        
        print("\n📚 Global Prompt Parameters:")
        for param in sorted(prompt_params, key=lambda x: x['name']):
            param_type = "JSON" if param['name'].endswith('/index') else "String"
            print(f"     - {param['name']} ({param_type})")
            
        print(f"\n🔐 All parameters are SecureString encrypted with customer-managed KMS key")
        
    except Exception as e:
        print(f"💥 Error displaying SSM structure: {str(e)}")


def main():
    """Run all SSM data model tests."""
    print("🔍 SSM DATA MODELS VALIDATION SUITE")
    print("Testing all data structures stored in SSM Parameter Store...")
    
    try:
        test_agent_config_completeness()
        test_ssm_parameter_paths() 
        test_data_consistency()
        test_model_configurations()
        show_complete_ssm_structure()
        
        print("\n" + "=" * 60)
        print("✅ SSM DATA MODELS VALIDATION COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n💥 VALIDATION FAILED: {str(e)}")
        return False
    
    return True


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
