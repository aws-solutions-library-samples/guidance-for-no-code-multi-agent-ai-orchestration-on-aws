"""
SSM Data Models - Comprehensive representation of all data stored in SSM Parameter Store.

This module provides Pydantic models that define the exact structure of data
stored in SSM, ensuring consistency between storage, retrieval, and validation.
"""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, RootModel, Field
from enum import Enum


class PromptCategory(str, Enum):
    """Categories for organizing prompt templates."""
    GENERAL = "general"
    TECHNICAL = "technical"
    FINANCIAL = "financial"
    DATA = "data"
    COORDINATION = "coordination"
    EXTERNAL_API = "external_api"
    CUSTOM = "custom"


class ThinkingType(str, Enum):
    """Types of thinking configurations."""
    STANDARD = "standard"
    ENABLED = "enabled"
    DISABLED = "disabled"


class ProviderType(str, Enum):
    """Provider types for various services."""
    NO = "No"
    YES = "Yes"
    DEFAULT = "default"
    CUSTOM = "custom"
    # Memory providers
    MEM0 = "mem0"
    ELASTICSEARCH = "elasticsearch"
    BEDROCK_AGENTCORE = "bedrock_agentcore"
    OPENSEARCH = "opensearch"
    # Knowledge base providers
    BEDROCK = "bedrock"
    BEDROCK_KB = "bedrock_kb"
    CUSTOM_KB = "custom_kb"
    # Guardrail providers
    BEDROCK_GUARDRAIL = "bedrock"


class StreamingType(str, Enum):
    """Streaming configuration options."""
    TRUE = "True"
    FALSE = "False"  
    ENABLED = "enabled"
    DISABLED = "disabled"
    YES = "Yes"
    NO = "No"


class SSMThinkingConfig(BaseModel):
    """Thinking configuration stored in SSM."""
    type: ThinkingType = Field(..., description="Type of thinking configuration")
    budget_tokens: int = Field(
        default=100000,
        ge=0,
        description="Token budget for thinking processes"
    )


class SSMProviderConfig(BaseModel):
    """Provider configuration stored in SSM."""
    name: str = Field(..., description="Provider name")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific configuration parameters"
    )


class SSMToolConfig(BaseModel):
    """Tool configuration stored in SSM."""
    name: str = Field(..., description="Tool name")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific configuration parameters"
    )


class SSMAgentConfiguration(BaseModel):
    """
    Complete agent configuration as stored in SSM Parameter Store.
    
    This model defines the exact structure of data stored at:
    /agent/{agent_name}/config
    """
    
    # Basic agent information
    agent_name: str = Field(..., description="Unique identifier for the agent")
    agent_description: str = Field(..., description="Human-readable agent description")
    
    # System prompt configuration
    system_prompt_name: str = Field(..., description="Name of the system prompt template")
    
    # Model configuration - all model IDs should include region prefix (us.)
    model_id: str = Field(
        ..., 
        description="Primary model identifier with region prefix (e.g. us.anthropic.claude-3-5-sonnet-20241022-v2:0)"
    )
    model_ids: Optional[List[str]] = Field(
        default=None,
        description="Multiple model identifiers for dynamic model switching (optional, for multi-model support)"
    )
    judge_model_id: str = Field(
        ..., 
        description="Judge model identifier with region prefix for evaluation tasks"
    )
    embedding_model_id: str = Field(
        ..., 
        description="Embedding model identifier for text embeddings and similarity"
    )
    region_name: str = Field(
        default="us-east-1",
        description="AWS region name for model deployment"
    )
    
    # Generation parameters
    temperature: float = Field(
        default=0.7,
        ge=0.0, 
        le=2.0,
        description="Temperature parameter for text generation randomness"
    )
    top_p: float = Field(
        default=0.9,
        ge=0.0, 
        le=1.0,
        description="Top-p parameter for nucleus sampling"
    )
    
    # Configuration flags - stored as strings in SSM for consistency
    streaming: StreamingType = Field(
        default=StreamingType.TRUE,
        description="Streaming configuration flag"
    )
    cache_prompt: StreamingType = Field(
        default=StreamingType.FALSE,
        description="Prompt caching configuration flag"
    )
    cache_tools: StreamingType = Field(
        default=StreamingType.FALSE,
        description="Tool caching configuration flag"
    )
    
    # Advanced configurations
    thinking: SSMThinkingConfig = Field(
        default_factory=lambda: SSMThinkingConfig(type=ThinkingType.STANDARD, budget_tokens=100000),
        description="Thinking process configuration"
    )
    
    # Memory configuration - stored as strings for UI compatibility
    memory: StreamingType = Field(
        default=StreamingType.FALSE,
        description="Memory system enable/disable flag"
    )
    memory_provider: ProviderType = Field(
        default=ProviderType.NO,
        description="Memory provider type selection"
    )
    memory_provider_details: List[SSMProviderConfig] = Field(
        default_factory=list,
        description="Memory provider configuration details"
    )
    
    # Knowledge base configuration - stored as strings for UI compatibility
    knowledge_base: StreamingType = Field(
        default=StreamingType.FALSE,
        description="Knowledge base enable/disable flag"
    )
    knowledge_base_provider: ProviderType = Field(
        default=ProviderType.NO,
        description="Knowledge base provider type"
    )
    knowledge_base_provider_type: ProviderType = Field(
        default=ProviderType.NO,
        description="Knowledge base provider implementation type"
    )
    knowledge_base_details: List[SSMProviderConfig] = Field(
        default_factory=list,
        description="Knowledge base configuration details"
    )
    
    # Observability configuration - stored as strings for UI compatibility
    observability: StreamingType = Field(
        default=StreamingType.FALSE,
        description="Observability enable/disable flag"
    )
    observability_provider: str = Field(
        default="No",
        description="Observability provider selection (langfuse, dynatrace, etc.)"
    )
    observability_provider_details: List[SSMProviderConfig] = Field(
        default_factory=list,
        description="Observability provider configuration details"
    )
    
    # Guardrail configuration - stored as strings for UI compatibility  
    guardrail: StreamingType = Field(
        default=StreamingType.FALSE,
        description="Guardrail enable/disable flag"
    )
    guardrail_provider: ProviderType = Field(
        default=ProviderType.NO,
        description="Guardrail provider type"
    )
    guardrail_provider_details: List[SSMProviderConfig] = Field(
        default_factory=list,
        description="Guardrail provider configuration details"
    )
    
    # Tools configuration
    tools: List[SSMToolConfig] = Field(
        default_factory=list,
        description="List of tool configurations for the agent"
    )


