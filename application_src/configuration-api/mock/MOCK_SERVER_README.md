# Configuration API Mock Server

This mock server provides a local testing environment for the Configuration API that responds with predefined data instead of making actual AWS API calls. This allows you to test dependent projects locally without needing AWS credentials or services.

## 🎯 Purpose

The mock server addresses the requirement:
> "I have other projects which are dependent on the configuration API's response. In local environment, I want to ensure I can mock the response. I don't want to modify anything in app.py but I am fine in running any other server locally which uses app.py but responds back with mocked response specially for AWS clients."

## 📋 What's Included

### Core Files

- **`mock_server.py`** - Main mock server that uses your existing `app.py` with mocked AWS clients
- **`mock_clients.py`** - Mock implementations of AWS SSM and VPC Lattice clients
- **`mock_data.yaml`** - Configuration file containing all mock responses
- **`requirements.mock.txt`** - Dependencies for the mock server
- **`start_mock_server.sh`** - Convenient startup script
- **`test_mock.py`** - Test suite to verify mock server functionality

### How It Works

1. **Uses Your Actual app.py**: The mock server imports and runs your existing `app.py` file
2. **No app.py Modifications**: Your original `app.py` remains unchanged  
3. **boto3 Patching**: Before importing your app, boto3 is patched to return mock data
4. **Future-Proof**: Any changes you make to `app.py` will automatically be reflected in the mock server
5. **AWS Calls Mocked**: Only AWS boto3 calls return mock data from `mock_data.yaml`
6. **Same Endpoints**: All endpoints work exactly like the real API because it IS your real API

## 🚀 Quick Start

### Option 1: Using the Startup Script (Recommended)

```bash
cd application_src/configuration-api
./start_mock_server.sh
```

The script will:
- Create a virtual environment if needed
- Install dependencies
- Start the mock server on `http://localhost:8000`

### Option 2: Manual Setup

```bash
cd application_src/configuration-api

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.mock.txt

# Start the mock server
python3 mock_server.py
```

## 🧪 Testing the Mock Server

### Automated Tests

Run the comprehensive test suite:

```bash
# In another terminal (while mock server is running)
cd application_src/configuration-api
source venv/bin/activate
python3 test_mock.py
```

### Manual Testing

Test individual endpoints using curl or your browser:

```bash
# Health check
curl http://localhost:8000/health

# Discover DNS entries
curl http://localhost:8000/discover

# Load QA agent config
curl -X POST http://localhost:8000/config/load \
  -H "Content-Type: application/json" \
  -d '{"agent_name": "qa_agent"}'

# List all agents
curl http://localhost:8000/config/list
```

## 📊 Mock Data Configuration

### Adding New Mock Data

Edit `mock_data.yaml` to customize responses:

```yaml
ssm_parameters:
  "/agent/your_new_agent/config":
    agent_name: "your_new_agent"
    agent_description: "Description of your agent"
    # ... other configuration fields

  "/agent/your_new_agent/system-prompts/index":
    "prompt_name": "/agent/your_new_agent/system-prompts/prompt_name"

  "/agent/your_new_agent/system-prompts/prompt_name": |
    Your system prompt content here.
    Can be multiple lines.

vpc_lattice:
  service_associations:
    - serviceName: "your-new-service"
      dnsEntry:
        domainName: "your-service.example.com"
```

### Environment Variables

Configure environment variables in the `environment` section:

```yaml
environment:
  AWS_REGION: "us-east-1"
  VPC_LATTICE_SERVICE_NETWORK_ARN: "arn:aws:vpc-lattice:..."
  PORT: "8000"
```

## 🔌 API Endpoints

All endpoints from the original API are available:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check endpoint |
| GET | `/discover` | Discover VPC Lattice DNS entries |
| POST | `/config/save` | Save agent configuration |
| POST | `/config/load` | Load agent configuration |
| GET | `/config/list` | List all agent configurations |
| GET | `/config/test-ssm` | Test SSM connectivity (mocked) |
| GET | `/config/debug/{agent}` | Debug agent configuration |

## 📦 Sample Mock Data

The mock server comes with pre-configured data for:

### Agents
- **qa_agent** - Q&A Agent with Bedrock KB integration
- **chat_agent** - Chat Agent with memory and guardrails

### System Prompts
- Multiple system prompts per agent
- Different prompt variations (technical, friendly, professional)

### VPC Lattice Services
- Sample service associations with DNS entries
- Realistic ARNs and domain names

## 🔧 Customization

### Adding New AWS Services

To mock additional AWS services:

1. Create a new mock client class in `mock_clients.py`:

```python
class MockNewServiceClient:
    def __init__(self, region_name='us-east-1'):
        self.region_name = region_name
        self._load_mock_data()
    
    def some_api_method(self, **kwargs):
        # Return mock data
        pass
```

2. Update `mock_boto3_client()` to handle the new service:

```python
elif service_name == 'new-service':
    return MockNewServiceClient(region_name=region_name)
```

3. Add mock data to `mock_data.yaml`

### Modifying Responses

To change mock responses:

1. Edit `mock_data.yaml`
2. Restart the mock server
3. The changes take effect immediately

## 🐛 Troubleshooting

### Common Issues

1. **Port 8000 in use**
   - Change port in `mock_data.yaml` under `environment.PORT`
   - Or set environment variable: `PORT=8001 python3 mock_server.py`

2. **Mock data not loading**
   - Check `mock_data.yaml` syntax with a YAML validator
   - Check file permissions

3. **Dependencies missing**
   - Run: `pip install -r requirements.mock.txt`

### Debug Mode

Enable verbose logging by setting environment variable:

```bash
export PYTHONPATH=.
python3 -c "
import logging
logging.basicConfig(level=logging.DEBUG)
exec(open('mock_server.py').read())
"
```

## 🔄 Integration with Other Projects

### Point Your Projects to Mock Server

Update your dependent projects to use the mock server URL:

```python
# Instead of production URL
API_BASE_URL = "https://your-production-api.com"

# Use mock server URL
API_BASE_URL = "http://localhost:8000"
```

### Environment-Based Configuration

```python
import os

if os.getenv('ENVIRONMENT') == 'local':
    API_BASE_URL = "http://localhost:8000"
else:
    API_BASE_URL = "https://your-production-api.com"
```

## 📝 Development Workflow

1. **Start Mock Server**: `./start_mock_server.sh`
2. **Test Mock Server**: `python3 test_mock.py`
3. **Update Mock Data**: Edit `mock_data.yaml` as needed
4. **Test Your Project**: Point your dependent projects to `http://localhost:8000`
5. **Iterate**: Modify mock data based on your testing needs

## 🚨 Important Notes

- **No app.py Changes**: The original `app.py` file is never modified
- **Local Only**: This mock server is intended for local development only
- **No Persistence**: Changes made via API calls are not persisted to `mock_data.yaml`
- **Development Tool**: Not suitable for production use

## 📚 Files Reference

- `app.py` - Original application (unchanged)
- `mock_server.py` - Mock server entry point
- `mock_clients.py` - AWS service mock implementations
- `mock_data.yaml` - Mock response configuration
- `requirements.mock.txt` - Mock server dependencies
- `test_mock.py` - Test suite
- `start_mock_server.sh` - Startup script

---

**Happy Mocking! 🎭**

Need help? Check the test suite in `test_mock.py` for usage examples.
