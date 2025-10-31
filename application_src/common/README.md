# GenAI-In-A-Box API

This directory contains the API component of the GenAI-In-A-Box application, which provides a flexible and extensible framework for building AI-powered applications with various knowledge base integrations, observability providers, and memory capabilities.

## Table of Contents

- [Overview](#overview)
- [Getting Started](#getting-started)
- [API Endpoints](#api-endpoints)
- [Configuration](#configuration)
- [Extending the API](#extending-the-api)
  - [Adding a New Knowledge Base Provider](#adding-a-new-knowledge-base-provider)
  - [Adding a New Observability Provider](#adding-a-new-observability-provider)
  - [Adding a New Memory Provider](#adding-a-new-memory-provider)
- [Architecture](#architecture)
- [Troubleshooting](#troubleshooting)

## Overview

The GenAI-In-A-Box API is built on FastAPI and provides endpoints for interacting with AI agents that can leverage different knowledge bases, observability tools, and memory providers. The API is designed to be modular and extensible, allowing you to easily add new providers and capabilities.

Key features:
- Multiple knowledge base integrations (Elasticsearch, Snowflake, Bedrock KB)
- Observability providers (Langfuse, Dynatrace)
- Memory capabilities (Mem0)
- Streaming and non-streaming response modes
- Dynamic agent configuration via SSM Parameter Store

## Getting Started

### Prerequisites

- Python 3.9+
- AWS credentials configured
- Access to Amazon Bedrock models
- Required environment variables (see below)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/generative-ai-in-box.git
cd generative-ai-in-box/application_src/api
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables (optional):
```bash
# These are optional and can be configured in other ways
export AWS_PROFILE=your-profile-name
```

### Running the API

Start the API server:
```bash
cd app
uvicorn app:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### Agent Endpoint (Non-Streaming)

**Endpoint**: `/agent`

**Method**: POST

**Description**: Send a prompt to the agent and receive a complete response.

**Example Request**:
```bash
curl -X POST http://localhost:8000/agent \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is AWS Bedrock?",
    "user_id": "user123",
    "agent_name": "qa_agent"
  }'
```

**Example Response**:
```json
{
  "response": "AWS Bedrock is a fully managed service that offers a choice of high-performing foundation models (FMs) from leading AI companies like AI21 Labs, Anthropic, Cohere, Meta, Stability AI, and Amazon with a single API. It provides access to FMs for text, images, and embeddings to build generative AI applications with security, privacy, and responsible AI."
}
```

### Agent Streaming Endpoint

**Endpoint**: `/agent-streaming`

**Method**: POST

**Description**: Send a prompt to the agent and receive a streaming response.

**Example Request**:
```bash
curl -X POST http://localhost:8000/agent-streaming \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is AWS Bedrock?",
    "user_id": "user123",
    "agent_name": "qa_agent"
  }' --no-buffer
```

**Example Response**: The response will stream back in chunks as they are generated.

### JavaScript Example for Streaming

```javascript
async function streamResponse() {
  const response = await fetch('http://localhost:8000/agent-streaming', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      prompt: 'What is AWS Bedrock?',
      user_id: 'user123',
      agent_name: 'qa_agent'
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    console.log(chunk); // Process or display the chunk
  }
}

streamResponse();
```

### Python Example for Streaming

```python
import requests

response = requests.post(
    'http://localhost:8000/agent-streaming',
    json={
        'prompt': 'What is AWS Bedrock?',
        'user_id': 'user123',
        'agent_name': 'qa_agent'
    },
    stream=True
)

for chunk in response.iter_content(chunk_size=None):
    if chunk:
        print(chunk.decode('utf-8'), end='', flush=True)
```

### DNS Discovery Endpoint

**Endpoint**: `/discover`

**Method**: GET

**Description**: Discover DNS entries from VPC Lattice Service Network associations. This endpoint retrieves all DNS information for services associated with a specific VPC Lattice Service Network.

**Environment Variables Required**:
- `VPC_LATTICE_SERVICE_NETWORK_ARN`: The ARN of the VPC Lattice Service Network to query

**Example Request**:
```bash
curl -X GET http://localhost:8000/discover
```

**Example Response**:
```json
[
  "my-api-service-1234567890abcdef0.7d67968.vpc-lattice-svcs.us-east-1.on.aws",
  "my-web-service-0987654321fedcba0.7d67968.vpc-lattice-svcs.us-east-1.on.aws"
]
```

**Response Format**:
The endpoint returns a simple JSON array containing the domain names of all services associated with the specified VPC Lattice Service Network.

**Error Responses**:
- `400 Bad Request`: VPC_LATTICE_SERVICE_NETWORK_ARN environment variable is missing
- `403 Forbidden`: Insufficient IAM permissions to access VPC Lattice
- `500 Internal Server Error`: Other VPC Lattice API errors

## Configuration

The API uses AWS SSM Parameter Store for configuration. Each agent has its own configuration stored at `/agent/{agent_name}/config`.

Example configuration structure:
```json
{
  "agent_name": "qa_agent_2",
  "agent_description": "Question Answer Agent",
  "system_prompt_name": "ElasticsearchSystemPrompt",
  "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
  "judge_model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
  "embedding_model_id": "amazon.titan-embed-text-v2:0",
  "region_name": "us-east-1",
  "temperature": 0.3,
  "top_p": 0.8,
  "streaming": "True",
  "cache_prompt": "default",
  "cache_tools": "default",
  "thinking": {
    "type": "enabled",
    "budget_tokens": 4096
  },
  "memory": "False",
  "memory_provider": "mem0",
  "memory_provider_details": [
    {
      "name": "opensearch",
      "config": {
        "opensearch_host": ""
      }
    },
    {
      "name": "mem0",
      "config": {
        "mem0_api_key": "YOUR_MEM0_API_KEY"
      }
    },
    {
      "name": "faiss",
      "config": {}
    }
  ],
  "knowledge_base": "True",
  "knowledge_base_provider": "elasticsearch",
  "knowledge_base_provider_type": "custom",
  "knowledge_base_details": [
    {
      "name": "elasticsearch",
      "config": {
        "es_url": "YOUR_ELASTICSEARCH_URL",
        "es_api_key": "YOUR_ELASTICSEARCH_API_KEY",
        "index_name": "YOUR_INDEX_NAME"
      }
    },
    {
      "name": "bedrock_kb",
      "config": {
        "knowledge_base_id": "",
        "region": "us-east-1",
        "number_of_results": 5
      }
    },
    {
      "name": "snowflake",
      "config": {
        "snowflake_account": "YOUR_SNOWFLAKE_ACCOUNT",
        "snowflake_database": "YOUR_DATABASE",
        "snowflake_role": "YOUR_ROLE",
        "snowflake_warehouse": "YOUR_WAREHOUSE",
        "snowflake_username": "YOUR_USERNAME",
        "snowflake_password": "YOUR_PASSWORD",
        "snowflake_schema": "YOUR_SCHEMA",
        "semantic_model_path": "YOUR_MODEL_PATH",
        "private_key_passphrase": "YOUR_PASSPHRASE"
      }
    }
  ],
  "observability": "No",
  "observability_provider": "dynatrace",
  "observability_provider_details": [
    {
      "name": "langfuse",
      "config": {
        "type": "custom",
        "public_key": "YOUR_LANGFUSE_PUBLIC_KEY",
        "secret_key": "YOUR_LANGFUSE_SECRET_KEY",
        "host": "https://us.cloud.langfuse.com"
      }
    },
    {
      "name": "dynatrace",
      "config": {
        "type": "custom",
        "dt_token": "YOUR_DYNATRACE_TOKEN",
        "otlp_endpoint": "YOUR_DYNATRACE_ENDPOINT"
      }
    }
  ],
  "guardrail": "No",
  "guardrail_provider": "Bedrock GuardRails",
  "guardrail_provider_details": [
    {
      "name": "bedrock_guardrails",
      "config": {
        "guardrail_id": ""
      }
    }
  ],
  "tools": [
    {
      "name": "http_request",
      "config": {
        "enabled": "No"
      }
    }
  ]
}
```

## Extending the API

### Adding a New Knowledge Base Provider

1. Create a new file in the `knowledge_base` directory (e.g., `my_provider.py`):

```python
from .base import BaseKnowledgeBaseProvider

class MyKnowledgeBaseProvider(BaseKnowledgeBaseProvider):
    """Custom knowledge base provider implementation."""
    
    def __init__(self, config):
        """Initialize the provider with configuration."""
        super().__init__(config)
        self.provider_name = "MyProvider"
        # Initialize your provider with the config
        self.client = YourClient(
            host=config.get("host"),
            api_key=config.get("api_key")
        )
        
        # Initialize tools
        self.tools = self._create_tools()
    
    def _create_tools(self):
        """Create tools for the provider."""
        def my_search_tool(query: str):
            """Search the knowledge base."""
            results = self.client.search(query)
            return results
            
        # Return a list of tools
        return [my_search_tool]
    
    def get_tools(self):
        """Get the tools for this provider."""
        return self.tools
```

2. Update the `KnowledgeBaseFactory` in `__init__.py` to include your provider:

```python
@staticmethod
def _create_my_provider(kb_config, provider_type):
    """Create a custom knowledge base provider."""
    print(f"KB Factory: Creating MyProvider with type: {provider_type}")
    return MyKnowledgeBaseProvider(kb_config)

# Then add to the provider mapping
if provider == "myprovider":
    print(f"KB Factory: Creating MyProvider with type: {provider_type}")
    _kb_provider_instance = KnowledgeBaseFactory._create_my_provider(kb_config, provider_type)
```

### Adding a New Observability Provider

1. Create a new file in the `observability` directory (e.g., `my_observability.py`):

```python
from .base import BaseObservabilityProvider

class MyObservabilityProvider(BaseObservabilityProvider):
    """Custom observability provider implementation."""
    
    def __init__(self, config):
        """Initialize the provider with configuration."""
        super().__init__(config)
        self.provider_name = "MyObservability"
        # Initialize your provider with the config
        self.client = YourObservabilityClient(
            host=config.get("host"),
            api_key=config.get("api_key")
        )
    
    def initialize(self):
        """Initialize the observability provider."""
        # Set up any environment variables or configurations needed
        os.environ["MY_OBSERVABILITY_API_KEY"] = self.config.get("api_key")
        os.environ["MY_OBSERVABILITY_HOST"] = self.config.get("host")
        
        # Initialize any tracers or exporters
        # ...
        
    def get_trace_attributes(self):
        """Get trace attributes for use with Strands Agent."""
        return {
            "my_attribute": "value",
            "trace_id": str(uuid.uuid4())
        }
```

2. Update the `ObservabilityFactory` in `__init__.py` to include your provider:

```python
elif provider == "myobservability":
    print("✅ Creating MyObservability provider")
    return MyObservabilityProvider(obs_config)
```

### Adding a New Memory Provider

1. Create a new file in the `memory` directory (e.g., `my_memory.py`):

```python
from .base import BaseMemoryProvider

class MyMemoryProvider(BaseMemoryProvider):
    """Custom memory provider implementation."""
    
    def __init__(self, config):
        """Initialize the provider with configuration."""
        super().__init__(config)
        self.provider_name = "MyMemory"
        # Initialize your provider with the config
        self.client = YourMemoryClient(
            host=config.get("host"),
            api_key=config.get("api_key")
        )
    
    def get_tools(self):
        """Get memory tools for this provider."""
        def my_memory_tool(user_id: str, query: str = None):
            """Retrieve memory for a user."""
            if query:
                return self.client.search_memory(user_id, query)
            else:
                return self.client.get_recent_memory(user_id)
                
        def store_memory(user_id: str, content: str):
            """Store memory for a user."""
            return self.client.store_memory(user_id, content)
            
        return [my_memory_tool, store_memory]
```

2. Update the `MemoryFactory` in `__init__.py` to include your provider:

```python
elif provider == "mymemory":
    print("✅ Creating MyMemory provider")
    return MyMemoryProvider(memory_config)
```

## Architecture

The API is structured with the following components:

- **app.py**: Main FastAPI application with API endpoints
- **agent.py**: Agent creation and execution logic
- **config.py**: Configuration management using SSM Parameter Store
- **knowledge_base/**: Knowledge base provider implementations
- **observability/**: Observability provider implementations
- **memory/**: Memory provider implementations
- **tools/**: Custom tools for the agent

The application follows a factory pattern for creating providers, allowing for easy extension and configuration.

## Troubleshooting

### Common Issues

1. **Agent not using the correct knowledge base provider**:
   - Check that the agent_name is correctly passed from the UI to the API
   - Verify the configuration in SSM Parameter Store
   - Reset the knowledge base provider with `reset_knowledge_base_provider()`

2. **Memory not working**:
   - Ensure the memory provider is correctly configured
   - Check that the user_id is being passed correctly
   - Verify that the memory tools are being added to the agent

3. **Observability not sending traces**:
   - Check that the observability provider is correctly initialized
   - Verify the API keys and endpoints are correct
   - Ensure the trace attributes are being passed to the agent

For more detailed troubleshooting, check the logs for debug messages with prefixes like `DEBUG AGENT:`, `DEBUG KB FACTORY:`, etc.
