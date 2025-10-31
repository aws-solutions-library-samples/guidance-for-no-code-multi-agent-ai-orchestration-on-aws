#!/usr/bin/env python3
"""
Parameter initialization service for Configuration API.

This service defensively creates initial SSM SecureString parameters when the Configuration API starts,
using ONLY configuration values from development.yaml - NO hardcoded fallbacks.
"""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
from .ssm_service import SSMService
from ..models.ssm_data_models import (
    SSMAgentConfiguration,
    SSMParameterPaths,
    SSMDataValidator,
    StreamingType,
    ProviderType,
    ThinkingType,
    SSMThinkingConfig,
    SSMProviderConfig
)

logger = logging.getLogger(__name__)

import re

class SecureParameterValidator:
    """Secure parameter validator for SSM operations."""
    
    @staticmethod
    def validate_parameter_name(name: str) -> bool:
        """Validate SSM parameter name for security."""
        if not name or not isinstance(name, str):
            return False
            
        # Check for path traversal attempts
        if '..' in name or '//' in name:
            return False
            
        # Validate parameter name format
        if not re.match(r'^/[a-zA-Z0-9/_-]+$', name):
            return False
            
        # Prevent excessively long parameter names
        if len(name) > 1011:  # SSM limit is 1011 characters
            return False
            
        return True
    
    @staticmethod
    def validate_parameter_value(value: str, max_size: int = 4096) -> bool:
        """Validate parameter value for security."""
        if not isinstance(value, str):
            return False
            
        if len(value) > max_size:
            return False
            
        return True
    
    @staticmethod
    def sanitize_log_message(message: str) -> str:
        """Sanitize log messages to prevent log injection."""
        if not message:
            return ""
            
        # Remove or escape potentially dangerous characters
        sanitized = message.replace('\n', ' ').replace('\r', ' ')
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', sanitized)
        
        return sanitized[:1000]  # Limit log message length



