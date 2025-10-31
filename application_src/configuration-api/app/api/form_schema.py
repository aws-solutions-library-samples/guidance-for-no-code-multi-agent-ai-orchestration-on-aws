"""
Form schema API routes.

This module provides endpoints for dynamic form generation in the frontend.
All form schemas are defined in FormSchemaRegistry - the single source of truth.
"""

import logging
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Depends
from common.secure_logging_utils import log_exception_safely

logger = logging.getLogger(__name__)

from ..models import (
    ComponentFormSchema,
    ProviderFormSchema,
    FormSchemaRegistry
)
from ..middleware.auth_middleware import get_current_user

form_schema_router = APIRouter(prefix="/form-schema")


@form_schema_router.get('/components')
async def list_available_components(user_info = Depends(get_current_user)) -> Dict[str, List[str]]:
    """
    List all available component types and their providers.
    
    Returns:
        Dictionary mapping component types to available provider names
    """
    return {
        "agent": list(FormSchemaRegistry.get_agent_schemas().keys()),
        "models": list(FormSchemaRegistry.get_model_schemas().keys()),
        "knowledge_base": list(FormSchemaRegistry.get_knowledge_base_schemas().keys()),
        "memory": list(FormSchemaRegistry.get_memory_schemas().keys()),
        "observability": list(FormSchemaRegistry.get_observability_schemas().keys()),
        "guardrail": list(FormSchemaRegistry.get_guardrail_schemas().keys()),
        "tools": list(FormSchemaRegistry.get_tools_schemas().keys())
    }


@form_schema_router.get('/components/{component_type}')
async def get_component_schema(component_type: str, user_info = Depends(get_current_user)) -> ComponentFormSchema:
    """
    Get complete form schema for a component type.
    
    Args:
        component_type: Component type (agent, models, knowledge_base, memory, observability, guardrail, tools)
        
    Returns:
        Complete component form schema with all providers
        
    Raises:
        HTTPException: If component type is not found
    """
    # Special handling for agent component type
    if component_type == 'agent':
        agent_schemas = FormSchemaRegistry.get_agent_schemas()
        if agent_schemas:
            # Wrap agent schemas in ComponentFormSchema
            return ComponentFormSchema(
                component_type='agent',
                providers=agent_schemas
            )
    
    # Special handling for models component type
    elif component_type == 'models':
        model_schemas = FormSchemaRegistry.get_model_schemas()
        if model_schemas:
            # Wrap model schemas in ComponentFormSchema
            return ComponentFormSchema(
                component_type='models',
                providers=model_schemas
            )
    
    # Special handling for tools component type
    elif component_type == 'tools':
        tools_schemas = FormSchemaRegistry.get_tools_schemas()
        if tools_schemas:
            # Wrap tools schemas in ComponentFormSchema
            return ComponentFormSchema(
                component_type='tools',
                providers=tools_schemas
            )
    
    # Standard component types (knowledge_base, memory, observability, guardrail)
    schema = FormSchemaRegistry.get_component_schema(component_type)
    if not schema:
        raise HTTPException(
            status_code=404, 
            detail=f"Component type '{component_type}' not found"
        )
    
    return schema


@form_schema_router.get('/providers/{component_type}/{provider_name}')
async def get_provider_schema(
    component_type: str, 
    provider_name: str,
    user_info = Depends(get_current_user)
) -> ProviderFormSchema:
    """
    Get form schema for a specific provider.
    
    Args:
        component_type: Component type (knowledge_base, memory, observability, guardrail)
        provider_name: Provider name (bedrock, elasticsearch, snowflake, etc.)
        
    Returns:
        Provider-specific form schema
        
    Raises:
        HTTPException: If component type or provider is not found
    """
    schema = FormSchemaRegistry.get_provider_schema(component_type, provider_name)
    if not schema:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_name}' not found for component '{component_type}'"
        )
    
    return schema


