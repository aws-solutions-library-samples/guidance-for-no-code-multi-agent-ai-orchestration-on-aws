"""
Form schema models for dynamic UI generation.

This module provides the single source of truth for form field definitions
used to generate dynamic forms in the frontend.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field

# Import BedrockModelService for dynamic model options
from ..services.bedrock_model_service import BedrockModelService


class FieldType(str, Enum):
    """Supported form field types."""
    TEXT = "text"
    PASSWORD = None
    EMAIL = "email"
    URL = "url"
    NUMBER = "number"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RANGE = "range"


class ValidationRule(BaseModel):
    """Validation rule for form fields."""
    type: str = Field(..., description="Type of validation rule")
    value: Union[str, int, float, bool] = Field(..., description="Validation value")
    message: Optional[str] = Field(None, description="Custom validation message")


class SelectOption(BaseModel):
    """Option for select field types."""
    value: str = Field(..., description="Option value")
    label: str = Field(..., description="Option display label")
    disabled: Optional[bool] = Field(False, description="Whether option is disabled")


class FormField(BaseModel):
    """Definition of a form field."""
    name: str = Field(..., description="Field name/key")
    type: FieldType = Field(..., description="Field input type")
    label: str = Field(..., description="Field display label")
    placeholder: Optional[str] = Field(None, description="Placeholder text")
    help_text: Optional[str] = Field(None, description="Help text description")
    required: bool = Field(False, description="Whether field is required")
    default_value: Optional[Union[str, int, float, bool, List[str]]] = Field(None, description="Default field value")
    
    # Field-specific configurations
    options: Optional[List[SelectOption]] = Field(None, description="Options for select fields")
    min_value: Optional[Union[int, float]] = Field(None, description="Minimum value for number/range fields")
    max_value: Optional[Union[int, float]] = Field(None, description="Maximum value for number/range fields")
    step: Optional[Union[int, float]] = Field(None, description="Step value for number/range fields")
    rows: Optional[int] = Field(None, description="Rows for textarea fields")
    max_selections: Optional[int] = Field(None, description="Maximum number of selections for multi-select fields")
    
    # Validation
    validation: Optional[List[ValidationRule]] = Field(None, description="Validation rules")
    
    # UI hints
    secure: Optional[bool] = Field(False, description="Whether field contains sensitive data")
    conditional: Optional[Dict[str, Any]] = Field(None, description="Conditional display logic")
    disabled: Optional[bool] = Field(False, description="Whether field is disabled/read-only")


class ProviderFormSchema(BaseModel):
    """Form schema for a provider."""
    provider_name: str = Field(..., description="Provider name")
    provider_label: str = Field(..., description="Human-readable provider name")
    description: Optional[str] = Field(None, description="Provider description")
    fields: List[FormField] = Field(..., description="List of form fields")


class ComponentFormSchema(BaseModel):
    """Complete form schema for a component type."""
    component_type: str = Field(..., description="Component type (e.g., knowledge_base, memory)")
    providers: Dict[str, ProviderFormSchema] = Field(..., description="Provider schemas by name")


class FormSchemaRegistry:
    """
    Registry for all form schemas - single source of truth.
    
    This class contains all form field definitions and serves as the
    single source of truth for both API validation and UI generation.
    """
    
    @staticmethod
    def get_knowledge_base_schemas() -> Dict[str, ProviderFormSchema]:
        """Get form schemas for knowledge base providers."""
        return {
            "bedrock": ProviderFormSchema(
                provider_name="bedrock",
                provider_label="Amazon Bedrock Knowledge Base",
                description="Connect to Amazon Bedrock Knowledge Base for retrieval-augmented generation",
                fields=[
                    FormField(
                        name="knowledge_base_id",
                        type=FieldType.TEXT,
                        label="Knowledge Base ID",
                        placeholder="Enter Bedrock Knowledge Base ID",
                        help_text="The unique identifier for your Bedrock Knowledge Base",
                        required=True,
                        validation=[
                            ValidationRule(
                                type="pattern",
                                value="^[a-zA-Z0-9]+$",
                                message="Knowledge Base ID must contain only letters and numbers"
                            )
                        ]
                    ),
                    FormField(
                        name="data_source_id",
                        type=FieldType.TEXT,
                        label="Data Source ID (Optional)",
                        placeholder="Enter Data Source ID",
                        help_text="Optional data source identifier within the knowledge base",
                        required=False
                    )
                ]
            ),
            
            "elasticsearch": ProviderFormSchema(
                provider_name="elasticsearch",
                provider_label="Elasticsearch",
                description="Connect to Elasticsearch cluster for document search and retrieval",
                fields=[
                    FormField(
                        name="endpoint",
                        type=FieldType.URL,
                        label="Elasticsearch Endpoint",
                        placeholder="https://elasticsearch-endpoint.amazonaws.com",
                        help_text="The HTTPS endpoint of your Elasticsearch cluster",
                        required=True
                    ),
                    FormField(
                        name="index_name",
                        type=FieldType.TEXT,
                        label="Index Name",
                        placeholder="knowledge-index",
                        help_text="The name of the Elasticsearch index to search",
                        required=True
                    ),
                    FormField(
                        name="username",
                        type=FieldType.TEXT,
                        label="Username (Optional)",
                        placeholder="elasticsearch-user",
                        help_text="Username for authentication (if required)",
                        required=False
                    ),
                    FormField(
                        name="password",
                        type=FieldType.PASSWORD,
                        label="Password (Optional)",
                        placeholder="Enter password",
                        help_text="Password for authentication (if required)",
                        required=False,
                        secure=True
                    )
                ]
            ),
            
            "snowflake": ProviderFormSchema(
                provider_name="snowflake",
                provider_label="Snowflake Cortex Analyst",
                description="Connect to Snowflake Cortex Analyst for natural language business intelligence",
                fields=[
                    FormField(
                        name="snowflake_account",
                        type=FieldType.TEXT,
                        label="Snowflake Account",
                        placeholder="your-account.snowflakecomputing.com",
                        help_text="Your Snowflake account identifier",
                        required=True
                    ),
                    FormField(
                        name="snowflake_username",
                        type=FieldType.TEXT,
                        label="Username",
                        placeholder="snowflake-username",
                        help_text="Snowflake username for authentication",
                        required=True
                    ),
                    FormField(
                        name="snowflake_role",
                        type=FieldType.TEXT,
                        label="Role",
                        placeholder="ACCOUNTADMIN",
                        help_text="Snowflake role to use for connections",
                        required=False,
                        default_value="ACCOUNTADMIN"
                    ),
                    FormField(
                        name="snowflake_warehouse",
                        type=FieldType.TEXT,
                        label="Warehouse",
                        placeholder="LARGE_WH",
                        help_text="Snowflake warehouse for query execution",
                        required=False,
                        default_value="LARGE_WH"
                    ),
                    FormField(
                        name="snowflake_database",
                        type=FieldType.TEXT,
                        label="Database",
                        placeholder="SALES_INTELLIGENCE",
                        help_text="Target database name",
                        required=False,
                        default_value="SALES_INTELLIGENCE"
                    ),
                    FormField(
                        name="snowflake_schema",
                        type=FieldType.TEXT,
                        label="Schema",
                        placeholder="DATA",
                        help_text="Database schema name",
                        required=False,
                        default_value="DATA"
                    ),
                    FormField(
                        name="semantic_model_path",
                        type=FieldType.TEXT,
                        label="Semantic Model Path",
                        placeholder="@your_stage/semantic_model.yaml",
                        help_text="Path to your Cortex Analyst semantic model file",
                        required=True
                    ),
                    FormField(
                        name="snowflake_private_key_content",
                        type=FieldType.TEXTAREA,
                        label="Private Key Content",
                        placeholder="Private Key or base64 encoded content",
                        help_text="Private key for JWT authentication (stored securely in SSM)",
                        required=True,
                        secure=True,
                        rows=4
                    ),
                    FormField(
                        name="snowflake_private_key_passphrase",
                        type=FieldType.PASSWORD,
                        label="Private Key Passphrase",
                        placeholder="Enter private key passphrase",
                        help_text="Passphrase for the private key",
                        required=True,
                        secure=True
                    )
                ]
            ),
            
            "aurora": ProviderFormSchema(
                provider_name="aurora",
                provider_label="Aurora PostgreSQL Knowledge Base",
                description="Connect to Aurora PostgreSQL database via Data API for knowledge base functionality",
                fields=[
                    FormField(
                        name="aurora_cluster_arn",
                        type=FieldType.TEXT,
                        label="Aurora Cluster ARN",
                        placeholder="arn:aws:rds:us-east-1:123456789012:cluster:your-cluster-name",
                        help_text="The ARN of your Aurora PostgreSQL cluster with Data API enabled",
                        required=True,
                        validation=[
                            ValidationRule(
                                type="pattern",
                                value="^arn:aws:rds:.+:.+:cluster:.+$",
                                message="Must be a valid Aurora cluster ARN"
                            )
                        ]
                    ),
                    FormField(
                        name="aurora_secret_arn",
                        type=FieldType.TEXT,
                        label="Aurora Secret ARN",
                        placeholder="arn:aws:secretsmanager:us-east-1:123456789012:secret:your-secret-name",
                        help_text="The ARN of the Secrets Manager secret containing database credentials",
                        required=True,
                        secure=True,
                        validation=[
                            ValidationRule(
                                type="pattern",
                                value="^arn:aws:secretsmanager:.+:.+:secret:.+$",
                                message="Must be a valid Secrets Manager secret ARN"
                            )
                        ]
                    ),
                    FormField(
                        name="aurora_database_name",
                        type=FieldType.TEXT,
                        label="Database Name",
                        placeholder="db_finserve_intel",
                        help_text="The name of the database within the Aurora cluster",
                        required=True,
                        default_value="db_finserve_intel"
                    ),
                    FormField(
                        name="aurora_region",
                        type=FieldType.SELECT,
                        label="AWS Region",
                        help_text="AWS region where the Aurora cluster is deployed",
                        required=True,
                        default_value="us-east-1",
                        options=[
                            SelectOption(value="us-east-1", label="US East (N. Virginia)"),
                            SelectOption(value="us-west-2", label="US West (Oregon)"),
                            SelectOption(value="us-west-1", label="US West (N. California)"),
                            SelectOption(value="eu-west-1", label="Europe (Ireland)"),
                            SelectOption(value="eu-central-1", label="Europe (Frankfurt)"),
                            SelectOption(value="ap-southeast-1", label="Asia Pacific (Singapore)"),
                            SelectOption(value="ap-northeast-1", label="Asia Pacific (Tokyo)")
                        ]
                    ),
                    FormField(
                        name="aurora_schema_name",
                        type=FieldType.TEXT,
                        label="Schema Name (Optional)",
                        placeholder="schema-finserve-intel",
                        help_text="Database schema name to search within (optional, defaults to public schema)",
                        required=False,
                        default_value="schema-finserve-intel"
                    ),
                    FormField(
                        name="aurora_max_results",
                        type=FieldType.NUMBER,
                        label="Max Results",
                        placeholder="10",
                        help_text="Maximum number of results to return from queries",
                        required=False,
                        default_value=10,
                        min_value=1,
                        max_value=100
                    ),
                    FormField(
                        name="aurora_timeout",
                        type=FieldType.NUMBER,
                        label="Query Timeout (seconds)",
                        placeholder="30",
                        help_text="Timeout for Data API queries in seconds",
                        required=False,
                        default_value=30,
                        min_value=5,
                        max_value=300
                    )
                ]
            ),
            
            "mongodb": ProviderFormSchema(
                provider_name="mongodb",
                provider_label="MongoDB Atlas Knowledge Base",
                description="Connect to MongoDB Atlas for vector search and document retrieval using LangChain",
                fields=[
                    FormField(
                        name="mongodb_atlas_cluster_uri",
                        type=FieldType.TEXT,
                        label="MongoDB Atlas Cluster URI",
                        placeholder="mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0",
                        help_text="The complete connection string for your MongoDB Atlas cluster including credentials",
                        required=True,
                        secure=True,
                        validation=[
                            ValidationRule(
                                type="pattern",
                                value=r"^mongodb(\+srv)?://.*",
                                message="Must be a valid MongoDB connection string starting with mongodb:// or mongodb+srv://"
                            )
                        ]
                    ),
                    FormField(
                        name="database_name",
                        type=FieldType.TEXT,
                        label="Database Name",
                        placeholder="db_aaa",
                        help_text="The name of the MongoDB database containing your documents",
                        required=True,
                        default_value="db_aaa"
                    ),
                    FormField(
                        name="collection_name",
                        type=FieldType.TEXT,
                        label="Collection Name",
                        placeholder="collection_aaa",
                        help_text="The name of the MongoDB collection containing your documents",
                        required=True,
                        default_value="collection_aaa"
                    ),
                    FormField(
                        name="index_name",
                        type=FieldType.TEXT,
                        label="Vector Search Index Name",
                        placeholder="index_aaa",
                        help_text="The name of the MongoDB Atlas vector search index for semantic search",
                        required=True,
                        default_value="index_aaa"
                    ),
                    FormField(
                        name="max_results",
                        type=FieldType.NUMBER,
                        label="Max Results",
                        placeholder="5",
                        help_text="Maximum number of results to return from semantic search",
                        required=False,
                        default_value=5,
                        min_value=1,
                        max_value=50
                    ),
                    FormField(
                        name="similarity_threshold",
                        type=FieldType.RANGE,
                        label="Similarity Threshold",
                        help_text="Minimum similarity score for search results (0.0 = any similarity, 1.0 = exact match)",
                        required=False,
                        default_value=0.7,
                        min_value=0.0,
                        max_value=1.0,
                        step=0.1
                    )
                ]
            )
        }
    
    @staticmethod
    def get_memory_schemas() -> Dict[str, ProviderFormSchema]:
        """Get form schemas for memory providers."""
        return {
            "mem0": ProviderFormSchema(
                provider_name="mem0",
                provider_label="Mem0",
                description="AI-powered memory layer for conversation context",
                fields=[
                    FormField(
                        name="enabled",
                        type=FieldType.CHECKBOX,
                        label="Enable Memory Integration",
                        help_text="Enable Mem0 memory integration for conversation context",
                        required=False,
                        default_value=False
                    ),
                    FormField(
                        name="api_key",
                        type=FieldType.PASSWORD,
                        label="Mem0 API Key",
                        placeholder="Enter Mem0 API key",
                        help_text="Your Mem0 service API key",
                        required=True,
                        secure=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    )
                ]
            ),
            
            "bedrock_agentcore": ProviderFormSchema(
                provider_name="bedrock_agentcore",
                provider_label="Amazon Bedrock AgentCore",
                description="AWS Bedrock AgentCore memory service with short-term and long-term memory capabilities",
                fields=[
                    FormField(
                        name="enabled",
                        type=FieldType.CHECKBOX,
                        label="Enable Memory Integration",
                        help_text="Enable Bedrock AgentCore memory integration for advanced conversation context and learning",
                        required=False,
                        default_value=False
                    ),
                    FormField(
                        name="region",
                        type=FieldType.SELECT,
                        label="AWS Region",
                        help_text="AWS region for Bedrock AgentCore memory service",
                        required=True,
                        default_value="us-east-1",
                        options=[
                            SelectOption(value="us-east-1", label="US East (N. Virginia)"),
                            SelectOption(value="us-west-2", label="US West (Oregon)"),
                            SelectOption(value="us-west-1", label="US West (N. California)"),
                            SelectOption(value="eu-west-1", label="Europe (Ireland)"),
                            SelectOption(value="eu-central-1", label="Europe (Frankfurt)"),
                            SelectOption(value="ap-southeast-1", label="Asia Pacific (Singapore)"),
                            SelectOption(value="ap-northeast-1", label="Asia Pacific (Tokyo)")
                        ],
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="memory_name",
                        type=FieldType.TEXT,
                        label="Memory Resource Name",
                        placeholder="GenAI_In_A_Box_Memory",
                        help_text="Name for the Bedrock AgentCore memory resource. Must start with a letter and contain only letters, numbers, and underscores. Examples: AgenticAiAccelerator, GenAI_Memory, MyAgentMemory",
                        required=True,
                        default_value="GenAI_In_A_Box_Memory",
                        validation=[
                            ValidationRule(
                                type="pattern",
                                value="^[a-zA-Z][a-zA-Z0-9_]{0,47}$",
                                message="Memory name must start with a letter and contain only letters, numbers, and underscores (no hyphens). Max 48 characters. Try: agentic_ai_accelerator or AgenticAiAccelerator"
                            )
                        ],
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="memory_id",
                        type=FieldType.TEXT,
                        label="Existing Memory ID (Optional)",
                        placeholder="Leave empty to create new memory resource",
                        help_text="Use existing Bedrock AgentCore memory resource ID, or leave empty to create a new one",
                        required=False,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="event_expiry_days",
                        type=FieldType.NUMBER,
                        label="Event Expiry Days",
                        placeholder="90",
                        help_text="Number of days to retain conversation events (default: 90 days)",
                        required=False,
                        default_value=90,
                        min_value=1,
                        max_value=365,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="enable_short_term_memory",
                        type=FieldType.CHECKBOX,
                        label="Enable Short-term Memory",
                        help_text="Enable session-based short-term memory for recent conversation context",
                        required=False,
                        default_value=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="enable_long_term_memory",
                        type=FieldType.CHECKBOX,
                        label="Enable Long-term Memory",
                        help_text="Enable persistent long-term memory for user preferences and important facts",
                        required=False,
                        default_value=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="enable_semantic_search",
                        type=FieldType.CHECKBOX,
                        label="Enable Semantic Search",
                        help_text="Enable semantic search capabilities for intelligent memory retrieval",
                        required=False,
                        default_value=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="enable_memory_hooks",
                        type=FieldType.CHECKBOX,
                        label="Enable Memory Hooks",
                        help_text="Enable automatic context injection and interaction saving through memory hooks",
                        required=False,
                        default_value=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="memory_execution_role_arn",
                        type=FieldType.TEXT,
                        label="Memory Execution Role ARN (Optional)",
                        placeholder="arn:aws:iam::123456789012:role/BedrockAgentCoreMemoryRole",
                        help_text="IAM role ARN for Bedrock AgentCore memory operations (optional, uses default if not specified)",
                        required=False,
                        validation=[
                            ValidationRule(
                                type="pattern",
                                value="^(arn:aws:iam::[0-9]{12}:role/.+)?$",
                                message="Must be a valid IAM role ARN or empty"
                            )
                        ],
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    )
                ]
            ),
            
            "opensearch": ProviderFormSchema(
                provider_name="opensearch",
                provider_label="OpenSearch",
                description="Amazon OpenSearch for memory storage and retrieval",
                fields=[
                    FormField(
                        name="enabled",
                        type=FieldType.CHECKBOX,
                        label="Enable Memory Integration",
                        help_text="Enable OpenSearch memory integration for conversation context",
                        required=False,
                        default_value=False
                    ),
                    FormField(
                        name="endpoint",
                        type=FieldType.URL,
                        label="OpenSearch Endpoint",
                        placeholder="https://opensearch-endpoint.amazonaws.com",
                        help_text="The HTTPS endpoint of your OpenSearch cluster",
                        required=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="index_name",
                        type=FieldType.TEXT,
                        label="Index Name",
                        placeholder="memory-index",
                        help_text="The name of the OpenSearch index for memory storage",
                        required=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    )
                ]
            ),
            
            "elasticsearch": ProviderFormSchema(
                provider_name="elasticsearch",
                provider_label="Elasticsearch",
                description="Elasticsearch memory storage with semantic search capabilities using strands-tools elasticsearch_memory",
                fields=[
                    FormField(
                        name="enabled",
                        type=FieldType.CHECKBOX,
                        label="Enable Memory Integration",
                        help_text="Enable Elasticsearch memory integration for conversation context and semantic search",
                        required=False,
                        default_value=False
                    ),
                    FormField(
                        name="elasticsearch_url",
                        type=FieldType.URL,
                        label="Elasticsearch URL",
                        placeholder="http://localhost:9200",
                        help_text="The URL of your Elasticsearch cluster",
                        required=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="index_name",
                        type=FieldType.TEXT,
                        label="Index Name",
                        placeholder="agent_memory",
                        help_text="The name of the Elasticsearch index for memory storage",
                        required=True,
                        default_value="agent_memory",
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="username",
                        type=FieldType.TEXT,
                        label="Username (Optional)",
                        placeholder="elastic",
                        help_text="Elasticsearch username for authentication (optional)",
                        required=False,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="password",
                        type=FieldType.PASSWORD,
                        label="Password (Optional)",
                        placeholder="Enter password",
                        help_text="Elasticsearch password for authentication (optional)",
                        required=False,
                        secure=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    )
                ]
            )
        }
    
    @staticmethod
    def get_observability_schemas() -> Dict[str, ProviderFormSchema]:
        """Get form schemas for observability providers."""
        return {
            "langfuse": ProviderFormSchema(
                provider_name="langfuse",
                provider_label="Langfuse",
                description="Open-source LLM observability and analytics platform",
                fields=[
                    FormField(
                        name="public_key",
                        type=FieldType.TEXT,
                        label="Langfuse Public Key",
                        placeholder="Enter Langfuse public key",
                        help_text="Your Langfuse project public key",
                        required=True
                    ),
                    FormField(
                        name="secret_key",
                        type=FieldType.PASSWORD,
                        label="Langfuse Secret Key",
                        placeholder="Enter Langfuse secret key",
                        help_text="Your Langfuse project secret key",
                        required=True,
                        secure=True
                    ),
                    FormField(
                        name="host",
                        type=FieldType.URL,
                        label="Langfuse Host (Optional)",
                        placeholder="https://cloud.langfuse.com",
                        help_text="Langfuse host URL (defaults to cloud.langfuse.com)",
                        required=False,
                        default_value="https://cloud.langfuse.com"
                    )
                ]
            ),
            
            "dynatrace": ProviderFormSchema(
                provider_name="dynatrace",
                provider_label="Dynatrace",
                description="Full-stack observability platform",
                fields=[
                    FormField(
                        name="environment_url",
                        type=FieldType.URL,
                        label="Dynatrace Environment URL",
                        placeholder="https://your-environment.live.dynatrace.com",
                        help_text="Your Dynatrace environment URL",
                        required=True
                    ),
                    FormField(
                        name="api_token",
                        type=FieldType.PASSWORD,
                        label="Dynatrace API Token",
                        placeholder="Enter Dynatrace API token",
                        help_text="API token with appropriate permissions",
                        required=True,
                        secure=True
                    )
                ]
            ),
            
            "elastic": ProviderFormSchema(
                provider_name="elastic",
                provider_label="Elastic Observability",
                description="Elastic Cloud Managed OTLP Endpoint for OpenTelemetry-based observability",
                fields=[
                    FormField(
                        name="otlp_endpoint",
                        type=FieldType.URL,
                        label="Elastic OTLP Endpoint",
                        placeholder="https://your-cluster.elastic-cloud.com:443",
                        help_text="Your Elastic Cloud Managed OTLP endpoint URL (found in Elastic Cloud console)",
                        required=True
                    ),
                    FormField(
                        name="api_key",
                        type=FieldType.PASSWORD,
                        label="Elastic API Key",
                        placeholder="Enter Elastic API key",
                        help_text="API key for authentication with Elastic Cloud",
                        required=True,
                        secure=True
                    ),
                    FormField(
                        name="dataset",
                        type=FieldType.TEXT,
                        label="Data Stream Dataset (Optional)",
                        placeholder="generic.otel",
                        help_text="Dataset name for routing logs to dedicated data streams (default: generic.otel)",
                        required=False,
                        default_value="generic.otel"
                    ),
                    FormField(
                        name="namespace",
                        type=FieldType.TEXT,
                        label="Data Stream Namespace (Optional)",
                        placeholder="default",
                        help_text="Namespace for data stream organization (default: default)",
                        required=False,
                        default_value="default"
                    )
                ]
            ),
            
            "datadog": ProviderFormSchema(
                provider_name="datadog",
                provider_label="Datadog",
                description="Complete Datadog observability platform using official ddtrace library - supports traces, logs, metrics, and specialized LLM observability for AI applications",
                fields=[
                    FormField(
                        name="api_key",
                        type=FieldType.PASSWORD,
                        label="Datadog API Key",
                        placeholder="Enter Datadog API key",
                        help_text="Your Datadog API key for authentication",
                        required=True,
                        secure=True
                    ),
                    FormField(
                        name="site",
                        type=FieldType.SELECT,
                        label="Datadog Site",
                        help_text="Datadog site/region for your organization",
                        required=False,
                        default_value="datadoghq.com",
                        options=[
                            SelectOption(value="datadoghq.com", label="US1 (datadoghq.com)"),
                            SelectOption(value="us3.datadoghq.com", label="US3 (us3.datadoghq.com)"),
                            SelectOption(value="us5.datadoghq.com", label="US5 (us5.datadoghq.com)"),
                            SelectOption(value="datadoghq.eu", label="EU (datadoghq.eu)"),
                            SelectOption(value="ap1.datadoghq.com", label="AP1 (ap1.datadoghq.com)"),
                            SelectOption(value="ap2.datadoghq.com", label="AP2 (ap2.datadoghq.com)"),
                            SelectOption(value="us1-fed.datadoghq.com", label="US1-FED (us1-fed.datadoghq.com)")
                        ]
                    ),
                    FormField(
                        name="environment",
                        type=FieldType.TEXT,
                        label="Environment (Optional)",
                        placeholder="production",
                        help_text="Environment tag for organizing your services (e.g., production, staging, development)",
                        required=False,
                        default_value="production"
                    ),
                    FormField(
                        name="service_name",
                        type=FieldType.TEXT,
                        label="Service Name (Optional)",
                        placeholder="Leave empty to use agent name",
                        help_text="Custom service name for Datadog (defaults to agent name if not specified)",
                        required=False,
                        default_value=""
                    ),
                    FormField(
                        name="version",
                        type=FieldType.TEXT,
                        label="Service Version (Optional)",
                        placeholder="1.0.0",
                        help_text="Version tag for tracking deployments and releases",
                        required=False,
                        default_value="1.0.0"
                    ),
                    FormField(
                        name="enable_llm_obs",
                        type=FieldType.CHECKBOX,
                        label="Enable LLM Observability",
                        help_text="Enable specialized AI/ML observability for LLM interactions, prompt tracking, and cost analysis",
                        required=False,
                        default_value=True
                    ),
                    FormField(
                        name="enable_logs",
                        type=FieldType.CHECKBOX,
                        label="Enable Log Collection",
                        help_text="Enable direct log submission to Datadog with automatic trace correlation",
                        required=False,
                        default_value=True
                    ),
                    FormField(
                        name="tags",
                        type=FieldType.TEXTAREA,
                        label="Additional Tags (Optional)",
                        placeholder="service:genai-agent\nteam:ai-platform\nversion:1.0.0",
                        help_text="Additional tags for organizing metrics and logs (one tag per line, format: key:value)",
                        required=False,
                        rows=3
                    )
                ]
            )
        }
    
    @staticmethod
    def get_guardrail_schemas() -> Dict[str, ProviderFormSchema]:
        """Get form schemas for guardrail providers."""
        return {
            "bedrock": ProviderFormSchema(
                provider_name="bedrock",
                provider_label="Amazon Bedrock Guardrails",
                description="Amazon Bedrock native content filtering and safety guardrails",
                fields=[
                    FormField(
                        name="enabled",
                        type=FieldType.CHECKBOX,
                        label="Enable Guardrails",
                        help_text="Enable Amazon Bedrock Guardrails for content filtering and safety",
                        required=False,
                        default_value=False
                    ),
                    FormField(
                        name="guardrail_id",
                        type=FieldType.TEXT,
                        label="Guardrail ID",
                        placeholder="Enter Bedrock Guardrail ID",
                        help_text="The unique identifier for your Bedrock Guardrail",
                        required=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="guardrail_version",
                        type=FieldType.TEXT,
                        label="Guardrail Version (Optional)",
                        placeholder="Enter version (e.g., 1, DRAFT)",
                        help_text="Specific version of the guardrail to use",
                        required=False,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    )
                ]
            ),
            
            "custom": ProviderFormSchema(
                provider_name="custom",
                provider_label="Custom Implementation",
                description="Custom guardrail implementation with configurable rules",
                fields=[
                    FormField(
                        name="enabled",
                        type=FieldType.CHECKBOX,
                        label="Enable Guardrails",
                        help_text="Enable custom guardrail implementation",
                        required=False,
                        default_value=False
                    ),
                    FormField(
                        name="custom_config",
                        type=FieldType.TEXTAREA,
                        label="Custom Guardrail Configuration",
                        placeholder="Enter custom guardrail configuration as JSON",
                        help_text="JSON configuration for your custom guardrail implementation",
                        required=True,
                        rows=4,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    )
                ]
            )
        }
    
    @staticmethod
    def get_agent_schemas() -> Dict[str, ProviderFormSchema]:
        """Get form schemas for agent configuration."""
        return {
            "basic": ProviderFormSchema(
                provider_name="basic",
                provider_label="Basic Agent Configuration",
                description="Core agent settings and metadata",
                fields=[
                    FormField(
                        name="agent_name",
                        type=FieldType.TEXT,
                        label="Agent Name",
                        placeholder="Enter agent name",
                        help_text="Unique identifier for this agent (read-only during configuration)",
                        required=True,
                        disabled=True
                    ),
                    FormField(
                        name="agent_description",
                        type=FieldType.TEXTAREA,
                        label="Agent Description",
                        placeholder="Describe what this agent does",
                        help_text="Brief description of the agent's purpose and capabilities",
                        required=False,
                        rows=3
                    ),
                    FormField(
                        name="system_prompt_name",
                        type=FieldType.SELECT,
                        label="System Prompt Template",
                        help_text="Choose from available system prompt templates or global templates",
                        required=False,
                        options=[
                            SelectOption(value="", label="Select a prompt template...")
                        ]
                    ),
                    FormField(
                        name="system_prompt",
                        type=FieldType.TEXTAREA,
                        label="System Prompt",
                        placeholder="Enter the system prompt for this agent",
                        help_text="Instructions that define the agent's behavior and personality",
                        required=False,
                        rows=8
                    ),
                    FormField(
                        name="region_name",
                        type=FieldType.SELECT,
                        label="AWS Region",
                        help_text="AWS region for model and service calls",
                        required=True,
                        default_value="us-east-1",
                        options=[
                            SelectOption(value="us-east-1", label="US East (N. Virginia)"),
                            SelectOption(value="us-west-2", label="US West (Oregon)"),
                            SelectOption(value="eu-west-1", label="Europe (Ireland)"),
                            SelectOption(value="ap-southeast-1", label="Asia Pacific (Singapore)")
                        ]
                    ),
                    FormField(
                        name="streaming",
                        type=FieldType.CHECKBOX,
                        label="Enable Streaming",
                        help_text="Enable real-time response streaming for better user experience",
                        required=False,
                        default_value=True
                    ),
                    FormField(
                        name="cache_prompt",
                        type=FieldType.SELECT,
                        label="Prompt Caching",
                        help_text="Enable prompt caching to improve performance and reduce costs",
                        required=False,
                        default_value="default",
                        options=[
                            SelectOption(value="default", label="Default"),
                            SelectOption(value="enabled", label="Enabled"),
                            SelectOption(value="disabled", label="Disabled")
                        ]
                    ),
                    FormField(
                        name="cache_tools",
                        type=FieldType.SELECT,
                        label="Tool Caching",
                        help_text="Enable tool response caching to improve performance",
                        required=False,
                        default_value="default",
                        options=[
                            SelectOption(value="default", label="Default"),
                            SelectOption(value="enabled", label="Enabled"),
                            SelectOption(value="disabled", label="Disabled")
                        ]
                    )
                ]
            ),
            
            "thinking": ProviderFormSchema(
                provider_name="thinking",
                provider_label="Thinking Configuration",
                description="Configure the agent's thinking and reasoning capabilities",
                fields=[
                    FormField(
                        name="thinking_type",
                        type=FieldType.SELECT,
                        label="Thinking Mode",
                        help_text="Enable or disable the agent's internal reasoning process",
                        required=False,
                        default_value="enabled",
                        options=[
                            SelectOption(value="enabled", label="Enabled"),
                            SelectOption(value="disabled", label="Disabled")
                        ]
                    ),
                    FormField(
                        name="thinking_budget_tokens",
                        type=FieldType.NUMBER,
                        label="Thinking Budget (Tokens)",
                        placeholder="4096",
                        help_text="Maximum number of tokens allocated for internal reasoning",
                        required=False,
                        default_value=4096,
                        min_value=512,
                        max_value=8192
                    )
                ]
            )
        }
    
    @staticmethod
    def get_model_schemas() -> Dict[str, ProviderFormSchema]:
        """Get form schemas for model configuration with dynamic model options from AWS Bedrock API."""
        # Get dynamic model options from BedrockModelService
        bedrock_service = BedrockModelService()
        
        # Generate dynamic options for different model categories
        main_model_options = bedrock_service.generate_form_schema_options("text_generation")
        judge_model_options = [SelectOption(value="", label="Use Main Model")] + bedrock_service.generate_form_schema_options("text_generation")
        embedding_model_options = [SelectOption(value="", label="No Embedding Model")] + bedrock_service.generate_form_schema_options("text_embedding")
        
        # Get default values from BedrockModelService
        default_recommendations = bedrock_service.get_recommended_models_for_agent_type("default")
        
        return {
            "bedrock": ProviderFormSchema(
                provider_name="bedrock",
                provider_label="Amazon Bedrock Models",
                description="Configure Amazon Bedrock models for AI generation",
                fields=[
                    FormField(
                        name="model_id",
                        type=FieldType.SELECT,
                        label="Main Model",
                        help_text="Primary model for agent responses (dynamically loaded from AWS Bedrock API)",
                        required=True,
                        default_value=default_recommendations.get("model_id", "us.anthropic.claude-3-5-sonnet-20241022-v2:0"),
                        options=main_model_options
                    ),
                    FormField(
                        name="judge_model_id",
                        type=FieldType.SELECT,
                        label="Judge Model (Optional)",
                        help_text="Model used for evaluation and judging - leave empty to use main model (dynamically loaded from AWS Bedrock API)",
                        required=False,
                        default_value="",
                        options=judge_model_options
                    ),
                    FormField(
                        name="embedding_model_id",
                        type=FieldType.SELECT,
                        label="Embedding Model (Optional)",
                        help_text="Model for text embeddings and similarity search - leave empty to disable embeddings (dynamically loaded from AWS Bedrock API)",
                        required=False,
                        default_value="",
                        options=embedding_model_options
                    ),
                    FormField(
                        name="temperature",
                        type=FieldType.RANGE,
                        label="Temperature",
                        help_text="Controls randomness (0 = deterministic, 2 = very random)",
                        required=True,
                        default_value=0.3,
                        min_value=0.0,
                        max_value=2.0,
                        step=0.1
                    ),
                    FormField(
                        name="top_p",
                        type=FieldType.RANGE,
                        label="Top P",
                        help_text="Nucleus sampling threshold (0.1 = conservative, 1.0 = diverse)",
                        required=True,
                        default_value=0.8,
                        min_value=0.1,
                        max_value=1.0,
                        step=0.1
                    ),
                    FormField(
                        name="model_ids",
                        type=FieldType.SELECT,
                        label="Multiple Models for Switching",
                        help_text="Select multiple models for automatic switching when throttling occurs (dynamically loaded from AWS Bedrock API)",
                        required=False,
                        default_value=bedrock_service.default_models.get("fallback_models", []),
                        max_selections=5,
                        options=main_model_options  # Use same options as main model for multi-select
                    )
                ]
            )
        }
    
    @staticmethod
    def get_tools_schemas() -> Dict[str, ProviderFormSchema]:
        """Get form schemas for tools configuration."""
        return {
            "builtin": ProviderFormSchema(
                provider_name="builtin",
                provider_label="Built-in Tools",
                description="Built-in tools available in the agent platform for common operations",
                fields=[
                    FormField(
                        name="enabled_tools",
                        type=FieldType.TEXTAREA,
                        label="Enabled Built-in Tools Configuration",
                        placeholder='''[
  {
    "name": "http_request",
    "enabled": true,
    "config": {
      "timeout": 30,
      "max_retries": 3,
      "follow_redirects": true
    }
  },
  {
    "name": "use_aws",
    "enabled": true,
    "config": {
      "default_region": "us-east-1",
      "enable_dynamodb": true,
      "enable_s3": true,
      "enable_lambda": true
    }
  },
  {
    "name": "load_tool",
    "enabled": false,
    "config": {
      "allowed_modules": ["strands_tools"],
      "cache_loaded_tools": true
    }
  },
  {
    "name": "mcp_client",
    "enabled": false,
    "config": {
      "connection_timeout": 10,
      "request_timeout": 30
    }
  },
  {
    "name": "retrieve",
    "enabled": false,
    "config": {
      "auto_configure_from_kb": true,
      "max_results": 10,
      "score_threshold": 0.7
    }
  }
]''',
                        help_text="JSON array of built-in tool configurations. Each tool can be individually enabled/disabled and configured.",
                        required=False,
                        rows=25
                    )
                ]
            ),
            
            "mcp": ProviderFormSchema(
                provider_name="mcp",
                provider_label="MCP Remote Tools",
                description="Configure remote MCP (Model Context Protocol) server tools for external capabilities",
                fields=[
                    FormField(
                        name="enabled",
                        type=FieldType.CHECKBOX,
                        label="Enable MCP Tools",
                        help_text="Enable integration with remote MCP servers as tools",
                        required=False,
                        default_value=False
                    ),
                    FormField(
                        name="servers",
                        type=FieldType.TEXTAREA,
                        label="MCP Server Configurations",
                        placeholder='''[
  {
    "name": "aws-docs-server",
    "url": "https://api.aws-docs.example.com",
    "description": "AWS Documentation and search capabilities",
    "transport": "http",
    "auth": {
      "type": "bearer",  
      "token": "your-api-key"
    },
    "tools": ["search_documentation", "read_documentation"],
    "timeout": 30,
    "retry_attempts": 3,
    "enabled": true
  },
  {
    "name": "cdk-server",
    "url": "https://cdk-tools.example.com",
    "description": "AWS CDK guidance and tools",
    "transport": "http", 
    "auth": {
      "type": "none"
    },
    "tools": ["explain_cdk_nag_rule", "get_construct_pattern"],
    "timeout": 45,
    "retry_attempts": 2,
    "enabled": true
  }
]''',
                        help_text="JSON array of MCP server tool configurations. Each server should specify available tools that can be called by the agent",
                        required=False,
                        rows=20,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="discovery_timeout",
                        type=FieldType.NUMBER,
                        label="Discovery Timeout (seconds)",
                        placeholder="15",
                        help_text="Timeout for discovering available tools from MCP servers",
                        required=False,
                        default_value=15,
                        min_value=5,
                        max_value=60,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="request_timeout",
                        type=FieldType.NUMBER,
                        label="Default Request Timeout (seconds)",
                        placeholder="30",
                        help_text="Default timeout for tool execution requests to MCP servers",
                        required=False,
                        default_value=30,
                        min_value=10,
                        max_value=300,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="max_concurrent_requests",
                        type=FieldType.NUMBER,
                        label="Max Concurrent Requests",
                        placeholder="5",
                        help_text="Maximum number of concurrent requests to MCP servers",
                        required=False,
                        default_value=5,
                        min_value=1,
                        max_value=20,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="cache_tool_results",
                        type=FieldType.CHECKBOX,
                        label="Cache Tool Results",
                        help_text="Enable caching of MCP tool results to improve performance",
                        required=False,
                        default_value=True,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    ),
                    FormField(
                        name="cache_ttl",
                        type=FieldType.NUMBER,
                        label="Cache TTL (minutes)",
                        placeholder="10",
                        help_text="Time-to-live for cached MCP tool results in minutes",
                        required=False,
                        default_value=10,
                        min_value=1,
                        max_value=120,
                        conditional={
                            "field": "cache_tool_results",
                            "value": True
                        }
                    )
                ]
            ),
            
            "custom": ProviderFormSchema(
                provider_name="custom",
                provider_label="Custom Tools",
                description="Configure custom tool implementations and integrations",
                fields=[
                    FormField(
                        name="enabled",
                        type=FieldType.CHECKBOX,
                        label="Enable Custom Tools",
                        help_text="Enable custom tool implementations",
                        required=False,
                        default_value=False
                    ),
                    FormField(
                        name="tool_modules",
                        type=FieldType.TEXTAREA,
                        label="Tool Module Configurations",
                        placeholder='''[
  {
    "name": "database_tools",
    "module_path": "common.tools.custom.database",
    "description": "Database query and manipulation tools",
    "tools": ["query_database", "update_record", "create_table"],
    "config": {
      "connection_string": "postgresql://user:pass@host:port/db"
    },
    "enabled": true
  },
  {
    "name": "file_tools", 
    "module_path": "common.tools.custom.file_operations",
    "description": "File system operations",
    "tools": ["read_file", "write_file", "list_directory"],
    "config": {
      "base_path": "/allowed/path",
      "max_file_size": "10MB"
    },
    "enabled": true
  }
]''',
                        help_text="JSON array of custom tool module configurations",
                        required=False,
                        rows=15,
                        conditional={
                            "field": "enabled",
                            "value": True
                        }
                    )
                ]
            )
        }
    
    @staticmethod
    def get_component_schema(component_type: str) -> Optional[ComponentFormSchema]:
        """Get complete form schema for a component type."""
        schema_map = {
            "agent": FormSchemaRegistry.get_agent_schemas(),
            "models": FormSchemaRegistry.get_model_schemas(),
            "knowledge_base": FormSchemaRegistry.get_knowledge_base_schemas(),
            "memory": FormSchemaRegistry.get_memory_schemas(),
            "observability": FormSchemaRegistry.get_observability_schemas(),
            "guardrail": FormSchemaRegistry.get_guardrail_schemas(),
            "tools": FormSchemaRegistry.get_tools_schemas()
        }
        
        providers = schema_map.get(component_type)
        if not providers:
            return None
            
        return ComponentFormSchema(
            component_type=component_type,
            providers=providers
        )
    
    @staticmethod
    def get_provider_schema(component_type: str, provider_name: str) -> Optional[ProviderFormSchema]:
        """Get form schema for a specific provider."""
        component_schema = FormSchemaRegistry.get_component_schema(component_type)
        if not component_schema:
            return None
            
        return component_schema.providers.get(provider_name)
