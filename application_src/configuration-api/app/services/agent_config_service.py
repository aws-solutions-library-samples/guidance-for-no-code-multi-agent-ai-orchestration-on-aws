"""
Agent configuration management service.

This service handles the business logic for managing agent configurations,
including system prompts, configuration storage, and retrieval operations.
"""

import logging
from typing import Dict, List, Optional, Set

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../../'))
from common.secure_logging_utils import log_exception_safely

from ..models import AgentConfigRequest, AgentConfigResponse, AgentToolsUpdateRequest
from ..models.ssm_data_models import SSMDataValidator, SSMParameterPaths
from .ssm_service import SSMService

logger = logging.getLogger(__name__)


class AgentConfigService:
    """Service for managing agent configurations."""

    def __init__(self, ssm_service: SSMService):
        """
        Initialize Agent Configuration service.
        
        Args:
            ssm_service: SSM service instance for parameter operations
        """
        self.ssm_service = ssm_service
        logger.info("AgentConfigService initialized")

    def save_agent_configuration(self, config_request: AgentConfigRequest) -> Dict[str, str]:
        """
        Save agent configuration including system prompt and settings.
        
        CRITICAL: This method preserves existing configuration data when editing.
        When updating an existing agent, it merges new data with existing data to prevent
        loss of configurations that weren't modified in the current request.
        
        Args:
            config_request: Agent configuration request data
            
        Returns:
            Dictionary with operation status and details
            
        Raises:
            ValueError: If agent_name is missing or invalid
            Exception: If save operation fails
        """
        agent_name = config_request.agent_name.strip()
        
        if not agent_name:
            raise ValueError("Agent name is required and cannot be empty")

        logger.info(f"Saving configuration for agent: {agent_name}")

        try:
            # Store system prompt separately if provided
            if config_request.system_prompt:
                success = self._store_system_prompt(
                    agent_name=agent_name,
                    prompt_name=config_request.system_prompt_name,
                    prompt_content=config_request.system_prompt
                )
                if not success:
                    raise Exception("Failed to store system prompt")

            # CRITICAL FIX: Load existing configuration to preserve data during edits
            existing_config = self._get_agent_config(agent_name)
            
            # Prepare new configuration data (excluding system prompt content)
            # Use model_dump() for Pydantic v2 with proper nested model serialization
            new_config_data = config_request.model_dump(mode='json', exclude_none=True)
            new_config_data.pop('system_prompt', None)  # Remove prompt content from config
            
            # Normalize cache_prompt and cache_tools values to valid enum values
            # UI may send 'default' which needs to be converted to 'False'
            if new_config_data.get('cache_prompt') == 'default':
                new_config_data['cache_prompt'] = 'False'
                logger.info(f"Normalized cache_prompt from 'default' to 'False'")
            
            if new_config_data.get('cache_tools') == 'default':
                new_config_data['cache_tools'] = 'False'
                logger.info(f"Normalized cache_tools from 'default' to 'False'")

            # CRITICAL FIX: Merge new data with existing data to preserve unmodified fields
            if existing_config:
                logger.info(f"Merging with existing configuration for agent: {agent_name}")
                
                # Start with existing config as base
                merged_config = existing_config.copy()
                
                # Component types that have provider_details pattern
                component_types = ['memory', 'knowledge_base', 'observability', 'guardrail']
                
                # Track which components have existing configurations
                components_to_preserve = {}
                for component_type in component_types:
                    details_key = f"{component_type}_details" if component_type == 'knowledge_base' else f"{component_type}_provider_details"
                    existing_details = existing_config.get(details_key, [])
                    
                    # Check if this component has meaningful existing configuration
                    if isinstance(existing_details, list) and len(existing_details) > 0:
                        # Check if any provider has non-empty config
                        has_config = any(
                            isinstance(provider, dict) and 
                            isinstance(provider.get('config', {}), dict) and 
                            len(provider.get('config', {})) > 0 
                            for provider in existing_details
                        )
                        
                        if has_config:
                            components_to_preserve[component_type] = {
                                'details_key': details_key,
                                'enabled_key': component_type,
                                'provider_key': f"{component_type}_provider",
                                'existing_details': existing_details,
                                'existing_enabled': existing_config.get(component_type, 'False'),
                                'existing_provider': existing_config.get(f"{component_type}_provider", 'default')
                            }
                            logger.info(f"Component '{component_type}' has existing configuration to potentially preserve")
                
                # Update with new values
                for key, value in new_config_data.items():
                    # Check if this is a component field that should be preserved
                    should_preserve = False
                    
                    for component_type, preserve_info in components_to_preserve.items():
                        # Check if this key belongs to a component with existing config
                        if key == preserve_info['details_key']:
                            # If new value is empty list, preserve existing details
                            if isinstance(value, list) and len(value) == 0:
                                logger.info(f"Preserving existing {key} (has {len(preserve_info['existing_details'])} items)")
                                should_preserve = True
                                break
                        
                        # Also preserve the enabled flag if details are being preserved
                        elif key == preserve_info['enabled_key']:
                            new_details = new_config_data.get(preserve_info['details_key'], [])
                            if isinstance(new_details, list) and len(new_details) == 0:
                                # New request has empty details, check if we should preserve
                                if value in ['False', 'false', False, 'No', 'default']:
                                    logger.info(f"Preserving existing {key} enabled status: {preserve_info['existing_enabled']}")
                                    merged_config[key] = preserve_info['existing_enabled']
                                    should_preserve = True
                                    break
                        
                        # Also preserve the provider name if details are being preserved
                        elif key == preserve_info['provider_key']:
                            new_details = new_config_data.get(preserve_info['details_key'], [])
                            if isinstance(new_details, list) and len(new_details) == 0:
                                if value in ['default', 'No', 'no']:
                                    logger.info(f"Preserving existing {key}: {preserve_info['existing_provider']}")
                                    merged_config[key] = preserve_info['existing_provider']
                                    should_preserve = True
                                    break
                    
                    # If we should preserve this field, skip the update
                    if should_preserve:
                        continue
                    
                    # Otherwise, update the field with new value
                    merged_config[key] = value
                
                config_data = merged_config
                logger.info(f"Configuration merged successfully, preserved {len(components_to_preserve)} component configurations")
            else:
                # New agent - use new config as-is
                config_data = new_config_data
                logger.info(f"Creating new configuration for agent: {agent_name}")

            # Store main configuration
            success = self._store_agent_config(agent_name, config_data)
            if not success:
                raise Exception("Failed to store agent configuration")

            logger.info(f"Successfully saved configuration for agent: {agent_name}")
            return {
                "status": "success",
                "message": f"Configuration for agent '{agent_name}' saved successfully",
                "agent_name": agent_name
            }

        except Exception as e:
            logger.error(f"Error saving configuration for agent {agent_name}: {e}")
            raise

    def load_agent_configuration(self, agent_name: str) -> AgentConfigResponse:
        """
        Load complete agent configuration including system prompt.
        
        Args:
            agent_name: Name of the agent to load configuration for
            
        Returns:
            Complete agent configuration response
            
        Raises:
            ValueError: If agent_name is missing
            Exception: If agent configuration not found or loading fails
        """
        agent_name = agent_name.strip()
        
        if not agent_name:
            raise ValueError("Agent name is required and cannot be empty")

        logger.info(f"Loading configuration for agent: {agent_name}")

        try:
            # Retrieve main configuration
            config_data = self._get_agent_config(agent_name)
            if config_data is None:
                raise Exception(f"Agent '{agent_name}' not found")

            logger.debug("Raw config data loaded from SSM")
            logger.debug(f"Data types in SSM config: {list(config_data.keys())}")

            # Retrieve system prompt if specified
            system_prompt_name = config_data.get('system_prompt_name', '')
            system_prompt_content = ""

            if system_prompt_name:
                system_prompt_content = self._get_system_prompt(
                    agent_name=agent_name,
                    prompt_name=system_prompt_name
                )

            # Add system prompt content to response
            config_data['system_prompt'] = system_prompt_content
            
            # Add missing fields if not present
            if 'mcp_enabled' not in config_data:
                config_data['mcp_enabled'] = False
            if 'mcp_servers' not in config_data:
                config_data['mcp_servers'] = ""

            # Convert nested dictionaries to Pydantic models
            # This ensures proper deserialization of complex nested structures
            from ..models.agent_config import ThinkingConfig, ProviderConfig, ToolConfig
            
            # Helper function to safely convert nested structures
            def convert_to_provider_config(item):
                """Safely convert item to ProviderConfig, handling various input types."""
                if isinstance(item, dict):
                    return ProviderConfig(**item)
                elif isinstance(item, ProviderConfig):
                    return item
                else:
                    logger.warning(f"Unexpected provider config type: {type(item)}, item: {item}")
                    # Try to handle string or other types gracefully
                    if isinstance(item, str):
                        return ProviderConfig(name=item, config={})
                    return item
            
            def convert_to_tool_config(item):
                """Safely convert item to ToolConfig, handling various input types."""
                if isinstance(item, dict):
                    return ToolConfig(**item)
                elif isinstance(item, ToolConfig):
                    return item
                else:
                    logger.warning(f"Unexpected tool config type: {type(item)}, item: {item}")
                    if isinstance(item, str):
                        return ToolConfig(name=item, config={})
                    return item
            
            # Convert thinking config - handle missing or invalid data
            if 'thinking' in config_data:
                if isinstance(config_data['thinking'], dict):
                    config_data['thinking'] = ThinkingConfig(**config_data['thinking'])
                elif not isinstance(config_data['thinking'], ThinkingConfig):
                    logger.warning(f"Invalid thinking config type: {type(config_data['thinking'])}, using default")
                    config_data['thinking'] = ThinkingConfig(type="standard", budget_tokens=100000)
            else:
                config_data['thinking'] = ThinkingConfig(type="standard", budget_tokens=100000)
            
            # Convert tools list - handle empty, None, or invalid data
            if 'tools' in config_data:
                if isinstance(config_data['tools'], list):
                    config_data['tools'] = [convert_to_tool_config(tool) for tool in config_data['tools']]
                elif config_data['tools'] is None:
                    config_data['tools'] = []
                else:
                    logger.warning(f"Invalid tools type: {type(config_data['tools'])}, using empty list")
                    config_data['tools'] = []
            else:
                config_data['tools'] = []
            
            # Convert memory provider details - handle all cases
            if 'memory_provider_details' in config_data:
                if isinstance(config_data['memory_provider_details'], list):
                    config_data['memory_provider_details'] = [
                        convert_to_provider_config(provider) for provider in config_data['memory_provider_details']
                    ]
                elif config_data['memory_provider_details'] is None:
                    config_data['memory_provider_details'] = []
                else:
                    logger.warning(f"Invalid memory_provider_details type: {type(config_data['memory_provider_details'])}")
                    config_data['memory_provider_details'] = []
            else:
                config_data['memory_provider_details'] = []
            
            # Convert knowledge base details - handle all cases
            if 'knowledge_base_details' in config_data:
                if isinstance(config_data['knowledge_base_details'], list):
                    config_data['knowledge_base_details'] = [
                        convert_to_provider_config(provider) for provider in config_data['knowledge_base_details']
                    ]
                elif config_data['knowledge_base_details'] is None:
                    config_data['knowledge_base_details'] = []
                else:
                    logger.warning(f"Invalid knowledge_base_details type: {type(config_data['knowledge_base_details'])}")
                    config_data['knowledge_base_details'] = []
            else:
                config_data['knowledge_base_details'] = []
            
            # Convert observability provider details - handle all cases
            if 'observability_provider_details' in config_data:
                if isinstance(config_data['observability_provider_details'], list):
                    config_data['observability_provider_details'] = [
                        convert_to_provider_config(provider) for provider in config_data['observability_provider_details']
                    ]
                elif config_data['observability_provider_details'] is None:
                    config_data['observability_provider_details'] = []
                else:
                    logger.warning(f"Invalid observability_provider_details type: {type(config_data['observability_provider_details'])}")
                    config_data['observability_provider_details'] = []
            else:
                config_data['observability_provider_details'] = []
            
            # Convert guardrail provider details - handle all cases
            if 'guardrail_provider_details' in config_data:
                if isinstance(config_data['guardrail_provider_details'], list):
                    config_data['guardrail_provider_details'] = [
                        convert_to_provider_config(provider) for provider in config_data['guardrail_provider_details']
                    ]
                elif config_data['guardrail_provider_details'] is None:
                    config_data['guardrail_provider_details'] = []
                else:
                    logger.warning(f"Invalid guardrail_provider_details type: {type(config_data['guardrail_provider_details'])}")
                    config_data['guardrail_provider_details'] = []
            else:
                config_data['guardrail_provider_details'] = []

            logger.debug("Final config data converted to Pydantic models")
            logger.debug(f"Available config fields: {list(config_data.keys())}")

            logger.info(f"Successfully loaded configuration for agent: {agent_name}")
            return AgentConfigResponse(**config_data)

        except Exception as e:
            logger.error(f"Error loading configuration for agent {agent_name}: {e}")
            raise

    def list_available_agents(self) -> Dict[str, any]:
        """
        List all available agent configurations.
        
        Returns:
            Dictionary containing agent list and metadata
        """
        logger.info("Listing available agent configurations")

        try:
            # Get all parameters under /agent/ prefix
            parameters = self.ssm_service.list_parameters_by_prefix('/agent/', max_results=50)

            # Extract unique agent names from parameter paths
            agent_names = set()
            for param in parameters:
                # Parameter format: /agent/<agent_name>/config or /agent/<agent_name>/system-prompts/...
                path_parts = param['name'].split('/')
                if len(path_parts) >= 3 and path_parts[1] == 'agent':
                    agent_names.add(path_parts[2])

            sorted_agents = sorted(list(agent_names))
            
            logger.info(f"Found {len(sorted_agents)} available agents")
            return {
                "status": "success",
                "agents": sorted_agents,
                "count": len(sorted_agents)
            }

        except Exception as e:
            log_exception_safely(logger, e, "Error listing agent configurations")
            return {
                "status": "error",
                "error": "Internal error occurred",
                "agents": [],
                "count": 0
            }

    def get_agent_debug_info(self, agent_name: str) -> Dict[str, any]:
        """
        Get debug information for an agent configuration.
        
        Args:
            agent_name: Name of the agent to debug
            
        Returns:
            Dictionary containing debug information
        """
        agent_name = agent_name.strip()
        logger.info(f"Getting debug info for agent: {agent_name}")

        debug_info = {
            "agent_name": agent_name,
            "config_parameter": f"/agent/{agent_name}/config",
            "system_prompts_index": f"/agent/{agent_name}/system-prompts/index",
            "config_data": None,
            "system_prompts_data": None,
            "errors": []
        }

        # Get configuration data
        try:
            config_data = self.ssm_service.get_json_parameter(f"/agent/{agent_name}/config")
            debug_info["config_data"] = config_data
        except Exception as e:
            debug_info["errors"].append(f"Config error: {str(e)}")

        # Get system prompts index
        try:
            prompts_data = self.ssm_service.get_json_parameter(f"/agent/{agent_name}/system-prompts/index")
            debug_info["system_prompts_data"] = prompts_data
        except Exception as e:
            debug_info["errors"].append(f"System prompts error: {str(e)}")

        return debug_info

    def delete_agent_configuration(self, agent_name: str) -> Dict[str, str]:
        """
        Delete all configuration data for an agent using comprehensive parameter discovery.
        
        Args:
            agent_name: Name of the agent to delete
            
        Returns:
            Dictionary with operation status and details
        """
        agent_name = agent_name.strip()
        
        if not agent_name:
            raise ValueError("Agent name is required and cannot be empty")

        logger.info(f"Deleting configuration for agent: {agent_name}")

        try:
            # Use comprehensive approach: discover ALL parameters containing the agent name
            try:
                all_agent_parameters = self.ssm_service.find_all_agent_parameters(agent_name)
                logger.info(f"Found {len(all_agent_parameters)} parameters to delete for agent '{agent_name}'")
            except Exception as e:
                logger.error(f"Error discovering parameters for agent '{agent_name}': {e}")
                all_agent_parameters = []

            # Track deletion results
            deleted_parameters = []
            failed_deletions = []
            
            # Delete all discovered parameters
            for param in all_agent_parameters:
                param_name = param['name']
                try:
                    if self.ssm_service.delete_parameter(param_name):
                        deleted_parameters.append(param_name)
                        logger.info(f"Successfully deleted parameter: {param_name}")
                    else:
                        failed_deletions.append(param_name)
                        logger.warning(f"Failed to delete parameter: {param_name}")
                except Exception as e:
                    failed_deletions.append(param_name)
                    logger.error(f"Error deleting parameter {param_name}: {e}")

            # If no parameters were found through comprehensive search, try the legacy hardcoded approach
            if not all_agent_parameters:
                logger.info(f"No parameters found via comprehensive search, trying legacy hardcoded deletion for agent '{agent_name}'")
                
                # Try to delete known parameter patterns
                legacy_params = [
                    f"/agent/{agent_name}/config",
                    f"/agent/{agent_name}/system-prompts/index"
                ]
                
                for param_name in legacy_params:
                    try:
                        if self.ssm_service.delete_parameter(param_name):
                            deleted_parameters.append(param_name)
                            logger.info(f"Successfully deleted legacy parameter: {param_name}")
                    except Exception as e:
                        logger.warning(f"Could not delete legacy parameter {param_name}: {e}")

                # Try to delete individual system prompt parameters from index
                try:
                    prompts_data = self.ssm_service.get_json_parameter(f"/agent/{agent_name}/system-prompts/index")
                    if prompts_data:
                        for prompt_path in prompts_data.values():
                            if isinstance(prompt_path, str) and prompt_path.startswith('/'):
                                try:
                                    if self.ssm_service.delete_parameter(prompt_path):
                                        deleted_parameters.append(prompt_path)
                                        logger.info(f"Successfully deleted indexed system prompt: {prompt_path}")
                                except Exception as e:
                                    failed_deletions.append(prompt_path)
                                    logger.warning(f"Could not delete indexed system prompt {prompt_path}: {e}")
                except Exception as e:
                    logger.warning(f"Could not read system prompts index for cleanup: {e}")

            # Determine final status
            if deleted_parameters:
                logger.info(f"Successfully deleted configuration for agent: {agent_name}")
                logger.info(f"Deleted parameters: {deleted_parameters}")
                if failed_deletions:
                    logger.warning(f"Failed to delete some parameters: {failed_deletions}")
                
                return {
                    "status": "success",
                    "message": f"Configuration for agent '{agent_name}' deleted successfully",
                    "deleted_parameters": deleted_parameters,
                    "failed_deletions": failed_deletions,
                    "total_deleted": len(deleted_parameters),
                    "total_failed": len(failed_deletions)
                }
            else:
                logger.warning(f"No parameters found or deleted for agent '{agent_name}'")
                return {
                    "status": "not_found",
                    "message": f"No configuration found for agent '{agent_name}'",
                    "deleted_parameters": [],
                    "failed_deletions": failed_deletions,
                    "total_deleted": 0,
                    "total_failed": len(failed_deletions)
                }

        except Exception as e:
            logger.error(f"Error deleting configuration for agent {agent_name}: {e}")
            raise

    def _store_system_prompt(self, agent_name: str, prompt_name: str, prompt_content: str) -> bool:
        """Store system prompt and update the index."""
        try:
            # Sanitize the prompt name to ensure it's valid for SSM parameter names
            sanitized_prompt_name = self.ssm_service.sanitize_parameter_name(prompt_name.lower())
            
            # Store the actual system prompt content
            prompt_path = f"/agent/{agent_name}/system-prompts/{sanitized_prompt_name}"
            
            success = self.ssm_service.store_parameter(
                name=prompt_path,
                value=prompt_content,
                description=f"System prompt '{prompt_name}' for agent {agent_name}"
            )
            
            if not success:
                return False

            # Update the system prompts index
            index_path = f"/agent/{agent_name}/system-prompts/index"
            
            # Get existing index or create new one
            existing_index = self.ssm_service.get_json_parameter(index_path) or {}
            existing_index[prompt_name] = prompt_path
            
            # Store updated index
            success = self.ssm_service.store_json_parameter(
                name=index_path,
                data=existing_index,
                description=f"System prompts index for agent {agent_name}"
            )

            logger.info(f"System prompt '{prompt_name}' stored for agent '{agent_name}'")
            return success

        except Exception as e:
            logger.error(f"Error storing system prompt: {e}")
            return False

    def _get_system_prompt(self, agent_name: str, prompt_name: str) -> str:
        """
        Retrieve system prompt content with global template fallback.
        
        This method looks for prompts in the following order:
        1. Agent-specific prompts (/agent/{agent_name}/system-prompts/)
        2. Global prompt templates (/system/prompt-templates/)
        3. Default agent templates (/system/agent-templates/default)
        
        This ensures all agents can access any prompt from the prompts folder.
        """
        try:
            # First, try to get the agent-specific system prompts index
            index_path = f"/agent/{agent_name}/system-prompts/index"
            prompts_index = self.ssm_service.get_json_parameter(index_path)
            
            # If agent has specific prompts, check for the requested prompt
            if prompts_index and prompt_name in prompts_index:
                prompt_reference = prompts_index[prompt_name]
                
                # Check if it's a path reference or direct content
                if isinstance(prompt_reference, str) and prompt_reference.startswith('/'):
                    # It's a path reference
                    prompt_content = self.ssm_service.get_parameter(prompt_reference)
                    if prompt_content is not None:
                        logger.info(f"Retrieved prompt '{prompt_name}' from agent-specific location for {agent_name}")
                        return prompt_content
                else:
                    # It's direct content stored in the index
                    logger.info(f"Retrieved prompt '{prompt_name}' from agent-specific inline content for {agent_name}")
                    return str(prompt_reference)
            
            # If not found in agent-specific prompts, try global template library
            logger.info(f"Prompt '{prompt_name}' not found in agent-specific prompts for {agent_name}, checking global templates...")
            
            global_template_path = f"/system/prompt-templates/{prompt_name}"
            global_prompt_content = self.ssm_service.get_parameter(global_template_path)
            
            if global_prompt_content:
                logger.info(f"Retrieved prompt '{prompt_name}' from global template library for {agent_name}")
                return global_prompt_content
            
            # If still not found, try the default agent templates index
            logger.info(f"Prompt '{prompt_name}' not found in global templates, checking default agent templates...")
            
            default_templates_index = self.ssm_service.get_json_parameter("/system/agent-templates/default")
            if default_templates_index and prompt_name in default_templates_index:
                default_template_path = default_templates_index[prompt_name]
                default_prompt_content = self.ssm_service.get_parameter(default_template_path)
                
                if default_prompt_content:
                    logger.info(f"Retrieved prompt '{prompt_name}' from default agent templates for {agent_name}")
                    return default_prompt_content
            
            # If still not found, provide comprehensive error message with available options
            available_prompts = []
            
            # Get available agent-specific prompts
            if prompts_index:
                available_prompts.extend([f"{p} (agent-specific)" for p in prompts_index.keys()])
            
            # Get available global templates
            try:
                global_templates_index = self.ssm_service.get_json_parameter("/system/prompt-templates/index")
                if global_templates_index:
                    available_prompts.extend([f"{p} (global)" for p in global_templates_index.keys()])
            except:
                pass
            
            if available_prompts:
                return f"System prompt '{prompt_name}' not found for agent '{agent_name}'. Available prompts: {', '.join(available_prompts[:10])}{'...' if len(available_prompts) > 10 else ''}"
            else:
                return f"No system prompts found for agent '{agent_name}'. Global prompt library may need initialization."

        except Exception as e:
            logger.error(f"Error retrieving system prompt: {e}")
            return f"Error retrieving system prompt: {str(e)}"

    def _store_agent_config(self, agent_name: str, config_data: Dict) -> bool:
        """Store agent configuration data with validation against SSM data model."""
        try:
            # Validate configuration data against SSM data model before storing
            validation_result = SSMDataValidator.validate_agent_configuration(config_data)
            
            if not validation_result["valid"]:
                logger.error(f"Configuration validation failed for {agent_name}: {validation_result['errors']}")
                logger.error(f"Missing fields: {validation_result.get('missing_fields', [])}")
                # Don't fail silently - log the error but still attempt to store for backward compatibility
                logger.warning(f"Storing potentially incomplete configuration for {agent_name}")
            else:
                logger.info(f"Configuration validation passed for {agent_name} - conforms to SSM data model")
            
            # Use standardized path from SSM parameter paths
            config_path = SSMParameterPaths.agent_config(agent_name)
            return self.ssm_service.store_json_parameter(
                name=config_path,
                data=config_data,
                description=f"Configuration for agent {agent_name}"
            )
        except Exception as e:
            logger.error(f"Error storing agent config: {e}")
            return False

    def _get_agent_config(self, agent_name: str) -> Optional[Dict]:
        """Retrieve agent configuration data."""
        try:
            config_path = f"/agent/{agent_name}/config"
            return self.ssm_service.get_json_parameter(config_path)
        except Exception as e:
            logger.error(f"Error retrieving agent config: {e}")
            return None

    def list_system_prompts(self, agent_name: str) -> Dict[str, any]:
        """
        List available system prompts for an agent.
        
        Args:
            agent_name: Name of the agent
            
        Returns:
            Dictionary containing available prompts and metadata
        """
        agent_name = agent_name.strip()
        
        if not agent_name:
            raise ValueError("Agent name is required and cannot be empty")

        logger.info(f"Listing system prompts for agent: {agent_name}")

        try:
            # Get the system prompts index
            index_path = f"/agent/{agent_name}/system-prompts/index"
            prompts_index = self.ssm_service.get_json_parameter(index_path)
            
            if not prompts_index:
                # Agent exists but no prompts yet - return empty structure
                return {
                    "status": "success",
                    "agent_name": agent_name,
                    "prompts": [],
                    "count": 0,
                    "message": "No system prompts found for this agent"
                }

            # Build prompt list with metadata
            prompt_list = []
            for prompt_name, prompt_path in prompts_index.items():
                try:
                    # Get a preview of the prompt content (first 100 chars)
                    if isinstance(prompt_path, str) and prompt_path.startswith('/'):
                        content = self.ssm_service.get_parameter(prompt_path) or ""
                    else:
                        content = str(prompt_path)
                    
                    preview = content[:100] + "..." if len(content) > 100 else content
                    
                    prompt_list.append({
                        "name": prompt_name,
                        "path": prompt_path if isinstance(prompt_path, str) else None,
                        "preview": preview,
                        "length": len(content)
                    })
                except Exception as e:
                    logger.warning(f"Error getting preview for prompt {prompt_name}: {e}")
                    prompt_list.append({
                        "name": prompt_name,
                        "path": prompt_path if isinstance(prompt_path, str) else None,
                        "preview": "Error loading preview",
                        "length": 0
                    })

            logger.info(f"Found {len(prompt_list)} system prompts for agent {agent_name}")
            return {
                "status": "success",
                "agent_name": agent_name,
                "prompts": prompt_list,
                "count": len(prompt_list)
            }

        except Exception as e:
            logger.error(f"Error listing system prompts for agent {agent_name}: {e}")
            raise Exception(f"Failed to list system prompts: {str(e)}")

    def get_system_prompt_content(self, agent_name: str, prompt_name: str) -> Dict[str, any]:
        """
        Get system prompt content for preview/editing.
        
        Args:
            agent_name: Name of the agent
            prompt_name: Name of the system prompt
            
        Returns:
            Dictionary containing prompt content and metadata
        """
        agent_name = agent_name.strip()
        prompt_name = prompt_name.strip()
        
        if not agent_name or not prompt_name:
            raise ValueError("Both agent_name and prompt_name are required")

        logger.info(f"Getting content for system prompt '{prompt_name}' of agent '{agent_name}'")

        try:
            # Get the system prompts index
            index_path = f"/agent/{agent_name}/system-prompts/index"
            prompts_index = self.ssm_service.get_json_parameter(index_path)
            
            if not prompts_index:
                raise Exception(f"No system prompts found for agent '{agent_name}'")

            if prompt_name not in prompts_index:
                available_prompts = list(prompts_index.keys())
                raise Exception(f"System prompt '{prompt_name}' not found. Available: {', '.join(available_prompts)}")

            prompt_reference = prompts_index[prompt_name]

            # Get the content
            if isinstance(prompt_reference, str) and prompt_reference.startswith('/'):
                # It's a path reference
                content = self.ssm_service.get_parameter(prompt_reference)
                if content is None:
                    raise Exception(f"Could not retrieve system prompt content from {prompt_reference}")
            else:
                # It's direct content stored in the index
                content = str(prompt_reference)

            logger.info(f"Successfully retrieved content for prompt '{prompt_name}'")
            return {
                "status": "success",
                "agent_name": agent_name,
                "prompt_name": prompt_name,
                "prompt_content": content,
                "content_length": len(content),
                "storage_path": prompt_reference if isinstance(prompt_reference, str) else "inline"
            }

        except Exception as e:
            logger.error(f"Error getting system prompt content: {e}")
            raise Exception(f"Failed to get system prompt content: {str(e)}")

    def list_global_prompt_templates(self) -> Dict[str, any]:
        """
        Get global system prompt templates that can be used across agents.
        
        Returns:
            Dictionary containing global prompt templates
        """
        logger.info("Listing global system prompt templates")

        try:
            # Define built-in prompt templates that can be used across agents
            global_templates = {
                "qa_assistant": {
                    "name": "Q&A Assistant",
                    "description": "General-purpose question and answer assistant",
                    "content": """You are a helpful Q&A assistant designed to answer questions based on provided documents and knowledge sources.

Your capabilities include:
1. Answering questions using retrieved information
2. Providing accurate and well-sourced responses  
3. Admitting when you don't know something
4. Asking clarifying questions when needed

Guidelines:
- Always prioritize accuracy over speed
- Cite sources when possible
- Be concise but comprehensive
- If information is unavailable, say so clearly
- Provide helpful suggestions for finding more information""",
                    "category": "General"
                },
                
                "technical_assistant": {
                    "name": "Technical Assistant", 
                    "description": "Specialized assistant for software development and technical queries",
                    "content": """You are a technical assistant specializing in software development, architecture, and engineering best practices.

Your expertise includes:
1. Software development and programming languages
2. System architecture and design patterns
3. DevOps and deployment strategies
4. Code review and optimization
5. Troubleshooting and debugging

Guidelines:
- Provide practical, actionable advice
- Include code examples when relevant
- Follow industry best practices
- Explain complex concepts clearly
- Consider security and performance implications
- Stay current with modern development practices""",
                    "category": "Technical"
                },
                
                "chat_assistant": {
                    "name": "Conversational Assistant",
                    "description": "Friendly assistant for general conversation and support",
                    "content": """You are a friendly and engaging conversational AI assistant designed to help users with various tasks and questions.

Your approach:
1. Be warm, helpful, and approachable
2. Listen actively to user needs
3. Provide clear and useful information
4. Maintain a positive and supportive tone
5. Adapt your communication style to the user

Guidelines:
- Be empathetic and understanding
- Ask follow-up questions to better help
- Provide step-by-step guidance when needed
- Keep conversations engaging and productive
- Respect user privacy and boundaries""",
                    "category": "Conversational"
                },
                
                "professional_assistant": {
                    "name": "Professional Assistant",
                    "description": "Business-focused assistant for workplace communications",
                    "content": """You are a professional AI assistant focused on business and workplace communications.

Your capabilities include:
1. Professional writing and communication
2. Business analysis and strategy
3. Project management guidance
4. Process improvement recommendations
5. Meeting and presentation support

Guidelines:
- Maintain a professional and polished tone
- Focus on business value and outcomes
- Provide structured and organized responses
- Use industry-standard terminology appropriately
- Support decision-making with data and analysis
- Respect confidentiality and business protocols""",
                    "category": "Business"
                }
            }

            logger.info(f"Returning {len(global_templates)} global prompt templates")
            return {
                "status": "success",
                "templates": global_templates,
                "count": len(global_templates),
                "categories": list(set(template["category"] for template in global_templates.values()))
            }

        except Exception as e:
            log_exception_safely(logger, e, "Error listing global prompt templates")
            return {
                "status": "error", 
                "error": "Internal error occurred",
                "templates": {},
                "count": 0,
                "categories": []
            }

    def list_all_system_prompts_across_agents(self) -> Dict[str, any]:
        """
        Get all system prompts from all agents for cross-agent reusability.
        
        Returns:
            Dictionary containing all prompts grouped by agent source
        """
        logger.info("Listing all system prompts across all agents for reusability")

        try:
            # Get list of all available agents
            agents_result = self.list_available_agents()
            if agents_result["status"] != "success":
                return {
                    "status": "error",
                    "error": "Failed to get agent list",
                    "prompts_by_agent": {},
                    "total_prompts": 0
                }

            all_agents = agents_result["agents"]
            prompts_by_agent = {}
            total_prompts = 0

            # For each agent, get their system prompts
            for agent_name in all_agents:
                try:
                    prompts_result = self.list_system_prompts(agent_name)
                    if prompts_result["status"] == "success" and prompts_result["prompts"]:
                        # Add agent source info to each prompt
                        agent_prompts = []
                        for prompt in prompts_result["prompts"]:
                            prompt_with_source = prompt.copy()
                            prompt_with_source["source_agent"] = agent_name
                            prompt_with_source["display_name"] = f"{prompt['name']} (from {agent_name})"
                            agent_prompts.append(prompt_with_source)
                        
                        prompts_by_agent[agent_name] = {
                            "agent_name": agent_name,
                            "prompts": agent_prompts,
                            "count": len(agent_prompts)
                        }
                        total_prompts += len(agent_prompts)
                        
                except Exception as e:
                    logger.warning(f"Error getting prompts for agent {agent_name}: {e}")
                    # Continue with other agents
                    continue

            logger.info(f"Found {total_prompts} total system prompts across {len(prompts_by_agent)} agents")
            return {
                "status": "success",
                "prompts_by_agent": prompts_by_agent,
                "total_prompts": total_prompts,
                "agents_with_prompts": len(prompts_by_agent)
            }

        except Exception as e:
            log_exception_safely(logger, e, "Error listing all system prompts across agents")
            return {
                "status": "error",
                "error": "Internal error occurred",
                "prompts_by_agent": {},
                "total_prompts": 0
            }

    def create_system_prompt(self, agent_name: str, prompt_name: str, prompt_content: str) -> Dict[str, str]:
        """
        Create a new system prompt for an agent.
        
        Args:
            agent_name: Name of the agent
            prompt_name: Name of the system prompt
            prompt_content: Content of the system prompt
            
        Returns:
            Dictionary with operation status
        """
        agent_name = agent_name.strip()
        prompt_name = prompt_name.strip()
        prompt_content = prompt_content.strip()
        
        if not agent_name or not prompt_name or not prompt_content:
            raise ValueError("agent_name, prompt_name, and prompt_content are all required")

        logger.info(f"Creating system prompt '{prompt_name}' for agent '{agent_name}'")

        try:
            # Check if prompt already exists
            try:
                index_path = f"/agent/{agent_name}/system-prompts/index"
                prompts_index = self.ssm_service.get_json_parameter(index_path) or {}
                
                if prompt_name in prompts_index:
                    raise ValueError(f"System prompt '{prompt_name}' already exists for agent '{agent_name}'")
            except Exception as e:
                if "already exists" in str(e):
                    raise e
                # Index doesn't exist yet, which is fine for new agent
                pass

            # Store the system prompt
            success = self._store_system_prompt(agent_name, prompt_name, prompt_content)
            
            if not success:
                raise Exception("Failed to store system prompt")

            logger.info(f"Successfully created system prompt '{prompt_name}' for agent '{agent_name}'")
            return {
                "status": "success",
                "message": f"System prompt '{prompt_name}' created successfully for agent '{agent_name}'",
                "agent_name": agent_name,
                "prompt_name": prompt_name
            }

        except ValueError as e:
            logger.error(f"Validation error creating system prompt: {e}")
            raise e
        except Exception as e:
            logger.error(f"Error creating system prompt: {e}")
            raise Exception(f"Failed to create system prompt: {str(e)}")

    def update_agent_tools(self, tools_request: AgentToolsUpdateRequest) -> Dict[str, str]:
        """
        Update only the tools configuration for an agent.
        
        Args:
            tools_request: Agent tools update request data
            
        Returns:
            Dictionary with operation status and details
            
        Raises:
            ValueError: If agent_name is missing or invalid
            Exception: If update operation fails
        """
        agent_name = tools_request.agent_name.strip()
        
        if not agent_name:
            raise ValueError("Agent name is required and cannot be empty")

        logger.info(f"Updating tools configuration for agent: {agent_name}")

        try:
            # Get current configuration
            current_config = self._get_agent_config(agent_name)
            if current_config is None:
                raise Exception(f"Agent '{agent_name}' configuration not found")

            # Update only the tools field
            # Use model_dump() for Pydantic v2 with proper nested model serialization
            current_config['tools'] = [tool.model_dump(mode='json') for tool in tools_request.tools]

            # Store updated configuration
            success = self._store_agent_config(agent_name, current_config)
            if not success:
                raise Exception("Failed to store updated agent configuration")

            logger.info(f"Successfully updated tools configuration for agent: {agent_name}")
            return {
                "status": "success",
                "message": f"Tools configuration for agent '{agent_name}' updated successfully",
                "agent_name": agent_name,
                "tools_count": len(tools_request.tools)
            }

        except Exception as e:
            logger.error(f"Error updating tools for agent {agent_name}: {e}")
            raise
