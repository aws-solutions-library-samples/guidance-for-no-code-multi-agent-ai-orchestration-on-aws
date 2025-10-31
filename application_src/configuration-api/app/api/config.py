"""
Configuration management API routes.

This module provides endpoints for managing agent configurations.
"""

import logging
from typing import Dict, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends

from ..models import AgentConfigRequest, AgentConfigResponse, AgentNameRequest, AgentToolsUpdateRequest
from ..services import AgentConfigService, SSMService
from ..utils.dependencies import get_agent_config_service, get_ssm_service

# Authentication middleware imports
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))

from common.auth import UserInfo
from ..middleware.auth_middleware import get_current_user, RequirePermission
from common.secure_logging_utils import SecureLogger, log_exception_safely

logger = logging.getLogger(__name__)

config_router = APIRouter(prefix="/config")


@config_router.post('/save')
async def save_agent_config(
    request: AgentConfigRequest,
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:update")),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    Save agent configuration to SSM Parameter Store.
    
    This endpoint saves the agent configuration to SSM. To deploy the agent
    infrastructure, use the dedicated deployment endpoints:
    - POST /api/v1/deployment/deploy - Deploy agent from CloudFormation template
    - POST /api/v1/deployment/deploy-with-config - Save config and deploy in one call
    
    Args:
        request: Agent configuration data
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary with operation status and details
        
    Raises:
        HTTPException: If save operation fails
    """
    try:
        logger.info(f"Saving configuration for agent: {request.agent_name}")
        result = agent_service.save_agent_configuration(request)
        logger.info(f"Successfully saved configuration for agent: {request.agent_name}")
        return result
        
    except ValueError as e:
        logger.warning("Validation error in save_agent_config")
        log_exception_safely(logger, e, "Validation error in save_agent_config")
        raise HTTPException(status_code=400, detail="Invalid agent configuration data")
    except Exception as e:
        logger.error("Unexpected error in save_agent_config")
        log_exception_safely(logger, e, "Unexpected error saving configuration")
        raise HTTPException(status_code=500, detail="Internal server error occurred while saving configuration")


@config_router.post('/update-tools')
async def update_agent_tools(
    request: AgentToolsUpdateRequest,
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:update")),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, str]:
    """
    Update only the tools configuration for an agent.
    
    Args:
        request: Agent tools update data
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary with operation status and details
        
    Raises:
        HTTPException: If update operation fails
    """
    try:
        result = agent_service.update_agent_tools(request)
        return result
        
    except ValueError as e:
        logger.warning("Validation error in update_agent_tools")
        log_exception_safely(logger, e, "Validation error in update_agent_tools")
        raise HTTPException(status_code=400, detail="Invalid agent tools configuration")
    except Exception as e:
        logger.error("Unexpected error in update_agent_tools")
        log_exception_safely(logger, e, "Unexpected error updating tools")
        raise HTTPException(status_code=500, detail="Internal server error occurred while updating tools")


@config_router.post('/load')
async def load_agent_config(
    request: AgentNameRequest,
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:read")),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> AgentConfigResponse:
    """
    Load agent configuration from SSM Parameter Store.
    
    Args:
        request: Request containing agent name
        agent_service: Injected agent configuration service
        
    Returns:
        Complete agent configuration
        
    Raises:
        HTTPException: If agent not found or load operation fails
    """
    agent_name = request.agent_name
    
    try:
        result = agent_service.load_agent_configuration(agent_name)
        return result

    except ValueError as e:
        log_exception_safely(logger, e, "Validation error loading configuration")
        raise HTTPException(status_code=400, detail="Invalid agent name")
    except Exception as e:
        logger.error("Error loading agent configuration")
        log_exception_safely(logger, e, "Error loading agent configuration")
        raise HTTPException(status_code=404, detail="Agent configuration not found")


@config_router.get('/agent/{agent_name}')
async def get_agent_config(
    agent_name: str,
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:read")),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    Get agent configuration from SSM Parameter Store.
    
    This endpoint provides the same functionality as POST /load but with GET method
    to match the UI's expectations.
    
    Args:
        agent_name: Name of the agent to load configuration for
        agent_service: Injected agent configuration service
        
    Returns:
        Complete agent configuration
        
    Raises:
        HTTPException: If agent not found or load operation fails
    """
    try:
        result = agent_service.load_agent_configuration(agent_name)
        
        # Convert result to dict for manipulation
        config_dict = result.dict() if hasattr(result, 'dict') else dict(result)
        
        return config_dict

    except ValueError as e:
        log_exception_safely(logger, e, "Validation error getting configuration")
        raise HTTPException(status_code=400, detail="Invalid agent name")
    except Exception as e:
        logger.error("Error getting agent configuration")
        log_exception_safely(logger, e, "Error getting agent configuration")
        raise HTTPException(status_code=404, detail="Agent configuration not found")


@config_router.get('/list')
async def list_agent_configs(
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:read")),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    List all available agent configurations.
    
    Args:
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary containing list of available agents and metadata
    """
    try:
        result = agent_service.list_available_agents()
        return result
        
    except Exception as e:
        logger.error("Error listing available agents")
        log_exception_safely(logger, e, "Error listing available agents")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@config_router.get('/agents')
async def get_agents_list(
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:read")),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    Get list of available agent configurations (UI-friendly endpoint).
    
    This endpoint provides the same functionality as /config/list but matches
    the UI's expected endpoint path.
    
    Args:
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary containing list of available agents and metadata
    """
    try:
        result = agent_service.list_available_agents()
        return result
        
    except Exception as e:
        logger.error("Error listing agent configurations")
        log_exception_safely(logger, e, "Error listing agent configurations")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@config_router.get('/debug/{agent_name}')
async def debug_agent_config(
    agent_name: str,
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("*:*")),  # Admin only
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    Debug endpoint to see what's stored in SSM for an agent.
    ADMIN ONLY - This endpoint exposes sensitive system information.
    
    Args:
        agent_name: Name of the agent to debug
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary containing debug information
    """
    try:
        result = agent_service.get_agent_debug_info(agent_name)
        return result
        
    except Exception as e:
        logger.error("Error in debug endpoint")
        log_exception_safely(logger, e, "Error in debug endpoint")
        return {
            "agent_name": agent_name,
            "error": "Debug information unavailable",
            "config_data": None,
            "system_prompts_data": None
        }


@config_router.get('/test-ssm')
async def test_ssm_connection(
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("*:*")),  # Admin only
    ssm_service: SSMService = Depends(get_ssm_service)
) -> Dict[str, Any]:
    """
    Test SSM connectivity and list agent parameters.
    ADMIN ONLY - This endpoint exposes sensitive system configuration.
    
    Args:
        ssm_service: Injected SSM service
        
    Returns:
        Dictionary containing connection status and available parameters
    """
    try:
        # Get connection status
        status = ssm_service.get_connection_status()
        
        if status.get("status") == "connected":
            # List available agent parameters
            parameters = ssm_service.list_parameters_by_prefix('/agent/', max_results=50)

            # Only return safe fields from status, never include "error" field
            return {
                "status": "success",
                "region": status.get("region"),
                "parameters_found": len(parameters),
                "parameters": parameters
            }
        else:
            # Never expose error message to client
            raise HTTPException(
                status_code=503,
                detail="SSM connection failed"
            )

    except Exception as e:
        logger.error("Error in test-ssm connection")
        log_exception_safely(logger, e, "Error in test-ssm connection")
        raise HTTPException(
            status_code=500,
            detail="SSM connection test failed"
        )


@config_router.delete('/delete/{agent_name}')
async def delete_agent_config(
    agent_name: str,
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:delete")),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, str]:
    """
    Delete all configuration data for an agent.
    
    Args:
        agent_name: Name of the agent to delete
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary with operation status
        
    Raises:
        HTTPException: If delete operation fails
    """
    try:
        result = agent_service.delete_agent_configuration(agent_name)
        
        if result["status"] == "not_found":
            raise HTTPException(status_code=404, detail=result["message"])
        
        return result

    except ValueError as e:
        log_exception_safely(logger, e, "Validation error deleting configuration")
        raise HTTPException(status_code=400, detail="Invalid agent name")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in delete agent config")
        log_exception_safely(logger, e, "Error in delete agent config")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@config_router.delete('/delete-complete/{agent_name}')
async def delete_agent_complete(
    agent_name: str,
    include_infrastructure: bool = True,
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:delete")),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    Delete agent completely - both configuration and CloudFormation infrastructure.
    
    This endpoint provides comprehensive agent deletion by:
    1. Identifying the associated CloudFormation stack
    2. Deleting the CloudFormation stack (if requested)
    3. Deleting the agent configuration from SSM
    4. Providing status tracking for the deletion process
    
    Args:
        agent_name: Name of the agent to delete
        include_infrastructure: Whether to delete CloudFormation stack (default: True)
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary with comprehensive deletion status
        
    Raises:
        HTTPException: If delete operation fails
    """
    http_exception_raised = False
    general_error = False
    
    try:
        logger.info(f"Starting complete deletion for agent '{agent_name}', include_infrastructure: {include_infrastructure}")
        
        deletion_result = {
            "agent_name": agent_name,
            "deletion_timestamp": datetime.utcnow().isoformat(),
            "include_infrastructure": include_infrastructure,
            "steps_completed": [],
            "steps_failed": [],
            "overall_status": "in_progress"
        }
        
        # Step 1: Find CloudFormation stack using strict pattern if infrastructure deletion is requested
        stack_info = None
        if include_infrastructure:
            try:
                from ..services.deployment_service import DeploymentService
                from ..utils.dependencies import get_deployment_service
                
                deployment_service = get_deployment_service()
                
                # Use strict pattern to find the exact stack for this agent
                # Get project name for pattern
                project_name = os.environ.get('PROJECT_NAME', 'genai-box')
                
                stack_info = await deployment_service.find_agent_stack_by_name(agent_name)
                
                if stack_info:
                    logger.info(f"Found CloudFormation stack for agent '{agent_name}': {stack_info['stack_name']}")
                    deletion_result["cloudformation_stack"] = {
                        "stack_name": stack_info['stack_name'],
                        "stack_id": stack_info.get('stack_id'),
                        "status": stack_info.get('status'),
                        "found": True,
                        "pattern": f"{project_name}-{agent_name.replace('_', '-')}-stack"
                    }
                else:
                    expected_stack_name = f"{project_name}-{agent_name.replace('_', '-')}-stack"
                    logger.warning(f"No CloudFormation stack found for agent '{agent_name}' using expected pattern: {expected_stack_name}")
                    deletion_result["cloudformation_stack"] = {
                        "stack_name": None,
                        "found": False,
                        "expected_pattern": expected_stack_name,
                        "message": f"No CloudFormation stack found for agent '{agent_name}' using expected pattern"
                    }
                    
            except Exception as e:
                logger.error(f"Error searching for CloudFormation stack for agent '{agent_name}'")
                log_exception_safely(logger, e, "Error searching for CloudFormation stack")
                deletion_result["steps_failed"].append({
                    "step": "cloudformation_stack_search",
                    "error": "Stack search failed",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        # Step 2: Delete CloudFormation stack if found and requested
        if include_infrastructure and stack_info:
            try:
                logger.info(f"Initiating CloudFormation stack deletion: {stack_info['stack_name']}")
                
                stack_deletion_result = await deployment_service.delete_stack(stack_info['stack_name'])
                
                deletion_result["cloudformation_deletion"] = {
                    "initiated": True,
                    "stack_name": stack_info['stack_name'],
                    "deletion_status": stack_deletion_result.get('status', 'initiated'),
                    "message": "CloudFormation stack deletion initiated - monitor via AWS console"
                }
                deletion_result["steps_completed"].append({
                    "step": "cloudformation_deletion_initiated",
                    "timestamp": datetime.utcnow().isoformat(),
                    "details": f"Stack '{stack_info['stack_name']}' deletion initiated"
                })
                
                logger.info(f"CloudFormation stack deletion initiated for: {stack_info['stack_name']}")
                
            except Exception as e:
                logger.error(f"Error deleting CloudFormation stack for agent '{agent_name}'")
                log_exception_safely(logger, e, "Error deleting CloudFormation stack")
                deletion_result["cloudformation_deletion"] = {
                    "initiated": False,
                    "error": "CloudFormation stack deletion failed"
                }
                deletion_result["steps_failed"].append({
                    "step": "cloudformation_deletion",
                    "error": "Stack deletion failed",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        # Step 3: Delete agent configuration
        try:
            logger.info(f"Deleting agent configuration for: {agent_name}")
            
            config_result = agent_service.delete_agent_configuration(agent_name)
            
            if config_result["status"] == "success":
                deletion_result["configuration_deletion"] = {
                    "success": True,
                    "message": config_result["message"],
                    "deleted_parameters": config_result.get("deleted_parameters", [])
                }
                deletion_result["steps_completed"].append({
                    "step": "configuration_deletion",
                    "timestamp": datetime.utcnow().isoformat(),
                    "details": f"Deleted {len(config_result.get('deleted_parameters', []))} SSM parameters"
                })
                
                logger.info(f"Agent configuration deleted successfully for: {agent_name}")
            elif config_result["status"] == "not_found":
                # Agent config not found - this might be expected if only deleting infrastructure
                deletion_result["configuration_deletion"] = {
                    "success": False,
                    "message": config_result["message"],
                    "not_found": True
                }
                deletion_result["steps_failed"].append({
                    "step": "configuration_deletion",
                    "error": f"Agent configuration not found: {config_result['message']}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "recoverable": True
                })
            else:
                raise Exception(f"Configuration deletion failed: {config_result['message']}")
                
        except Exception as e:
            logger.error(f"Error deleting agent configuration for '{agent_name}'")
            log_exception_safely(logger, e, "Error deleting agent configuration")
            deletion_result["configuration_deletion"] = {
                "success": False,
                "error": "Agent configuration deletion failed"
            }
            deletion_result["steps_failed"].append({
                "step": "configuration_deletion",
                "error": "Agent configuration deletion failed",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Determine overall status
        has_failures = len(deletion_result["steps_failed"]) > 0
        has_successes = len(deletion_result["steps_completed"]) > 0
        
        if has_failures and not has_successes:
            deletion_result["overall_status"] = "failed"
        elif has_failures and has_successes:
            deletion_result["overall_status"] = "partial_success"
        elif has_successes:
            deletion_result["overall_status"] = "success"
        else:
            deletion_result["overall_status"] = "no_actions_taken"
        
        # Add summary message
        if deletion_result["overall_status"] == "success":
            if include_infrastructure and stack_info:
                deletion_result["summary"] = f"Agent '{agent_name}' and its infrastructure are being deleted. CloudFormation stack deletion may take several minutes to complete."
            else:
                deletion_result["summary"] = f"Agent '{agent_name}' configuration deleted successfully."
        elif deletion_result["overall_status"] == "partial_success":
            deletion_result["summary"] = f"Agent '{agent_name}' partially deleted. Some operations failed - check details."
        else:
            deletion_result["summary"] = f"Failed to delete agent '{agent_name}'. Check error details."
        
        # Set appropriate HTTP status code - but be more lenient for deletion operations
        if deletion_result["overall_status"] == "failed":
            # Special handling: If only config not found but we have infrastructure to delete, treat as success
            config_only_not_found = (
                len(deletion_result["steps_failed"]) == 1 and
                any(step.get("recoverable") and "not found" in step.get("error", "").lower() 
                    for step in deletion_result["steps_failed"]) and
                include_infrastructure and stack_info  # We have infrastructure to delete
            )
            
            if config_only_not_found:
                # Config not found but we have infrastructure - change status to partial_success
                deletion_result["overall_status"] = "partial_success"
                deletion_result["summary"] = f"Agent '{agent_name}' infrastructure deletion initiated. No configuration found to delete (already clean)."
                logger.info(f"Treating config-not-found as partial success for agent '{agent_name}' since infrastructure deletion succeeded")
            else:
                # True failure - both config and infrastructure failed or no infrastructure requested
                raise HTTPException(status_code=500, detail=deletion_result["summary"])
        
        return deletion_result
        
    except HTTPException:
        http_exception_raised = True
        raise
    except Exception as e:
        logger.error("Error in complete agent deletion")
        log_exception_safely(logger, e, "Error in complete agent deletion")
        general_error = True
    
    # Raise HTTPException outside try/except to prevent stack trace exposure
    if general_error and not http_exception_raised:
        raise HTTPException(status_code=500, detail="Internal server error during deletion")


@config_router.get('/system-prompts/available/{agent_name}')
async def list_available_system_prompts(
    agent_name: str,
    current_user: UserInfo = Depends(get_current_user),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    Get list of available system prompts for dropdown selection.
    
    Args:
        agent_name: Name of the agent to get prompts for
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary containing available prompt names and descriptions
        
    Raises:
        HTTPException: If agent not found or operation fails
    """
    try:
        result = agent_service.list_system_prompts(agent_name)
        return result

    except ValueError as e:
        log_exception_safely(logger, e, "Validation error listing prompts")
        raise HTTPException(status_code=400, detail="Invalid system prompt request")
    except Exception as e:
        logger.error("Error listing available system prompts")
        log_exception_safely(logger, e, "Error listing available system prompts")
        raise HTTPException(status_code=404, detail="System prompts not found")


@config_router.get('/system-prompts/content/{agent_name}/{prompt_name}')
async def get_system_prompt_content(
    agent_name: str,
    prompt_name: str,
    current_user: UserInfo = Depends(get_current_user),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    Get system prompt content for preview/editing.
    
    Args:
        agent_name: Name of the agent
        prompt_name: Name of the system prompt
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary containing prompt content and metadata
        
    Raises:
        HTTPException: If prompt not found or operation fails
    """
    try:
        result = agent_service.get_system_prompt_content(agent_name, prompt_name)
        return result

    except ValueError as e:
        log_exception_safely(logger, e, "Validation error getting prompt content")
        raise HTTPException(status_code=400, detail="Invalid system prompt content request")
    except Exception as e:
        logger.error("Error getting system prompt content")
        log_exception_safely(logger, e, "Error getting system prompt content")
        raise HTTPException(status_code=404, detail="System prompt content not found")


@config_router.get('/system-prompts/templates')
async def list_system_prompt_templates(
    current_user: UserInfo = Depends(get_current_user),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    Get global system prompt templates that can be used across agents.
    
    Args:
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary containing global prompt templates
    """
    try:
        result = agent_service.list_global_prompt_templates()
        return result
        
    except Exception as e:
        logger.error("Error listing system prompt templates")
        log_exception_safely(logger, e, "Error listing system prompt templates")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@config_router.get('/system-prompts/all-across-agents')
async def list_all_system_prompts_across_agents(
    current_user: UserInfo = Depends(get_current_user),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, Any]:
    """
    Get all system prompts from all agents for cross-agent reusability during agent creation.
    
    Args:
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary containing all prompts grouped by agent source
    """
    try:
        result = agent_service.list_all_system_prompts_across_agents()
        if result.get("status") == "error":
            # Log the internal error detail safely, but do not expose it to the user
            log_exception_safely(logger, result.get("error", ""), "Error listing system prompts across agents (service returned error status)")
            raise HTTPException(status_code=500, detail="Internal server error occurred")
        return result
        
    except Exception as e:
        logger.error("Error listing system prompts across agents")
        log_exception_safely(logger, e, "Error listing system prompts across agents")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@config_router.post('/system-prompts/create/{agent_name}')
async def create_system_prompt(
    agent_name: str,
    prompt_data: Dict[str, str],
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:update")),
    agent_service: AgentConfigService = Depends(get_agent_config_service)
) -> Dict[str, str]:
    """
    Create a new system prompt for an agent.
    
    Args:
        agent_name: Name of the agent
        prompt_data: Dictionary containing prompt_name and prompt_content
        agent_service: Injected agent configuration service
        
    Returns:
        Dictionary with operation status
        
    Raises:
        HTTPException: If creation fails
    """
    try:
        prompt_name = prompt_data.get('prompt_name', '').strip()
        prompt_content = prompt_data.get('prompt_content', '').strip()
        
        if not prompt_name or not prompt_content:
            raise ValueError("Both prompt_name and prompt_content are required")
            
        result = agent_service.create_system_prompt(agent_name, prompt_name, prompt_content)
        return result

    except ValueError as e:
        log_exception_safely(logger, e, "Validation error creating system prompt")
        raise HTTPException(status_code=400, detail="Invalid system prompt creation request")
    except Exception as e:
        logger.error("Error creating system prompt")
        log_exception_safely(logger, e, "Error creating system prompt")
        raise HTTPException(status_code=500, detail="Internal server error occurred")


@config_router.post('/refresh-agent/{agent_name}')
async def refresh_agent_instances(
    agent_name: str,
    current_user: UserInfo = Depends(get_current_user),
    _: None = Depends(RequirePermission("config:update"))
) -> Dict[str, Any]:
    """
    Refresh specific agent instances by calling their /config/load endpoints.
    
    This endpoint discovers active agents running the specified agent configuration
    and calls their individual /config/load endpoints to force complete reinitialization.
    
    Args:
        agent_name: Name of the agent configuration to reload
        
    Returns:
        Dictionary with refresh results for matching agent instances
    """
    import httpx
    import os
    
    try:
        logger.info(f"Starting agent refresh for configuration '{agent_name}'")
        
        # Get discovered agent URLs from discovery service
        from ..services import DiscoveryService
        from ..utils.dependencies import get_discovery_service
        
        discovery_service = get_discovery_service()
        service_network_arn = os.environ.get('VPC_LATTICE_SERVICE_NETWORK_ARN')
        
        if not service_network_arn:
            # For local development, use mock services
            discovered_urls = [
                "http://agent-1:8080",
                "http://agent-2:8080"  
            ]
            logger.info("Using local development agent URLs")
        else:
            try:
                discovered_urls = discovery_service.get_service_https_urls(service_network_arn)
                logger.info(f"Discovered {len(discovered_urls)} agent URLs from VPC Lattice")
            except Exception as e:
                logger.warning("VPC Lattice discovery failed, using mock services")
                log_exception_safely(logger, e, "VPC Lattice discovery failed")
                discovered_urls = [
                    "http://agent-1:8080",
                    "http://agent-2:8080"
                ]
        
        # Track refresh results
        refresh_results = {}
        successful_refreshes = []
        failed_refreshes = []
        matching_agents_found = 0
        
        # Check each discovered agent to see if it matches our target agent name
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
            for agent_url in discovered_urls:
                try:
                    logger.info(f"Checking agent at {agent_url}")
                    
                    # First, get the agent's current name from /config/status
                    status_url = f"{agent_url.rstrip('/')}/config/status"
                    status_response = await client.get(status_url)
                    
                    if status_response.status_code != 200:
                        refresh_results[agent_url] = {
                            "status": "unreachable",
                            "message": "Cannot get agent status",
                            "checked": True,
                            "matches_target": False
                        }
                        failed_refreshes.append({"url": agent_url, "reason": "status check failed"})
                        continue
                    
                    status_data = status_response.json()
                    current_agent_name = status_data.get('agent', {}).get('name', 'unknown_agent')
                    
                    logger.info(f"Agent at {agent_url} reports name: '{current_agent_name}'")
                    
                    # Check if this agent matches our target
                    if current_agent_name == agent_name:
                        matching_agents_found += 1
                        logger.info(f"✅ Found matching agent '{agent_name}' at {agent_url}, triggering refresh")
                        
                        # Call the agent's /config/load endpoint with its own name  
                        load_url = f"{agent_url.rstrip('/')}/config/load"
                        load_payload = {"config_name": agent_name}
                        
                        response = await client.post(load_url, json=load_payload)
                        
                        if response.status_code == 200:
                            response_data = response.json()
                            refresh_results[agent_url] = {
                                "status": "success",
                                "agent_name": current_agent_name,
                                "message": f"Agent '{agent_name}' refreshed successfully",
                                "checked": True,
                                "matches_target": True,
                                "agent_response": response_data,
                                "timestamp": response_data.get("timestamp", "unknown")
                            }
                            successful_refreshes.append(agent_url)
                            logger.info(f"✅ Successfully refreshed agent '{agent_name}' at {agent_url}")
                            
                        else:
                            refresh_results[agent_url] = {
                                "status": "error",
                                "agent_name": current_agent_name,
                                "message": f"Agent '{agent_name}' refresh failed",
                                "checked": True,
                                "matches_target": True,
                                "timestamp": None
                            }
                            failed_refreshes.append({"url": agent_url, "reason": "refresh failed"})
                            logger.error(f"❌ Agent '{agent_name}' at {agent_url} refresh failed")
                    else:
                        # Agent doesn't match, skip it
                        refresh_results[agent_url] = {
                            "status": "skipped",
                            "agent_name": current_agent_name,
                            "message": f"Agent name '{current_agent_name}' does not match target '{agent_name}', skipped",
                            "checked": True,
                            "matches_target": False
                        }
                        logger.info(f"⏭️ Agent '{current_agent_name}' at {agent_url} does not match target '{agent_name}', skipped")
                        
                except httpx.TimeoutException as e:
                    log_exception_safely(logger, e, f"Timeout checking agent at {agent_url}")
                    refresh_results[agent_url] = {
                        "status": "timeout",
                        "message": "Agent request timed out",
                        "checked": False,
                        "matches_target": False,
                        "error": "Request timeout after 30 seconds"
                    }
                    failed_refreshes.append({"url": agent_url, "reason": "timeout"})
                    logger.error(f"⏰ Agent at {agent_url} timed out")
                    
                except httpx.RequestError as e:
                    log_exception_safely(logger, e, f"Request error checking agent at {agent_url}")
                    refresh_results[agent_url] = {
                        "status": "unreachable",
                        "message": "Agent is unreachable",
                        "checked": False,
                        "matches_target": False,
                        "error": "Agent unreachable"
                    }
                    failed_refreshes.append({"url": agent_url, "reason": "network error"})
                    logger.error(f"Agent at {agent_url} is unreachable")
                    
                except Exception as e:
                    log_exception_safely(logger, e, f"Unexpected error checking agent at {agent_url}")
                    refresh_results[agent_url] = {
                        "status": "error",
                        "message": "Unexpected error during agent check",
                        "checked": False,
                        "matches_target": False,
                        "error": "Unexpected agent check error"
                    }
                    failed_refreshes.append({"url": agent_url, "reason": "unexpected error"})
                    logger.error(f"Unexpected error checking agent at {agent_url}")
        
        # Build summary response
        summary = {
            "target_agent_name": agent_name,
            "total_agents_discovered": len(discovered_urls),
            "matching_agents_found": matching_agents_found,
            "successful_refreshes": len(successful_refreshes),
            "failed_refresh_count": len([f for f in failed_refreshes if f.get("reason", "").startswith("refresh failed")]),
            "successful_agent_urls": successful_refreshes,
            "failed_refreshes": failed_refreshes,
            "refresh_results": refresh_results,
            "discovery_source": "vpc_lattice" if service_network_arn else "local_mock"
        }
        
        if matching_agents_found == 0:
            logger.warning(f"No active agents found running configuration '{agent_name}'")
            return {
                "status": "no_matches",
                "message": f"No active agents found running configuration '{agent_name}'. The configuration may not be deployed or agents may be offline.",
                "summary": summary
            }
        elif len(successful_refreshes) == matching_agents_found:
            logger.info(f"All {matching_agents_found} agents running '{agent_name}' refreshed successfully")
            return {
                "status": "success",
                "message": f"Successfully refreshed {len(successful_refreshes)} agent instance(s) running configuration '{agent_name}'",
                "summary": summary
            }
        else:
            logger.warning(f"Partial success: {len(successful_refreshes)}/{matching_agents_found} agents refreshed for '{agent_name}'")
            return {
                "status": "partial_success", 
                "message": f"Partially successful: {len(successful_refreshes)}/{matching_agents_found} agent instance(s) running configuration '{agent_name}' were refreshed",
                "summary": summary
            }
        
    except Exception as e:
        logger.error(f"Unexpected error in refresh_agent_instances for '{agent_name}'")
        log_exception_safely(logger, e, f"Error refreshing agent instances for {agent_name}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during agent refresh"
        )