@form_schema_router.get('/providers/{component_type}')
async def list_component_providers(component_type: str, user_info = Depends(get_current_user)) -> Dict[str, ProviderFormSchema]:
    """
    List all providers for a specific component type.
    
    Args:
        component_type: Component type (knowledge_base, memory, observability, guardrail)
        
    Returns:
        Dictionary of provider schemas for the component type
        
    Raises:
        HTTPException: If component type is not found
    """
    component_schema = FormSchemaRegistry.get_component_schema(component_type)
    if not component_schema:
        raise HTTPException(
            status_code=404,
            detail=f"Component type '{component_type}' not found"
        )
    
    return component_schema.providers


@form_schema_router.get('/providers/{component_type}/{provider_name}/fields')
async def get_provider_fields(
    component_type: str, 
    provider_name: str,
    user_info = Depends(get_current_user)
) -> List[Dict]:
    """
    Get just the field definitions for a specific provider.
    
    This is a lightweight endpoint for cases where you only need
    the field definitions without the full schema metadata.
    
    Args:
        component_type: Component type (knowledge_base, memory, observability, guardrail)
        provider_name: Provider name (bedrock, elasticsearch, snowflake, etc.)
        
    Returns:
        List of field definitions
        
    Raises:
        HTTPException: If component type or provider is not found
    """
    schema = FormSchemaRegistry.get_provider_schema(component_type, provider_name)
    if not schema:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider_name}' not found for component '{component_type}'"
        )
    
    return [field.model_dump() for field in schema.fields]


@form_schema_router.get('/tools/categories')
async def get_tool_categories(user_info = Depends(get_current_user)) -> Dict[str, Dict[str, Any]]:
    """
    Get tool categories with metadata for enhanced tool management UI.
    
    Returns:
        Dictionary mapping category names to their metadata including
        available tools count, description, and category type.
    """
    tools_schemas = FormSchemaRegistry.get_tools_schemas()
    
    categories = {}
    for provider_name, provider_schema in tools_schemas.items():
        # Count available tools based on provider type
        if provider_name == "builtin":
            # For builtin tools, parse the placeholder to count tools
            enabled_tools_field = next(
                (field for field in provider_schema.fields if field.name == "enabled_tools"), 
                None
            )
            # Count tools from placeholder JSON
            tool_count = 5  # http_request, use_aws, load_tool, mcp_client, retrieve
        elif provider_name == "mcp":
            # For MCP, tools are dynamic based on server configuration
            tool_count = "Dynamic"
        elif provider_name == "custom":
            # For custom, tools are based on module configuration
            tool_count = "Variable"
        else:
            tool_count = 0
            
        categories[provider_name] = {
            "name": provider_schema.provider_name,
            "label": provider_schema.provider_label,
            "description": provider_schema.description,
            "available_tools": tool_count,
            "category_type": provider_name
        }
    
    return categories


