"""
Generic Agent Instance implementation using environment-driven configuration.
This replaces agent-1 and agent-2 with a single scalable agent that can 
handle thousands of different agent configurations through SSM parameters.
"""

import logging
import os
import sys
from pathlib import Path

# Add common directory to Python path for importing base service
current_dir = Path(__file__).parent
common_dir_container = Path("/app/common")
common_dir_local = current_dir.parent.parent / "common"

if common_dir_container.exists():
    sys.path.insert(0, str(common_dir_container))
else:
    sys.path.insert(0, str(common_dir_local))

from base_agent_service import run_agent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Fixed internal port for all containers (Docker handles external mapping)
INTERNAL_PORT = 8080

def get_environment_config():
    """Get agent configuration from environment variables with proper defaults."""
    # Required environment variables
    agent_name = os.environ.get('AGENT_NAME')
    if not agent_name:
        raise ValueError("AGENT_NAME environment variable is required")
    
    # Optional environment variables with sensible defaults
    agent_description = os.environ.get(
        'AGENT_DESCRIPTION', 
        f'A configurable agent instance for {agent_name}'
    )
    
    return agent_name, agent_description

if __name__ == "__main__":
    try:
        # Get configuration from environment
        agent_name, agent_description = get_environment_config()
        
        logger.info(f"🚀 Starting Generic Agent Instance")
        logger.info(f"   Agent Name: {agent_name}")
        logger.info(f"   Description: {agent_description}")
        logger.info(f"   Internal Port: {INTERNAL_PORT}")
        logger.info(f"   SSM Config Path: /agent/{agent_name}/config")
        
        # Run the agent using the base service with fixed internal port
        run_agent(agent_name, agent_description, INTERNAL_PORT)
        
    except ValueError as e:
        logger.error(f"❌ Configuration Error: {str(e)}")
        logger.error("Required environment variables:")
        logger.error("  - AGENT_NAME: The name of the agent (determines SSM config path)")
        logger.error("Optional environment variables:")
        logger.error("  - AGENT_DESCRIPTION: Human-readable description")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Failed to start agent: {str(e)}")
        sys.exit(1)
