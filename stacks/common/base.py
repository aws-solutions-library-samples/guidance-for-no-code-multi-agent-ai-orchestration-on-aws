"""
Base classes and common patterns for CDK stacks.

This module provides base classes that follow Python best practices:
- Single responsibility principle
- Proper error handling
- Type safety
- Clear documentation
"""

from typing import Dict, Any, Optional, List

import aws_cdk as cdk
from aws_cdk import (
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecr_assets as ecr_assets,
    aws_logs as logs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_iam as iam,
    Stack
)
from constructs import Construct

from helper.config import Config
from .exceptions import StackConfigurationError, ResourceCreationError
from .validators import ConfigValidator, AWSResourceValidator
from .mixins import IAMPolicyMixin, SecurityGroupMixin, VpcLatticeServiceMixin
from .mixins.blue_green_deployment import BlueGreenDeploymentMixin
from .constants import (
    DEFAULT_MINIMUM_HEALTHY_PERCENT_ROLLING,
    DEFAULT_MAXIMUM_PERCENT_ROLLING,
    DEFAULT_MINIMUM_HEALTHY_PERCENT_BLUE_GREEN,
    DEFAULT_MAXIMUM_PERCENT_BLUE_GREEN,
    DEFAULT_HEALTHY_THRESHOLD_COUNT,
    DEFAULT_UNHEALTHY_THRESHOLD_COUNT,
    DEFAULT_HEALTH_CHECK_INTERVAL,
    DEFAULT_HEALTH_CHECK_TIMEOUT
)

# Import data protection modules - use direct import path
try:
    from stacks.data_protection import (
        ManagedDataIdentifierRegistry,
        CustomDataIdentifierBuilder,
        DataIdentifierValidator,
        get_credentials_identifiers,
        get_pii_identifiers,
        get_custom_platform_identifiers,
        DataProtectionPolicyConfig,
        DataProtectionPolicyType
    )
except ImportError:
    # Fallback if import fails - data protection will be disabled
    ManagedDataIdentifierRegistry = None
    CustomDataIdentifierBuilder = None
    DataIdentifierValidator = None
    get_credentials_identifiers = None
    get_pii_identifiers = None
    get_custom_platform_identifiers = None
    DataProtectionPolicyConfig = None
    DataProtectionPolicyType = None


