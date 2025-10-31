"""
Agent configuration models for data validation and serialization.

This module provides Pydantic models for validating and serializing
agent configuration data throughout the application.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PromptRequest(BaseModel):
    """Request model for prompt processing."""
    
    prompt: str = Field(..., description="The prompt text to process")
    user_id: Optional[str] = Field(None, description="User identifier")
    agent_name: Optional[str] = Field(
        default="qa_agent", 
        description="Agent name for backward compatibility"
    )
    stream: Optional[bool] = Field(
        default=False, 
        description="Whether to stream the response"
    )


class ThinkingConfig(BaseModel):
    """Configuration for agent thinking processes."""
    
    type: str = Field(..., description="Type of thinking configuration")
    budget_tokens: int = Field(
        ..., 
        ge=0,
        description="Token budget for thinking processes"
    )


class ProviderConfig(BaseModel):
    """Configuration for external service providers."""
    
    name: str = Field(..., description="Provider name")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific configuration parameters"
    )


class ToolConfig(BaseModel):
    """Configuration for agent tools."""
    
    name: str = Field(..., description="Tool name")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific configuration parameters"
    )


class AgentConfigRequest(BaseModel):
    """Request model for saving agent configurations."""
    
    model_config = ConfigDict(protected_namespaces=())
    
    # Basic agent information
    agent_name: str = Field(..., description="Unique identifier for the agent")
    agent_description: str = Field(..., description="Human-readable agent description")
    
    # System prompt configuration
    system_prompt_name: str = Field(..., description="Name of the system prompt")
    system_prompt: str = Field(..., description="System prompt content")
    
    # Model configuration
    model_id: str = Field(..., description="Primary model identifier")
    judge_model_id: str = Field(..., description="Judge model identifier")
    embedding_model_id: str = Field(..., description="Embedding model identifier")
    region_name: str = Field(..., description="AWS region name")
    
    # Generation parameters
    temperature: float = Field(
        ..., 
        ge=0.0, 
        le=2.0,
        description="Temperature parameter for text generation"
    )
    top_p: float = Field(
        ..., 
        ge=0.0, 
        le=1.0,
        description="Top-p parameter for text generation"
    )
    
    # Configuration flags
    streaming: str = Field(..., description="Streaming configuration")
    cache_prompt: str = Field(..., description="Prompt caching configuration")
    cache_tools: str = Field(..., description="Tool caching configuration")
    
    # Advanced configurations
    thinking: ThinkingConfig = Field(..., description="Thinking process configuration")
    
    # Memory configuration
    memory: str = Field(..., description="Memory system configuration")
    memory_provider: str = Field(..., description="Memory provider type")
    memory_provider_details: List[ProviderConfig] = Field(
        default_factory=list,
        description="Memory provider configuration details"
    )
    
    # Knowledge base configuration
    knowledge_base: str = Field(..., description="Knowledge base configuration")
    knowledge_base_provider: str = Field(..., description="Knowledge base provider")
    knowledge_base_provider_type: str = Field(..., description="Knowledge base provider type")
    knowledge_base_details: List[ProviderConfig] = Field(
        default_factory=list,
        description="Knowledge base configuration details"
    )
    
    # Observability configuration
    observability: str = Field(..., description="Observability configuration")
    observability_provider: str = Field(..., description="Observability provider")
    observability_provider_details: List[ProviderConfig] = Field(
        default_factory=list,
        description="Observability provider configuration details"
    )
    
    # Guardrail configuration
    guardrail: str = Field(..., description="Guardrail configuration")
    guardrail_provider: str = Field(..., description="Guardrail provider")
    guardrail_provider_details: List[ProviderConfig] = Field(
        default_factory=list,
        description="Guardrail provider configuration details"
    )
    
    # Tools configuration
    tools: List[ToolConfig] = Field(
        default_factory=list,
        description="List of tool configurations"
    )
    
    # MCP configuration
    mcp_enabled: Optional[bool] = Field(
        default=False,
        description="Whether MCP (Model Context Protocol) integration is enabled"
    )
    mcp_servers: Optional[str] = Field(
        default="",
        description="JSON string containing MCP server configurations"
    )


class AgentConfigResponse(BaseModel):
    """Response model for agent configurations."""
    
    model_config = ConfigDict(protected_namespaces=())
    
    # Basic agent information
    agent_name: str = Field(..., description="Unique identifier for the agent")
    agent_description: str = Field(..., description="Human-readable agent description")
    
    # System prompt configuration
    system_prompt_name: str = Field(..., description="Name of the system prompt")
    system_prompt: str = Field(..., description="System prompt content")
    
    # Model configuration
    model_id: str = Field(..., description="Primary model identifier")
    judge_model_id: str = Field(..., description="Judge model identifier")
    embedding_model_id: str = Field(..., description="Embedding model identifier")
    region_name: str = Field(..., description="AWS region name")
    
    # Generation parameters
    temperature: float = Field(..., description="Temperature parameter for text generation")
    top_p: float = Field(..., description="Top-p parameter for text generation")
    
    # Configuration flags
    streaming: str = Field(..., description="Streaming configuration")
    cache_prompt: str = Field(..., description="Prompt caching configuration")
    cache_tools: str = Field(..., description="Tool caching configuration")
    
    # Advanced configurations
    thinking: ThinkingConfig = Field(..., description="Thinking process configuration")
    
    # Memory configuration
    memory: str = Field(..., description="Memory system configuration")
    memory_provider: str = Field(..., description="Memory provider type")
    memory_provider_details: List[ProviderConfig] = Field(
        ..., description="Memory provider configuration details"
    )
    
    # Knowledge base configuration
    knowledge_base: str = Field(..., description="Knowledge base configuration")
    knowledge_base_provider: str = Field(..., description="Knowledge base provider")
    knowledge_base_provider_type: str = Field(..., description="Knowledge base provider type")
    knowledge_base_details: List[ProviderConfig] = Field(
        ..., description="Knowledge base configuration details"
    )
    
    # Observability configuration
    observability: str = Field(..., description="Observability configuration")
    observability_provider: str = Field(..., description="Observability provider")
    observability_provider_details: List[ProviderConfig] = Field(
        ..., description="Observability provider configuration details"
    )
    
    # Guardrail configuration
    guardrail: str = Field(..., description="Guardrail configuration")
    guardrail_provider: str = Field(..., description="Guardrail provider")
    guardrail_provider_details: List[ProviderConfig] = Field(
        ..., description="Guardrail provider configuration details"
    )
    
    # Tools configuration
    tools: List[ToolConfig] = Field(..., description="List of tool configurations")
    
    # MCP configuration
    mcp_enabled: Optional[bool] = Field(
        default=False,
        description="Whether MCP (Model Context Protocol) integration is enabled"
    )
    mcp_servers: Optional[str] = Field(
        default="",
        description="JSON string containing MCP server configurations"
    )


class AgentNameRequest(BaseModel):
    """Request model for operations requiring only an agent name."""
    
    agent_name: str = Field(..., description="Unique identifier for the agent")


class AgentToolsUpdateRequest(BaseModel):
    """Request model for updating only the tools configuration of an agent."""
    
    agent_name: str = Field(..., description="Unique identifier for the agent")
    tools: List[ToolConfig] = Field(
        default_factory=list,
        description="List of tool configurations to update"
    )
