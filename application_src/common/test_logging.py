#!/usr/bin/env python3
"""
Test script for the enhanced logging configuration with agent name identification.

This script demonstrates how the AgentNameFormatter automatically includes
agent names in log messages based on the AGENT_NAME environment variable.
"""

import os
import sys
from pathlib import Path

# Add current directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from logging_config import get_logger, setup_logging


def test_agent_logging():
    """Test logging with different agent names."""
    
    print("🧪 Testing Enhanced Logging Configuration with Agent Name Identification")
    print("=" * 70)
    
    # Test 1: Default agent name when AGENT_NAME not set
    print("\n1️⃣ Testing with no AGENT_NAME environment variable:")
    if 'AGENT_NAME' in os.environ:
        del os.environ['AGENT_NAME']
    
    logger1 = get_logger("test_module_1")
    logger1.info("This log should show [unknown-agent] as the identifier")
    
    # Test 2: Agent name from environment variable (snowflake agent)
    print("\n2️⃣ Testing with AGENT_NAME='snowflake-finserve-intel':")
    os.environ['AGENT_NAME'] = 'snowflake-finserve-intel'
    
    logger2 = get_logger("test_module_2")
    logger2.info("This log should show [snowflake-finserve-intel] as the identifier")
    logger2.warning("Warning message from snowflake agent")
    logger2.error("Error message from snowflake agent")
    
    # Test 3: Different agent name (supervisor agent)
    print("\n3️⃣ Testing with AGENT_NAME='supervisor_agent':")
    os.environ['AGENT_NAME'] = 'supervisor_agent'
    
    logger3 = get_logger("test_module_3")
    logger3.info("This log should show [supervisor_agent] as the identifier")
    logger3.debug("Debug message (may not show depending on log level)")
    
    # Test 4: Agent name change during runtime
    print("\n4️⃣ Testing dynamic agent name change:")
    logger4 = get_logger("test_module_4")
    logger4.info("Before agent name change")
    
    os.environ['AGENT_NAME'] = 'qa_agent_2' 
    logger4.info("After changing to qa_agent_2 - should show new name")
    
    # Test 5: Multiple log levels and context
    print("\n5️⃣ Testing different log levels with agent identification:")
    os.environ['AGENT_NAME'] = 'configuration-api'
    
    logger5 = get_logger("config_service")
    logger5.info("Service starting up")
    logger5.warning("Configuration parameter missing, using default")
    logger5.error("Failed to connect to database")
    
    print("\n✅ Logging tests completed!")
    print("\n📋 Expected log format:")
    print("   TIMESTAMP - [AGENT_NAME] - MODULE_NAME - LEVEL - MESSAGE")
    print("\n💡 In CloudWatch, you can now filter logs by agent name using:")
    print("   - [snowflake-finserve-intel] for snowflake agent logs")
    print("   - [supervisor_agent] for supervisor agent logs")
    print("   - [qa_agent_2] for QA agent logs")
    print("   - [configuration-api] for configuration API logs")


if __name__ == "__main__":
    test_agent_logging()
