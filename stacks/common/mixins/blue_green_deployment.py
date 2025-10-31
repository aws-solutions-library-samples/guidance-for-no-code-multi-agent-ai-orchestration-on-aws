"""
Native Blue-Green Deployment Mixin for ECS Fargate services.

This module provides native ECS blue-green deployment capabilities without CodeDeploy,
using ECS service deployment configuration and ALB target group switching.
"""

from typing import Dict, Any, Optional

import aws_cdk as cdk
from aws_cdk import (
    aws_ecs as ecs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ec2 as ec2
)
from constructs import Construct

from ..constants import (
    DEFAULT_MINIMUM_HEALTHY_PERCENT_BLUE_GREEN,
    DEFAULT_MAXIMUM_PERCENT_BLUE_GREEN,
    DEFAULT_MINIMUM_HEALTHY_PERCENT_ROLLING,
    DEFAULT_MAXIMUM_PERCENT_ROLLING,
    DEFAULT_HEALTH_CHECK_GRACE_PERIOD,
    DEFAULT_DEREGISTRATION_DELAY,
    DEFAULT_HEALTHY_THRESHOLD_COUNT,
    DEFAULT_UNHEALTHY_THRESHOLD_COUNT,
    DEFAULT_HEALTH_CHECK_INTERVAL,
    DEFAULT_HEALTH_CHECK_TIMEOUT
)