class SSMPromptMetadata(BaseModel):
    """
    Individual prompt metadata in the global prompt library index.
    """
    parameter_name: str = Field(..., description="SSM parameter name for this prompt")
    file_name: str = Field(..., description="Original markdown filename")
    category: PromptCategory = Field(..., description="Prompt category classification")
    description: str = Field(..., description="Human-readable description of the prompt")


class SSMSystemPromptIndex(RootModel[Dict[str, str]]):
    """
    System prompt index as stored in SSM Parameter Store.
    
    This model defines the structure of data stored at:
    /agent/{agent_name}/system-prompts/index
    
    Example: {"qa": "/agent/qa_agent/system-prompts/qa", ...}
    """
    root: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of prompt names to their SSM parameter paths"
    )


class SSMPromptLibraryIndex(RootModel[Dict[str, SSMPromptMetadata]]):
    """
    Global prompt library index as stored in SSM Parameter Store.
    
    This model defines the structure of data stored at:
    /prompts/index
    """
    root: Dict[str, SSMPromptMetadata] = Field(
        default_factory=dict,
        description="Global index of all available prompt templates with metadata"
    )


class SSMParameterStructure(BaseModel):
    """
    Complete representation of all SSM parameter structures used in the system.
    
    This class serves as documentation and validation for the entire SSM data architecture.
    """
    
    # Agent Configurations
    agent_configs: Dict[str, SSMAgentConfiguration] = Field(
        default_factory=dict,
        description="Agent configurations stored at /agent/{agent_name}/config"
    )
    
    # System Prompts (raw content)
    system_prompts: Dict[str, str] = Field(
        default_factory=dict,
        description="System prompt content stored at /agent/{agent_name}/system-prompts/{prompt_name}"
    )
    
    # System Prompt Indexes
    system_prompt_indexes: Dict[str, SSMSystemPromptIndex] = Field(
        default_factory=dict,
        description="System prompt indexes stored at /agent/{agent_name}/system-prompts/index"
    )
    
    # Global Prompt Library (raw content)
    global_prompts: Dict[str, str] = Field(
        default_factory=dict,
        description="Global prompt templates stored at /prompts/{prompt_name}"
    )
    
    # Global Prompt Library Index
    global_prompt_index: Optional[SSMPromptLibraryIndex] = Field(
        default=None,
        description="Global prompt library index stored at /prompts/index"
    )
    
    @classmethod
    def get_expected_parameters(cls) -> Dict[str, str]:
        """
        Get a dictionary of all expected SSM parameter paths and their data types.
        
        Returns:
            Dictionary mapping parameter paths to their expected data types
        """
        return {
            # Agent configurations
            "/agent/{agent_name}/config": "JSON - SSMAgentConfiguration",
            
            # System prompts  
            "/agent/{agent_name}/system-prompts/{prompt_name}": "String - Raw prompt content",
            "/agent/{agent_name}/system-prompts/index": "JSON - SSMSystemPromptIndex",
            
            # Global prompt library
            "/prompts/{prompt_name}": "String - Raw prompt content from markdown files",
            "/prompts/index": "JSON - SSMPromptLibraryIndex",
        }
    
    @classmethod
    def validate_agent_config_completeness(cls, config_data: Dict[str, Any]) -> List[str]:
        """
        Validate that an agent configuration contains all required fields.
        
        Args:
            config_data: Agent configuration dictionary from SSM
            
        Returns:
            List of missing field names (empty if complete)
        """
        try:
            # Try to create the model - will raise ValidationError if incomplete
            SSMAgentConfiguration(**config_data)
            return []
        except Exception as e:
            # Extract missing field names from validation error
            missing_fields = []
            error_str = str(e)
            
            # Parse Pydantic validation errors to extract field names
            if "validation error" in error_str.lower():
                # Extract field names from validation error messages
                lines = error_str.split('\n')
                for line in lines:
                    if "Field required" in line and "[type=missing" in line:
                        # Find the field name in the error
                        parts = line.split()
                        for part in parts:
                            if not part.startswith('[') and not part.endswith(']') and part != 'Field' and part != 'required':
                                if part not in ['type=missing,', 'input_value=']:
                                    missing_fields.append(part)
                                    break
            
            return missing_fields
    
    @classmethod
    def create_complete_qa_agent_config(cls) -> SSMAgentConfiguration:
        """Create a complete QA agent configuration with all required fields."""
        return SSMAgentConfiguration(
            agent_name="qa_agent",
            agent_description="Default Question Answer Agent",
            system_prompt_name="qa",
            model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            judge_model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            embedding_model_id="amazon.titan-embed-text-v2:0",
            region_name="us-east-1",
            temperature=0.7,
            top_p=0.9,
            streaming=StreamingType.TRUE,
            cache_prompt=StreamingType.FALSE,
            cache_tools=StreamingType.FALSE,
            thinking=SSMThinkingConfig(type=ThinkingType.STANDARD, budget_tokens=100000),
            memory=StreamingType.FALSE,
            memory_provider=ProviderType.NO,
            memory_provider_details=[],
            knowledge_base=StreamingType.FALSE,
            knowledge_base_provider=ProviderType.NO,
            knowledge_base_provider_type=ProviderType.NO,
            knowledge_base_details=[],
            observability=StreamingType.FALSE,
            observability_provider="No",
            observability_provider_details=[],
            guardrail=StreamingType.FALSE,
            guardrail_provider=ProviderType.NO,
            guardrail_provider_details=[],
            tools=[]
        )
    
    @classmethod
    def create_complete_supervisor_agent_config(cls) -> SSMAgentConfiguration:
        """Create a complete supervisor agent configuration with all required fields."""
        return SSMAgentConfiguration(
            agent_name="supervisor_agent",
            agent_description="Multi-Agent Supervisor",
            system_prompt_name="supervisor",
            model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
            judge_model_id="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            embedding_model_id="amazon.titan-embed-text-v2:0",
            region_name="us-east-1",
            temperature=0.7,
            top_p=0.9,
            streaming=StreamingType.TRUE,
            cache_prompt=StreamingType.FALSE,
            cache_tools=StreamingType.FALSE,
            thinking=SSMThinkingConfig(type=ThinkingType.STANDARD, budget_tokens=100000),
            memory=StreamingType.FALSE,
            memory_provider=ProviderType.NO,
            memory_provider_details=[],
            knowledge_base=StreamingType.FALSE,
            knowledge_base_provider=ProviderType.NO,
            knowledge_base_provider_type=ProviderType.NO,
            knowledge_base_details=[],
            observability=StreamingType.TRUE,
            observability_provider="langfuse",
            observability_provider_details=[
                SSMProviderConfig(
                    name="langfuse",
                    config={
                        "enabled": False,
                        "trace_level": "info"
                    }
                )
            ],
            guardrail=StreamingType.FALSE,
            guardrail_provider=ProviderType.NO,
            guardrail_provider_details=[],
            tools=[]
        )