class BaseStack(Stack):
    """
    Base stack class with common functionality and validation.
    
    This class provides:
    - Configuration validation
    - Standardized resource creation
    - Error handling
    - Common utilities
    """
    
    def __init__(self, 
                 scope: Construct, 
                 construct_id: str,
                 config: Config,
                 **kwargs) -> None:
        """
        Initialize the base stack.
        
        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            config: Configuration object
            **kwargs: Additional keyword arguments for Stack
            
        Raises:
            StackConfigurationError: If configuration is invalid
        """
        super().__init__(scope, construct_id, **kwargs)
        self.config = config
        self._validate_config()
    
    def _validate_config(self) -> None:
        """
        Validate configuration parameters.
        
        Raises:
            StackConfigurationError: If configuration is invalid
        """
        if not isinstance(self.config, Config):
            raise StackConfigurationError(
                "Configuration must be a Config instance",
                config_key="config"
            )
    
    def create_log_group(self, 
                        name: str, 
                        retention_days: int = 30,
                        removal_policy: cdk.RemovalPolicy = cdk.RemovalPolicy.DESTROY) -> logs.LogGroup:
        """
        Create a standardized log group with validation.
        Supports both individual and shared log groups based on configuration.
        
        Args:
            name: Name for the log group (used for individual groups or as identifier for shared)
            retention_days: Log retention period in days
            removal_policy: Removal policy for the log group
            
        Returns:
            The created or referenced log group
            
        Raises:
            ResourceCreationError: If log group creation fails
        """
        try:
            ConfigValidator.validate_resource_name(name)
            
            # Check if shared logging is enabled
            use_shared_log_group = self.get_optional_config('UseSharedLogGroup', False)
            
            if use_shared_log_group:
                return self._create_or_reference_shared_log_group(retention_days, removal_policy)
            else:
                return self._create_individual_log_group(name, retention_days, removal_policy)
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create log group '{name}': {str(e)}",
                resource_type="LogGroup"
            )
    
    def _create_or_reference_shared_log_group(self, 
                                            retention_days: int,
                                            removal_policy: cdk.RemovalPolicy) -> logs.LogGroup:
        """
        Create or reference the shared log group based on stack type.
        Only the VPC stack creates the actual CloudFormation resource.
        All other stacks reference it by ARN to use proper CDK references.
        """
        # Check if this is the VPC stack (the designated creator of shared resources)
        if self.stack_name.endswith('-vpc'):
            # VPC stack creates the log group - this is handled in VpcStack directly
            shared_log_group_name = self.get_required_config('SharedLogGroupName')
            
            # Map retention days to CDK enum values
            retention_mapping = {
                1: logs.RetentionDays.ONE_DAY,
                3: logs.RetentionDays.THREE_DAYS,
                5: logs.RetentionDays.FIVE_DAYS,
                7: logs.RetentionDays.ONE_WEEK,
                14: logs.RetentionDays.TWO_WEEKS,
                30: logs.RetentionDays.ONE_MONTH,
                60: logs.RetentionDays.TWO_MONTHS,
                90: logs.RetentionDays.THREE_MONTHS,
                120: logs.RetentionDays.FOUR_MONTHS,
                150: logs.RetentionDays.FIVE_MONTHS,
                180: logs.RetentionDays.SIX_MONTHS,
                365: logs.RetentionDays.ONE_YEAR,
                400: logs.RetentionDays.THIRTEEN_MONTHS,
                545: logs.RetentionDays.EIGHTEEN_MONTHS,
                731: logs.RetentionDays.TWO_YEARS,
                1827: logs.RetentionDays.FIVE_YEARS,
                3653: logs.RetentionDays.TEN_YEARS
            }
            
            retention = retention_mapping.get(retention_days, logs.RetentionDays.ONE_MONTH)
            
            # Create the shared log group with explicit name
            shared_log_group = logs.LogGroup(
                self,
                "shared-log-group",
                log_group_name=shared_log_group_name,
                retention=retention,
                removal_policy=removal_policy
            )
            
            # Add data protection policy to shared log group if enabled
            self._create_log_group_data_protection_policy(shared_log_group, "shared-log-group-data-protection")
            
            return shared_log_group
        else:
            # All non-VPC stacks import the shared log group ARN from VPC stack
            # This uses proper CDK cross-stack references instead of hardcoded names
            try:
                shared_log_group_arn = cdk.Fn.import_value(
                    f"{self.get_required_config('ProjectName')}-SharedLogGroupArn"
                )
                return logs.LogGroup.from_log_group_arn(
                    self,
                    "shared-log-group-ref",
                    log_group_arn=shared_log_group_arn
                )
            except Exception:
                # Fallback to name-based reference if cross-stack reference fails
                shared_log_group_name = self.get_required_config('SharedLogGroupName')
                return logs.LogGroup.from_log_group_name(
                    self,
                    "shared-log-group-ref",
                    log_group_name=shared_log_group_name
                )
    
    def _create_individual_log_group(self, 
                                   name: str,
                                   retention_days: int,
                                   removal_policy: cdk.RemovalPolicy) -> logs.LogGroup:
        """
        Create an individual log group with automatic data protection policy.
        """
        # Map retention days to CDK enum values
        retention_mapping = {
            1: logs.RetentionDays.ONE_DAY,
            3: logs.RetentionDays.THREE_DAYS,
            5: logs.RetentionDays.FIVE_DAYS,
            7: logs.RetentionDays.ONE_WEEK,
            14: logs.RetentionDays.TWO_WEEKS,
            30: logs.RetentionDays.ONE_MONTH,
            60: logs.RetentionDays.TWO_MONTHS,
            90: logs.RetentionDays.THREE_MONTHS,
            120: logs.RetentionDays.FOUR_MONTHS,
            150: logs.RetentionDays.FIVE_MONTHS,
            180: logs.RetentionDays.SIX_MONTHS,
            365: logs.RetentionDays.ONE_YEAR,
            400: logs.RetentionDays.THIRTEEN_MONTHS,
            545: logs.RetentionDays.EIGHTEEN_MONTHS,
            731: logs.RetentionDays.TWO_YEARS,
            1827: logs.RetentionDays.FIVE_YEARS,
            3653: logs.RetentionDays.TEN_YEARS
        }
        
        retention = retention_mapping.get(retention_days, logs.RetentionDays.ONE_MONTH)
        
        log_group = logs.LogGroup(
            self, 
            f"{name}-log-group",
            # No explicit log group name - let CloudFormation auto-generate for better reusability
            retention=retention,
            removal_policy=removal_policy
        )
        
        # Add data protection policy if enabled
        self._create_log_group_data_protection_policy(log_group, f"{name}-data-protection")
        
        return log_group
    
    def _create_log_group_data_protection_policy(self, log_group: logs.LogGroup, policy_id: str) -> Optional[Any]:
        """
        Create a data protection policy for the log group if data protection is enabled.
        
        Args:
            log_group: The log group to protect
            policy_id: Unique identifier for the policy construct
            
        Returns:
            The created data protection policy or None if disabled
        """
        try:
            # Check if data protection is enabled in configuration
            if not self.config.is_data_protection_enabled():
                return None
            
            # Build data protection policy document for log group
            import json
            
            # Skip data protection if modules not available
            if not ManagedDataIdentifierRegistry or not get_custom_platform_identifiers:
                return None
            
            # Get managed identifiers from configuration
            managed_identifier_names = self.config.get_data_protection_managed_identifiers()
            managed_identifiers = []
            
            for identifier_name in managed_identifier_names:
                identifier = ManagedDataIdentifierRegistry.get_identifier_by_name(
                    identifier_name, self.region
                )
                if identifier:
                    managed_identifiers.append({
                        "Name": identifier_name,
                        "Arn": identifier.arn
                    })
            
            # Get custom identifiers from configuration
            custom_identifier_names = self.config.get_data_protection_custom_identifiers()
            custom_identifiers = []
            platform_identifiers = get_custom_platform_identifiers()
            
            for custom_name in custom_identifier_names:
                # Find matching custom identifier
                for custom_id in platform_identifiers:
                    if custom_id.name == custom_name:
                        custom_identifiers.append({
                            "Name": custom_id.name,
                            "DataIdentifier": {
                                "Regex": custom_id.regex,
                                "Keywords": custom_id.keywords or [],
                                "IgnoreWords": custom_id.ignore_words or [],
                                "MaximumMatchDistance": custom_id.maximum_match_distance or 50
                            }
                        })
                        break
            
            # Build all data identifiers
            all_data_identifiers = managed_identifiers + custom_identifiers
            
            if not all_data_identifiers:
                # No identifiers configured, skip data protection
                return None
            
            # Create the data protection policy document
            policy_document = {
                "Name": f"PlatformDataProtectionPolicy-{policy_id}",
                "Description": "Data protection policy for multi-agent AI platform log group",
                "Version": "2021-06-01", 
                "Statement": [
                    {
                        "Sid": "audit-policy",
                        "DataIdentifier": all_data_identifiers,
                        "Operation": {
                            "Audit": {
                                "FindingsDestination": {}
                            }
                        }
                    }
                ]
            }
            
            # Add audit findings destination using CloudWatch Logs - always enabled by default
            audit_log_group_name = self.config.get_audit_findings_log_group_name()
            if audit_log_group_name:
                # Create audit findings log group
                audit_log_group = logs.LogGroup(
                    self,
                    f"{policy_id}-audit-log-group",
                    log_group_name=audit_log_group_name,
                    retention=logs.RetentionDays.ONE_MONTH,
                    removal_policy=cdk.RemovalPolicy.DESTROY
                )
                
                # Use CloudWatch Logs ARN for audit findings destination
                audit_log_group_arn = f"arn:aws:logs:{self.region}:{self.account}:log-group:{audit_log_group_name}"
                policy_document["Statement"][0]["Operation"]["Audit"]["FindingsDestination"]["CloudWatchLogs"] = {
                    "LogGroup": audit_log_group_arn
                }
            
            # Convert to JSON string for CloudFormation
            policy_json = json.dumps(policy_document)
            
            # Use AwsCustomResource to directly call CloudWatch Logs API
            from aws_cdk import custom_resources as cr
            
            # Create custom resource to manage data protection policy
            data_protection_custom_resource = cr.AwsCustomResource(
                self,
                policy_id,
                on_create=cr.AwsSdkCall(
                    service="CloudWatchLogs",
                    action="putDataProtectionPolicy",
                    parameters={
                        "logGroupIdentifier": log_group.log_group_name,
                        "policyDocument": policy_json
                    },
                    physical_resource_id=cr.PhysicalResourceId.of(f"DataProtectionPolicy-{log_group.log_group_name}")
                ),
                on_update=cr.AwsSdkCall(
                    service="CloudWatchLogs", 
                    action="putDataProtectionPolicy",
                    parameters={
                        "logGroupIdentifier": log_group.log_group_name,
                        "policyDocument": policy_json
                    }
                ),
                on_delete=cr.AwsSdkCall(
                    service="CloudWatchLogs",
                    action="deleteDataProtectionPolicy",
                    parameters={
                        "logGroupIdentifier": log_group.log_group_name
                    }
                ),
                policy=cr.AwsCustomResourcePolicy.from_statements([
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=[
                            "logs:PutDataProtectionPolicy",
                            "logs:DeleteDataProtectionPolicy",
                            "logs:DescribeLogGroups"
                        ],
                        resources=[
                            f"arn:aws:logs:{self.region}:{self.account}:log-group:{log_group.log_group_name}",
                            f"arn:aws:logs:{self.region}:{self.account}:log-group:{log_group.log_group_name}:*"
                        ]
                    )
                ])
            )
            
            # Add dependency to ensure log group is created first
            data_protection_custom_resource.node.add_dependency(log_group)
            
            return data_protection_custom_resource
            
        except Exception as e:
            # Log error but don't fail stack creation if data protection fails
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to create data protection policy for log group: {str(e)}")
            return None
    
    def get_required_config(self, key: str) -> Any:
        """
        Get a required configuration value with validation.
        
        Args:
            key: Configuration key to retrieve
            
        Returns:
            The configuration value
            
        Raises:
            StackConfigurationError: If key is missing
        """
        try:
            value = self.config.get(key)
            if value is None:
                raise StackConfigurationError(
                    f"Required configuration key '{key}' is missing",
                    config_key=key
                )
            return value
        except Exception as e:
            raise StackConfigurationError(
                f"Error retrieving configuration key '{key}': {str(e)}",
                config_key=key
            )
    
    def get_optional_config(self, key: str, default_value: Any = None) -> Any:
        """
        Get an optional configuration value.
        
        Args:
            key: Configuration key to retrieve
            default_value: Default value if key is not found
            
        Returns:
            The configuration value or default
        """
        try:
            return self.config.get(key)
        except KeyError:
            return default_value
    
    def add_common_tags(self, resource: Any, additional_tags: Dict[str, str] = None) -> None:
        """
        Add common tags to a resource.
        
        Args:
            resource: The resource to tag
            additional_tags: Additional tags to add
        """
        common_tags = {
            "Environment": self.get_optional_config("Environment", "unknown"),
            "Project": self.get_optional_config("ProjectName", "default-project"),
            "ManagedBy": "CDK"
        }
        
        if additional_tags:
            common_tags.update(additional_tags)
        
        for key, value in common_tags.items():
            cdk.Tags.of(resource).add(key, value)
    
    def _get_kms_key_arn(self) -> str:
        """
        Get KMS key ARN using direct stack reference instead of import/export.
        This is more reliable and avoids naming mismatches.
        
        Returns:
            KMS key ARN for SSM parameter encryption
        """
        try:
            # Try to get KMS stack from app context (set in app.py)
            kms_stack = self.node.scope.node.try_get_context("kms_stack")
            if kms_stack and hasattr(kms_stack, 'ssm_parameter_key'):
                return kms_stack.ssm_parameter_key.key_arn
        except:
            pass
        
        # Fallback: Use wildcard ARN for KMS permissions
        # This allows access to any KMS key in the account, which is more flexible
        # but less precise. For production, consider using specific key ARNs.
        return f"arn:aws:kms:{self.region}:{self.account}:key/*"


