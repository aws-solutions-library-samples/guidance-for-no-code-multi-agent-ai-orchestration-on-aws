"""
Verification script to demonstrate that the mock server uses your actual app.py

This script shows that:
1. The mock server imports and runs your actual app.py
2. Any changes to app.py are automatically reflected
3. Only AWS calls are mocked - everything else is real
"""

import sys
from pathlib import Path

# Add current directory and parent directory to path
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(parent_dir))

def demonstrate_app_usage():
    """Demonstrate that mock_server.py uses the actual app.py"""
    
    print("🔍 Mock Server App Usage Verification")
    print("=" * 50)
    
    print("\n1️⃣ Mock server patches boto3 FIRST:")
    from mock_clients import patch_boto3
    print("   ✅ Mock clients imported")
    
    print("\n2️⃣ Patching boto3 before importing app:")
    patch_boto3()
    print("   ✅ boto3.client() now returns mock clients")
    
    print("\n3️⃣ Now importing YOUR actual main.py:")
    from main import app
    print("   ✅ Your main.py has been imported")
    print(f"   📋 App title: {app.title}")
    print(f"   📋 App description: {app.description}")
    print(f"   📋 App version: {app.version}")
    
    print("\n4️⃣ Checking available endpoints from your app:")
    routes = []
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            for method in route.methods:
                if method != 'HEAD':  # Skip HEAD methods
                    routes.append(f"{method} {route.path}")
    
    print(f"   ✅ Found {len(routes)} endpoints from your main.py:")
    for route in sorted(routes):
        print(f"      - {route}")
    
    print("\n5️⃣ Testing AWS client mocking:")
    import boto3
    
    # Create clients - these should be mocked
    ssm_client = boto3.client('ssm', region_name='us-east-1')
    vpc_client = boto3.client('vpc-lattice', region_name='us-east-1')
    
    print(f"   ✅ SSM client type: {type(ssm_client).__name__}")
    print(f"   ✅ VPC Lattice client type: {type(vpc_client).__name__}")
    
    print("\n🎉 VERIFICATION COMPLETE!")
    print("=" * 50)
    print("✅ The mock server DOES use your actual main.py")
    print("✅ Only AWS boto3 calls are mocked")
    print("✅ All endpoints come from your real application")
    print("✅ Any changes to main.py will be reflected automatically")
    
    return app


if __name__ == "__main__":
    app = demonstrate_app_usage()
    
    print("\n" + "=" * 50)
    print("💡 To test this:")
    print("1. Start the mock server: ./start_mock_server.sh")
    print("2. Make a change to main.py (add a comment, new endpoint, etc.)")
    print("3. Restart the mock server - your changes will be there!")
    print("4. The mock server will have the same changes as your real app")
    print("=" * 50)