@form_schema_router.get('/tools/{category}/available')
async def get_available_tools_in_category(category: str, user_info = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get available tools for a specific tool category.
    
    Args:
        category: Tool category (builtin, mcp, custom)
        
    Returns:
        Dictionary with available tools and their metadata
        
    Raises:
        HTTPException: If category is not found
    """
    tools_schemas = FormSchemaRegistry.get_tools_schemas()
    
    if category not in tools_schemas:
        raise HTTPException(
            status_code=404,
            detail=f"Tool category '{category}' not found"
        )
    
    provider_schema = tools_schemas[category]
    
    if category == "builtin":
        # Return only the 5 tools currently implemented in the codebase
        builtin_tools = [
            {
                "name": "http_request",
                "label": "HTTP Request",
                "description": "Make HTTP requests to external APIs and services (from strands_tools)",
                "config_schema": {}
            },
            {
                "name": "use_aws",
                "label": "AWS Services",
                "description": "Access AWS services including DynamoDB, S3, Lambda and more (from strands_tools)",
                "config_schema": {}
            },
            {
                "name": "load_tool",
                "label": "Dynamic Tool Loader", 
                "description": "Dynamically load tools from specified modules (from strands_tools)",
                "config_schema": {}
            },
            {
                "name": "mcp_client",
                "label": "MCP Client",
                "description": "Client for communicating with MCP servers (from strands_tools)",
                "config_schema": {}
            },
            {
                "name": "retrieve",
                "label": "Knowledge Base Retrieval",
                "description": "Retrieve information from Bedrock Knowledge Base (configured via Knowledge Base settings)",
                "config_schema": {}
            }
        ]
        
        return {
            "category": category,
            "category_label": provider_schema.provider_label,
            "description": provider_schema.description,
            "tools": builtin_tools
        }
    
    elif category == "mcp":
        return {
            "category": category,
            "category_label": provider_schema.provider_label,
            "description": provider_schema.description,
            "tools": "dynamic",  # MCP tools are discovered from server configurations
            "configuration_required": True,
            "schema": provider_schema.model_dump()
        }
    
    elif category == "custom":
        return {
            "category": category,
            "category_label": provider_schema.provider_label,
            "description": provider_schema.description,
            "tools": "module_based",  # Custom tools are based on module configurations
            "configuration_required": True,
            "schema": provider_schema.model_dump()
        }
    
    else:
        return {
            "category": category,
            "category_label": provider_schema.provider_label,
            "description": provider_schema.description,
            "tools": [],
            "schema": provider_schema.model_dump()
        }


@form_schema_router.get('/tools/{category}/{tool_name}')
async def get_specific_tool_schema(category: str, tool_name: str, user_info = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Get configuration schema for a specific tool.
    
    Args:
        category: Tool category (builtin, mcp, custom)
        tool_name: Name of the specific tool
        
    Returns:
        Tool configuration schema and metadata
        
    Raises:
        HTTPException: If category or tool is not found
    """
    if category != "builtin":
        raise HTTPException(
            status_code=400,
            detail=f"Tool-specific schemas only available for 'builtin' category"
        )
    
    # Define accurate tool-specific schemas based on actual strands-agents/tools inputSchema
    tool_schemas = {
        "http_request": {
            "name": "http_request",
            "label": "HTTP Request Tool",
            "description": "Make HTTP requests with comprehensive authentication and enterprise features",
            "category": "builtin",
            "enabled": True,
            "config_fields": [
                {
                    "name": "auth_type",
                    "type": "select",
                    "label": "Authentication Type",
                    "default": "",
                    "options": [
                        {"value": "", "label": "No Authentication"},
                        {"value": "Bearer", "label": "Bearer Token"},
                        {"value": "token", "label": "Token (GitHub style)"},
                        {"value": "basic", "label": "Basic Authentication"},
                        {"value": "digest", "label": "Digest Authentication"},
                        {"value": "jwt", "label": "JWT Token"},
                        {"value": "aws_sig_v4", "label": "AWS SigV4"},
                        {"value": "api_key", "label": "API Key"},
                        {"value": "custom", "label": "Custom Authorization"}
                    ],
                    "help_text": "Type of authentication to use for requests"
                },
                {
                    "name": "auth_env_var",
                    "type": "text",
                    "label": "Auth Environment Variable",
                    "placeholder": "GITHUB_TOKEN",
                    "help_text": "Environment variable containing authentication token (e.g., GITHUB_TOKEN, GITLAB_TOKEN)"
                },
                {
                    "name": "verify_ssl",
                    "type": "boolean",
                    "label": "Verify SSL Certificates",
                    "default": True,
                    "help_text": "Whether to verify SSL certificates for HTTPS requests"
                },
                {
                    "name": "allow_redirects",
                    "type": "boolean",
                    "label": "Follow Redirects",
                    "default": True,
                    "help_text": "Whether to follow HTTP redirects automatically"
                },
                {
                    "name": "max_redirects",
                    "type": "number",
                    "label": "Maximum Redirects",
                    "default": 30,
                    "min": 1,
                    "max": 50,
                    "help_text": "Maximum number of redirects to follow"
                },
                {
                    "name": "convert_to_markdown",
                    "type": "boolean",
                    "label": "Convert HTML to Markdown",
                    "default": False,
                    "help_text": "Convert HTML responses to markdown format for better readability"
                },
                {
                    "name": "metrics",
                    "type": "boolean",
                    "label": "Collect Request Metrics",
                    "default": False,
                    "help_text": "Whether to collect and display request timing and performance metrics"
                },
                {
                    "name": "streaming",
                    "type": "boolean",
                    "label": "Enable Streaming",
                    "default": False,
                    "help_text": "Enable streaming response handling for large responses"
                }
            ]
        },
        "use_aws": {
            "name": "use_aws",
            "label": "AWS Services Tool",
            "description": "Universal interface to all AWS services through boto3 with validation and schema help",
            "category": "builtin",
            "enabled": True,
            "config_fields": [
                {
                    "name": "runtime_parameters_note",
                    "type": "textarea",
                    "label": "Required Runtime Parameters (Read Only)",
                    "default": 'use_aws requires these parameters per call:\n• service_name: str (required) - AWS service name\n• operation_name: str (required) - boto3 operation name\n• parameters: dict (required) - operation parameters\n• region: str (required) - AWS region\n• label: str (required) - human readable description',
                    "disabled": True,
                    "help_text": "use_aws requires runtime parameters for each call",
                    "rows": 4
                },
                {
                    "name": "default_region",
                    "type": "select",
                    "label": "Default AWS Region",
                    "default": "us-west-2",
                    "options": [
                        {"value": "us-east-1", "label": "US East (N. Virginia)"},
                        {"value": "us-west-2", "label": "US West (Oregon)"},
                        {"value": "eu-west-1", "label": "Europe (Ireland)"},
                        {"value": "ap-southeast-1", "label": "Asia Pacific (Singapore)"}
                    ],
                    "help_text": "Default AWS region when not specified in runtime call"
                },
                {
                    "name": "default_profile",
                    "type": "text",
                    "label": "Default AWS Profile",
                    "default": "",
                    "placeholder": "default",
                    "help_text": "Default AWS profile name from ~/.aws/credentials (optional)"
                },
                {
                    "name": "require_user_confirmation",
                    "type": "boolean",
                    "label": "Require Confirmation for Mutative Operations",
                    "default": True,
                    "help_text": "Prompt for confirmation before create/delete/update operations (can be bypassed with BYPASS_TOOL_CONSENT=true)"
                }
            ]
        },
        "load_tool": {
            "name": "load_tool",
            "label": "Dynamic Tool Loader",
            "description": "Dynamically load custom Python tools at runtime - takes path and name parameters per call",
            "category": "builtin",
            "enabled": False,
            "config_fields": [
                {
                    "name": "runtime_parameters_note",
                    "type": "textarea",
                    "label": "Runtime Parameters (Read Only)",
                    "default": 'load_tool accepts runtime parameters per call:\n• path: str - Path to Python tool file to load\n• name: str - Name to register the tool under\n• agent: Optional agent instance (auto-provided)',
                    "disabled": True,
                    "help_text": "load_tool uses runtime parameters, not global configuration",
                    "rows": 3
                },
                {
                    "name": "security_note",
                    "type": "textarea",
                    "label": "Security Note (Read Only)",
                    "default": 'Can be disabled via STRANDS_DISABLE_LOAD_TOOL=true environment variable for production security',
                    "disabled": True,
                    "help_text": "Security considerations for dynamic tool loading",
                    "rows": 2
                }
            ]
        },
        "mcp_client": {
            "name": "mcp_client",
            "label": "MCP Client Tool",
            "description": "⚠️ Dynamically connect to external MCP servers and load remote tools (SECURITY RISK)",
            "category": "builtin",
            "enabled": False,
            "config_fields": [
                {
                    "name": "default_transport",
                    "type": "select",
                    "label": "Default Transport",
                    "default": "stdio",
                    "options": [
                        {"value": "stdio", "label": "STDIO (local command)"},
                        {"value": "sse", "label": "SSE (server-sent events)"},
                        {"value": "streamable_http", "label": "Streamable HTTP"}
                    ],
                    "help_text": "Default transport type for MCP connections"
                },
                {
                    "name": "server_url",
                    "type": "url",
                    "label": "Default Server URL",
                    "placeholder": "https://mcp-server.example.com",
                    "help_text": "Default MCP server URL for SSE and streamable_http transports"
                },
                {
                    "name": "default_command",
                    "type": "text",
                    "label": "Default STDIO Command",
                    "default": "python",
                    "placeholder": "python",
                    "help_text": "Default command for STDIO transport (e.g., python, node)"
                },
                {
                    "name": "default_args",
                    "type": "textarea",
                    "label": "Default STDIO Arguments",
                    "default": '["server.py"]',
                    "placeholder": '["server.py"]',
                    "help_text": "Default arguments as JSON array for STDIO command",
                    "rows": 2
                },
                {
                    "name": "default_timeout",
                    "type": "number",
                    "label": "Default Timeout (seconds)",
                    "default": 30,
                    "min": 5,
                    "max": 300,
                    "help_text": "Default timeout for MCP operations"
                },
                {
                    "name": "default_headers",
                    "type": "textarea",
                    "label": "Default Headers (JSON)",
                    "default": '{}',
                    "placeholder": '{"Authorization": "Bearer token"}',
                    "help_text": "Default HTTP headers as JSON for streamable_http transport",
                    "rows": 3
                },
                {
                    "name": "sse_read_timeout",
                    "type": "number",
                    "label": "SSE Read Timeout (seconds)",
                    "default": 600,
                    "min": 30,
                    "max": 1800,
                    "help_text": "Timeout for SSE read operations in streamable_http transport"
                },
                {
                    "name": "terminate_on_close",
                    "type": "boolean",
                    "label": "Terminate Connection on Close",
                    "default": True,
                    "help_text": "Whether to terminate connection when closing for streamable_http"
                },
                {
                    "name": "security_acknowledgment",
                    "type": "select",
                    "label": "Security Risk Acknowledgment",
                    "default": "not_acknowledged",
                    "options": [
                        {"value": "not_acknowledged", "label": "⚠️ Security risks NOT acknowledged"},
                        {"value": "development_only", "label": "✓ Acknowledged - Development use only"},
                        {"value": "production_aware", "label": "✓ Acknowledged - Production use with extreme caution"}
                    ],
                    "help_text": "CRITICAL: MCP client can execute arbitrary code from external servers"
                }
            ]
        },
        "retrieve": {
            "name": "retrieve",
            "label": "Knowledge Base Retrieval",
            "description": "Retrieve information from Bedrock Knowledge Base with advanced filtering",
            "category": "builtin",
            "enabled": False,
            "config_fields": [
                {
                    "name": "runtime_parameters_note",
                    "type": "textarea",
                    "label": "Runtime Parameters (Read Only)",
                    "default": 'retrieve requires these parameters per call:\n• text: str (required) - query to search for\n• numberOfResults: int (optional) - max results (default: 5)\n• knowledgeBaseId: str (optional) - KB ID (uses KNOWLEDGE_BASE_ID env)\n• region: str (optional) - AWS region (default: us-west-2)\n• score: float (optional) - min score threshold (default: 0.4)\n• profile_name: str (optional) - AWS profile\n• retrieveFilter: dict (optional) - advanced filtering',
                    "disabled": True,
                    "help_text": "retrieve uses runtime parameters with environment variable defaults",
                    "rows": 5
                },
                {
                    "name": "default_knowledge_base_id",
                    "type": "text",
                    "label": "Default Knowledge Base ID",
                    "placeholder": "Set via KNOWLEDGE_BASE_ID env variable",
                    "help_text": "Default knowledge base ID when not specified in runtime call (uses KNOWLEDGE_BASE_ID environment variable)"
                },
                {
                    "name": "default_score_threshold",
                    "type": "range",
                    "label": "Default Score Threshold",
                    "default": 0.4,
                    "min": 0.0,
                    "max": 1.0,
                    "step": 0.1,
                    "help_text": "Default minimum similarity score threshold (uses MIN_SCORE environment variable)"
                },
                {
                    "name": "default_max_results",
                    "type": "number",
                    "label": "Default Maximum Results",
                    "default": 10,
                    "min": 1,
                    "max": 50,
                    "help_text": "Default maximum number of results when not specified"
                },
                {
                    "name": "default_region",
                    "type": "select",
                    "label": "Default AWS Region",
                    "default": "us-west-2",
                    "options": [
                        {"value": "us-east-1", "label": "US East (N. Virginia)"},
                        {"value": "us-west-2", "label": "US West (Oregon)"},
                        {"value": "eu-west-1", "label": "Europe (Ireland)"}
                    ],
                    "help_text": "Default AWS region (uses AWS_REGION environment variable)"
                },
                {
                    "name": "enable_advanced_filtering",
                    "type": "boolean",
                    "label": "Enable Advanced Filtering Support",
                    "default": True,
                    "help_text": "Enable support for retrieveFilter parameter with complex queries"
                }
            ]
        }
    }
    
    if tool_name not in tool_schemas:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found in category '{category}'"
        )
    
    return tool_schemas[tool_name]


