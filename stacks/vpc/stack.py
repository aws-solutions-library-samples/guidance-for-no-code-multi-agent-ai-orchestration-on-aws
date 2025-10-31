from constructs import Construct
from aws_cdk import (
    aws_ecs as ecs,
    aws_ec2 as ec2,
    aws_s3 as s3,
    aws_iam as iam,
    aws_vpclattice as vpclattice,
    aws_logs as logs,
    RemovalPolicy,
    Duration
)

from helper.config import Config
from stacks.common.base import BaseStack
from stacks.common.mixins.load_balancer_logging import LoadBalancerLoggingMixin
from stacks.common.constants import (
    DEFAULT_MAX_AZS, 
    DEFAULT_CIDR_MASK,
    DEFAULT_ECS_CLUSTER_SUFFIX,
    DEFAULT_VPC_LATTICE_SERVICE_NETWORK_SUFFIX
)


class VpcStack(BaseStack, LoadBalancerLoggingMixin):

    def __init__(self, 
                 scope: Construct, 
                 construct_id: str,
                 config: Config,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, config, **kwargs)

        # Get configuration values
        project_name = self.get_required_config('ProjectName')
        max_azs = self.get_optional_config('MaxAZs', DEFAULT_MAX_AZS)
        cidr_mask = self.get_optional_config('CIDRMask', DEFAULT_CIDR_MASK)
        
        # Create a new VPC with two subnets in two availability zones
        vpc = ec2.Vpc(
            self,
            "VPC",
            max_azs=max_azs,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PUBLIC,
                    name="Public",
                    cidr_mask=cidr_mask,
                ),
                ec2.SubnetConfiguration(
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    name="Private",
                    cidr_mask=cidr_mask,
                ),
            ],
        )

        vpc.add_flow_log("FlowLog")
        self.vpc = vpc

        # Create a ECS Cluster in the VPC
        cluster_name = f"{project_name}-{DEFAULT_ECS_CLUSTER_SUFFIX}"
        cluster = ecs.Cluster(
            self,
            "ecs-cluster",
            vpc=vpc,
            container_insights=True,
            enable_fargate_capacity_providers=True,
            cluster_name=cluster_name
        )

        self.ecs_cluster = cluster

        # Create security group for VPC Lattice Service Network
        service_network_security_group = ec2.SecurityGroup(
            self,
            "service-network-security-group",
            vpc=vpc,
            description="Security group for VPC Lattice Service Network",
            allow_all_outbound=True
        )

        # Allow ingress on port 80 from VPC CIDR ranges
        service_network_security_group.add_ingress_rule(
            peer=ec2.Peer.ipv4(vpc.vpc_cidr_block),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP traffic from VPC CIDR"
        )

        # Create VPC Lattice Service Network
        service_network_name = f"{project_name}-{DEFAULT_VPC_LATTICE_SERVICE_NETWORK_SUFFIX}"
        service_network = vpclattice.CfnServiceNetwork(
            self,
            "service-network",
            name=service_network_name,
            auth_type="NONE"
        )

        # Associate VPC with the Service Network
        service_network_vpc_association = vpclattice.CfnServiceNetworkVpcAssociation(
            self,
            "service-network-vpc-association",
            service_network_identifier=service_network.attr_id,
            vpc_identifier=vpc.vpc_id,
            security_group_ids=[service_network_security_group.security_group_id]
        )

        self.service_network = service_network
        self.service_network_arn = service_network.attr_arn

        # Create network-level access logging for VPC Lattice Service Network
        # This is created once per service network to avoid conflicts between services
        network_access_log_group = logs.LogGroup(
            self,
            "vpc-lattice-network-access-logs",
            log_group_name=f"/aws/vpclattice/{service_network_name}/network-access",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY
        )

        # Create access log subscription for the service network (network-level logging)
        network_access_subscription = vpclattice.CfnAccessLogSubscription(
            self,
            "vpc-lattice-network-access-log-subscription",
            resource_identifier=service_network.attr_arn,
            destination_arn=network_access_log_group.log_group_arn
        )

        # Set up dependency to ensure proper creation order
        network_access_subscription.add_dependency(service_network)
        network_access_subscription.add_dependency(service_network_vpc_association)

        # Store references for other stacks
        self.network_access_log_group = network_access_log_group
        self.network_access_subscription = network_access_subscription

        # Create shared log group for ECS services if shared logging is enabled
        use_shared_log_group = self.get_optional_config('UseSharedLogGroup', False)
        if use_shared_log_group:
            shared_log_group_name = self.get_required_config('SharedLogGroupName')
            shared_log_retention_days = self.get_optional_config('SharedLogGroupRetentionDays', 30)
            
            # Convert retention days to RetentionDays enum
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
            retention = retention_mapping.get(shared_log_retention_days, logs.RetentionDays.ONE_MONTH)
            
            self.shared_log_group = logs.LogGroup(
                self,
                "shared-log-group",
                log_group_name=shared_log_group_name,
                retention=retention,
                removal_policy=RemovalPolicy.DESTROY
            )
            
            # TODO: Data protection disabled - feature not available in this account
            # The CloudWatch Logs data protection API rejects managed identifiers
            # This might require additional account setup or permissions
            # self._create_log_group_data_protection_policy(
            #     self.shared_log_group, 
            #     "shared-log-group-data-protection"
            # )
            
            # Export the shared log group ARN for other stacks to use
            from aws_cdk import CfnOutput
            CfnOutput(
                self, "SharedLogGroupArn",
                value=self.shared_log_group.log_group_arn,
                export_name=f"{project_name}-SharedLogGroupArn",
                description="ARN of the shared log group for all ECS services"
            )

        # Access Logs specific S3 Bucket with ALB permissions
        # Create bucket with proper lifecycle and security settings including ACL access for CloudFront
        bucket = s3.Bucket(self, "AccessLog",
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,  # Enable ACL access for CloudFront logging
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="alb-logs-lifecycle",
                    enabled=True,
                    expiration=Duration.days(90),
                    noncurrent_version_expiration=Duration.days(30),
                    abort_incomplete_multipart_upload_after=Duration.days(7)
                )
            ]
        )

        # Use the mixin method to apply proper region-aware bucket policies
        # This replaces the hardcoded us-east-1 policies with proper AWS documentation-compliant ones
        self.update_vpc_bucket_policy_for_regions(bucket)

        self.access_logs_bucket = bucket
        
        # Export critical infrastructure values for dynamic agent deployment
        # These exports allow the agent template generator to reference infrastructure
        # without querying CloudFormation, making it work in new environments
        from aws_cdk import CfnOutput
        
        CfnOutput(
            self, "VpcIdExport",
            value=vpc.vpc_id,
            export_name=f"{project_name}-VpcId",
            description="VPC ID for agent deployment"
        )
        
        CfnOutput(
            self, "ClusterNameExport",
            value=cluster.cluster_name,
            export_name=f"{project_name}-ClusterName",
            description="ECS Cluster name for agent deployment"
        )
        
        CfnOutput(
            self, "AccessLogBucketNameExport",
            value=bucket.bucket_name,
            export_name=f"{project_name}-AccessLogBucketName",
            description="Access log bucket name for agent deployment"
        )
        
        # Export private subnet IDs for agent deployment
        private_subnets = vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS)
        CfnOutput(
            self, "PrivateSubnetIdsExport",
            value=",".join(private_subnets.subnet_ids),
            export_name=f"{project_name}-PrivateSubnetIds",
            description="Private subnet IDs for agent deployment (comma-separated)"
        )
        
        CfnOutput(
            self, "VpcCidrExport",
            value=vpc.vpc_cidr_block,
            export_name=f"{project_name}-VpcCidr",
            description="VPC CIDR block for agent deployment"
        )
