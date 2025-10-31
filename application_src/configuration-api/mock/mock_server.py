"""
Mock server for Configuration API.

This server uses the existing app.py but patches boto3 to use mock clients
that return predefined responses instead of making actual AWS API calls.
"""

import os
import sys
import uvicorn
import yaml
from pathlib import Path

# Add the current directory and parent directory to Python path to import modules
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(parent_dir))

# Import mock clients and patch boto3 BEFORE importing the app
from mock_clients import patch_boto3

# Set up environment variables from mock data
def setup_mock_environment():
    """Set up environment variables from mock_data.yaml."""
    mock_data_path = current_dir / 'mock_data.yaml'
    
    try:
        with open(mock_data_path, 'r', encoding='utf-8') as f:
            mock_data = yaml.safe_load(f)
        
        # Set environment variables from mock data
        env_vars = mock_data.get('environment', {})
        for key, value in env_vars.items():
            os.environ[key] = str(value)
            print(f"[MOCK ENV] Set {key} = {value}")
        
        print(f"[MOCK ENV] Environment variables configured from {mock_data_path}")
        
    except Exception as e:
        print(f"[MOCK ENV] Error loading environment from mock data: {e}")
        # Set default values
        os.environ.setdefault('AWS_REGION', 'us-east-1')
        os.environ.setdefault('VPC_LATTICE_SERVICE_NETWORK_ARN', 
                             'arn:aws:vpc-lattice:us-east-1:123456789012:servicenetwork/sn-0123456789abcdef0')
        os.environ.setdefault('PORT', '8000')

def main():
    """Main function to start the mock server."""
    print("="*60)
    print("🚀 Configuration API Mock Server")
    print("="*60)
    print("📝 IMPORTANT: This server uses your existing main.py")
    print("   Any changes to main.py will be reflected automatically!")
    print("   Only AWS boto3 calls are mocked.")
    print("="*60)
    
    # Set up mock environment
    setup_mock_environment()
    
    # Patch boto3 to use mock clients BEFORE importing app
    print("🔧 Patching boto3 with mock implementations...")
    patch_boto3()
    
    # Now import your actual main.py (after patching boto3)
    print("📥 Importing your existing main.py...")
    from main import app
    
    print("\n✅ Mock server setup complete!")
    print("📋 Mock data loaded from: mock_data.yaml")
    print("🔧 AWS clients replaced with mock implementations")
    print("🚀 Using your ACTUAL main.py with mocked AWS responses")
    print("🔄 Future changes to main.py will be reflected here!")
    print("\nServer starting with same endpoints as your real app...")
    print("\n" + "="*60)
    
    # Get port from environment
    port = int(os.environ.get('PORT', 8000))
    
    # Start the server using your actual FastAPI app
    # Get host from environment variable with secure default
    host = os.environ.get('HOST', '127.0.0.1')
    uvicorn.run(
        app,  # This is your actual app from app.py
        host=host, 
        port=port,
        log_level='info'
    )

if __name__ == '__main__':
    main()
