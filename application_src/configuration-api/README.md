# Configuration API

A FastAPI-based microservice for managing AI agent configurations in the GenAI In a Box platform.

## Overview

This service provides centralized configuration management for AI agents, including:

- System prompts storage and retrieval
- Agent configuration parameters (model settings, temperature, etc.)
- VPC Lattice service discovery
- Health monitoring endpoints

## Features

- **Agent Configuration Management**: Save and load complete agent configurations
- **System Prompt Management**: Store system prompts separately with versioning support
- **Service Discovery**: DNS discovery for VPC Lattice services
- **Health Checks**: Built-in health monitoring for load balancers
- **Debug Endpoints**: Debugging tools for troubleshooting configurations

## API Endpoints

### Health & Discovery
- `GET /health` - Health check endpoint
- `GET /discover` - Discover VPC Lattice DNS entries

### Configuration Management
- `POST /config/save` - Save agent configuration
- `POST /config/load` - Load agent configuration
- `GET /config/list` - List all available agent configurations

### Debug & Testing
- `GET /config/debug/{agent_name}` - Debug agent configuration
- `GET /config/test-ssm` - Test SSM connectivity

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AWS_REGION` | AWS region for SSM operations | `us-east-1` |
| `PORT` | Server port | `8000` |
| `VPC_LATTICE_SERVICE_NETWORK_ARN` | VPC Lattice service network ARN | Required for discovery |

## Configuration Storage

Agent configurations are stored in AWS Systems Manager (SSM) Parameter Store:

- Agent config: `/agent/{agent_name}/config`
- System prompts: `/agent/{agent_name}/system-prompts/{prompt_name}`
- System prompt index: `/agent/{agent_name}/system-prompts/index`

## Docker

### Building the Image
```bash
docker build -t configuration-api .
```

### Running the Container
```bash
docker run -p 8000:8000 \
  -e AWS_REGION=us-east-1 \
  -e AWS_ACCESS_KEY_ID=your_key \
  -e AWS_SECRET_ACCESS_KEY=your_secret \
  configuration-api
```

## Security Features

- Non-root user execution in Docker
- Minimal dependencies
- Proper error handling with security context
- Input validation using Pydantic models

## Development

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

### Testing
```bash
# Health check
curl http://localhost:8000/health

# Test SSM connectivity
curl http://localhost:8000/config/test-ssm
```

## Dependencies

- **FastAPI**: Modern web framework for building APIs
- **Uvicorn**: ASGI server for running FastAPI applications
- **Pydantic**: Data validation using Python type annotations
- **Boto3**: AWS SDK for Python
- **HTTPx**: HTTP client for making requests

## Architecture

The service follows a clean architecture pattern:

- **API Layer**: FastAPI endpoints for HTTP requests
- **Business Logic**: Helper functions for configuration management
- **Data Layer**: AWS SSM Parameter Store integration
- **Models**: Pydantic models for request/response validation

## Error Handling

The service implements comprehensive error handling:

- AWS API errors with proper status codes
- JSON validation errors
- Configuration not found scenarios
- Network connectivity issues

## Logging

Structured logging is configured with:

- Timestamp and log level
- Service name identification
- Detailed error messages
- Request tracing capabilities