class SSMParameterPaths(BaseModel):
    """
    Standardized SSM parameter path patterns used throughout the system.
    
    This ensures consistent parameter naming across all components.
    """
    
    @staticmethod
    def agent_config(agent_name: str) -> str:
        """Get SSM parameter path for agent configuration."""
        return f"/agent/{agent_name}/config"
    
    @staticmethod
    def agent_system_prompt(agent_name: str, prompt_name: str) -> str:
        """Get SSM parameter path for agent system prompt."""
        return f"/agent/{agent_name}/system-prompts/{prompt_name}"
    
    @staticmethod
    def agent_system_prompt_index(agent_name: str) -> str:
        """Get SSM parameter path for agent system prompt index."""
        return f"/agent/{agent_name}/system-prompts/index"
    
    @staticmethod
    def global_prompt(prompt_name: str) -> str:
        """Get SSM parameter path for global prompt template."""
        return f"/prompts/{prompt_name}"
    
    @staticmethod
    def global_prompt_index() -> str:
        """Get SSM parameter path for global prompt library index."""
        return "/prompts/index"
    
    @classmethod
    def get_all_parameter_patterns(cls) -> List[str]:
        """Get list of all SSM parameter path patterns used in the system."""
        return [
            "/agent/{agent_name}/config",
            "/agent/{agent_name}/system-prompts/{prompt_name}",
            "/agent/{agent_name}/system-prompts/index", 
            "/prompts/{prompt_name}",
            "/prompts/index"
        ]
    
    @classmethod
    def validate_parameter_path(cls, path: str) -> bool:
        """
        Validate that a parameter path follows expected patterns.
        
        Args:
            path: SSM parameter path to validate
            
        Returns:
            True if path follows expected pattern, False otherwise
        """
        patterns = [
            r"^/agent/[^/]+/config$",
            r"^/agent/[^/]+/system-prompts/[^/]+$",
            r"^/agent/[^/]+/system-prompts/index$",
            r"^/prompts/[^/]+$",
            r"^/prompts/index$"
        ]
        
        import re
        for pattern in patterns:
            if re.match(pattern, path):
                return True
        return False


