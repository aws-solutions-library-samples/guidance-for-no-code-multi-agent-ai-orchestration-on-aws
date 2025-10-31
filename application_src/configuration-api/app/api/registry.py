"""
Service Registry API routes.

This module provides centralized endpoint discovery and documentation
for all services in the GenAI-in-a-Box application.
"""

import asyncio
import httpx
import os
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from common.secure_logging_utils import SecureLogger, log_exception_safely

logger = logging.getLogger(__name__)
registry_router = APIRouter()


class EndpointInfo(BaseModel):
    """Model for endpoint information."""
    path: str
    method: str
    description: str
    tags: Optional[List[str]] = None
    parameters: Optional[Dict[str, Any]] = None
    responses: Optional[Dict[str, Any]] = None


class ServiceInfo(BaseModel):
    """Model for service information."""
    name: str
    url: str
    port: int
    status: str
    endpoints: List[EndpointInfo]
    openapi_url: Optional[str] = None
    docs_url: Optional[str] = None
    last_checked: str
    error: Optional[str] = None


class ServiceRegistry:
    """Service registry for discovering and documenting all API endpoints."""
    
    def __init__(self):
        self.services = []
        self.timeout = httpx.Timeout(3.0)  # Further reduced timeout
        self.cache = {}
        self.cache_ttl = 120  # Cache for 2 minutes to reduce load
        self.last_discovery_time = 0
    
    async def discover_services(self) -> List[ServiceInfo]:
        """
        Discover all services and their endpoints with caching to reduce load.
        
        Returns:
            List of ServiceInfo objects with endpoint details
        """
        import time
        current_time = time.time()
        
        # Return cached results if still valid
        if (current_time - self.last_discovery_time) < self.cache_ttl and self.cache:
            return self.cache.get('services', [])
        
        # Define known services based on docker-compose.yml with configurable project name
        project_name = os.environ.get('PROJECT_NAME', 'genai-box')
        ui_container_name = f"{project_name}-ui-react"
        
        known_services = [
            {
                "name": "Configuration API",
                "url": "http://configuration-api:8000",
                "port": 8000,
                "external_url": "http://localhost:8000",
                "type": "fastapi"
            },
            {
                "name": "Agent Instance 1 (QA Agent)",
                "url": "http://agent-1:8080",
                "port": 9001,  # External port
                "external_url": "http://localhost:9001",
                "type": "agent"
            },
            {
                "name": "Agent Instance 2 (QA Agent 2)",
                "url": "http://agent-2:8080",
                "port": 9002,  # External port
                "external_url": "http://localhost:9002",
                "type": "agent"
            },
            {
                "name": "Supervisor Agent",
                "url": "http://supervisor-agent:9003",
                "port": 9003,
                "external_url": "http://localhost:9003",
                "type": "fastapi"
            },
            {
                "name": "React UI Backend",
                "url": f"http://{ui_container_name}:3001",
                "port": 3001,
                "external_url": "http://localhost:3001",
                "type": "express"
            },
            {
                "name": "React UI Frontend", 
                "url": f"http://{ui_container_name}:3000",
                "port": 3000,
                "external_url": "http://localhost:3000",
                "type": "react"
            }
        ]
        
        discovered_services = []
        
        # Check each known service
        for service_config in known_services:
            service_info = await self._check_service(service_config)
            discovered_services.append(service_info)
        
        # Also check for dynamically discovered services from VPC Lattice
        try:
            vpc_services = await self._discover_vpc_lattice_services()
            discovered_services.extend(vpc_services)
        except Exception as e:
            log_exception_safely(logger, "Warning: Could not discover VPC Lattice services", e)
        
        # Cache the results and update discovery time
        self.cache['services'] = discovered_services
        self.last_discovery_time = current_time
        
        return discovered_services
    
    async def _check_service(self, service_config: Dict[str, Any]) -> ServiceInfo:
        """
        Check a specific service and discover its endpoints.
        
        Args:
            service_config: Service configuration dictionary
            
        Returns:
            ServiceInfo object with endpoint details
        """
        service_name = service_config["name"]
        service_url = service_config["url"]
        external_url = service_config.get("external_url", service_url)
        service_port = service_config["port"]
        service_type = service_config.get("type", "unknown")
        
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Check if service is running
                health_endpoints = ["/health", "/", "/api/health"]
                service_available = False
                
                for health_endpoint in health_endpoints:
                    try:
                        response = await client.get(f"{service_url}{health_endpoint}")
                        if response.status_code == 200:
                            service_available = True
                            break
                    except:
                        continue
                
                if not service_available:
                    return ServiceInfo(
                        name=service_name,
                        url=external_url,
                        port=service_port,
                        status="unreachable",
                        endpoints=[],
                        last_checked=now,
                        error="Service not responding to health checks"
                    )
                
                # Try to get OpenAPI documentation
                endpoints = []
                openapi_url = None
                docs_url = None
                
                if service_type == "fastapi":
                    endpoints, openapi_url, docs_url = await self._discover_fastapi_endpoints(
                        client, service_url, external_url
                    )
                elif service_type == "agent":
                    endpoints = await self._discover_agent_endpoints(
                        client, service_url, external_url
                    )
                elif service_type == "express":
                    endpoints = await self._discover_express_endpoints(
                        client, service_url, external_url
                    )
                elif service_type == "react":
                    endpoints = await self._discover_react_endpoints(
                        client, service_url, external_url
                    )
                
                return ServiceInfo(
                    name=service_name,
                    url=external_url,
                    port=service_port,
                    status="active",
                    endpoints=endpoints,
                    openapi_url=openapi_url,
                    docs_url=docs_url,
                    last_checked=now
                )
                
        except Exception as e:
            return ServiceInfo(
                name=service_name,
                url=external_url,
                port=service_port,
                status="error",
                endpoints=[],
                last_checked=now,
                error="Service connection failed"
            )
    
    async def _discover_fastapi_endpoints(
        self, 
        client: httpx.AsyncClient, 
        service_url: str, 
        external_url: str
    ) -> tuple[List[EndpointInfo], Optional[str], Optional[str]]:
        """Discover FastAPI endpoints using OpenAPI spec."""
        endpoints = []
        openapi_url = None
        docs_url = None
        
        try:
            # Try to get OpenAPI spec
            openapi_response = await client.get(f"{service_url}/openapi.json")
            if openapi_response.status_code == 200:
                openapi_spec = openapi_response.json()
                openapi_url = f"{external_url}/openapi.json"
                docs_url = f"{external_url}/docs"
                
                # Parse endpoints from OpenAPI spec
                paths = openapi_spec.get("paths", {})
                for path, methods in paths.items():
                    for method, details in methods.items():
                        if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                            endpoint = EndpointInfo(
                                path=path,
                                method=method.upper(),
                                description=details.get("description", details.get("summary", "")),
                                tags=details.get("tags", []),
                                parameters=details.get("parameters", {}),
                                responses=details.get("responses", {})
                            )
                            endpoints.append(endpoint)
            else:
                # Fallback to common FastAPI endpoints
                endpoints = await self._discover_common_endpoints(client, service_url)
                
        except Exception:
            # Fallback to common endpoints
            endpoints = await self._discover_common_endpoints(client, service_url)
        
        return endpoints, openapi_url, docs_url
    
    async def _discover_agent_endpoints(
        self, 
        client: httpx.AsyncClient, 
        service_url: str, 
        external_url: str
    ) -> List[EndpointInfo]:
        """Discover agent-specific endpoints."""
        endpoints = []
        
        # Common agent endpoints
        agent_endpoints = [
            {"path": "/", "method": "GET", "description": "Root endpoint with agent information"},
            {"path": "/health", "method": "GET", "description": "Health check endpoint"},
            {"path": "/agent", "method": "POST", "description": "Agent interaction endpoint"},
            {"path": "/agent-streaming", "method": "POST", "description": "Streaming agent responses"},
            {"path": "/.well-known/agent-card.json", "method": "GET", "description": "A2A agent card for discovery"},
            {"path": "/config/status", "method": "GET", "description": "Agent configuration status"},
            {"path": "/config/load", "method": "POST", "description": "Load specific agent configuration"},
        ]
        
        for endpoint_def in agent_endpoints:
            try:
                response = await client.request(
                    endpoint_def["method"], 
                    f"{service_url}{endpoint_def['path']}"
                )
                if response.status_code < 500:  # Endpoint exists
                    endpoints.append(EndpointInfo(**endpoint_def))
            except:
                # Try to add it anyway for documentation
                endpoints.append(EndpointInfo(**endpoint_def))
        
        return endpoints
    
    async def _discover_express_endpoints(
        self, 
        client: httpx.AsyncClient, 
        service_url: str, 
        external_url: str
    ) -> List[EndpointInfo]:
        """Discover Express.js endpoints."""
        endpoints = []
        
        # Common Express endpoints based on server.js
        express_endpoints = [
            {"path": "/api/health", "method": "GET", "description": "Health check endpoint"},
            {"path": "/api/config/agents", "method": "GET", "description": "Get list of agents"},
            {"path": "/api/config/agent/:agentName", "method": "GET", "description": "Get specific agent config"},
            {"path": "/api/config/agent", "method": "POST", "description": "Save agent configuration"},
            {"path": "/api/config/save", "method": "POST", "description": "Save agent configuration (direct)"},
            {"path": "/api/form-schema/components", "method": "GET", "description": "Get form schema components"},
            {"path": "/api/form-schema/components/:componentType", "method": "GET", "description": "Get form schema for component type"},
            {"path": "/api/form-schema/providers/:componentType", "method": "GET", "description": "Get providers for component type"},
            {"path": "/api/config/discover", "method": "GET", "description": "Discover services"},
            {"path": "/api/config/agent-mapping", "method": "GET", "description": "Get agent mapping"},
            {"path": "/api/agent/chat", "method": "POST", "description": "Chat with supervisor agent (streaming)"},
            {"path": "/api/agent/chat-sync", "method": "POST", "description": "Chat with supervisor agent (sync)"},
            {"path": "/api/auth/cognito-config", "method": "GET", "description": "Get Cognito configuration"},
        ]
        
        for endpoint_def in express_endpoints:
            endpoints.append(EndpointInfo(**endpoint_def))
        
        return endpoints
    
    async def _discover_react_endpoints(
        self, 
        client: httpx.AsyncClient, 
        service_url: str, 
        external_url: str
    ) -> List[EndpointInfo]:
        """Discover React frontend endpoints."""
        endpoints = [
            EndpointInfo(
                path="/",
                method="GET",
                description="React application root"
            ),
            EndpointInfo(
                path="/agents",
                method="GET", 
                description="Agent management interface"
            ),
            EndpointInfo(
                path="/chat",
                method="GET",
                description="Agent chat interface"
            ),
        ]
        
        return endpoints
    
    async def _discover_common_endpoints(
        self, 
        client: httpx.AsyncClient, 
        service_url: str
    ) -> List[EndpointInfo]:
        """Discover common endpoints by probing."""
        endpoints = []
        common_paths = [
            {"path": "/", "method": "GET", "description": "Root endpoint"},
            {"path": "/health", "method": "GET", "description": "Health check"},
            {"path": "/docs", "method": "GET", "description": "API documentation"},
            {"path": "/redoc", "method": "GET", "description": "ReDoc documentation"},
        ]
        
        for endpoint_def in common_paths:
            try:
                response = await client.request(
                    endpoint_def["method"], 
                    f"{service_url}{endpoint_def['path']}"
                )
                if response.status_code < 500:
                    endpoints.append(EndpointInfo(**endpoint_def))
            except:
                continue
        
        return endpoints
    
    async def _discover_vpc_lattice_services(self) -> List[ServiceInfo]:
        """Discover services from VPC Lattice (if configured)."""
        # This would integrate with the existing discovery service
        # For now, return empty list
        return []


