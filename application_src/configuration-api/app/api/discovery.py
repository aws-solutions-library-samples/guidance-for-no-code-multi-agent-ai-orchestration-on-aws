"""
Service discovery API routes.

This module provides VPC Lattice service discovery endpoints.
"""

import os
import httpx
from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException, Depends

from ..services import DiscoveryService
from ..utils.dependencies import get_discovery_service
from ..middleware.auth_middleware import get_current_user

import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../'))
from common.auth import UserInfo
from common.secure_logging_utils import SecureLogger, log_exception_safely

import logging
logger = logging.getLogger(__name__)

discovery_router = APIRouter()


@discovery_router.get('/discover', response_model=List[str])
async def discover_dns(
    current_user: UserInfo = Depends(get_current_user),
    discovery_service: DiscoveryService = Depends(get_discovery_service)
) -> List[str]:
    """
    Discover DNS entries from VPC Lattice Service Network associations.
    Requires authentication for external API access.
    
    Returns:
        List of HTTP URLs for discovered services
        
    Raises:
        HTTPException: If service network ARN is missing or discovery fails
    """
    return await _internal_discover_dns(discovery_service)


@discovery_router.get('/internal/discover', response_model=List[str])
async def internal_discover_dns(
    discovery_service: DiscoveryService = Depends(get_discovery_service)
) -> List[str]:
    """
    Internal service discovery endpoint for service-to-service calls.
    Does not require authentication as it's intended for startup/internal use only.
    
    Returns:
        List of HTTP URLs for discovered services
        
    Raises:
        HTTPException: If service network ARN is missing or discovery fails
    """
    return await _internal_discover_dns(discovery_service)


async def _internal_discover_dns(discovery_service: DiscoveryService) -> List[str]:
    """
    Shared discovery logic for both authenticated and internal endpoints.
    """
    try:
        # Get the service network ARN from environment variable
        service_network_arn = os.environ.get('VPC_LATTICE_SERVICE_NETWORK_ARN')
        
        if not service_network_arn:
            # For local development, return environment-based URLs
            environment = os.environ.get('ENVIRONMENT', 'development')
            
            if environment == 'production':
                # In production without VPC Lattice, return empty list to force proper configuration
                return []
            else:
                # Development/staging environment - use docker-compose service names
                mock_services = [
                    "http://agent-1:9001",  # Updated to match actual ports
                    "http://agent-2:9002"
                ]
                return mock_services
        
        # Retrieve HTTP URLs from service network associations
        http_urls = discovery_service.get_service_https_urls(service_network_arn)
        
        return http_urls
        
    except HTTPException:
        raise
    except Exception as e:
        # Handle VPC Lattice errors based on environment
        environment = os.environ.get('ENVIRONMENT', 'development')
        
        if environment == 'production':
            # In production, log the error and return empty list
            logger.error("VPC Lattice discovery failed in production")
            log_exception_safely(logger, e, "VPC Lattice discovery failed in production")
            return []
        else:
            # Development/staging fallback
            mock_services = [
                "http://agent-1:9001",
                "http://agent-2:9002"
            ]
            return mock_services