class SSMDataValidator(BaseModel):
    """
    Validation utilities for SSM data consistency and completeness.
    """
    
    @staticmethod
    def validate_agent_configuration(config_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate agent configuration data against the SSM model.
        
        Args:
            config_data: Agent configuration dictionary
            
        Returns:
            Dictionary with validation results
        """
        try:
            # Try to create the SSM model
            validated_config = SSMAgentConfiguration(**config_data)
            
            return {
                "valid": True,
                "model": validated_config.model_dump(mode='json'),
                "errors": [],
                "warnings": []
            }
            
        except Exception as e:
            missing_fields = SSMParameterStructure.validate_agent_config_completeness(config_data)
            
            return {
                "valid": False,
                "model": None,
                "errors": [str(e)],
                "missing_fields": missing_fields,
                "warnings": []
            }
    
    @staticmethod
    def compare_configs(ssm_data: Dict[str, Any], api_response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare SSM stored data with API response data to identify discrepancies.
        
        Args:
            ssm_data: Raw data from SSM parameter
            api_response: Data returned by API endpoint
            
        Returns:
            Dictionary with comparison results and discrepancies
        """
        discrepancies = {}
        
        # Compare each field
        all_keys = set(list(ssm_data.keys()) + list(api_response.keys()))
        
        for key in all_keys:
            ssm_value = ssm_data.get(key, "<MISSING>")
            api_value = api_response.get(key, "<MISSING>")
            
            # Handle type conversions and compare
            if ssm_value != api_value:
                discrepancies[key] = {
                    "ssm_value": ssm_value,
                    "ssm_type": type(ssm_value).__name__,
                    "api_value": api_value,
                    "api_type": type(api_value).__name__
                }
        
        return {
            "identical": len(discrepancies) == 0,
            "discrepancies": discrepancies,
            "total_fields_compared": len(all_keys),
            "discrepancy_count": len(discrepancies)
        }


# Export all models for use in other modules
__all__ = [
    "SSMAgentConfiguration",
    "SSMThinkingConfig", 
    "SSMProviderConfig",
    "SSMToolConfig",
    "SSMSystemPromptIndex",
    "SSMPromptMetadata",
    "SSMPromptLibraryIndex",
    "SSMParameterStructure",
    "SSMParameterPaths",
    "SSMDataValidator",
    "PromptCategory",
    "ThinkingType",
    "ProviderType", 
    "StreamingType"
]
