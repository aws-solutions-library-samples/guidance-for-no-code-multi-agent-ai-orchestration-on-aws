"""VPC Lattice mixin for CDK stacks."""

from typing import Dict, Any, Optional

from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_iam as iam,
    aws_vpclattice as vpclattice,
    RemovalPolicy
)

from ..exceptions import ResourceCreationError
from ..validators import ConfigValidator, AWSResourceValidator


class VpcLatticeServiceMixin:
    """
    Mixin class providing VPC Lattice functionality.
    
    This mixin provides methods for creating and managing VPC Lattice services
    with proper validation and error handling.
    """
    
    def create_vpc_lattice_service(self,
                                   service_name: str,
                                   vpc: ec2.Vpc,
                                   service_network_arn: str,
                                   port: int,
                                   health_check_path: str,
                                   port_name: Optional[str] = None,
                                   enable_access_logging: bool = True,
                                   aws_service_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a complete VPC Lattice service setup with comprehensive access logging.
        
        Args:
            service_name: Name for the VPC Lattice service
            vpc: VPC to create the service in
            service_network_arn: ARN of the service network
            port: Port for the service
            health_check_path: Path for health checks
            port_name: Optional custom port name
            enable_access_logging: Whether to enable comprehensive access logging
            
        Returns:
            Dictionary containing all created resources including access logging
            
        Raises:
            ResourceCreationError: If service creation fails
            ValidationError: If input validation fails
        """
        try:
            # Validate inputs
            ConfigValidator.validate_resource_name(service_name)
            ConfigValidator.validate_port_range(port)
            AWSResourceValidator.validate_vpc(vpc)
            AWSResourceValidator.validate_arn(service_network_arn, "vpc-lattice")
            
            if not health_check_path.startswith('/'):
                raise ValueError("Health check path must start with '/'")
                
        except Exception as e:
            raise ResourceCreationError(
                f"VPC Lattice service validation failed: {str(e)}",
                resource_type="VpcLatticeService"
            )
        
        try:
            # Create CloudWatch log groups for access logging
            access_logging_resources = {}
            if enable_access_logging:
                access_logging_resources = self._create_vpc_lattice_access_logging(service_name)
            
            # Create VPC Lattice Service  
            # Use aws_service_name for actual AWS resource name if provided, otherwise use service_name
            # For VPC Lattice compatibility, we need to handle underscore-to-hyphen conversion
            if aws_service_name:
                # For CloudFormation parameter, use it directly - VPC Lattice will accept both
                # The user can control the naming via the parameter value
                lattice_service_name = aws_service_name
            else:
                lattice_service_name = service_name.replace("_", "-")
                
            lattice_service = vpclattice.CfnService(
                self,
                f"{service_name}-lattice-service",  # CDK construct ID uses static service_name
                # No explicit name - let CloudFormation auto-generate for VPC Lattice naming compliance
                auth_type="NONE"
            )
            
            # Create Target Group
            target_group = self._create_target_group(
                service_name, vpc, port, health_check_path, aws_service_name
            )
            
            # Create Listener
            listener = self._create_listener(
                service_name, lattice_service, target_group
            )
            
            # Associate with service network
            service_network_association = vpclattice.CfnServiceNetworkServiceAssociation(
                self,
                f"{service_name}-service-network-association",
                service_identifier=lattice_service.attr_id,
                service_network_identifier=service_network_arn
            )
            
            # Create ECS service role
            ecs_service_role = self._create_vpc_lattice_service_role(service_name)
            
            # Set up access logging if enabled
            access_log_subscriptions = {}
            if enable_access_logging:
                access_log_subscriptions = self._create_access_log_subscriptions(
                    service_name, lattice_service, service_network_arn, access_logging_resources
                )
            
            # Set up dependencies
            listener.add_dependency(target_group)
            service_network_association.add_dependency(lattice_service)
            
            # Ensure access log subscriptions depend on the service being created
            for subscription in access_log_subscriptions.values():
                subscription.add_dependency(lattice_service)
                subscription.add_dependency(service_network_association)
            
            result = {
                "service": lattice_service,
                "target_group": target_group,
                "listener": listener,
                "service_network_association": service_network_association,
                "ecs_service_role": ecs_service_role
            }
            
            # Add access logging resources to return value
            if enable_access_logging:
                result.update({
                    "access_logging": access_logging_resources,
                    "access_log_subscriptions": access_log_subscriptions
                })
            
            return result
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create VPC Lattice service: {str(e)}",
                resource_type="VpcLatticeService"
            )
    
    def _create_target_group(self,
                            service_name: str,
                            vpc: ec2.Vpc,
                            port: int,
                            health_check_path: str,
                            aws_service_name: Optional[str] = None) -> vpclattice.CfnTargetGroup:
        """
        Create a VPC Lattice target group optimized for fast rolling deployments.
        
        Args:
            service_name: Name for the target group (CDK construct ID)
            vpc: VPC for the target group
            port: Port for the target group
            health_check_path: Path for health checks
            aws_service_name: Actual AWS resource name (CloudFormation parameter)
            
        Returns:
            The created target group
        """
        # Use aws_service_name for actual AWS target group name if provided
        actual_name = aws_service_name if aws_service_name else service_name
        target_group_name = f"{actual_name}-targets".replace("_", "-")
        
        target_group = vpclattice.CfnTargetGroup(
            self,
            f"{service_name}-lattice-target-group",
            # No explicit name - let CloudFormation auto-generate for VPC Lattice naming compliance
            type="IP",
            config=vpclattice.CfnTargetGroup.TargetGroupConfigProperty(
                port=port,
                protocol="HTTP",
                vpc_identifier=vpc.vpc_id,
                ip_address_type="IPV4",
                health_check=vpclattice.CfnTargetGroup.HealthCheckConfigProperty(
                    enabled=True,
                    health_check_interval_seconds=30,   # More frequent checks for faster feedback
                    health_check_timeout_seconds=15,    # Longer timeout for slow-starting containers
                    healthy_threshold_count=2,          # Keep low for faster recovery
                    unhealthy_threshold_count=2,        # More tolerance for startup delays
                    matcher=vpclattice.CfnTargetGroup.MatcherProperty(
                        http_code="200"
                    ),
                    path=health_check_path,
                    protocol="HTTP",
                    protocol_version="HTTP1"
                )
            )
        )
        
        return target_group
    
    def _create_listener(self,
                        service_name: str,
                        lattice_service: vpclattice.CfnService,
                        target_group: vpclattice.CfnTargetGroup) -> vpclattice.CfnListener:
        """
        Create a VPC Lattice listener with 30-minute idle timeout.
        
        Args:
            service_name: Name for the listener
            lattice_service: The VPC Lattice service
            target_group: The target group to route to
            
        Returns:
            The created listener
        """
        listener = vpclattice.CfnListener(
            self,
            f"{service_name}-lattice-listener",
            service_identifier=lattice_service.attr_id,
            protocol="HTTP",
            port=80,
            default_action=vpclattice.CfnListener.DefaultActionProperty(
                forward=vpclattice.CfnListener.ForwardProperty(
                    target_groups=[
                        vpclattice.CfnListener.WeightedTargetGroupProperty(
                            target_group_identifier=target_group.attr_id,
                            weight=100
                        )
                    ]
                )
            )
        )
        
        return listener
    
    def _create_vpc_lattice_service_role(self, service_name: str) -> iam.Role:
        """
        Create IAM role for VPC Lattice ECS integration.
        
        Args:
            service_name: Name for the role
            
        Returns:
            The created IAM role
            
        Note:
            This role must be deleted AFTER any ECS services that depend on it.
            The calling code should ensure proper dependency management.
        """
        role = iam.Role(
            self,
            f"{service_name}-ecs-service-role",
            assumed_by=iam.ServicePrincipal("ecs.amazonaws.com"),
            description=f"ECS service role for VPC Lattice integration - {service_name}",
            inline_policies={
                "VPCLatticePolicy": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            resources=["*"],
                            actions=[
                                "vpc-lattice:RegisterTargets",
                                "vpc-lattice:DeregisterTargets",
                                "vpc-lattice:GetService",
                                "vpc-lattice:GetTargetGroup",
                                "vpc-lattice:ListTargets",
                                "vpc-lattice:GetTargetGroupHealth"
                            ]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            resources=["*"],
                            actions=[
                                "ec2:DescribeNetworkInterfaces",
                                "ec2:DescribeSubnets",
                                "ec2:DescribeVpcs"
                            ]
                        )
                    ]
                )
            }
        )
        
        # Add removal policy to ensure clean deletion
        role.apply_removal_policy(RemovalPolicy.DESTROY)
        
        return role
    
    def create_service_network(self,
                              network_name: str,
                              auth_type: str = "NONE") -> vpclattice.CfnServiceNetwork:
        """
        Create a VPC Lattice service network.
        
        Args:
            network_name: Name for the service network
            auth_type: Authentication type for the network
            
        Returns:
            The created service network
        """
        ConfigValidator.validate_resource_name(network_name)
        
        if auth_type not in ["NONE", "AWS_IAM"]:
            raise ValueError(f"Invalid auth_type: {auth_type}")
        
        try:
            return vpclattice.CfnServiceNetwork(
                self,
                f"{network_name}-service-network",
                name=f"{network_name}-network",
                auth_type=auth_type
            )
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create service network: {str(e)}",
                resource_type="ServiceNetwork"
            )
    
    def associate_vpc_with_service_network(self,
                                          association_name: str,
                                          vpc: ec2.Vpc,
                                          service_network_arn: str) -> vpclattice.CfnServiceNetworkVpcAssociation:
        """
        Associate a VPC with a service network.
        
        Args:
            association_name: Name for the association
            vpc: VPC to associate
            service_network_arn: ARN of the service network
            
        Returns:
            The created association
        """
        ConfigValidator.validate_resource_name(association_name)
        AWSResourceValidator.validate_vpc(vpc)
        AWSResourceValidator.validate_arn(service_network_arn, "vpc-lattice")
        
        try:
            return vpclattice.CfnServiceNetworkVpcAssociation(
                self,
                f"{association_name}-vpc-association",
                vpc_identifier=vpc.vpc_id,
                service_network_identifier=service_network_arn
            )
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create VPC association: {str(e)}",
                resource_type="ServiceNetworkVpcAssociation"
            )
    
    def create_access_log_subscription(self,
                                       subscription_name: str,
                                       resource_arn: str,
                                       destination_arn: str) -> vpclattice.CfnAccessLogSubscription:
        """
        Create access log subscription for VPC Lattice.
        
        Args:
            subscription_name: Name for the subscription
            resource_arn: ARN of the resource to log
            destination_arn: ARN of the log destination
            
        Returns:
            The created access log subscription
        """
        ConfigValidator.validate_resource_name(subscription_name)
        AWSResourceValidator.validate_arn(resource_arn)
        AWSResourceValidator.validate_arn(destination_arn)
        
        try:
            return vpclattice.CfnAccessLogSubscription(
                self,
                f"{subscription_name}-access-log-subscription",
                resource_identifier=resource_arn,
                destination_arn=destination_arn
            )
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create access log subscription: {str(e)}",
                resource_type="AccessLogSubscription"
            )
    
    def _create_vpc_lattice_access_logging(self, service_name: str) -> Dict[str, Any]:
        """
        Create CloudWatch log groups for comprehensive VPC Lattice access logging.
        
        This creates separate log groups for:
        - Service access logs (requests to the specific service)
        - Resource access logs (requests to resources within the service network)
        
        Args:
            service_name: Name of the service for log group naming
            
        Returns:
            Dictionary containing created log groups and their ARNs
        """
        try:
            # Import here to avoid circular dependency
            from aws_cdk import aws_logs as logs
            
            # Create log group for service-level access logs
            service_access_log_group = logs.LogGroup(
                self,
                f"{service_name}-lattice-service-access-logs",
                # No explicit log group name - let CloudFormation auto-generate for better reusability
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY
            )
            
            # Create log group for resource-level access logs within the service network
            resource_access_log_group = logs.LogGroup(
                self,
                f"{service_name}-lattice-resource-access-logs",
                # No explicit log group name - let CloudFormation auto-generate for better reusability
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY
            )
            
            # Create log group for service network level logs
            network_access_log_group = logs.LogGroup(
                self,
                f"{service_name}-lattice-network-access-logs", 
                # No explicit log group name - let CloudFormation auto-generate for better reusability
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY
            )
            
            return {
                "service_log_group": service_access_log_group,
                "resource_log_group": resource_access_log_group,
                "network_log_group": network_access_log_group,
                "service_log_group_arn": service_access_log_group.log_group_arn,
                "resource_log_group_arn": resource_access_log_group.log_group_arn,
                "network_log_group_arn": network_access_log_group.log_group_arn
            }
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create VPC Lattice access logging resources: {str(e)}",
                resource_type="VpcLatticeAccessLogging"
            )
    
    def _create_access_log_subscriptions(self,
                                        service_name: str,
                                        lattice_service: vpclattice.CfnService,
                                        service_network_arn: str,
                                        access_logging_resources: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create access log subscriptions for VPC Lattice service monitoring.
        
        This creates subscriptions for:
        1. Service access logs - monitors all requests/responses to the specific service
        
        Note: Network-level access logging is handled centrally in the VPC stack 
        to avoid conflicts between multiple services sharing the same service network.
        
        Args:
            service_name: Name of the service
            lattice_service: The VPC Lattice service
            service_network_arn: ARN of the service network (unused, kept for compatibility)
            access_logging_resources: Dictionary containing log groups and ARNs
            
        Returns:
            Dictionary containing created access log subscriptions
        """
        try:
            subscriptions = {}
            
            # Create access log subscription for the specific service
            # This monitors all requests and responses to/from this service
            service_subscription = vpclattice.CfnAccessLogSubscription(
                self,
                f"{service_name}-service-access-log-subscription",
                resource_identifier=lattice_service.attr_arn,
                destination_arn=access_logging_resources["service_log_group_arn"]
            )
            subscriptions["service_subscription"] = service_subscription
            
            return subscriptions
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create VPC Lattice access log subscriptions: {str(e)}",
                resource_type="VpcLatticeAccessLogSubscriptions"
            )
    
    def create_enhanced_service_network_with_logging(self,
                                                    network_name: str,
                                                    auth_type: str = "NONE") -> Dict[str, Any]:
        """
        Create a VPC Lattice service network with comprehensive access logging enabled.
        
        Args:
            network_name: Name for the service network
            auth_type: Authentication type for the network
            
        Returns:
            Dictionary containing the service network and logging resources
        """
        try:
            # Create the service network
            service_network = self.create_service_network(network_name, auth_type)
            
            # Create CloudWatch log group for service network level access logs
            from aws_cdk import aws_logs as logs
            
            network_log_group = logs.LogGroup(
                self,
                f"{network_name}-network-access-logs",
                log_group_name=f"/aws/vpclattice/{network_name}/network-access",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY
            )
            
            # Create access log subscription for the service network
            network_access_subscription = vpclattice.CfnAccessLogSubscription(
                self,
                f"{network_name}-network-access-log-subscription",
                resource_identifier=service_network.attr_arn,
                destination_arn=network_log_group.log_group_arn
            )
            
            # Set up dependency
            network_access_subscription.add_dependency(service_network)
            
            return {
                "service_network": service_network,
                "network_log_group": network_log_group,
                "network_access_subscription": network_access_subscription,
                "network_log_group_arn": network_log_group.log_group_arn
            }
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create enhanced service network with logging: {str(e)}",
                resource_type="EnhancedServiceNetwork"
            )