@form_schema_router.post('/tools/validate')
async def validate_tool_configuration(config_data: Dict[str, Any], user_info = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Validate tool configuration data.
    
    Args:
        config_data: Tool configuration to validate
        
    Returns:
        Validation results with any errors or warnings
    """
    try:
        # Basic validation structure
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "validated_config": config_data
        }
        
        # Validate based on tool category and configuration
        category = config_data.get("category", "")
        tools = config_data.get("tools", [])
        
        if not category:
            validation_result["errors"].append("Tool category is required")
            validation_result["valid"] = False
        
        if not tools and category == "builtin":
            validation_result["warnings"].append("No tools selected for builtin category")
        
        # Category-specific validation
        if category == "builtin":
            for tool in tools:
                tool_name = tool.get("name", "")
                if not tool_name:
                    validation_result["errors"].append("Tool name is required for builtin tools")
                    validation_result["valid"] = False
                    continue
                
                # Validate tool configuration
                config = tool.get("config", {})
                if tool_name == "http_request":
                    timeout = config.get("timeout", 30)
                    if not isinstance(timeout, (int, float)) or timeout < 1 or timeout > 300:
                        validation_result["errors"].append(f"Invalid timeout for {tool_name}: must be between 1 and 300 seconds")
                        validation_result["valid"] = False
                
                elif tool_name == "use_aws":
                    region = config.get("default_region", "us-east-1")
                    valid_regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
                    if region not in valid_regions:
                        validation_result["warnings"].append(f"Non-standard AWS region for {tool_name}: {region}")
        
        elif category == "mcp":
            servers = config_data.get("servers", [])
            if not servers:
                validation_result["warnings"].append("No MCP servers configured")
            else:
                for server in servers:
                    if not server.get("name"):
                        validation_result["errors"].append("MCP server name is required")
                        validation_result["valid"] = False
                    if not server.get("url"):
                        validation_result["errors"].append("MCP server URL is required")
                        validation_result["valid"] = False
        
        elif category == "custom":
            modules = config_data.get("tool_modules", [])
            if not modules:
                validation_result["warnings"].append("No custom tool modules configured")
            else:
                for module in modules:
                    if not module.get("name"):
                        validation_result["errors"].append("Custom tool module name is required")
                        validation_result["valid"] = False
                    if not module.get("module_path"):
                        validation_result["errors"].append("Custom tool module path is required")
                        validation_result["valid"] = False
        
        return validation_result
        
    except Exception as e:
        log_exception_safely(logger, "Tool configuration validation error", e)
        return {
            "valid": False,
            "errors": ["Configuration validation failed"],
            "warnings": [],
            "validated_config": {}
        }
