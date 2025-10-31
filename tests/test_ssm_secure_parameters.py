#!/usr/bin/env python3
"""
Test script to validate SecureString parameter access and KMS decryption.

This script validates:
1. Parameter existence and type (SecureString)
2. KMS decryption capabilities
3. IAM permissions for parameter access
4. Enhanced SSM client functionality
"""

import sys
import os
import json
import logging
from pathlib import Path

# Add the application source to Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "application_src"))

from common.ssm_client import ssm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_parameter_access(parameter_name: str) -> bool:
    """Test access to a specific parameter."""
    logger.info(f"Testing access to parameter: {parameter_name}")
    
    # Test parameter metadata retrieval
    metadata = ssm.get_parameter_metadata(parameter_name)
    if metadata:
        logger.info(f"Parameter metadata: Type={metadata.get('Type')}, Tier={metadata.get('Tier')}")
        
        # Verify it's a SecureString
        if metadata.get('Type') != 'SecureString':
            logger.warning(f"Parameter {parameter_name} is not SecureString type")
            return False
        
        # Verify it's Advanced tier
        if metadata.get('Tier') != 'Advanced':
            logger.warning(f"Parameter {parameter_name} is not Advanced tier")
            return False
            
    else:
        logger.error(f"Could not retrieve metadata for {parameter_name}")
        return False
    
    # Test parameter value retrieval with validation
    if ssm.validate_parameter_access(parameter_name):
        value = ssm.get_parameter(parameter_name)
        if value:
            logger.info(f"Successfully retrieved parameter value (length: {len(value)} characters)")
            
            # Test JSON parsing if it looks like JSON
            if value.strip().startswith('{'):
                try:
                    parsed = json.loads(value)
                    logger.info(f"Parameter contains valid JSON with {len(parsed)} keys")
                except json.JSONDecodeError:
                    logger.warning(f"Parameter value is not valid JSON")
            
            return True
        else:
            logger.error(f"Retrieved empty value for {parameter_name}")
            return False
    else:
        logger.error(f"Failed parameter access validation for {parameter_name}")
        return False


def test_parameters_by_path(path: str) -> bool:
    """Test retrieval of parameters by path."""
    logger.info(f"Testing parameter retrieval by path: {path}")
    
    parameters = ssm.get_parameters_by_path(path, recursive=True)
    
    if parameters:
        logger.info(f"Successfully retrieved {len(parameters)} parameters from path {path}")
        
        # Check that all parameters are accessible
        for param_name in parameters.keys():
            metadata = ssm.get_parameter_metadata(param_name)
            if metadata and metadata.get('Type') == 'SecureString':
                logger.info(f"Confirmed SecureString parameter: {param_name}")
            else:
                logger.warning(f"Parameter {param_name} is not SecureString")
        
        return True
    else:
        logger.error(f"No parameters found at path {path}")
        return False


def main():
    """Main test function."""
    logger.info("Starting SecureString parameter validation tests")
    
    # Test configuration - these should match your actual parameter names
    # Update these based on your environment configuration
    agent_name = os.environ.get('AGENT_NAME', 'qa_agent')
    supervisor_agent_name = os.environ.get('SUPERVISOR_AGENT_NAME', 'supervisor_agent')
    
    test_parameters = [
        f"/agent/{agent_name}/config",
        f"/agent/{agent_name}/system-prompts/index",
        f"/agent/{agent_name}/system-prompts/qa",
        f"/agent/{supervisor_agent_name}/config",
        f"/agent/{supervisor_agent_name}/system-prompts/index",
        f"/agent/{supervisor_agent_name}/system-prompts/supervisor"
    ]
    
    test_paths = [
        f"/agent/{agent_name}",
        f"/agent/{supervisor_agent_name}",
        f"/agent/{agent_name}/system-prompts",
        f"/agent/{supervisor_agent_name}/system-prompts"
    ]
    
    results = {
        'parameter_tests': {},
        'path_tests': {},
        'cache_stats': {}
    }
    
    # Test individual parameter access
    logger.info("=" * 50)
    logger.info("TESTING INDIVIDUAL PARAMETER ACCESS")
    logger.info("=" * 50)
    
    for param in test_parameters:
        try:
            results['parameter_tests'][param] = test_parameter_access(param)
        except Exception as e:
            logger.error(f"Exception testing parameter {param}: {str(e)}")
            results['parameter_tests'][param] = False
    
    # Test path-based parameter retrieval
    logger.info("=" * 50)
    logger.info("TESTING PATH-BASED PARAMETER RETRIEVAL")
    logger.info("=" * 50)
    
    for path in test_paths:
        try:
            results['path_tests'][path] = test_parameters_by_path(path)
        except Exception as e:
            logger.error(f"Exception testing path {path}: {str(e)}")
            results['path_tests'][path] = False
    
    # Get cache statistics
    results['cache_stats'] = ssm.get_cache_stats()
    
    # Summary
    logger.info("=" * 50)
    logger.info("TEST SUMMARY")
    logger.info("=" * 50)
    
    param_passed = sum(1 for v in results['parameter_tests'].values() if v)
    param_total = len(results['parameter_tests'])
    path_passed = sum(1 for v in results['path_tests'].values() if v)
    path_total = len(results['path_tests'])
    
    logger.info(f"Individual parameter tests: {param_passed}/{param_total} passed")
    logger.info(f"Path-based tests: {path_passed}/{path_total} passed")
    logger.info(f"Cache statistics: {results['cache_stats']}")
    
    # Return overall success
    all_passed = (param_passed == param_total) and (path_passed == path_total)
    
    if all_passed:
        logger.info("✅ ALL TESTS PASSED - SecureString parameters are working correctly!")
    else:
        logger.error("❌ SOME TESTS FAILED - Check IAM permissions and KMS key access")
        
        # Print detailed failure information
        logger.error("Failed parameter tests:")
        for param, result in results['parameter_tests'].items():
            if not result:
                logger.error(f"  - {param}")
                
        logger.error("Failed path tests:")
        for path, result in results['path_tests'].items():
            if not result:
                logger.error(f"  - {path}")
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