@discovery_router.get('/agent-card/{agent_url:path}', response_model=Dict[str, Any])
async def get_agent_card(
    agent_url: str,
    current_user: UserInfo = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Fetch agent card information from /.well-known/agent-card.json endpoint.
    
    This endpoint acts as a proxy to avoid CORS issues when the UI calls
    the agent's /.well-known/agent-card.json endpoint directly.
    
    Args:
        agent_url: The base URL of the agent (URL encoded)
        
    Returns:
        Dictionary containing agent card information including skills
        
    Raises:
        HTTPException: If agent card fetch fails
    """
    try:
        # Decode the URL (FastAPI path parameters are URL encoded)
        import urllib.parse
        decoded_agent_url = urllib.parse.unquote(agent_url)
        
        # Construct the agent card URL
        agent_card_url = f"{decoded_agent_url.rstrip('/')}/.well-known/agent-card.json"
        
        # Fetch the agent card information
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            response = await client.get(agent_card_url)
            
            if response.status_code == 200:
                agent_card_data = response.json()
                return {
                    "success": True,
                    "agent_url": decoded_agent_url,
                    "agent_card": agent_card_data,
                    "fetched_at": __import__('datetime').datetime.now().isoformat()
                }
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Agent card endpoint returned {response.status_code}: {response.text}"
                )
                
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=408,
            detail="Timeout while fetching agent card information"
        )
    except httpx.RequestError as e:
        logger.error("Failed to connect to agent")
        log_exception_safely(logger, e, "Failed to connect to agent")
        raise HTTPException(
            status_code=503,
            detail="Failed to connect to agent"
        )
    except Exception as e:
        logger.error("Failed to fetch agent card")
        log_exception_safely(logger, e, "Failed to fetch agent card")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch agent card"
        )


@discovery_router.get('/agent-mapping', response_model=Dict[str, Any])
async def get_agent_mapping(
    current_user: UserInfo = Depends(get_current_user),
    discovery_service: DiscoveryService = Depends(get_discovery_service)
) -> Dict[str, Any]:
    """
    Get mapping between discovered agent URLs and their actual agent names.
    
    This endpoint calls /config/status on each discovered agent to fetch
    the agent name and other details.
    
    Returns:
        Dictionary containing mapping of agent URLs to agent information
        
    Raises:
        HTTPException: If discovery or agent communication fails
    """
    try:
        # First, discover all available agent URLs
        service_network_arn = os.environ.get('VPC_LATTICE_SERVICE_NETWORK_ARN')
        
        if not service_network_arn:
            # For local development, use mock services
            discovered_urls = [
                "http://agent-1:8080",
                "http://agent-2:8080"
            ]
        else:
            try:
                discovered_urls = discovery_service.get_service_https_urls(service_network_arn)
            except Exception:
                # Fallback to mock services on discovery failure
                discovered_urls = [
                    "http://agent-1:8080",
                    "http://agent-2:8080"
                ]
        
        agent_mapping = {}
        successful_agents = []
        failed_agents = []
        
        # For each discovered URL, try to fetch agent information
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            for agent_url in discovered_urls:
                try:
                    # Call the agent's /config/status endpoint
                    status_url = f"{agent_url.rstrip('/')}/config/status"
                    response = await client.get(status_url)
                    
                    if response.status_code == 200:
                        status_data = response.json()
                        
                        # Extract agent information from the status response
                        agent_info = status_data.get('agent', {})
                        agent_name = agent_info.get('name', 'Unknown Agent')
                        agent_description = agent_info.get('description', 'No description available')
                        
                        # Store the mapping
                        agent_mapping[agent_url] = {
                            "agent_name": agent_name,
                            "agent_description": agent_description,
                            "status": "active",
                            "tools_count": agent_info.get('tools_count', 0),
                            "streaming_enabled": agent_info.get('streaming_enabled', False),
                            "uptime_seconds": agent_info.get('uptime_seconds', 0),
                            "last_updated": status_data.get('timestamp', 'Unknown')
                        }
                        
                        successful_agents.append(agent_url)
                        
                    else:
                        # Agent responded but with error status
                        agent_mapping[agent_url] = {
                            "agent_name": "Unknown Agent",
                            "agent_description": "Agent unavailable",
                            "status": "error",
                            "error": f"HTTP {response.status_code}",
                            "last_updated": None
                        }
                        failed_agents.append({"url": agent_url, "reason": f"HTTP {response.status_code}"})
                        
                except httpx.TimeoutException:
                    # Timeout calling agent
                    agent_mapping[agent_url] = {
                        "agent_name": "Unknown Agent",
                        "agent_description": "Agent timeout",
                        "status": "timeout",
                        "error": "Request timeout",
                        "last_updated": None
                    }
                    failed_agents.append({"url": agent_url, "reason": "timeout"})
                    
                except httpx.RequestError as e:
                    # Network or connection error
                    logger.warning(f"Agent unreachable at {agent_url}")
                    log_exception_safely(logger, e, f"Agent unreachable at {agent_url}")
                    agent_mapping[agent_url] = {
                        "agent_name": "Unknown Agent", 
                        "agent_description": "Agent unreachable",
                        "status": "unreachable",
                        "error": "Connection error",
                        "last_updated": None
                    }
                    failed_agents.append({"url": agent_url, "reason": "connection_error"})
                    
                except Exception as e:
                    # Other unexpected errors
                    logger.warning(f"Error communicating with agent at {agent_url}")
                    log_exception_safely(logger, e, f"Error communicating with agent at {agent_url}")
                    agent_mapping[agent_url] = {
                        "agent_name": "Unknown Agent",
                        "agent_description": "Agent error", 
                        "status": "error",
                        "error": "Communication error",
                        "last_updated": None
                    }
                    failed_agents.append({"url": agent_url, "reason": "communication_error"})
        
        return {
            "agent_mapping": agent_mapping,
            "summary": {
                "total_discovered": len(discovered_urls),
                "successful_connections": len(successful_agents), 
                "failed_connections": len(failed_agents),
                "discovered_urls": discovered_urls,
                "successful_agents": successful_agents,
                "failed_agents": failed_agents
            },
            "discovery_source": "vpc_lattice" if service_network_arn else "local_mock"
        }
        
    except Exception as e:
        logger.error("Failed to create agent mapping")
        log_exception_safely(logger, e, "Failed to create agent mapping")
        raise HTTPException(
            status_code=500, 
            detail="Failed to create agent mapping"
        )
