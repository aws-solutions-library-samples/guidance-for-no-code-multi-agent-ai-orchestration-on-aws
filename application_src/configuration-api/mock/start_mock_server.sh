#!/bin/bash

# Configuration API Mock Server Startup Script

echo "========================================================"
echo "🚀 Configuration API Mock Server"
echo "========================================================"

# Check if we're in the right directory
if [ ! -f "mock_server.py" ]; then
    echo "❌ Error: mock_server.py not found in current directory"
    echo "Please run this script from the application_src/configuration-api directory"
    exit 1
fi

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python3 is not installed or not in PATH"
    exit 1
fi

# Check if virtual environment exists and create if needed
VENV_DIR="venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv $VENV_DIR
fi

# Activate virtual environment
echo "🔄 Activating virtual environment..."
source $VENV_DIR/bin/activate

# Install requirements
echo "📚 Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.mock.txt

# Start the mock server
echo "🌟 Starting Configuration API Mock Server..."
echo ""
echo "Server will be available at: http://localhost:8000"
echo "Health check: http://localhost:8000/health"
echo ""
echo "📋 Available endpoints:"
echo "  GET  /health                    - Health check"
echo "  GET  /discover                  - Discover DNS entries"
echo "  POST /config/save              - Save agent configuration"
echo "  POST /config/load              - Load agent configuration"
echo "  GET  /config/list              - List all agent configurations"
echo "  GET  /config/test-ssm          - Test SSM connectivity"
echo "  GET  /config/debug/{agent}     - Debug agent configuration"
echo ""
echo "Press Ctrl+C to stop the server"
echo "========================================================"

# Run the mock server
python3 mock_server.py