# Initialize registry
service_registry = ServiceRegistry()


@registry_router.get('/registry/services', response_model=List[ServiceInfo])
async def get_service_registry():
    """
    Get comprehensive service registry with all discovered endpoints.
    
    Returns:
        List of services with their endpoints and status
    """
    try:
        services = await service_registry.discover_services()
        return services
    except Exception as e:
        log_exception_safely(logger, "Failed to discover services", e)
        raise HTTPException(
            status_code=500, 
            detail="Failed to discover services"
        )


@registry_router.get('/registry/summary')
async def get_registry_summary():
    """
    Get a summary of all services and endpoint counts.
    
    Returns:
        Summary statistics of the service registry
    """
    try:
        services = await service_registry.discover_services()
        
        total_services = len(services)
        active_services = len([s for s in services if s.status == "active"])
        total_endpoints = sum(len(s.endpoints) for s in services)
        
        services_by_status = {}
        for service in services:
            status = service.status
            if status not in services_by_status:
                services_by_status[status] = []
            services_by_status[status].append(service.name)
        
        return {
            "total_services": total_services,
            "active_services": active_services,
            "total_endpoints": total_endpoints,
            "services_by_status": services_by_status,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "services": [
                {
                    "name": service.name,
                    "url": service.url,
                    "status": service.status,
                    "endpoint_count": len(service.endpoints),
                    "docs_url": service.docs_url
                }
                for service in services
            ]
        }
    except Exception as e:
        log_exception_safely(logger, "Failed to generate registry summary", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to generate registry summary"
        )


