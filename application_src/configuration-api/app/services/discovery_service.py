"""
VPC Lattice service discovery service.

This service handles discovery of services through VPC Lattice,
providing DNS resolution and service network management capabilities.
"""

import logging
from typing import List, Dict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class DiscoveryService:
    """Service for VPC Lattice service discovery operations."""

    def __init__(self, region_name: str):
        """
        Initialize Discovery service.
        
        Args:
            region_name: AWS region name for VPC Lattice operations
        """
        self.region_name = region_name
        self.client = boto3.client('vpc-lattice', region_name=region_name)
        logger.info(f"DiscoveryService initialized for region: {region_name}")

    def get_service_dns_entries(self, service_network_arn: str) -> List[str]:
        """
        Retrieve DNS domain names from VPC Lattice service network associations.
        
        Args:
            service_network_arn: ARN of the VPC Lattice service network
            
        Returns:
            List of DNS domain names
            
        Raises:
            ClientError: If AWS API call fails
            ValueError: If service_network_arn is invalid
        """
        if not service_network_arn:
            raise ValueError("Service network ARN cannot be empty")

        try:
            logger.info(f"Retrieving service associations for ARN: {service_network_arn}")
            
            associations_response = self.client.list_service_network_service_associations(
                serviceNetworkIdentifier=service_network_arn
            )
            
            domain_names = []
            
            for association in associations_response.get('items', []):
                dns_entry = association.get('dnsEntry', {})
                domain_name = dns_entry.get('domainName', '')
                
                if domain_name:
                    domain_names.append(domain_name)
                    service_name = association.get('serviceName', 'Unknown')
                    logger.info(f"Found service: {service_name} -> {domain_name}")
            
            logger.info(f"Successfully retrieved {len(domain_names)} DNS entries")
            return domain_names
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            
            logger.error(f"ClientError retrieving service associations: {error_code} - {error_message}")
            
            if error_code == 'AccessDeniedException':
                raise ClientError(
                    error_response={
                        'Error': {
                            'Code': 'AccessDenied',
                            'Message': 'Access denied to VPC Lattice service. Check IAM permissions.'
                        }
                    },
                    operation_name='ListServiceNetworkServiceAssociations'
                )
            else:
                raise ClientError(
                    error_response={
                        'Error': {
                            'Code': error_code,
                            'Message': f"VPC Lattice API error: {error_message}"
                        }
                    },
                    operation_name='ListServiceNetworkServiceAssociations'
                )
        except Exception as e:
            logger.error(f"Unexpected error retrieving service associations: {e}")
            raise

    def get_service_https_urls(self, service_network_arn: str) -> List[str]:
        """
        Retrieve HTTP URLs from VPC Lattice service network associations.
        
        This method adds the http:// prefix to domain names for backward compatibility.
        
        Args:
            service_network_arn: ARN of the VPC Lattice service network
            
        Returns:
            List of HTTP URLs
        """
        domain_names = self.get_service_dns_entries(service_network_arn)
        http_urls = [f"http://{domain}" for domain in domain_names]
        
        logger.info(f"Converted {len(domain_names)} domain names to HTTP URLs")
        return http_urls

    def get_service_details(self, service_network_arn: str) -> Dict[str, List[Dict[str, str]]]:
        """
        Get detailed information about services in the network.
        
        Args:
            service_network_arn: ARN of the VPC Lattice service network
            
        Returns:
            Dictionary containing detailed service information
        """
        try:
            associations_response = self.client.list_service_network_service_associations(
                serviceNetworkIdentifier=service_network_arn
            )
            
            services = []
            
            for association in associations_response.get('items', []):
                service_info = {
                    'service_name': association.get('serviceName', 'Unknown'),
                    'service_arn': association.get('serviceArn', ''),
                    'dns_domain': association.get('dnsEntry', {}).get('domainName', ''),
                    'status': association.get('status', 'Unknown'),
                    'association_id': association.get('id', ''),
                    'created_at': association.get('createdAt', ''),
                }
                services.append(service_info)
            
            logger.info(f"Retrieved detailed info for {len(services)} services")
            return {
                'service_network_arn': service_network_arn,
                'services': services,
                'total_count': len(services)
            }
            
        except Exception as e:
            logger.error(f"Error retrieving service details: {e}")
            raise

    def validate_service_network_arn(self, service_network_arn: str) -> bool:
        """
        Validate that a service network ARN is accessible.
        
        Args:
            service_network_arn: ARN to validate
            
        Returns:
            True if valid and accessible, False otherwise
        """
        try:
            if not service_network_arn:
                return False
            
            # Test access by trying to list associations
            self.client.list_service_network_service_associations(
                serviceNetworkIdentifier=service_network_arn,
                maxResults=1  # Minimal request for validation
            )
            
            logger.info(f"Service network ARN validated: {service_network_arn}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            logger.warning(f"Service network ARN validation failed: {error_code}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error validating service network ARN: {e}")
            return False

    def get_connection_status(self) -> Dict[str, str]:
        """
        Test VPC Lattice connectivity and return status information.
        
        Returns:
            Dictionary containing connection status and region info
        """
        try:
            # Test basic connectivity by listing service networks (limited)
            self.client.list_service_networks(maxResults=1)
            return {
                "status": "connected",
                "region": self.region_name,
                "service": "vpc-lattice"
            }
        except Exception as e:
            logger.error(f"VPC Lattice connectivity test failed: {e}")
            return {
                "status": "error",
                "region": self.region_name,
                "service": "vpc-lattice",
                "error": str(e)
            }