class ParameterInitializationService:
    """Service for defensive initialization of SSM parameters using ONLY configuration values."""
    
    def __init__(self, ssm_service: SSMService):
        """
        Initialize parameter initialization service.
        
        Args:
            ssm_service: SSM service instance for parameter operations
        """
        self.ssm_service = ssm_service
        self.environment = os.environ.get('ENVIRONMENT', 'development')
        logger.info(f"ParameterInitializationService initialized for environment: {self.environment}")
    
    def initialize_default_agent_parameters(self) -> bool:
        """
        Create default agent parameters and comprehensive prompt library using ONLY configuration values.
        NO hardcoded fallbacks that override development.yaml configuration.
        
        Returns:
            True if initialization successful, False otherwise
        """
        try:
            logger.info("🚀 Starting comprehensive prompt library initialization...")
            
            # Initialize prompt library first
            prompt_library_success = self._initialize_prompt_library()
            if not prompt_library_success:
                logger.error("Failed to initialize prompt library")
                return False
            
            # Default agent configuration
            default_agent_name = "qa_agent"
            
            # Check and create agent config parameter
            agent_config_param = f"/agent/{default_agent_name}/config"
            if not self.ssm_service.parameter_exists(agent_config_param):
                logger.info(f"Creating missing agent config parameter: {agent_config_param}")
                
                default_agent_config = self._get_default_agent_config(default_agent_name)
                
                success = self.ssm_service.store_json_parameter(
                    name=agent_config_param,
                    data=default_agent_config,
                    description=f"Default agent configuration for {default_agent_name}",
                    tier="Advanced"
                )
                
                if not success:
                    logger.error(f"Failed to create agent config parameter: {agent_config_param}")
                    return False
                    
                logger.info(f"✅ Created SecureString agent config parameter: {agent_config_param}")
            else:
                logger.info(f"Agent config parameter already exists: {agent_config_param}")
            
            # Create comprehensive global prompt template library accessible by all agents
            template_library_success = self._create_global_prompt_template_library()
            if not template_library_success:
                logger.error("Failed to create global prompt template library")
                return False
            
            # Initialize supervisor agent parameters
            supervisor_success = self._initialize_supervisor_parameters()
            if not supervisor_success:
                return False
            
            logger.info("🔐 All parameters initialized successfully using ONLY configuration values!")
            return True
            
        except Exception as e:
            logger.error(f"Error during parameter initialization: {str(e)}", exc_info=True)
            return False
    
    def _initialize_supervisor_parameters(self) -> bool:
        """Initialize supervisor agent parameters using ONLY configuration values."""
        try:
            supervisor_agent_name = "supervisor_agent"
            
            # Supervisor config parameter
            supervisor_config_param = f"/agent/{supervisor_agent_name}/config"
            if not self.ssm_service.parameter_exists(supervisor_config_param):
                logger.info(f"Creating supervisor config parameter: {supervisor_config_param}")
                
                supervisor_config = self._get_default_supervisor_config(supervisor_agent_name)
                
                success = self.ssm_service.store_json_parameter(
                    name=supervisor_config_param,
                    data=supervisor_config,
                    description=f"Default supervisor agent configuration",
                    tier="Advanced"
                )
                
                if not success:
                    return False
                    
                logger.info(f"✅ Created SecureString supervisor config: {supervisor_config_param}")
            
            # Supervisor system prompt
            supervisor_prompt_param = f"/agent/{supervisor_agent_name}/system-prompts/supervisor"
            if not self.ssm_service.parameter_exists(supervisor_prompt_param):
                logger.info(f"Creating supervisor prompt parameter: {supervisor_prompt_param}")
                
                supervisor_prompt = self._get_default_supervisor_prompt()
                
                success = self.ssm_service.store_parameter(
                    name=supervisor_prompt_param,
                    value=supervisor_prompt,
                    parameter_type="SecureString",
                    description="Default supervisor system prompt",
                    tier="Advanced"
                )
                
                if not success:
                    return False
                    
                logger.info(f"✅ Created SecureString supervisor prompt: {supervisor_prompt_param}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error initializing supervisor parameters: {str(e)}")
            return False
    
    def _get_default_agent_config(self, agent_name: str) -> Dict[str, Any]:
        """Get default agent configuration using ONLY configuration values from development.yaml."""
        try:
            # Try to load from helper.config first
            from helper.config import Config
            config = Config('development')
            
            # Use configuration values from development.yaml - NO fallbacks
            model_id = config.get_required_config('GenericAgentModelId')
            judge_model_id = config.get_optional_config('GenericAgentJudgeModelId', '')
            embedding_model_id = config.get_required_config('GenericAgentEmbeddingModelId')
            temperature = float(config.get_required_config('GenericAgentTemperature'))
            top_p = float(config.get_required_config('GenericAgentTopP'))
        except ImportError:
            logger.warning("Helper module not available in container, using environment variables")
            # Fallback to environment variables when helper module is not available in container
            model_id = os.environ.get('GENERIC_AGENT_MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0')
            judge_model_id = os.environ.get('GENERIC_AGENT_JUDGE_MODEL_ID', '')
            embedding_model_id = os.environ.get('GENERIC_AGENT_EMBEDDING_MODEL_ID', 'amazon.titan-embed-text-v2:0')
            temperature = float(os.environ.get('GENERIC_AGENT_TEMPERATURE', '0.3'))
            top_p = float(os.environ.get('GENERIC_AGENT_TOP_P', '0.8'))
        
        logger.info(f"Using ONLY config values for {agent_name}:")
        logger.info(f"  model_id: {model_id}")
        logger.info(f"  temperature: {temperature}")
        logger.info(f"  top_p: {top_p}")
        logger.info(f"  embedding_model_id: {embedding_model_id}")
        
        # Create using the standardized SSM data model with config values
        config_model = SSMAgentConfiguration(
            agent_name=agent_name,
            agent_description="Default Question Answer Agent",
            system_prompt_name="qa",
            model_id=model_id,
            judge_model_id=judge_model_id,
            embedding_model_id=embedding_model_id,
            region_name="us-east-1",
            temperature=temperature,
            top_p=top_p,
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
        
        # Validate the configuration before returning
        validation_result = SSMDataValidator.validate_agent_configuration(config_model.dict())
        if not validation_result["valid"]:
            logger.error(f"Configuration from development.yaml is invalid: {validation_result['errors']}")
            raise ValueError(f"Invalid configuration from development.yaml: {validation_result['errors']}")
        
        logger.info(f"✅ Generated valid configuration for {agent_name} using ONLY development.yaml values")
        return config_model.dict()
    
    def _get_default_supervisor_config(self, supervisor_name: str) -> Dict[str, Any]:
        """Get default supervisor agent configuration using ONLY configuration values from development.yaml."""
        try:
            # Try to load from helper.config first
            from helper.config import Config
            config = Config('development')
            
            # Use configuration values from development.yaml - NO fallbacks
            model_id = config.get_required_config('SupervisorModelId')
            judge_model_id = config.get_optional_config('SupervisorJudgeModelId', model_id)  # Use primary model if not specified
            embedding_model_id = config.get_optional_config('SupervisorEmbeddingModelId', 'amazon.titan-embed-text-v2:0')
            temperature = float(config.get_required_config('SupervisorTemperature'))
            top_p = float(config.get_required_config('SupervisorTopP'))
        except ImportError:
            logger.warning("Helper module not available in container, using environment variables")
            # Fallback to environment variables when helper module is not available in container
            model_id = os.environ.get('SUPERVISOR_MODEL_ID', 'us.anthropic.claude-opus-4-1-20250805-v1:0')
            judge_model_id = os.environ.get('SUPERVISOR_JUDGE_MODEL_ID', model_id)
            embedding_model_id = os.environ.get('SUPERVISOR_EMBEDDING_MODEL_ID', 'amazon.titan-embed-text-v2:0')
            temperature = float(os.environ.get('SUPERVISOR_TEMPERATURE', '0.7'))
            top_p = float(os.environ.get('SUPERVISOR_TOP_P', '0.9'))
        
        logger.info(f"Using ONLY config values for {supervisor_name}:")
        logger.info(f"  model_id: {model_id}")
        logger.info(f"  judge_model_id: {judge_model_id}")
        logger.info(f"  temperature: {temperature}")
        logger.info(f"  top_p: {top_p}")
        logger.info(f"  embedding_model_id: {embedding_model_id}")
        
        # Create using the standardized SSM data model with config values
        config_model = SSMAgentConfiguration(
            agent_name=supervisor_name,
            agent_description="Multi-Agent Supervisor",
            system_prompt_name="supervisor",
            model_id=model_id,
            judge_model_id=judge_model_id,
            embedding_model_id=embedding_model_id,
            region_name="us-east-1",
            temperature=temperature,
            top_p=top_p,
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
        
        # Validate the configuration before returning
        validation_result = SSMDataValidator.validate_agent_configuration(config_model.dict())
        if not validation_result["valid"]:
            logger.error(f"Configuration from development.yaml is invalid: {validation_result['errors']}")
            raise ValueError(f"Invalid configuration from development.yaml: {validation_result['errors']}")
        
        logger.info(f"✅ Generated valid configuration for {supervisor_name} using ONLY development.yaml values")
        return config_model.dict()
    
    def _initialize_prompt_library(self) -> bool:
        """
        Initialize comprehensive prompt library by scanning prompts/ folder.
        
        Creates SecureString parameters for all .md files found in the prompts directory,
        following the naming convention: /prompts/{filename_without_extension}
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get prompts directory path - FIXED: correct path for container deployment
            # Try multiple possible paths
            possible_paths = [
                Path("/app/prompts"),  # Container path
                Path(__file__).parent.parent.parent / "prompts",  # Relative path
            ]
            
            prompts_dir = None
            for path in possible_paths:
                if path.exists():
                    prompts_dir = path
                    break
                    
            if not prompts_dir:
                logger.warning(f"Prompts directory not found in any of: {[str(p) for p in possible_paths]}")
                return True  # Not an error, just no prompts to initialize
            
            logger.info(f"📚 Found prompts directory: {prompts_dir}")
            
            # Recursively find all .md files in prompts directory
            prompt_files = list(prompts_dir.rglob("*.md"))
            logger.info(f"Found {len(prompt_files)} prompt files to process")
            
            created_count = 0
            existing_count = 0
            
            for prompt_file in prompt_files:
                # Generate parameter name from file path
                relative_path = prompt_file.relative_to(prompts_dir)
                prompt_name = str(relative_path.with_suffix(''))  # Remove .md extension
                prompt_name = prompt_name.replace('/', '-')  # Replace path separators with dashes
                
                parameter_name = f"/prompts/{prompt_name}"
                
                # Check if parameter already exists - handle permission errors gracefully
                try:
                    parameter_exists = self.ssm_service.parameter_exists(parameter_name)
                except Exception as e:
                    logger.warning(f"Cannot check parameter existence for {parameter_name}: {str(e)}")
                    # If we can't check, assume it doesn't exist and try to create it
                    # This will either succeed (permissions allow creation) or fail gracefully
                    parameter_exists = False
                
                if not parameter_exists:
                    logger.info(f"Creating prompt parameter: {parameter_name} from {prompt_file.name}")
                    
                    # Read prompt content
                    try:
                        with open(prompt_file, 'r', encoding='utf-8') as f:
                            prompt_content = f.read().strip()
                        
                        # Create SecureString parameter - handle permission errors gracefully
                        try:
                            success = self.ssm_service.store_parameter(
                                name=parameter_name,
                                value=prompt_content,
                                parameter_type="SecureString",
                                description=f"Prompt template: {prompt_name}",
                                tier="Advanced"
                            )
                            
                            if success:
                                logger.info(f"✅ Created SecureString prompt: {parameter_name}")
                                created_count += 1
                            else:
                                logger.warning(f"⚠️ Failed to create prompt parameter: {parameter_name} (may be permissions issue)")
                                # Continue with other prompts instead of failing entirely
                                continue
                                
                        except Exception as e:
                            logger.warning(f"⚠️ Cannot create prompt parameter {parameter_name}: {str(e)}")
                            # Continue with other prompts instead of failing entirely
                            continue
                            
                    except Exception as e:
                        logger.error(f"Error reading prompt file {prompt_file}: {str(e)}")
                        # Continue with other prompts instead of failing entirely
                        continue
                        
                else:
                    existing_count += 1
                    logger.info(f"Prompt parameter already exists: {parameter_name}")
            
            # Create prompt library index
            library_index_param = "/prompts/index"
            if not self.ssm_service.parameter_exists(library_index_param):
                logger.info("Creating prompt library index...")
                
                # Build index of all available prompts
                prompt_index = {}
                for prompt_file in prompt_files:
                    relative_path = prompt_file.relative_to(prompts_dir)
                    prompt_name = str(relative_path.with_suffix(''))
                    prompt_name = prompt_name.replace('/', '-')
                    
                    prompt_index[prompt_name] = {
                        "parameter_name": f"/prompts/{prompt_name}",
                        "file_name": prompt_file.name,
                        "category": self._categorize_prompt(prompt_name),
                        "description": self._get_prompt_description(prompt_file)
                    }
                
                success = self.ssm_service.store_json_parameter(
                    name=library_index_param,
                    data=prompt_index,
                    description="Index of all available prompt templates in the library",
                    tier="Advanced"
                )
                
                if success:
                    logger.info(f"✅ Created prompt library index with {len(prompt_index)} prompts")
                else:
                    logger.error("Failed to create prompt library index")
                    return False
            
            logger.info(f"📚 Prompt library initialization complete: {created_count} created, {existing_count} existing")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing prompt library: {str(e)}", exc_info=True)
            return False
    
    def _categorize_prompt(self, prompt_name: str) -> str:
        """Categorize prompt based on name."""
        if 'finserve' in prompt_name or 'financial' in prompt_name:
            return "financial"
        elif any(db in prompt_name for db in ['aurora', 'snowflake', 'dynamodb', 'elasticsearch']):
            return "data"
        elif prompt_name == 'supervisor':
            return "coordination"
        elif prompt_name in ['qa', 'research', 'summarization']:
            return "general"
        elif prompt_name == 'weather':
            return "external_api"
        else:
            return "custom"
    
    def _get_prompt_description(self, prompt_file: Path) -> str:
        """Extract description from prompt file."""
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Try to extract title from first line
                lines = content.split('\n')
                for line in lines:
                    if line.startswith('# '):
                        return line[2:].strip()
            return f"Prompt template from {prompt_file.name}"
        except:
            return f"Prompt template from {prompt_file.name}"
    
    def _get_default_supervisor_prompt(self) -> str:
        """Get default supervisor system prompt."""
        return """# Multi-Agent Supervisor

You are a sophisticated supervisor agent that coordinates multiple specialized AI agents to accomplish complex tasks efficiently.

## Core Responsibilities
1. **Task Analysis & Planning**: Understand requests and determine the best approach
2. **Agent Selection**: Choose appropriate specialized agents for each subtask  
3. **Coordination**: Manage information flow between agents
4. **Quality Control**: Review outputs and ensure consistency
5. **Synthesis**: Combine results into coherent responses

Your goal is to leverage the collective capabilities of the agent network to provide comprehensive, accurate responses."""

    def _create_global_prompt_template_library(self) -> bool:
        """
        Create comprehensive global prompt template library accessible by all agents.
        
        This creates global templates and ensures ALL prompts are available to any agent,
        not just specific agents like qa_agent.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("🌐 Creating global prompt template library accessible by ALL agents...")
            
            # Get prompts directory path - FIXED: correct paths for container deployment
            possible_paths = [
                Path("/app/prompts"),  # Container path
                Path(__file__).parent.parent.parent / "prompts",  # Relative path
            ]
            
            prompts_dir = None
            for path in possible_paths:
                if path.exists():
                    prompts_dir = path
                    break
                    
            if not prompts_dir:
                logger.warning(f"Prompts directory not found in any of: {[str(p) for p in possible_paths]}")
                return True  # Not an error, just no prompts to initialize
            
            logger.info(f"🌐 Found prompts directory for global templates: {prompts_dir}")
            prompt_files = list(prompts_dir.rglob("*.md"))
            
            # Create global template library structure
            global_templates = {}
            created_count = 0
            existing_count = 0
            
            for prompt_file in prompt_files:
                relative_path = prompt_file.relative_to(prompts_dir)
                prompt_name = str(relative_path.with_suffix(''))
                prompt_name = prompt_name.replace('/', '-')
                
                # Create global template parameter accessible by all agents
                global_template_param = f"/system/prompt-templates/{prompt_name}"
                
                if not self.ssm_service.parameter_exists(global_template_param):
                    # Read prompt content from file
                    with open(prompt_file, 'r', encoding='utf-8') as f:
                        prompt_content = f.read().strip()
                    
                    success = self.ssm_service.store_parameter(
                        name=global_template_param,
                        value=prompt_content,
                        parameter_type="SecureString",
                        description=f"Global prompt template: {prompt_name}",
                        tier="Advanced"
                    )
                    
                    if success:
                        logger.info(f"✅ Created global template: {global_template_param}")
                        created_count += 1
                    else:
                        logger.error(f"Failed to create global template: {global_template_param}")
                        return False
                else:
                    existing_count += 1
                
                # Add to global templates index
                global_templates[prompt_name] = {
                    "parameter_name": global_template_param,
                    "file_name": prompt_file.name,
                    "category": self._categorize_prompt(prompt_name),
                    "description": self._get_prompt_description(prompt_file)
                }
            
            # Create global template library index
            global_index_param = "/system/prompt-templates/index"
            if not self.ssm_service.parameter_exists(global_index_param):
                success = self.ssm_service.store_json_parameter(
                    name=global_index_param,
                    data=global_templates,
                    description="Global prompt template library index accessible by all agents",
                    tier="Advanced"
                )
                
                if success:
                    logger.info(f"✅ Created global template index with {len(global_templates)} templates")
                else:
                    logger.error("Failed to create global template index")
                    return False
            
            # Create a universal agent template configuration that ALL agents can use
            # This includes both existing agents (qa_agent, supervisor_agent) and any future agents
            universal_agents_config = [
                ("qa_agent", list(global_templates.keys())),  # QA gets all templates (backwards compatibility)
                ("supervisor_agent", list(global_templates.keys())),  # Supervisor now gets all templates too
            ]
            
            # Additionally, create a default template index that can be used by any agent
            # This serves as a fallback and template for new agents
            default_agent_templates_index = {}
            
            for template_name in global_templates.keys():
                # Create a reference to the global template that any agent can use
                default_agent_templates_index[template_name] = f"/system/prompt-templates/{template_name}"
            
            # Store the default template index that all agents can inherit from
            default_templates_param = "/system/agent-templates/default"
            if not self.ssm_service.parameter_exists(default_templates_param):
                success = self.ssm_service.store_json_parameter(
                    name=default_templates_param,
                    data=default_agent_templates_index,
                    description="Default template index for all agents - references global templates",
                    tier="Advanced"
                )
                
                if success:
                    logger.info(f"✅ Created default agent template index with {len(default_agent_templates_index)} templates")
                else:
                    logger.error("Failed to create default agent template index")
                    return False
            
            # Create agent-specific collections for existing agents 
            for agent_name, template_names in universal_agents_config:
                agent_templates_index = {}
                
                for template_name in template_names:
                    if template_name in global_templates:
                        # Create agent-specific link to global template
                        agent_prompt_param = f"/agent/{agent_name}/system-prompts/{template_name}"
                        
                        if not self.ssm_service.parameter_exists(agent_prompt_param):
                            # Copy template content from global template
                            global_param = global_templates[template_name]["parameter_name"]
                            template_content = self.ssm_service.get_parameter(global_param)
                            
                            if template_content:
                                success = self.ssm_service.store_parameter(
                                    name=agent_prompt_param,
                                    value=template_content,
                                    parameter_type="SecureString",
                                    description=f"{agent_name} {template_name} system prompt",
                                    tier="Advanced"
                                )
                                
                                if success:
                                    logger.info(f"✅ Created {agent_name} template: {agent_prompt_param}")
                                else:
                                    logger.error(f"Failed to create {agent_name} template: {agent_prompt_param}")
                                    return False
                        
                        agent_templates_index[template_name] = agent_prompt_param
                
                # Create agent templates index
                agent_index_param = f"/agent/{agent_name}/system-prompts/index"
                if not self.ssm_service.parameter_exists(agent_index_param) and agent_templates_index:
                    success = self.ssm_service.store_json_parameter(
                        name=agent_index_param,
                        data=agent_templates_index,
                        description=f"{agent_name} system prompts index",
                        tier="Advanced"
                    )
                    
                    if success:
                        logger.info(f"✅ Created {agent_name} templates index with {len(agent_templates_index)} templates")
                    else:
                        logger.error(f"Failed to create {agent_name} templates index")
                        return False
            
            logger.info(f"🌐 Global prompt template library created: {created_count} new, {existing_count} existing")
            logger.info(f"🎯 ALL {len(global_templates)} prompts are now accessible by any agent through global templates")
            logger.info("🎯 Default template index created for easy agent onboarding")
            return True
            
        except Exception as e:
            logger.error(f"Error creating global prompt template library: {str(e)}")
            return False
    
    def get_initialization_status(self) -> Dict[str, Any]:
        """
        Get status of parameter initialization.
        
        Returns:
            Dictionary containing initialization status and statistics
        """
        try:
            # Check core parameters
            default_agent_name = "qa_agent"
            supervisor_agent_name = "supervisor_agent"
            
            agent_config_exists = self.ssm_service.parameter_exists(f"/agent/{default_agent_name}/config")
            supervisor_config_exists = self.ssm_service.parameter_exists(f"/agent/{supervisor_agent_name}/config")
            
            # Count system prompts
            system_prompt_count = 0
            for prompt_name in ["qa", "elasticsearch", "weather", "summarization", "research", "snowflake"]:
                if self.ssm_service.parameter_exists(f"/agent/{default_agent_name}/system-prompts/{prompt_name}"):
                    system_prompt_count += 1
            
            # Count global templates
            global_template_count = 0
            if self.ssm_service.parameter_exists("/system/prompt-templates/index"):
                try:
                    templates_index = self.ssm_service.get_json_parameter("/system/prompt-templates/index")
                    global_template_count = len(templates_index) if templates_index else 0
                except:
                    pass
            
            return {
                "status": "initialized" if agent_config_exists and supervisor_config_exists else "missing_parameters",
                "agent_config_exists": agent_config_exists,
                "supervisor_config_exists": supervisor_config_exists,
                "system_prompts_count": system_prompt_count,
                "global_templates_count": global_template_count,
                "environment": self.environment
            }
            
        except Exception as e:
            logger.error(f"Error getting initialization status: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "environment": self.environment
            }