@registry_router.get('/registry/endpoints')
async def get_all_endpoints():
    """
    Get a flat list of all endpoints across all services.
    
    Returns:
        Flat list of all endpoints with service information
    """
    try:
        services = await service_registry.discover_services()
        
        all_endpoints = []
        for service in services:
            for endpoint in service.endpoints:
                all_endpoints.append({
                    "service_name": service.name,
                    "service_url": service.url,
                    "service_status": service.status,
                    "path": endpoint.path,
                    "method": endpoint.method,
                    "description": endpoint.description,
                    "tags": endpoint.tags,
                    "full_url": f"{service.url}{endpoint.path}"
                })
        
        return {
            "total_endpoints": len(all_endpoints),
            "endpoints": all_endpoints,
            "last_updated": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        log_exception_safely(logger, "Failed to get all endpoints", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to get all endpoints"
        )


@registry_router.get('/registry/services/{service_name}')
async def get_service_details(service_name: str):
    """
    Get detailed information about a specific service.
    
    Args:
        service_name: Name of the service to get details for
        
    Returns:
        Detailed service information
    """
    try:
        services = await service_registry.discover_services()
        
        # Find service by name (case-insensitive)
        matching_service = None
        for service in services:
            if service.name.lower() == service_name.lower():
                matching_service = service
                break
        
        if not matching_service:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_name}' not found"
            )
        
        return matching_service
    except HTTPException:
        raise
    except Exception as e:
        log_exception_safely(logger, "Failed to get service details", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to get service details"
        )