class BlueGreenDeploymentMixin:
    """
    Mixin class for implementing native ECS blue-green deployments.
    
    This mixin provides methods to create and configure ECS services
    with native blue-green deployment capabilities using ALB target groups.
    """
    
    def create_blue_green_target_groups(self,
                                       service_name: str,
                                       vpc,  # type: ignore
                                       port: int,
                                       health_check_path: str) -> Dict[str, elbv2.ApplicationTargetGroup]:
        """
        Create two target groups required for blue-green deployment.
        
        Args:
            service_name: Name of the service
            vpc: VPC to create target groups in
            port: Target port
            health_check_path: Health check path
            
        Returns:
            Dictionary with 'primary' and 'secondary' target groups
        """
        # Create shortened names for AWS resource limits
        short_name = service_name[-24:] if len(service_name) > 24 else service_name
        
        # Primary target group (current/blue)
        primary_tg = elbv2.ApplicationTargetGroup(
            self,  # type: ignore
            f"{service_name}-primary-tg",
            vpc=vpc,
            port=port,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path=health_check_path,
                interval=cdk.Duration.seconds(DEFAULT_HEALTH_CHECK_INTERVAL),
                timeout=cdk.Duration.seconds(DEFAULT_HEALTH_CHECK_TIMEOUT),
                healthy_threshold_count=DEFAULT_HEALTHY_THRESHOLD_COUNT,
                unhealthy_threshold_count=DEFAULT_UNHEALTHY_THRESHOLD_COUNT
            ),
            target_group_name=f"{short_name}-pri-tg"[:32],
            deregistration_delay=cdk.Duration.seconds(DEFAULT_DEREGISTRATION_DELAY)
        )
        
        # Secondary target group (new/green) - used during deployments
        secondary_tg = elbv2.ApplicationTargetGroup(
            self,  # type: ignore
            f"{service_name}-secondary-tg",
            vpc=vpc,
            port=port,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path=health_check_path,
                interval=cdk.Duration.seconds(DEFAULT_HEALTH_CHECK_INTERVAL),
                timeout=cdk.Duration.seconds(DEFAULT_HEALTH_CHECK_TIMEOUT),
                healthy_threshold_count=DEFAULT_HEALTHY_THRESHOLD_COUNT,
                unhealthy_threshold_count=DEFAULT_UNHEALTHY_THRESHOLD_COUNT
            ),
            target_group_name=f"{short_name}-sec-tg"[:32],
            deregistration_delay=cdk.Duration.seconds(DEFAULT_DEREGISTRATION_DELAY)
        )
        
        return {
            "primary": primary_tg,
            "secondary": secondary_tg
        }
    
    def create_blue_green_alb_resources(self, 
                                       service_name: str, 
                                       vpc,  # type: ignore
                                       port: int, 
                                       primary_target_group: elbv2.ApplicationTargetGroup,
                                       secondary_target_group: elbv2.ApplicationTargetGroup,
                                       access_log_bucket=None) -> Dict[str, Any]:
        """
        Create ALB resources optimized for blue-green deployment.
        
        Args:
            service_name: Name of the service
            vpc: VPC to create resources in
            port: Container port
            primary_target_group: Primary target group
            secondary_target_group: Secondary target group (for blue-green switching)
            
        Returns:
            Dictionary containing ALB resources
        """
        # Create security group for ALB
        alb_security_group = ec2.SecurityGroup(
            self,  # type: ignore
            f"{service_name}-bg-alb-sg",
            vpc=vpc,
            description=f"Security group for {service_name} blue-green ALB",
            allow_all_outbound=True
        )
        
        # Allow HTTP traffic from VPC CIDR (internal ALB)
        alb_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP traffic from VPC CIDR"
        )
        
        # Create security group for ECS tasks
        ecs_security_group = ec2.SecurityGroup(
            self,  # type: ignore
            f"{service_name}-bg-ecs-sg",
            vpc=vpc,
            description=f"Security group for {service_name} blue-green ECS tasks",
            allow_all_outbound=True
        )
        
        # Allow traffic from ALB to ECS tasks
        ecs_security_group.add_ingress_rule(
            peer=ec2.Peer.security_group_id(alb_security_group.security_group_id),
            connection=ec2.Port.tcp(port),
            description=f"Allow traffic from ALB to ECS tasks on port {port}"
        )
        
        # Create shortened names for AWS resource limits
        short_name = service_name[-26:] if len(service_name) > 26 else service_name
        alb_name = f"{short_name}-bg-alb"[:32]
        
        # Create Application Load Balancer (internal)
        load_balancer = elbv2.ApplicationLoadBalancer(
            self,  # type: ignore
            f"{service_name}-bg-alb",
            vpc=vpc,
            internet_facing=False,
            security_group=alb_security_group,
            load_balancer_name=alb_name
        )
        
        # Set load balancer idle timeout to 30 minutes (1800 seconds)
        load_balancer.set_attribute(
            key="idle_timeout.timeout_seconds",
            value="1800"
        )
        
        # Enable access logs and connection logs if S3 bucket is provided
        if access_log_bucket:
            # Enable access logs to S3 bucket
            load_balancer.set_attribute(
                key="access_logs.s3.enabled",
                value="true"
            )
            load_balancer.set_attribute(
                key="access_logs.s3.bucket",
                value=access_log_bucket.bucket_name
            )
            load_balancer.set_attribute(
                key="access_logs.s3.prefix",
                value=f"alb-access-logs/{service_name}"
            )
            
            # Enable connection logs to S3 bucket
            load_balancer.set_attribute(
                key="connection_logs.s3.enabled", 
                value="true"
            )
            load_balancer.set_attribute(
                key="connection_logs.s3.bucket",
                value=access_log_bucket.bucket_name
            )
            load_balancer.set_attribute(
                key="connection_logs.s3.prefix",
                value=f"alb-connection-logs/{service_name}"
            )
        
        # Create listener with primary target group as default
        listener = load_balancer.add_listener(
            f"{service_name}-listener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[primary_target_group]
        )
        
        # Create explicit listener rule for production traffic (required for blue-green)
        # Configure forward action with both target groups for blue-green switching
        production_rule = elbv2.CfnListenerRule(
            self,  # type: ignore
            f"{service_name}-production-rule",
            listener_arn=listener.listener_arn,
            priority=100,
            conditions=[
                elbv2.CfnListenerRule.RuleConditionProperty(
                    field="path-pattern",
                    values=["*"]  # Match all paths
                )
            ],
            actions=[
                elbv2.CfnListenerRule.ActionProperty(
                    type="forward",
                    forward_config=elbv2.CfnListenerRule.ForwardConfigProperty(
                        target_groups=[
                            elbv2.CfnListenerRule.TargetGroupTupleProperty(
                                target_group_arn=primary_target_group.target_group_arn,
                                weight=100  # Primary gets 100% traffic initially
                            ),
                            elbv2.CfnListenerRule.TargetGroupTupleProperty(
                                target_group_arn=secondary_target_group.target_group_arn,
                                weight=0  # Secondary gets 0% traffic initially
                            )
                        ]
                    )
                )
            ]
        )
        
        return {
            "load_balancer": load_balancer,
            "listener": listener,
            "production_rule": production_rule,
            "primary_target_group": primary_target_group,
            "secondary_target_group": secondary_target_group,
            "ecs_security_group": ecs_security_group,
            "alb_security_group": alb_security_group
        }
    
    def create_blue_green_fargate_service(self,
                                         service_name: str,
                                         cluster: ecs.Cluster,
                                         task_definition: ecs.FargateTaskDefinition,
                                         vpc_subnets,  # type: ignore
                                         security_groups: list,
                                         desired_count: int,
                                         target_groups: Dict[str, elbv2.ApplicationTargetGroup],
                                         port: int,
                                         container_name: str,
                                         production_rule: elbv2.CfnListenerRule) -> ecs.CfnService:
        """
        Create ECS Fargate service with native ECS blue/green deployment strategy.
        
        This implements true ECS native blue/green deployment using:
        - strategy: "BLUE_GREEN" in deploymentConfiguration
        - Two target groups for traffic switching
        - Load balancer management role for ALB rule updates
        - Bake time for simultaneous blue and green environments
        
        Note: This is only supported for ALB-based services, not VPC Lattice services.
        
        Args:
            service_name: Name of the service
            cluster: ECS cluster
            task_definition: Task definition
            vpc_subnets: VPC subnets for the service
            security_groups: Security groups for the service
            desired_count: Desired number of tasks
            target_groups: Dictionary with 'primary' and 'secondary' target groups
            port: Container port
            container_name: Name of the container in task definition
            listener: ALB listener for production traffic
            
        Returns:
            ECS CfnService configured with native blue/green deployment
        """
        # Create IAM role for ECS to manage load balancer during blue/green deployments
        lb_management_role = self._create_load_balancer_management_role(service_name)
        
        # Create the ECS service using CloudFormation for full blue/green control
        cfn_service = ecs.CfnService(
            self,  # type: ignore
            f"{service_name}-bg-service",
            cluster=cluster.cluster_arn,
            task_definition=task_definition.task_definition_arn,
            desired_count=desired_count,
            launch_type="FARGATE",
            service_name=f"{service_name}-service",
            
            # ECS deployment controller (required for blue/green)
            deployment_controller=ecs.CfnService.DeploymentControllerProperty(
                type="ECS"
            ),
            
            # Native ECS blue/green deployment configuration
            deployment_configuration=ecs.CfnService.DeploymentConfigurationProperty(
                # This enables native ECS blue/green deployment
                strategy="BLUE_GREEN",
                maximum_percent=200,
                minimum_healthy_percent=100,
                
                # Bake time: how long both blue and green environments run together
                bake_time_in_minutes=0,  # 2 minutes for testing, adjust as needed
                
                # Circuit breaker for automatic rollback
                deployment_circuit_breaker=ecs.CfnService.DeploymentCircuitBreakerProperty(
                    enable=True,
                    rollback=True
                )
            ),
            
            # Network configuration for Fargate
            network_configuration=ecs.CfnService.NetworkConfigurationProperty(
                awsvpc_configuration=ecs.CfnService.AwsVpcConfigurationProperty(
                    subnets=[subnet.subnet_id for subnet in vpc_subnets],
                    security_groups=[sg.security_group_id for sg in security_groups],
                    assign_public_ip="DISABLED"
                )
            ),
            
            # Load balancer configuration for blue/green deployment
            load_balancers=[
                ecs.CfnService.LoadBalancerProperty(
                    target_group_arn=target_groups["primary"].target_group_arn,
                    container_name=container_name,
                    container_port=port,
                    
                    # Advanced configuration for blue/green deployment
                    advanced_configuration=ecs.CfnService.AdvancedConfigurationProperty(
                        # Secondary target group for green deployment
                        alternate_target_group_arn=target_groups["secondary"].target_group_arn,
                        
                        # Production listener rule for traffic switching (use rule ARN for ALB)
                        production_listener_rule=production_rule.ref,
                        
                        # IAM role for ECS to manage load balancer rules
                        role_arn=lb_management_role.role_arn
                    )
                )
            ],
            
            # Health check grace period
            health_check_grace_period_seconds=DEFAULT_HEALTH_CHECK_GRACE_PERIOD,
            
            # Enable execute command for debugging
            enable_execute_command=True
        )
        
        # Add dependency on IAM role to ensure proper resource ordering
        cfn_service.add_dependency(lb_management_role.node.default_child)
        
        # Add tags to identify this as a native blue-green service
        cdk.Tags.of(cfn_service).add("DeploymentStrategy", "ECSNativeBlueGreen")
        cdk.Tags.of(cfn_service).add("BlueGreenEnabled", "true")
        cdk.Tags.of(cfn_service).add("DeploymentType", "BLUE_GREEN")
        cdk.Tags.of(cfn_service).add("LoadBalancerType", "ALB")
        
        return cfn_service
    
    def _create_load_balancer_management_role(self, service_name: str):
        """Create IAM role for ECS to manage load balancer during blue/green deployments."""
        from aws_cdk import aws_iam as iam
        
        role = iam.Role(
            self,  # type: ignore
            f"{service_name}-lb-management-role",
            assumed_by=iam.ServicePrincipal("ecs.amazonaws.com"),
            description=f"IAM role for ECS to manage load balancer during blue/green deployments for {service_name}",
            inline_policies={
                "LoadBalancerManagement": iam.PolicyDocument(
                    statements=[
                        # Permissions for managing ALB target groups and listener rules
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "elasticloadbalancing:CreateRule",
                                "elasticloadbalancing:DeleteRule",
                                "elasticloadbalancing:ModifyRule",
                                "elasticloadbalancing:SetRulePriorities",
                                "elasticloadbalancing:ModifyListener",
                                "elasticloadbalancing:DescribeRules",
                                "elasticloadbalancing:DescribeListeners",
                                "elasticloadbalancing:DescribeTargetGroups",
                                "elasticloadbalancing:DescribeLoadBalancers"
                            ],
                            resources=["*"]  # ECS needs broad permissions to manage ALB resources
                        ),
                        # Permissions for managing target group health and registration
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "elasticloadbalancing:RegisterTargets",
                                "elasticloadbalancing:DeregisterTargets",
                                "elasticloadbalancing:DescribeTargetHealth"
                            ],
                            resources=["*"]
                        )
                    ]
                )
            }
        )
        
        # Add tags for identification
        cdk.Tags.of(role).add("Purpose", "ECSBlueGreenDeployment")
        cdk.Tags.of(role).add("Service", service_name)
        
        return role
    
    def create_optimized_fargate_service(self,
                                        service_name: str,
                                        cluster: ecs.Cluster,
                                        task_definition: ecs.FargateTaskDefinition,
                                        vpc_subnets,  # type: ignore
                                        security_groups: list,
                                        desired_count: int,
                                        use_blue_green: bool = True) -> ecs.FargateService:
        """
        Create an optimized Fargate service with configurable deployment strategy.
        
        Args:
            service_name: Name of the service
            cluster: ECS cluster
            task_definition: Task definition
            vpc_subnets: VPC subnets for the service
            security_groups: Security groups for the service
            desired_count: Desired number of tasks
            use_blue_green: Whether to use blue-green deployment settings
            
        Returns:
            ECS Fargate service with optimized deployment configuration
        """
        if use_blue_green:
            min_healthy = DEFAULT_MINIMUM_HEALTHY_PERCENT_BLUE_GREEN
            max_healthy = DEFAULT_MAXIMUM_PERCENT_BLUE_GREEN
        else:
            min_healthy = DEFAULT_MINIMUM_HEALTHY_PERCENT_ROLLING
            max_healthy = DEFAULT_MAXIMUM_PERCENT_ROLLING
        
        return ecs.FargateService(
            self,  # type: ignore
            f"{service_name}-optimized-service",
            cluster=cluster,
            task_definition=task_definition,
            desired_count=desired_count,
            vpc_subnets=ec2.SubnetSelection(subnets=vpc_subnets),
            security_groups=security_groups,
            assign_public_ip=False,
            service_name=f"{service_name}-service",
            
            # Deployment configuration
            min_healthy_percent=min_healthy,
            max_healthy_percent=max_healthy,
            
            # Fast deployment settings
            health_check_grace_period=cdk.Duration.seconds(DEFAULT_HEALTH_CHECK_GRACE_PERIOD),
            
            # Circuit breaker for reliability
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            
            # Enable execute command for debugging
            enable_execute_command=True
        )
