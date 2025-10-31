import time
from typing import Optional
from constructs import Construct
from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr_assets as ecr_assets,
    aws_certificatemanager as acm,
    aws_wafv2 as waf,
    aws_logs as logs,
    aws_cloudfront as cloudfront,
    RemovalPolicy
)

from helper.config import Config
from stacks.common.base import BaseStack, FargateServiceStack
from stacks.common.mixins import CognitoMixin, CognitoConfiguration, CognitoResources, CognitoUserGroup, LoadBalancerLoggingMixin
from stacks.common.mixins.cognito import _get_feature_plan_from_string, _get_threat_protection_from_string
from stacks.common.constants import (
    UI_PORT,
    UI_HEALTH_CHECK_PATH,
    UI_CPU,
    UI_MEMORY,
    UI_DESIRED_COUNT,
    UI_MIN_HEALTHY_PERCENT,
    UI_DEREGISTRATION_DELAY,
    DEFAULT_UI_SERVICE_SUFFIX,
    DEFAULT_UI_LOAD_BALANCER_SUFFIX,
    DEFAULT_COGNITO_USER_POOL_SUFFIX,
    DEFAULT_COGNITO_DOMAIN_SUFFIX,
    DEFAULT_COGNITO_CLIENT_NAME,
    DEFAULT_COGNITO_PASSWORD_MIN_LENGTH,
    WAF_METRIC_NAME_PREFIX,
    DEFAULT_MINIMUM_HEALTHY_PERCENT_BLUE_GREEN,
    DEFAULT_MAXIMUM_PERCENT_BLUE_GREEN,
    UI_ACCESS_MODE_PUBLIC,
    UI_ACCESS_MODE_PRIVATE,
    CLOUDFRONT_MANAGED_PREFIX_LIST_NAME
)
from .cloudfront import CloudFrontVpcOriginConstruct


