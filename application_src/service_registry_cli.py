#!/usr/bin/env python3
"""
Service Registry CLI Tool

A command-line utility to interact with the GenAI-in-a-Box Service Registry.
This tool helps you discover and test all API endpoints across your services.
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Optional

import httpx


class ServiceRegistryCLI:
    """Command-line interface for the Service Registry."""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
    
    async def get_services(self) -> dict:
        """Get all services from the registry."""
        try:
            response = await self.client.get(f"{self.base_url}/registry/services")
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            print(f"❌ Connection error: {e}")
            return {}
        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP error {e.response.status_code}: {e.response.text}")
            return {}
    
    async def get_summary(self) -> dict:
        """Get registry summary."""
        try:
            response = await self.client.get(f"{self.base_url}/registry/summary")
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            print(f"❌ Connection error: {e}")
            return {}
        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP error {e.response.status_code}: {e.response.text}")
            return {}
    
    async def get_all_endpoints(self) -> dict:
        """Get all endpoints across all services."""
        try:
            response = await self.client.get(f"{self.base_url}/registry/endpoints")
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            print(f"❌ Connection error: {e}")
            return {}
        except httpx.HTTPStatusError as e:
            print(f"❌ HTTP error {e.response.status_code}: {e.response.text}")
            return {}
    
    async def test_endpoint(self, service_url: str, path: str, method: str = "GET") -> dict:
        """Test a specific endpoint."""
        full_url = f"{service_url}{path}"
        try:
            response = await self.client.request(method, full_url)
            return {
                "url": full_url,
                "method": method,
                "status_code": response.status_code,
                "success": response.status_code < 400,
                "response_size": len(response.content),
                "content_type": response.headers.get("content-type", "unknown")
            }
        except Exception as e:
            return {
                "url": full_url,
                "method": method,
                "success": False,
                "error": str(e)
            }
    
    def print_services_table(self, services: list):
        """Print services in a formatted table."""
        if not services:
            print("No services found.")
            return
        
        print("\n🚀 GenAI-in-a-Box Services")
        print("=" * 80)
        
        for service in services:
            status_emoji = {
                "active": "✅",
                "unreachable": "❌", 
                "error": "⚠️"
            }.get(service.get("status", "unknown"), "❓")
            
            print(f"\n{status_emoji} {service.get('name', 'Unknown')}")
            print(f"   URL: {service.get('url', 'Unknown')}")
            print(f"   Port: {service.get('port', 'Unknown')}")
            print(f"   Status: {service.get('status', 'Unknown')}")
            print(f"   Endpoints: {len(service.get('endpoints', []))}")
            
            if service.get('docs_url'):
                print(f"   Docs: {service['docs_url']}")
            
            if service.get('error'):
                print(f"   Error: {service['error']}")
    
    def print_summary(self, summary: dict):
        """Print registry summary."""
        print("\n📊 Service Registry Summary")
        print("=" * 50)
        print(f"Total Services: {summary.get('total_services', 0)}")
        print(f"Active Services: {summary.get('active_services', 0)}")
        print(f"Total Endpoints: {summary.get('total_endpoints', 0)}")
        print(f"Last Updated: {summary.get('last_updated', 'Unknown')}")
        
        services_by_status = summary.get('services_by_status', {})
        if services_by_status:
            print("\nServices by Status:")
            for status, service_names in services_by_status.items():
                emoji = {"active": "✅", "unreachable": "❌", "error": "⚠️"}.get(status, "❓")
                print(f"  {emoji} {status.title()}: {len(service_names)} services")
                for name in service_names:
                    print(f"    - {name}")
    
    def print_endpoints_table(self, endpoints_data: dict):
        """Print all endpoints in a formatted table."""
        endpoints = endpoints_data.get('endpoints', [])
        if not endpoints:
            print("No endpoints found.")
            return
        
        print(f"\n📋 All Endpoints ({len(endpoints)} total)")
        print("=" * 100)
        
        current_service = None
        for endpoint in endpoints:
            service_name = endpoint.get('service_name', 'Unknown')
            
            if service_name != current_service:
                current_service = service_name
                status_emoji = {
                    "active": "✅",
                    "unreachable": "❌",
                    "error": "⚠️"
                }.get(endpoint.get('service_status', 'unknown'), "❓")
                print(f"\n{status_emoji} {service_name}")
                print("-" * 60)
            
            method = endpoint.get('method', 'GET')
            path = endpoint.get('path', '/')
            description = endpoint.get('description', 'No description')
            
            method_emoji = {
                "GET": "📥",
                "POST": "📤", 
                "PUT": "📝",
                "DELETE": "🗑️",
                "PATCH": "✏️"
            }.get(method, "🔧")
            
            print(f"  {method_emoji} {method:6} {path:30} {description}")
    
    async def test_all_endpoints(self, limit: Optional[int] = None):
        """Test all endpoints and report results."""
        print("🧪 Testing all endpoints...")
        
        endpoints_data = await self.get_all_endpoints()
        endpoints = endpoints_data.get('endpoints', [])
        
        if limit:
            endpoints = endpoints[:limit]
        
        if not endpoints:
            print("No endpoints to test.")
            return
        
        print(f"\nTesting {len(endpoints)} endpoints...")
        
        results = []
        for i, endpoint in enumerate(endpoints, 1):
            service_url = endpoint.get('service_url', '')
            path = endpoint.get('path', '/')
            method = endpoint.get('method', 'GET')
            
            print(f"  {i:3d}/{len(endpoints)} Testing {method} {service_url}{path}...", end=' ')
            
            result = await self.test_endpoint(service_url, path, method)
            results.append({**endpoint, **result})
            
            if result.get('success'):
                print(f"✅ {result.get('status_code', 'OK')}")
            else:
                error = result.get('error', result.get('status_code', 'Failed'))
                print(f"❌ {error}")
        
        # Summary
        successful = len([r for r in results if r.get('success')])
        failed = len(results) - successful
        
        print(f"\n📊 Test Results:")
        print(f"  ✅ Successful: {successful}")
        print(f"  ❌ Failed: {failed}")
        print(f"  📈 Success Rate: {successful/len(results)*100:.1f}%")
        
        # Show failures
        failures = [r for r in results if not r.get('success')]
        if failures:
            print(f"\n❌ Failed Endpoints ({len(failures)}):")
            for failure in failures:
                service = failure.get('service_name', 'Unknown')
                method = failure.get('method', 'GET')
                path = failure.get('path', '/')
                error = failure.get('error', failure.get('status_code', 'Unknown error'))
                print(f"  - {service}: {method} {path} → {error}")


async def main():
    parser = argparse.ArgumentParser(
        description="GenAI-in-a-Box Service Registry CLI Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s summary                    # Show registry summary
  %(prog)s services                   # List all services
  %(prog)s endpoints                  # List all endpoints
  %(prog)s test                       # Test all endpoints
  %(prog)s test --limit 10           # Test first 10 endpoints
  %(prog)s --url http://localhost:8000 summary  # Use custom URL
        """
    )
    
    parser.add_argument(
        '--url', 
        default='http://localhost:8000',
        help='Base URL for the Configuration API (default: http://localhost:8000)'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Summary command
    subparsers.add_parser('summary', help='Show service registry summary')
    
    # Services command
    subparsers.add_parser('services', help='List all services')
    
    # Endpoints command
    subparsers.add_parser('endpoints', help='List all endpoints')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test all endpoints')
    test_parser.add_argument(
        '--limit', 
        type=int, 
        help='Limit number of endpoints to test'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    cli = ServiceRegistryCLI(base_url=args.url)
    
    try:
        print(f"🔗 Connecting to: {args.url}")
        
        if args.command == 'summary':
            summary = await cli.get_summary()
            cli.print_summary(summary)
        
        elif args.command == 'services':
            services = await cli.get_services()
            cli.print_services_table(services)
        
        elif args.command == 'endpoints':
            endpoints_data = await cli.get_all_endpoints()
            cli.print_endpoints_table(endpoints_data)
        
        elif args.command == 'test':
            await cli.test_all_endpoints(limit=args.limit)
        
        print(f"\n⏰ Completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
    except KeyboardInterrupt:
        print("\n⏹️  Operation cancelled by user.")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
    finally:
        await cli.close()


if __name__ == '__main__':
    asyncio.run(main())