@registry_router.get('/registry', response_class=HTMLResponse)
async def get_service_registry_html():
    """
    Get a web-based service registry interface showing all endpoints.
    
    Returns:
        HTML page with interactive service registry
    """
    try:
        services = await service_registry.discover_services()
        
        # Generate HTML with modern styling
        project_name = os.environ.get('PROJECT_NAME', 'genai-box')
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{project_name.title()} Service Registry</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
            color: white;
            padding: 30px 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        }}
        
        .header p {{
            font-size: 1.2em;
            opacity: 0.9;
        }}
        
        .stats {{
            background: #f8f9fa;
            padding: 20px 40px;
            border-bottom: 1px solid #e9ecef;
            display: flex;
            justify-content: space-around;
            flex-wrap: wrap;
        }}
        
        .stat-item {{
            text-align: center;
            margin: 10px;
        }}
        
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #4facfe;
        }}
        
        .stat-label {{
            font-size: 0.9em;
            color: #6c757d;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .service-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 25px;
            margin-bottom: 40px;
        }}
        
        .service-card {{
            border: 1px solid #e9ecef;
            border-radius: 10px;
            overflow: hidden;
            transition: all 0.3s ease;
            background: white;
        }}
        
        .service-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
        }}
        
        .service-header {{
            padding: 20px;
            border-bottom: 1px solid #e9ecef;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        .service-name {{
            font-size: 1.3em;
            font-weight: bold;
            color: #2c3e50;
        }}
        
        .service-status {{
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: bold;
            text-transform: uppercase;
        }}
        
        .status-active {{
            background: #d4edda;
            color: #155724;
        }}
        
        .status-unreachable {{
            background: #f8d7da;
            color: #721c24;
        }}
        
        .status-error {{
            background: #fff3cd;
            color: #856404;
        }}
        
        .service-info {{
            padding: 15px 20px;
            background: #f8f9fa;
            font-size: 0.9em;
            color: #6c757d;
        }}
        
        .endpoints {{
            padding: 20px;
        }}
        
        .endpoint {{
            display: flex;
            align-items: center;
            padding: 12px 0;
            border-bottom: 1px solid #f1f3f4;
        }}
        
        .endpoint:last-child {{
            border-bottom: none;
        }}
        
        .method {{
            width: 70px;
            text-align: center;
            font-size: 0.8em;
            font-weight: bold;
            padding: 4px 8px;
            border-radius: 4px;
            margin-right: 15px;
        }}
        
        .method-get {{
            background: #e3f2fd;
            color: #1565c0;
        }}
        
        .method-post {{
            background: #e8f5e8;
            color: #2e7d32;
        }}
        
        .method-put {{
            background: #fff3e0;
            color: #ef6c00;
        }}
        
        .method-delete {{
            background: #ffebee;
            color: #c62828;
        }}
        
        .endpoint-path {{
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            flex: 1;
            color: #2c3e50;
        }}
        
        .endpoint-description {{
            color: #6c757d;
            font-size: 0.85em;
            margin-left: 15px;
            flex: 2;
        }}
        
        .quick-links {{
            background: #f8f9fa;
            padding: 30px 40px;
            border-top: 1px solid #e9ecef;
        }}
        
        .quick-links h3 {{
            margin-bottom: 20px;
            color: #2c3e50;
        }}
        
        .links-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}
        
        .link-card {{
            background: white;
            border: 1px solid #e9ecef;
            border-radius: 8px;
            padding: 15px;
            text-align: center;
            text-decoration: none;
            color: #2c3e50;
            transition: all 0.3s ease;
        }}
        
        .link-card:hover {{
            background: #4facfe;
            color: white;
            text-decoration: none;
            transform: translateY(-2px);
        }}
        
        .refresh-button {{
            position: fixed;
            bottom: 30px;
            right: 30px;
            background: #4facfe;
            color: white;
            border: none;
            padding: 15px 20px;
            border-radius: 50px;
            cursor: pointer;
            font-size: 1em;
            box-shadow: 0 5px 15px rgba(79, 172, 254, 0.4);
            transition: all 0.3s ease;
        }}
        
        .refresh-button:hover {{
            background: #3498db;
            transform: translateY(-2px);
            box-shadow: 0 8px 20px rgba(79, 172, 254, 0.6);
        }}
        
        .last-updated {{
            text-align: center;
            color: #6c757d;
            font-size: 0.9em;
            margin-top: 30px;
        }}
        
        @media (max-width: 768px) {{
            .service-grid {{
                grid-template-columns: 1fr;
            }}
            
            .stats {{
                flex-direction: column;
            }}
            
            .endpoint {{
                flex-direction: column;
                align-items: flex-start;
            }}
            
            .method {{
                margin-bottom: 8px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 GenAI-in-a-Box Service Registry</h1>
            <p>Centralized API endpoint discovery and documentation</p>
        </div>
        
        <div class="stats">
            <div class="stat-item">
                <div class="stat-number">{len(services)}</div>
                <div class="stat-label">Services</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{len([s for s in services if s.status == 'active'])}</div>
                <div class="stat-label">Active</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{sum(len(s.endpoints) for s in services)}</div>
                <div class="stat-label">Endpoints</div>
            </div>
            <div class="stat-item">
                <div class="stat-number">{len([s for s in services if s.docs_url])}</div>
                <div class="stat-label">API Docs</div>
            </div>
        </div>
        
        <div class="content">
            <div class="service-grid">
        """
        
        # Generate service cards
        for service in services:
            status_class = f"status-{service.status}"
            
            html_content += f"""
                <div class="service-card">
                    <div class="service-header">
                        <div class="service-name">{service.name}</div>
                        <div class="service-status {status_class}">{service.status}</div>
                    </div>
                    <div class="service-info">
                        <strong>URL:</strong> <a href="{service.url}" target="_blank">{service.url}</a><br>
                        <strong>Port:</strong> {service.port}<br>
                        <strong>Endpoints:</strong> {len(service.endpoints)}
                        {f'<br><strong>API Docs:</strong> <a href="{service.docs_url}" target="_blank">View Docs</a>' if service.docs_url else ''}
                        {f'<br><strong>Error:</strong> {service.error}' if service.error else ''}
                    </div>
                    <div class="endpoints">
            """
            
            # Add endpoints
            for endpoint in service.endpoints:
                method_class = f"method-{endpoint.method.lower()}"
                html_content += f"""
                        <div class="endpoint">
                            <div class="method {method_class}">{endpoint.method}</div>
                            <div class="endpoint-path">{endpoint.path}</div>
                            <div class="endpoint-description">{endpoint.description}</div>
                        </div>
                """
            
            html_content += """
                    </div>
                </div>
            """
        
        # Quick links section
        html_content += f"""
            </div>
        </div>
        
        <div class="quick-links">
            <h3>🔗 Quick Links</h3>
            <div class="links-grid">
                <a href="/registry/summary" class="link-card">
                    📊 Registry Summary
                </a>
                <a href="/registry/endpoints" class="link-card">
                    📋 All Endpoints
                </a>
                <a href="/registry/services" class="link-card">
                    🔧 Services JSON
                </a>
                <a href="/docs" class="link-card">
                    📖 API Documentation
                </a>
                <a href="/agent-mapping" class="link-card">
                    🗺️ Agent Mapping
                </a>
                <a href="/discover" class="link-card">
                    🔍 Service Discovery
                </a>
            </div>
        </div>
        
        <div class="last-updated">
            Last updated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
    </div>
    
    <button class="refresh-button" onclick="window.location.reload()">
        🔄 Refresh
    </button>
    
    <script>
        // Auto-refresh every 5 minutes to reduce load on agent instances
        setInterval(function() {{
            window.location.reload();
        }}, 300000);
        
        // Add click handlers for external links
        document.querySelectorAll('a[href^="http"]').forEach(link => {{
            link.addEventListener('click', function(e) {{
                e.preventDefault();
                window.open(this.href, '_blank');
            }});
        }});
    </script>
</body>
</html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        error_html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Service Registry Error</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; }}
        .error {{ background: #f8d7da; color: #721c24; padding: 20px; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>Service Registry Error</h1>
    <div class="error">
        <strong>Error:</strong> Service registry temporarily unavailable
    </div>
    <p><a href="/registry">Try again</a></p>
</body>
</html>
        """
        return HTMLResponse(content=error_html, status_code=500)