class WebAppStack(FargateServiceStack, CognitoMixin, LoadBalancerLoggingMixin):
    """
    Web Application Stack for deploying the React UI with Cognito authentication,
    Application Load Balancer, and WAF protection.
    
    Supports two access modes:
    - public: CloudFront distribution with VPC origins, ALB in private subnets
    - private: ALB-only deployment in private subnets with customer certificate
    
    This stack uses the CognitoMixin for structured authentication setup,
    following coding best practices and providing flexibility for future
    configuration changes.
    """

    def __init__(self, 
                 scope: Construct, 
                 construct_id: str,
                 api_url: str,
                 supervisor_agent_url: str,
                 cluster: ecs.Cluster,
                 imported_cert_arn: Optional[str],
                 access_logs_bucket,
                 cognito_resources,  # CognitoResources from authentication stack
                 config: Config,
                 **kwargs) -> None:
        # Initialize with FargateServiceStack to inherit shared logging functionality
        super().__init__(scope, construct_id, cluster.vpc, cluster, "", config, **kwargs)

        # Store dependencies
        self.access_logs_bucket = access_logs_bucket
        self.cognito_resources = cognito_resources

        # Get configuration values
        project_name = self.get_required_config('ProjectName')
        
        # Get UI access mode configuration
        ui_access_mode = self.get_optional_config('UIAccessMode', UI_ACCESS_MODE_PUBLIC)
        self._validate_access_mode(ui_access_mode)
        
        # Initialize CloudFront properties
        self.cloudfront_distribution: Optional[cloudfront.Distribution] = None
        self.cloudfront_construct: Optional[CloudFrontVpcOriginConstruct] = None
        
        # Create the UI Fargate service with conditional ALB configuration
        ui_fargate_service = self._create_ui_fargate_service(
            project_name, cluster, imported_cert_arn, api_url, supervisor_agent_url, cognito_resources, ui_access_mode
        )
        
        # Configure security and networking based on access mode
        self._configure_ui_security(ui_fargate_service, ui_access_mode)
        
        # Create WAF protection based on access mode
        self._create_waf_protection(project_name, ui_fargate_service, ui_access_mode)
        
        # Create CloudFront integration for public mode
        if ui_access_mode == UI_ACCESS_MODE_PUBLIC:
            self._create_cloudfront_integration(project_name, ui_fargate_service)
            
            # Update the task definition environment with CloudFront URL for CORS
            self._update_cors_origins_with_cloudfront(ui_fargate_service)
            
            # Output CloudFront distribution URL for easy access
            from aws_cdk import CfnOutput
            CfnOutput(
                self,
                "CloudFrontDistributionURL",
                value=f"https://{self.cloudfront_distribution.distribution_domain_name}",
                description="CloudFront Distribution URL for public access to the UI",
                export_name=f"{project_name}-CloudFrontURL"
            )
            
            CfnOutput(
                self,
                "CloudFrontDistributionId", 
                value=self.cloudfront_distribution.distribution_id,
                description="CloudFront Distribution ID for management and monitoring"
            )
        
        # Store references for compatibility
        self.ui_fargate_service = ui_fargate_service
        self.ui_access_mode = ui_access_mode

    def _validate_access_mode(self, ui_access_mode: str) -> None:
        """Validate UIAccessMode configuration parameter."""
        valid_modes = [UI_ACCESS_MODE_PUBLIC, UI_ACCESS_MODE_PRIVATE]
        if ui_access_mode not in valid_modes:
            raise ValueError(f"Invalid UIAccessMode: {ui_access_mode}. Must be one of {valid_modes}")

    def _create_ui_fargate_service(self, 
                                   project_name: str, 
                                   cluster: ecs.Cluster, 
                                   imported_cert_arn: str,
                                   api_url: str,
                                   supervisor_agent_url: str,
                                   cognito_resources: CognitoResources,
                                   ui_access_mode: str) -> ecs_patterns.ApplicationLoadBalancedFargateService:
        """Create the UI Fargate service with load balancer and shared logging."""
        # Get UI configuration values
        ui_service_name = f"{project_name}-{DEFAULT_UI_SERVICE_SUFFIX}"
        ui_load_balancer_name = f"{project_name}-{DEFAULT_UI_LOAD_BALANCER_SUFFIX}"
        ui_cpu = self.get_optional_config('UiCPU', UI_CPU)
        ui_memory = self.get_optional_config('UiMemory', UI_MEMORY)
        ui_desired_count = self.get_optional_config('UiDesiredCount', UI_DESIRED_COUNT)
        ui_min_healthy_percent = self.get_optional_config('UiMinHealthyPercent', UI_MIN_HEALTHY_PERCENT)

        # Create shared log group using the inherited functionality
        log_group = self.create_log_group(f"{ui_service_name}-service")

        # Determine ALB configuration based on access mode
        # Public mode: ALB internal in private subnets, CloudFront connects via VPC Origins (proper VPC origins pattern)
        # Private mode: ALB internal in private subnets, accessible from VPC with customer certificate
        is_public_alb = False  # Both modes use internal ALB - VPC Origins handles CloudFront connectivity
        certificate_config = None
        
        # Certificate configuration based on access mode
        # Public mode: NO certificate required - CloudFront handles HTTPS termination, ALB uses HTTP
        # Private mode: Customer certificate required for direct HTTPS ALB access
        certificate_config = None
        if ui_access_mode == UI_ACCESS_MODE_PRIVATE:
            if not imported_cert_arn:
                raise ValueError("CertificateArn is required in config when UIAccessMode is 'private'")
            certificate_config = acm.Certificate.from_certificate_arn(self, "imported-cert-arn", imported_cert_arn)

        # Create the load balanced Fargate service
        ui_fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "react-ui-webapp",
            cluster=cluster,
            service_name=ui_service_name,
            memory_limit_mib=ui_memory,
            min_healthy_percent=ui_min_healthy_percent,
            cpu=ui_cpu,
            desired_count=ui_desired_count,
            load_balancer_name=ui_load_balancer_name,
            listener_port=443 if ui_access_mode == UI_ACCESS_MODE_PRIVATE else 80,  # HTTPS only for private mode
            public_load_balancer=is_public_alb,
            certificate=certificate_config,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_asset(
                    "./application_src/ui-react-cloudscape", 
                    platform=ecr_assets.Platform.LINUX_ARM64,
                    target="production"  # Explicitly target production stage
                ),
                container_port=UI_PORT,
                log_driver=ecs.LogDrivers.aws_logs(
                    log_group=log_group,
                    stream_prefix=f'{ui_service_name}-service',
                    mode=ecs.AwsLogDriverMode.NON_BLOCKING
                ),
                environment={
                    "CONFIGURATION_API_ENDPOINT": f"http://{api_url}" if not api_url.startswith(('http://', 'https://')) else api_url,
                    "SUPERVISOR_AGENT_ENDPOINT": f"http://{supervisor_agent_url}" if not supervisor_agent_url.startswith(('http://', 'https://')) else supervisor_agent_url,
                    "SECRETS_MANAGER_ARN": cognito_resources.secret_arn,
                    "REGION": self.region,
                    "PROJECT_NAME": project_name,
                    "RATE_LIMIT_WINDOW_MS": str(self.get_optional_config('RateLimitWindowMs', 900000)),
                    "RATE_LIMIT_MAX_REQUESTS": str(self.get_optional_config('RateLimitMaxRequests', 100)),
                    # AWS Infrastructure Domain Whitelist (for VPC Lattice, ALB URLs)
                    "ALLOWED_AWS_DOMAINS": self.get_optional_config('AllowedAwsDomains', '.elb.amazonaws.com,.on.aws,.amazonaws.com'),
                    # CORS Origins - Will be updated with CloudFront URL after distribution creation
                    # For private mode, use the ALB URL or custom domain
                    "ALLOWED_ORIGINS": ""  # Placeholder, will be updated below
                },
            ),
        )

        # Configure health check
        ui_fargate_service.target_group.configure_health_check(
            enabled=True, path=UI_HEALTH_CHECK_PATH, healthy_http_codes="200"
        )

        # Speed up deployments
        ui_deregistration_delay = self.get_optional_config('UiDeregistrationDelay', UI_DEREGISTRATION_DELAY)
        ui_fargate_service.target_group.set_attribute(
            key="deregistration_delay.timeout_seconds",
            value=str(ui_deregistration_delay),
        )

        # Configure CPU architecture
        task_definition = ui_fargate_service.task_definition.node.default_child
        task_definition.add_override("Properties.RuntimePlatform.CpuArchitecture", "ARM64")
        task_definition.add_override("Properties.RuntimePlatform.OperatingSystemFamily", "LINUX")

        # Configure BLUE_GREEN deployment strategy
        ecs_service = ui_fargate_service.service.node.default_child
        ecs_service.add_override("Properties.DeploymentConfiguration.MinimumHealthyPercent", DEFAULT_MINIMUM_HEALTHY_PERCENT_BLUE_GREEN)
        ecs_service.add_override("Properties.DeploymentConfiguration.MaximumPercent", DEFAULT_MAXIMUM_PERCENT_BLUE_GREEN)

        # Grant access to secrets
        cognito_resources.secrets_manager_secret.grant_read(ui_fargate_service.task_definition.task_role)
        
        # Add logging permissions for the shared log group
        self.add_logs_permissions(ui_fargate_service.task_definition.task_role, [log_group.log_group_arn])

        # Set load balancer idle timeout to 30 minutes (1800 seconds)
        ui_fargate_service.load_balancer.set_attribute(
            key="idle_timeout.timeout_seconds",
            value="1800"
        )

        # Enable ALB access logging and connection logging using the mixin
        # This complies with AWS documentation best practices for ELB logging
        self.configure_alb_logging(
            load_balancer=ui_fargate_service.load_balancer,
            access_logs_bucket=self.access_logs_bucket,
            prefix="ui-alb"
        )

        # Configure additional ALB attributes for security and CloudFront integration
        # Reference: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/application-load-balancers.html
        
        # Enable HTTP/2 for better performance (default is true, but explicitly set)
        ui_fargate_service.load_balancer.set_attribute(
            key="routing.http2.enabled",
            value="true"
        )
        
        # Drop invalid header fields for security
        # Recommended for all ALBs, especially those behind CloudFront
        ui_fargate_service.load_balancer.set_attribute(
            key="routing.http.drop_invalid_header_fields.enabled",
            value="true"
        )
        
        # Enable desync mitigation in defensive mode
        # Protects against HTTP desync attacks
        ui_fargate_service.load_balancer.set_attribute(
            key="routing.http.desync_mitigation_mode",
            value="defensive"
        )
        
        # Preserve X-Forwarded-For client port
        # Helps with client identification through CloudFront
        ui_fargate_service.load_balancer.set_attribute(
            key="routing.http.xff_client_port.enabled",
            value="true"
        )
        
        # Add TLS version and cipher suite info to request headers
        # Useful for security monitoring and debugging
        ui_fargate_service.load_balancer.set_attribute(
            key="routing.http.x_amzn_tls_version_and_cipher_suite.enabled",
            value="true"
        )
        
        # Enable cross-zone load balancing for better distribution
        ui_fargate_service.load_balancer.set_attribute(
            key="load_balancing.cross_zone.enabled",
            value="true"
        )

        return ui_fargate_service

    def _configure_ui_security(self, ui_fargate_service: ecs_patterns.ApplicationLoadBalancedFargateService, ui_access_mode: str) -> None:
        """Configure security settings for the UI service based on access mode."""
        # Get the load balancer security group
        lb_security_group = ui_fargate_service.load_balancer.connections.security_groups[0]
        
        # Remove all existing ingress rules (including the default 0.0.0.0/0 rule)
        # This is a more reliable way to remove the default rule
        cfn_security_group = lb_security_group.node.default_child
        cfn_security_group.add_property_override("SecurityGroupIngress", [])
        
        if ui_access_mode == UI_ACCESS_MODE_PUBLIC:
            # Dynamically look up CloudFront managed prefix list for current region
            from aws_cdk import custom_resources as cr
            import aws_cdk.aws_iam as iam
            
            # Create a custom resource to look up the CloudFront prefix list by name
            prefix_list_lookup = cr.AwsCustomResource(
                self,
                "CloudFrontPrefixListLookup",
                on_create=cr.AwsSdkCall(
                    service="EC2",
                    action="describeManagedPrefixLists",
                    parameters={
                        "Filters": [
                            {
                                "Name": "prefix-list-name",
                                "Values": [CLOUDFRONT_MANAGED_PREFIX_LIST_NAME]
                            }
                        ]
                    },
                    physical_resource_id=cr.PhysicalResourceId.of("cloudfront-prefix-list-lookup")
                ),
                policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                    resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
                )
            )
            
            cloudfront_prefix_list_id = prefix_list_lookup.get_response_field("PrefixLists.0.PrefixListId")
            
            # Public mode: Allow access only from CloudFront managed prefix list
            lb_security_group.add_ingress_rule(
                peer=ec2.Peer.prefix_list(cloudfront_prefix_list_id),
                connection=ec2.Port.tcp(80),  # CloudFront connects via HTTP to ALB
                description="Allow HTTP from CloudFront"
            )
            lb_security_group.add_ingress_rule(
                peer=ec2.Peer.prefix_list(cloudfront_prefix_list_id),
                connection=ec2.Port.tcp(443),  # Also allow HTTPS for end-to-end encryption
                description="Allow HTTPS from CloudFront"
            )
        elif ui_access_mode == UI_ACCESS_MODE_PRIVATE:
            # Private mode: Configure prefix list access if specified
            try:
                ui_prefix_list = self.config.get('UIPrefixList')
                if ui_prefix_list:
                    for item in ui_prefix_list:
                        lb_security_group.add_ingress_rule(
                            peer=ec2.Peer.prefix_list(item),
                            connection=ec2.Port.tcp(443),
                            description=f"Allow HTTPS from prefix list {item}"
                        )
            except KeyError:
                # UIPrefixList not found in config - that's okay
                pass

        # Allow outbound HTTPS traffic to the OIDC provider
        lb_security_group.add_egress_rule(
            peer=ec2.Peer.any_ipv4(),
            connection=ec2.Port(
                protocol=ec2.Protocol.TCP,
                string_representation="443",
                from_port=443,
                to_port=443,
            ),
            description="Outbound HTTPS traffic to the OIDC provider",
        )

    def _create_waf_protection(self, 
                               project_name: str, 
                               ui_fargate_service: ecs_patterns.ApplicationLoadBalancedFargateService,
                               ui_access_mode: str) -> None:
        """Create WAF protection based on access mode."""
        # Only create ALB-level WAF in private mode
        # Public mode will use CloudFront-level WAF
        if ui_access_mode == UI_ACCESS_MODE_PRIVATE:
            waf_metric_name = f"{project_name}-{WAF_METRIC_NAME_PREFIX}-alb"
            waf_rule_metric_name = f"{project_name}-{WAF_METRIC_NAME_PREFIX}-alb-owasp"
            
            waf_protection = waf.CfnWebACL(
                self, 
                "ALBWAFProtection", 
                default_action=waf.CfnWebACL.DefaultActionProperty(allow={}), 
                scope="REGIONAL", 
                visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True, 
                    metric_name=waf_metric_name, 
                    sampled_requests_enabled=True
                ), 
                rules=[
                    waf.CfnWebACL.RuleProperty(
                        name="CRSRule", 
                        priority=0, 
                        statement=waf.CfnWebACL.StatementProperty(
                            managed_rule_group_statement=waf.CfnWebACL.ManagedRuleGroupStatementProperty(
                                vendor_name="AWS",
                                name="AWSManagedRulesCommonRuleSet"
                            )
                        ),
                        override_action=waf.CfnWebACL.OverrideActionProperty(none={}), 
                        visibility_config=waf.CfnWebACL.VisibilityConfigProperty(
                            cloud_watch_metrics_enabled=True, 
                            metric_name=waf_rule_metric_name, 
                            sampled_requests_enabled=True
                        )
                    )
                ]
            )

            # Associate WAF with the load balancer
            waf.CfnWebACLAssociation(
                self, 
                "ALBWebACLAssociation",
                resource_arn=ui_fargate_service.load_balancer.load_balancer_arn,
                web_acl_arn=waf_protection.attr_arn
            )

    def _create_cloudfront_integration(self, project_name: str, ui_fargate_service: ecs_patterns.ApplicationLoadBalancedFargateService) -> None:
        """Create CloudFront distribution with VPC origins for public access mode."""
        # Get prefix lists for CloudFront WAF
        try:
            ui_prefix_list = self.config.get('UIPrefixList')
            if ui_prefix_list is None:
                ui_prefix_list = []
        except KeyError:
            ui_prefix_list = []
        
        # Get geo-restriction configuration
        try:
            geo_restriction_countries = self.config.get('CloudFrontGeoRestrictionCountries')
        except KeyError:
            geo_restriction_countries = None
        
        # Get CloudFront price class configuration
        try:
            cloudfront_price_class = self.config.get('CloudFrontPriceClass')
        except KeyError:
            cloudfront_price_class = None

        # Create CloudFront construct
        self.cloudfront_construct = CloudFrontVpcOriginConstruct(
            self,
            "CloudFrontVpcOrigin",
            project_name=project_name,
            load_balancer=ui_fargate_service.load_balancer,
            access_logs_bucket=self.access_logs_bucket,
            prefix_lists=ui_prefix_list,
            geo_restriction_countries=geo_restriction_countries,
            price_class=cloudfront_price_class
        )
        
        # Store CloudFront distribution reference
        self.cloudfront_distribution = self.cloudfront_construct.distribution

    def _update_cors_origins_with_cloudfront(self, ui_fargate_service: ecs_patterns.ApplicationLoadBalancedFargateService) -> None:
        """Update the ECS task definition environment with CloudFront URL for CORS.
        
        Automatically includes the CloudFront distribution URL.
        Optionally appends additional origins from AllowedOrigins config if specified.
        """
        # Get the CloudFront domain name as a CDK token that will be resolved at deploy time
        cloudfront_url = f"https://{self.cloudfront_distribution.distribution_domain_name}"
        
        # Check if there are additional origins in the config file
        try:
            additional_origins = self.get_optional_config('AllowedOrigins', '')
            if additional_origins and additional_origins.strip():
                # Append custom domains to CloudFront URL
                allowed_origins = f"{cloudfront_url},{additional_origins}"
            else:
                allowed_origins = cloudfront_url
        except Exception:
            # If config read fails for any reason, just use CloudFront URL
            allowed_origins = cloudfront_url
        
        # Add the ALLOWED_ORIGINS environment variable to the container definition
        # This uses CDK's addEnvironment method which properly handles the CloudFormation template
        ui_fargate_service.task_definition.default_container.add_environment(
            "ALLOWED_ORIGINS",
            allowed_origins
        )