class FargateServiceStack(BaseStack, VpcLatticeServiceMixin, SecurityGroupMixin, IAMPolicyMixin, BlueGreenDeploymentMixin):
    """
    Base class for Fargate services with VPC Lattice integration.
    
    This class provides:
    - Fargate service creation and management
    - VPC Lattice integration
    - Security group management
    - IAM policy management
    """
    
    def __init__(self,
                 scope: Construct,
                 construct_id: str,
                 vpc: ec2.Vpc,
                 cluster: ecs.Cluster,
                 service_network_arn: str,
                 config: Config,
                 **kwargs) -> None:
        """
        Initialize the Fargate service stack.
        
        Args:
            scope: CDK scope
            construct_id: Unique identifier for this construct
            vpc: VPC to deploy into
            cluster: ECS cluster
            service_network_arn: VPC Lattice service network ARN (optional for ALB-only services)
            config: Configuration object
            **kwargs: Additional keyword arguments
        """
        super().__init__(scope, construct_id, config, **kwargs)
        
        # Validate inputs
        AWSResourceValidator.validate_vpc(vpc)
        # Only validate service_network_arn if it's not empty (for ALB-only services)
        if service_network_arn:
            AWSResourceValidator.validate_arn(service_network_arn, "vpc-lattice")
        
        self.vpc = vpc
        self.cluster = cluster
        self.service_network_arn = service_network_arn
    
    def create_fargate_service(self,
                               service_name: str,
                               container_image_path: str,
                               port: int,
                               health_check_path: str = "/health",
                               cpu: int = 2048,
                               memory: int = 4096,
                               desired_count: int = 1,
                               environment_vars: Optional[Dict[str, str]] = None,
                               platform: ecr_assets.Platform = ecr_assets.Platform.LINUX_ARM64,
                               dockerfile_path: Optional[str] = None,
                               vpc_lattice_service_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a complete Fargate service with VPC Lattice integration.
        
        Args:
            service_name: Name for the service
            container_image_path: Path to container image
            port: Container port
            health_check_path: Health check endpoint
            cpu: CPU units (1024 = 1 vCPU)
            memory: Memory in MiB
            desired_count: Number of tasks to run
            environment_vars: Environment variables for the container
            platform: Container platform
            
        Returns:
            Dictionary containing all created resources
            
        Raises:
            ResourceCreationError: If service creation fails
        """
        try:
            # Validate inputs
            ConfigValidator.validate_resource_name(service_name)
            ConfigValidator.validate_port_range(port)
            ConfigValidator.validate_environment_vars(environment_vars)
            
            if not health_check_path.startswith('/'):
                raise ValueError("Health check path must start with '/'")
            
            # Create log group
            log_group = self.create_log_group(f"{service_name}-service")
            
            # Create security group
            security_group = self.create_vpc_lattice_security_group(
                service_name, self.vpc, port, self.region
            )
            
            # Create task definition
            task_definition = self._create_task_definition(
                service_name, cpu, memory, platform
            )
            
            # Create VPC Lattice resources with comprehensive access logging enabled
            # Pass both static service_name for CDK IDs and dynamic vpc_lattice_service_name for AWS resources
            lattice_resources = self.create_vpc_lattice_service(
                service_name, self.vpc, self.service_network_arn,
                port, health_check_path, enable_access_logging=True,
                aws_service_name=vpc_lattice_service_name
            )
            
            # Add container to task definition
            container = self._add_container_to_task(
                task_definition, service_name, container_image_path,
                port, log_group, environment_vars, 
                lattice_resources["service"].attr_dns_entry_domain_name,
                platform, dockerfile_path
            )
            
            # Create ECS service
            ecs_service = self._create_ecs_service(
                service_name, task_definition, security_group,
                desired_count, lattice_resources, port
            )
            
            # Configure IAM permissions
            self._configure_task_permissions(
                task_definition, [log_group.log_group_arn]
            )
            
            # CloudFormation output removed as requested - not needed for reusable template
            # self._create_service_output(service_name, lattice_resources["service"])
            
            # Add tags
            self.add_common_tags(ecs_service, {
                "ServiceName": service_name,
                "ServiceType": "Fargate"
            })
            
            return {
                "ecs_service": ecs_service,
                "task_definition": task_definition,
                "container": container,
                "log_group": log_group,
                "security_group": security_group,
                **lattice_resources
            }
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create Fargate service '{service_name}': {str(e)}",
                resource_type="FargateService"
            )
    
    def _create_task_definition(self,
                               service_name: str,
                               cpu: int,
                               memory: int,
                               platform: ecr_assets.Platform) -> ecs.FargateTaskDefinition:
        """Create ECS task definition."""
        runtime_platform = ecs.RuntimePlatform(
            cpu_architecture=ecs.CpuArchitecture.ARM64,
            operating_system_family=ecs.OperatingSystemFamily.LINUX
        )
        
        return ecs.FargateTaskDefinition(
            self,
            f"{service_name}-task-definition",
            cpu=cpu,
            memory_limit_mib=memory,
            runtime_platform=runtime_platform,
            family=f"{service_name}-task-definition"  # Set explicit generic family name
        )
    
    def _add_container_to_task(self,
                              task_definition: ecs.FargateTaskDefinition,
                              service_name: str,
                              container_image_path: str,
                              port: int,
                              log_group: logs.LogGroup,
                              environment_vars: Optional[Dict[str, str]],
                              lattice_dns: str,
                              platform: ecr_assets.Platform,
                              dockerfile_path: Optional[str] = None) -> ecs.ContainerDefinition:
        """Add container to task definition."""
        env_vars = environment_vars or {}
        env_vars["HOSTED_DNS"] = lattice_dns
        env_vars["SERVICE_NAME"] = service_name
        env_vars["ECS_CONTAINER_STOP_TIMEOUT"] = "2s"  # Fast container stop for rapid deployments
        
        # Create asset parameters for production build
        asset_params = {
            "platform": platform,
            "target": "production",  # Explicitly target production stage
            "build_args": {
                "BUILD_TARGET": "production"  # Set build argument for production
            }
        }
        if dockerfile_path:
            asset_params["file"] = dockerfile_path
            
        return task_definition.add_container(
            f"{service_name}-container",
            image=ecs.ContainerImage.from_asset(
                container_image_path, 
                **asset_params
            ),
            logging=ecs.LogDrivers.aws_logs(
                log_group=log_group,
                stream_prefix=f'{service_name}-service',
                mode=ecs.AwsLogDriverMode.NON_BLOCKING
            ),
            port_mappings=[ecs.PortMapping(
                container_port=port, 
                name=f'{service_name}-port-{port}-web'
            )],
            environment=env_vars,
            stop_timeout=cdk.Duration.seconds(2)  # Stop container within 2 seconds
        )
    
    def _create_ecs_service(self,
                           service_name: str,
                           task_definition: ecs.FargateTaskDefinition,
                           security_group: ec2.SecurityGroup,
                           desired_count: int,
                           lattice_resources: Dict[str, Any],
                           port: int,
                           force_new_deployment: bool = False) -> ecs.CfnService:
        """Create ECS service with VPC Lattice configuration and fast rolling deployment behavior.
        
        Args:
            force_new_deployment: When True, forces a new deployment even without task definition changes.
                                 This enables CloudFormation stack updates to trigger redeployment (e.g., for update button).
                                 Default is False for non-agent services.
        """
        # Use rolling deployment with 0% minimum for fastest deployments
        # This allows all previous tasks to be killed during deployment for speed
        minimum_healthy_percent = 0  # Allow all tasks to be replaced for fastest deployment
        maximum_percent = 200        # Allow temporary extra capacity during deployment
        
        # Create ECS deployment configuration for fast rolling deployment
        # - 0% minimum allows killing all previous tasks for speed
        # - 100% maximum prevents extra capacity usage
        deployment_config = ecs.CfnService.DeploymentConfigurationProperty(
            minimum_healthy_percent=minimum_healthy_percent,
            maximum_percent=maximum_percent,
            deployment_circuit_breaker=ecs.CfnService.DeploymentCircuitBreakerProperty(
                enable=True,
                rollback=True
            )
        )
        
        ecs_service = ecs.CfnService(
            self,
            f"{service_name}-ecs-service",
            cluster=self.cluster.cluster_arn,
            task_definition=task_definition.task_definition_arn,
            desired_count=desired_count,
            launch_type="FARGATE",
            # Native ECS deployment controller for rolling updates
            deployment_controller=ecs.CfnService.DeploymentControllerProperty(
                type="ECS"
            ),
            network_configuration=ecs.CfnService.NetworkConfigurationProperty(
                awsvpc_configuration=ecs.CfnService.AwsVpcConfigurationProperty(
                    subnets=[subnet.subnet_id for subnet in self.vpc.private_subnets],
                    security_groups=[security_group.security_group_id],
                    assign_public_ip="DISABLED"
                )
            ),
            deployment_configuration=deployment_config,
            health_check_grace_period_seconds=15,  # Reduced for faster deployments
            force_new_deployment=force_new_deployment,  # Configurable per service type
            vpc_lattice_configurations=[
                ecs.CfnService.VpcLatticeConfigurationProperty(
                    role_arn=lattice_resources["ecs_service_role"].role_arn,
                    target_group_arn=lattice_resources["target_group"].attr_arn,
                    port_name=f"{service_name}-port-{port}-web"
                )
            ]
        )
        
        # Ensure ECS service depends on IAM role to prevent dangling tasks during deletion
        # The IAM role must remain until the ECS service is fully deleted
        ecs_service.add_dependency(lattice_resources["ecs_service_role"].node.default_child)
        
        return ecs_service
    
    def _configure_task_permissions(self,
                                   task_definition: ecs.FargateTaskDefinition,
                                   log_group_arns: List[str],
                                   service_type: str = None) -> None:
        """
        Configure IAM permissions for the task with optional permissions boundary.
        
        Args:
            task_definition: The ECS task definition
            log_group_arns: List of log group ARNs to grant access to
            service_type: Optional service type for boundary policy selection
        """
        # Apply permissions boundary if service type is provided
        if service_type:
            self._apply_permissions_boundary_to_task_role(task_definition.task_role, service_type)
        
        # EXECUTION ROLE permissions (needed for ECS agent to start containers)
        self.add_ecr_permissions(task_definition.execution_role)  # ← FIXED: ECR permissions go to execution role
        self.add_logs_permissions(task_definition.execution_role, log_group_arns)  # ← FIXED: Logging goes to execution role
        
        # TASK ROLE permissions (needed by application running inside container)
        self.add_bedrock_permissions(task_definition.task_role)
        # Get KMS key from KMS stack via direct reference (no import/export needed)
        # This is more reliable than import/export and avoids naming mismatches
        kms_key_arn = self._get_kms_key_arn()
        self.add_ssm_permissions(task_definition.task_role, kms_key_arn=kms_key_arn)
        self.add_vpc_lattice_permissions(task_definition.task_role)
        self.add_ecs_task_permissions(task_definition.task_role)
        self.add_ec2_network_permissions(task_definition.task_role)
        # Aurora database integration permissions
        self.add_rds_data_permissions(task_definition.task_role)
        self.add_secrets_manager_permissions(task_definition.task_role)
        # DynamoDB and S3 read permissions for generic agent functionality
        self.add_dynamodb_read_permissions(task_definition.task_role)
        self.add_s3_read_permissions(task_definition.task_role)
    
    def _apply_permissions_boundary_to_task_role(self, role: iam.Role, service_type: str) -> None:
        """
        Apply the appropriate permissions boundary to a task role based on service type.
        
        Args:
            role: The IAM role to apply boundary to
            service_type: Service type from ServiceType enum
        """
        # Import boundary policy ARNs from IAM boundaries stack
        try:
            if service_type == "agent_service":
                boundary_arn = cdk.Fn.import_value(f"{self.config._environment}-AgentServiceBoundaryArn")
            elif service_type == "configuration_api":
                boundary_arn = cdk.Fn.import_value(f"{self.config._environment}-ConfigurationApiBoundaryArn")
            elif service_type == "supervisor_agent":
                boundary_arn = cdk.Fn.import_value(f"{self.config._environment}-SupervisorAgentBoundaryArn")
            else:
                # If unknown service type, skip boundary application
                return
            
            # Apply boundary to the role
            self.apply_permissions_boundary(role, boundary_arn)
            
        except Exception as e:
            # Log warning but don't fail deployment if boundary import fails
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to apply permissions boundary for service type {service_type}: {str(e)}")
    
    def create_alb_fargate_service(self,
                                   service_name: str,
                                   container_image_path: str,
                                   port: int,
                                   health_check_path: str = "/health",
                                   cpu: int = 2048,
                                   memory: int = 4096,
                                   desired_count: int = 1,
                                   environment_vars: Optional[Dict[str, str]] = None,
                                   platform: ecr_assets.Platform = ecr_assets.Platform.LINUX_ARM64,
                                   dockerfile_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a complete Fargate service with Application Load Balancer.
        
        Args:
            service_name: Name for the service
            container_image_path: Path to container image
            port: Container port
            health_check_path: Health check endpoint
            cpu: CPU units (1024 = 1 vCPU)
            memory: Memory in MiB
            desired_count: Number of tasks to run
            environment_vars: Environment variables for the container
            platform: Container platform
            
        Returns:
            Dictionary containing all created resources
            
        Raises:
            ResourceCreationError: If service creation fails
        """
        try:
            # Validate inputs
            ConfigValidator.validate_resource_name(service_name)
            ConfigValidator.validate_port_range(port)
            ConfigValidator.validate_environment_vars(environment_vars)
            
            if not health_check_path.startswith('/'):
                raise ValueError("Health check path must start with '/'")
            
            # Create log group
            log_group = self.create_log_group(f"{service_name}-service")
            
            # Create ALB and related resources
            alb_resources = self._create_alb_resources(service_name, port, health_check_path)
            
            # Create task definition
            task_definition = self._create_task_definition(
                service_name, cpu, memory, platform
            )
            
            # Add container to task definition
            container = self._add_alb_container_to_task(
                task_definition, service_name, container_image_path,
                port, log_group, environment_vars, platform, dockerfile_path
            )
            
            # Create ECS service for ALB
            ecs_service = self._create_alb_ecs_service(
                service_name, task_definition, alb_resources["security_group"],
                desired_count, alb_resources["target_group"]
            )
            
            # Configure IAM permissions (without VPC Lattice permissions)
            self._configure_alb_task_permissions(
                task_definition, [log_group.log_group_arn]
            )
            
            # Create CloudFormation output
            self._create_alb_service_output(service_name, alb_resources["load_balancer"])
            
            # Add tags
            self.add_common_tags(ecs_service, {
                "ServiceName": service_name,
                "ServiceType": "Fargate",
                "LoadBalancer": "ALB"
            })
            
            return {
                "ecs_service": ecs_service,
                "task_definition": task_definition,
                "container": container,
                "log_group": log_group,
                **alb_resources
            }
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create ALB Fargate service '{service_name}': {str(e)}",
                resource_type="ALBFargateService"
            )
    
    def _create_alb_resources(self, service_name: str, port: int, health_check_path: str) -> Dict[str, Any]:
        """Create Application Load Balancer and related resources."""
        # Create security group for ALB
        alb_security_group = ec2.SecurityGroup(
            self,
            f"{service_name}-alb-security-group",
            vpc=self.vpc,
            description=f"Security group for {service_name} ALB",
            allow_all_outbound=True
        )
        
        # Allow HTTP traffic from VPC CIDR only (internal-facing)
        alb_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP traffic from VPC CIDR"
        )
        
        # Create security group for ECS tasks
        ecs_security_group = ec2.SecurityGroup(
            self,
            f"{service_name}-ecs-security-group",
            vpc=self.vpc,
            description=f"Security group for {service_name} ECS tasks",
            allow_all_outbound=True
        )
        
        # Allow traffic from ALB to ECS tasks
        ecs_security_group.add_ingress_rule(
            peer=ec2.Peer.security_group_id(alb_security_group.security_group_id),
            connection=ec2.Port.tcp(port),
            description=f"Allow traffic from ALB to ECS tasks on port {port}"
        )
        
        # Create shorter names for AWS resource limits (32 chars max)
        short_name = service_name[-28:] if len(service_name) > 28 else service_name
        alb_name = f"{short_name}-alb"[:32]
        tg_name = f"{short_name}-tg"[:32]
        
        # Create Application Load Balancer (internal-only)
        load_balancer = elbv2.ApplicationLoadBalancer(
            self,
            f"{service_name}-alb",
            vpc=self.vpc,
            internet_facing=False,
            security_group=alb_security_group,
            load_balancer_name=alb_name
        )
        
        # Set load balancer idle timeout to 30 minutes (1800 seconds)
        load_balancer.set_attribute(
            key="idle_timeout.timeout_seconds",
            value="1800"
        )
        
        # Create target group
        target_group = elbv2.ApplicationTargetGroup(
            self,
            f"{service_name}-target-group",
            vpc=self.vpc,
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
            target_group_name=tg_name
        )
        
        # Create listener
        listener = load_balancer.add_listener(
            f"{service_name}-listener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[target_group]
        )
        
        return {
            "load_balancer": load_balancer,
            "target_group": target_group,
            "listener": listener,
            "security_group": ecs_security_group,
            "alb_security_group": alb_security_group
        }
    
    def _add_alb_container_to_task(self,
                                   task_definition: ecs.FargateTaskDefinition,
                                   service_name: str,
                                   container_image_path: str,
                                   port: int,
                                   log_group: logs.LogGroup,
                                   environment_vars: Optional[Dict[str, str]],
                                   platform: ecr_assets.Platform,
                                   dockerfile_path: Optional[str] = None,
                                   alb_dns: Optional[str] = None) -> ecs.ContainerDefinition:
        """Add container to task definition for ALB setup."""
        env_vars = environment_vars or {}
        env_vars["SERVICE_NAME"] = service_name
        env_vars["ECS_CONTAINER_STOP_TIMEOUT"] = "2s"  # Fast container stop for rapid deployments
        
        # Add ALB DNS as HOSTED_DNS if provided
        if alb_dns:
            env_vars["HOSTED_DNS"] = f"http://{alb_dns}"
        
        # Create asset parameters for production build
        asset_params = {
            "platform": platform,
            "target": "production",  # Explicitly target production stage
            "build_args": {
                "BUILD_TARGET": "production"  # Set build argument for production
            }
        }
        if dockerfile_path:
            asset_params["file"] = dockerfile_path
        
        return task_definition.add_container(
            f"{service_name}-container",
            image=ecs.ContainerImage.from_asset(
                container_image_path, 
                **asset_params
            ),
            logging=ecs.LogDrivers.aws_logs(
                log_group=log_group,
                stream_prefix=f'{service_name}-service',
                mode=ecs.AwsLogDriverMode.NON_BLOCKING
            ),
            port_mappings=[ecs.PortMapping(
                container_port=port,
                protocol=ecs.Protocol.TCP
            )],
            environment=env_vars,
            stop_timeout=cdk.Duration.seconds(2)  # Stop container within 2 seconds
        )
    
    def _create_alb_ecs_service(self,
                               service_name: str,
                               task_definition: ecs.FargateTaskDefinition,
                               security_group: ec2.SecurityGroup,
                               desired_count: int,
                               target_group: elbv2.ApplicationTargetGroup,
                               force_new_deployment: bool = False) -> ecs.FargateService:
        """Create ECS service with ALB integration."""
        # Circuit breaker is always enabled with rollback for reliability
        minimum_healthy_percent = self.get_optional_config('MinimumHealthyPercent', DEFAULT_MINIMUM_HEALTHY_PERCENT_ROLLING)
        maximum_percent = self.get_optional_config('MaximumPercent', DEFAULT_MAXIMUM_PERCENT_ROLLING)
        
        service = ecs.FargateService(
            self,
            f"{service_name}-ecs-service",
            cluster=self.cluster,
            task_definition=task_definition,
            desired_count=desired_count,
            vpc_subnets=ec2.SubnetSelection(subnets=self.vpc.private_subnets),
            security_groups=[security_group],
            assign_public_ip=False,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            min_healthy_percent=minimum_healthy_percent,
            max_healthy_percent=maximum_percent,
            # No explicit service_name - let CloudFormation auto-generate for uniqueness across stacks
            health_check_grace_period=cdk.Duration.seconds(120)
        )
        
        # Attach the service to the target group
        service.attach_to_application_target_group(target_group)
        
        # Set force_new_deployment on the underlying CFN resource if enabled
        if force_new_deployment:
            cfn_service = service.node.default_child
            cfn_service.force_new_deployment = True
        
        return service
    
    def _configure_alb_task_permissions(self,
                                       task_definition: ecs.FargateTaskDefinition,
                                       log_group_arns: List[str]) -> None:
        """Configure IAM permissions for the task (includes VPC Lattice permissions for service discovery)."""
        # Get KMS key ARN using direct reference instead of import/export
        kms_key_arn = self._get_kms_key_arn()
        
        # EXECUTION ROLE permissions (needed for ECS agent to start containers)
        self.add_ecr_permissions(task_definition.execution_role)  # ← FIXED: ECR permissions go to execution role
        self.add_logs_permissions(task_definition.execution_role, log_group_arns)  # ← FIXED: Logging goes to execution role
        
        # TASK ROLE permissions (needed by application running inside container)
        self.add_bedrock_permissions(task_definition.task_role)
        self.add_ssm_permissions(task_definition.task_role, kms_key_arn=kms_key_arn)
        self.add_vpc_lattice_permissions(task_definition.task_role)  # Added for service discovery
        self.add_ecs_task_permissions(task_definition.task_role)
        self.add_ec2_network_permissions(task_definition.task_role)
        # Aurora database integration permissions
        self.add_rds_data_permissions(task_definition.task_role)
        self.add_secrets_manager_permissions(task_definition.task_role)
        # DynamoDB and S3 read permissions for generic agent functionality
        self.add_dynamodb_read_permissions(task_definition.task_role)
        self.add_s3_read_permissions(task_definition.task_role)
    
    def _create_alb_service_output(self, service_name: str, load_balancer: elbv2.ApplicationLoadBalancer) -> None:
        """Create CloudFormation output for the ALB service."""
        cdk.CfnOutput(
            self,
            f"{service_name}-alb-dns",
            description=f"DNS of {service_name} service through Application Load Balancer",
            value=load_balancer.load_balancer_dns_name
            # No export_name - avoids import/export dependencies between stacks
        )

    def _create_service_output(self, service_name: str, lattice_service) -> None:
        """Create CloudFormation output for the service."""
        cdk.CfnOutput(
            self,
            f"{service_name}-service-dns",
            description=f"DNS of {service_name} service through VPC Lattice",
            value=lattice_service.attr_dns_entry_domain_name
            # No export_name - removed as requested
        )
    
    def create_alb_vpc_lattice_fargate_service(self,
                                              service_name: str,
                                              container_image_path: str,
                                              port: int,
                                              health_check_path: str = "/health",
                                              cpu: int = 2048,
                                              memory: int = 4096,
                                              desired_count: int = 1,
                                              environment_vars: Optional[Dict[str, str]] = None,
                                              platform: ecr_assets.Platform = ecr_assets.Platform.LINUX_ARM64,
                                              dockerfile_path: Optional[str] = None,
                                              vpc_lattice_service_name: Optional[str] = None,
                                              force_new_deployment: bool = False) -> Dict[str, Any]:
        """
        Create a Fargate service with ALB and VPC Lattice integration.
        
        This method creates a hybrid architecture that places an Application Load Balancer
        between VPC Lattice and ECS tasks. This solves VPC Lattice's hardcoded 60-second
        idle timeout by leveraging ALB's configurable timeout (up to 4000 seconds).
        
        Architecture flow: VPC Lattice → ALB (30min timeout) → ECS Tasks
        
        Args:
            service_name: Name for the service
            container_image_path: Path to container image
            port: Container port
            health_check_path: Health check endpoint
            cpu: CPU units (1024 = 1 vCPU)
            memory: Memory in MiB
            desired_count: Number of tasks to run
            environment_vars: Environment variables for the container
            platform: Container platform
            dockerfile_path: Optional dockerfile path
            vpc_lattice_service_name: Optional service name for VPC Lattice
            
        Returns:
            Dictionary containing all created resources
            
        Raises:
            ResourceCreationError: If service creation fails
        """
        try:
            # Validate inputs
            ConfigValidator.validate_resource_name(service_name)
            ConfigValidator.validate_port_range(port)
            ConfigValidator.validate_environment_vars(environment_vars)
            
            if not health_check_path.startswith('/'):
                raise ValueError("Health check path must start with '/'")
            
            # Create log group
            log_group = self.create_log_group(f"{service_name}-service")
            
            # Create ALB resources with extended timeout
            alb_resources = self._create_alb_resources_for_vpc_lattice(
                service_name, port, health_check_path
            )
            
            # Create VPC Lattice service that targets the ALB
            lattice_resources = self._create_vpc_lattice_service_for_alb(
                service_name, alb_resources["load_balancer"], 
                health_check_path, vpc_lattice_service_name
            )
            
            # Create task definition
            task_definition = self._create_task_definition(
                service_name, cpu, memory, platform
            )
            
            # Add container to task definition with VPC Lattice DNS
            container = self._add_container_to_task(
                task_definition, service_name, container_image_path,
                port, log_group, environment_vars,
                lattice_resources["service"].attr_dns_entry_domain_name,
                platform, dockerfile_path
            )
            
            # Create ECS service that targets the ALB
            ecs_service = self._create_alb_ecs_service(
                service_name, task_definition, alb_resources["security_group"],
                desired_count, alb_resources["target_group"], force_new_deployment
            )
            
            # Configure IAM permissions
            self._configure_alb_task_permissions(
                task_definition, [log_group.log_group_arn]
            )
            
            # Create CloudFormation output for VPC Lattice service
            self._create_service_output(service_name, lattice_resources["service"])
            
            # Add tags
            self.add_common_tags(ecs_service, {
                "ServiceName": service_name,
                "ServiceType": "Fargate",
                "LoadBalancer": "ALB",
                "ServiceMesh": "VPCLattice"
            })
            
            return {
                "ecs_service": ecs_service,
                "task_definition": task_definition,
                "container": container,
                "log_group": log_group,
                **alb_resources,
                **lattice_resources
            }
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create ALB-VPC Lattice Fargate service '{service_name}': {str(e)}",
                resource_type="ALBVPCLatticeFargateService"
            )
    
    def _create_alb_resources_for_vpc_lattice(self, service_name: str, port: int, health_check_path: str) -> Dict[str, Any]:
        """Create ALB resources optimized for VPC Lattice integration."""
        # Create security group for ALB (allows ingress from VPC Lattice)
        alb_security_group = ec2.SecurityGroup(
            self,
            f"{service_name}-alb-security-group",
            vpc=self.vpc,
            description=f"Security group for {service_name} ALB (VPC Lattice integration)",
            allow_all_outbound=True
        )
        
        # Allow HTTP traffic from VPC Lattice service network
        # VPC Lattice uses the service network CIDR for routing
        alb_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(self.vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP traffic from VPC Lattice via VPC CIDR"
        )
        
        # Create security group for ECS tasks  
        ecs_security_group = ec2.SecurityGroup(
            self,
            f"{service_name}-ecs-security-group", 
            vpc=self.vpc,
            description=f"Security group for {service_name} ECS tasks (ALB targets)",
            allow_all_outbound=True
        )
        
        # Allow traffic from ALB to ECS tasks
        ecs_security_group.add_ingress_rule(
            peer=ec2.Peer.security_group_id(alb_security_group.security_group_id),
            connection=ec2.Port.tcp(port),
            description=f"Allow traffic from ALB to ECS tasks on port {port}"
        )
        
        # Create ALB with extended idle timeout for long-running operations
        load_balancer = elbv2.ApplicationLoadBalancer(
            self,
            f"{service_name}-alb",
            vpc=self.vpc,
            internet_facing=False,  # Internal ALB for VPC Lattice integration
            security_group=alb_security_group
            # No explicit load_balancer_name - let CloudFormation auto-generate for uniqueness across stacks
        )
        
        # Set ALB idle timeout to 30 minutes (1800 seconds) to handle long-running agent operations
        load_balancer.set_attribute(
            key="idle_timeout.timeout_seconds",
            value="1800"
        )
        
        # Create target group for ECS tasks
        target_group = elbv2.ApplicationTargetGroup(
            self,
            f"{service_name}-target-group",
            vpc=self.vpc,
            port=port,
            protocol=elbv2.ApplicationProtocol.HTTP,
            target_type=elbv2.TargetType.IP,
            health_check=elbv2.HealthCheck(
                path=health_check_path,
                interval=cdk.Duration.seconds(DEFAULT_HEALTH_CHECK_INTERVAL),
                timeout=cdk.Duration.seconds(DEFAULT_HEALTH_CHECK_TIMEOUT),
                healthy_threshold_count=DEFAULT_HEALTHY_THRESHOLD_COUNT,
                unhealthy_threshold_count=DEFAULT_UNHEALTHY_THRESHOLD_COUNT
            )
            # No explicit target_group_name - let CloudFormation auto-generate for uniqueness across stacks
        )
        
        # Create listener
        listener = load_balancer.add_listener(
            f"{service_name}-listener",
            port=80,
            protocol=elbv2.ApplicationProtocol.HTTP,
            default_target_groups=[target_group]
        )
        
        return {
            "load_balancer": load_balancer,
            "target_group": target_group,
            "listener": listener,
            "security_group": ecs_security_group,
            "alb_security_group": alb_security_group
        }
    
    def _create_vpc_lattice_service_for_alb(self, 
                                           service_name: str,
                                           load_balancer: elbv2.ApplicationLoadBalancer,
                                           health_check_path: str,
                                           vpc_lattice_service_name: Optional[str] = None) -> Dict[str, Any]:
        """Create VPC Lattice service that targets an ALB instead of ECS tasks directly."""
        from aws_cdk import aws_vpclattice as vpclattice
        
        # Create VPC Lattice Service
        actual_service_name = vpc_lattice_service_name if vpc_lattice_service_name else service_name.replace("_", "-")
        
        lattice_service = vpclattice.CfnService(
            self,
            f"{service_name}-lattice-service",
            # No explicit name - let CloudFormation auto-generate for VPC Lattice naming compliance
            auth_type="NONE"
        )
        
        # Create target group that targets the ALB
        # Note: ALB target groups don't support health check config - ALB handles health checks to ECS tasks
        target_group = vpclattice.CfnTargetGroup(
            self,
            f"{service_name}-lattice-target-group",
            # No explicit name - let CloudFormation auto-generate for VPC Lattice naming compliance
            type="ALB",  # Target type is ALB instead of IP
            config=vpclattice.CfnTargetGroup.TargetGroupConfigProperty(
                port=80,  # ALB listens on port 80
                protocol="HTTP",
                vpc_identifier=self.vpc.vpc_id
                # No health_check config - ALB target groups don't support this
            ),
            # Target the ALB instead of ECS tasks
            targets=[
                vpclattice.CfnTargetGroup.TargetProperty(
                    id=load_balancer.load_balancer_arn,
                    port=80
                )
            ]
        )
        
        # Create listener
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
        
        # Associate with service network
        service_network_association = vpclattice.CfnServiceNetworkServiceAssociation(
            self,
            f"{service_name}-service-network-association",
            service_identifier=lattice_service.attr_id,
            service_network_identifier=self.service_network_arn
        )
        
        # Set up dependencies
        listener.add_dependency(target_group)
        service_network_association.add_dependency(lattice_service)
        
        return {
            "service": lattice_service,
            "lattice_target_group": target_group,
            "lattice_listener": listener,
            "service_network_association": service_network_association
        }
    
    def create_blue_green_alb_fargate_service(self,
                                             service_name: str,
                                             container_image_path: str,
                                             port: int,
                                             health_check_path: str = "/health",
                                             cpu: int = 2048,
                                             memory: int = 4096,
                                             desired_count: int = 1,
                                             environment_vars: Optional[Dict[str, str]] = None,
                                             platform: ecr_assets.Platform = ecr_assets.Platform.LINUX_ARM64,
                                             dockerfile_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a complete Fargate service with ALB and native blue-green deployment.
        
        This method creates:
        - Two target groups (primary and secondary for blue-green switching)
        - Application Load Balancer
        - ECS service with native blue-green deployment configuration
        - Fast 5-second deregistration delay for rapid deployments
        
        Args:
            service_name: Name for the service
            container_image_path: Path to container image
            port: Container port
            health_check_path: Health check endpoint
            cpu: CPU units (1024 = 1 vCPU)
            memory: Memory in MiB
            desired_count: Number of tasks to run
            environment_vars: Environment variables for the container
            platform: Container platform
            dockerfile_path: Optional dockerfile path
            
        Returns:
            Dictionary containing all created resources
            
        Raises:
            ResourceCreationError: If service creation fails
        """
        try:
            # Validate inputs
            ConfigValidator.validate_resource_name(service_name)
            ConfigValidator.validate_port_range(port)
            ConfigValidator.validate_environment_vars(environment_vars)
            
            if not health_check_path.startswith('/'):
                raise ValueError("Health check path must start with '/'")
            
            # Create log group
            log_group = self.create_log_group(f"{service_name}-service")
            
            # Create two target groups for blue-green deployment
            target_groups = self.create_blue_green_target_groups(
                service_name, self.vpc, port, health_check_path
            )
            
            # Create ALB resources optimized for blue-green
            alb_resources = self.create_blue_green_alb_resources(
                service_name, self.vpc, port, 
                target_groups["primary"], target_groups["secondary"],
                getattr(self, 'access_log_bucket', None)
            )
            
            # Create task definition
            task_definition = self._create_task_definition(
                service_name, cpu, memory, platform
            )
            
            # Add container to task definition
            container = self._add_alb_container_to_task(
                task_definition, service_name, container_image_path,
                port, log_group, environment_vars, platform, dockerfile_path,
                alb_resources["load_balancer"].load_balancer_dns_name
            )
            
            # Create ECS service with native blue-green deployment
            ecs_service = self.create_blue_green_fargate_service(
                service_name, self.cluster, task_definition,
                self.vpc.private_subnets, [alb_resources["ecs_security_group"]],
                desired_count, target_groups, port, f"{service_name}-container",
                alb_resources["production_rule"]
            )
            
            # Configure IAM permissions
            self._configure_alb_task_permissions(
                task_definition, [log_group.log_group_arn]
            )
            
            # Create CloudFormation outputs
            self._create_alb_service_output(service_name, alb_resources["load_balancer"])
            
            # Add tags
            self.add_common_tags(ecs_service, {
                "ServiceName": service_name,
                "ServiceType": "Fargate",
                "LoadBalancer": "ALB",
                "DeploymentType": "NativeBlueGreen"
            })
            
            return {
                "ecs_service": ecs_service,
                "task_definition": task_definition,
                "container": container,
                "log_group": log_group,
                "target_groups": target_groups,
                **alb_resources
            }
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create native blue-green ALB Fargate service '{service_name}': {str(e)}",
                resource_type="NativeBlueGreenALBFargateService"
            )
