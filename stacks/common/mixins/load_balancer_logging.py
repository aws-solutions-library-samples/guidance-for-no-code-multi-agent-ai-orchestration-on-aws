"""
Load Balancer Logging Mixin

Provides consistent access and connection logging configuration 
for Application Load Balancers across all stacks.

Follows AWS best practices as documented in:
- https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-access-logging.html  
- https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-connection-logging.html
"""

from typing import Optional, Dict, Any
from aws_cdk import (
    aws_s3 as s3,
    aws_iam as iam,
    aws_elasticloadbalancingv2 as elbv2,
    RemovalPolicy,
    Stack,
    Duration,
)
from constructs import Construct

# Removed COMMON_TAGS import as it doesn't exist in constants


class LoadBalancerLoggingMixin:
    """
    Mixin class that provides standardized load balancer logging configuration.
    
    This mixin creates the necessary S3 buckets, IAM policies, and configurations
    for both access logging and connection logging for Application Load Balancers.
    """
    
    def setup_load_balancer_logging(
        self,
        scope: Construct,
        construct_id: str,
        enable_access_logging: bool = True,
        enable_connection_logging: bool = True,
        custom_bucket_prefix: Optional[str] = None,
        log_retention_days: int = 90,
    ) -> Dict[str, Any]:
        """
        Set up S3 buckets and policies for load balancer logging.
        
        Args:
            scope: The construct scope
            construct_id: Unique identifier for this logging setup
            enable_access_logging: Whether to enable access logging
            enable_connection_logging: Whether to enable connection logging  
            custom_bucket_prefix: Custom prefix for S3 bucket names
            log_retention_days: Number of days to retain logs in S3
            
        Returns:
            Dictionary containing the created logging resources
        """
        resources = {}
        
        if enable_access_logging:
            access_bucket = self._create_logging_bucket(
                scope, 
                f"{construct_id}-access-logs",
                "access",
                custom_bucket_prefix,
                log_retention_days
            )
            resources['access_logs_bucket'] = access_bucket
        
        if enable_connection_logging:
            connection_bucket = self._create_logging_bucket(
                scope,
                f"{construct_id}-connection-logs", 
                "connection",
                custom_bucket_prefix,
                log_retention_days
            )
            resources['connection_logs_bucket'] = connection_bucket
            
        return resources
    
    def configure_load_balancer_logging(
        self,
        load_balancer: elbv2.ApplicationLoadBalancer,
        logging_resources: Dict[str, Any],
        access_log_prefix: str = "access-logs",
        connection_log_prefix: str = "connection-logs"
    ) -> None:
        """
        Configure logging attributes on an existing Application Load Balancer.
        
        Args:
            load_balancer: The ALB to configure logging for
            logging_resources: Dictionary returned from setup_load_balancer_logging
            access_log_prefix: S3 prefix for access logs
            connection_log_prefix: S3 prefix for connection logs
        """
        # Enable access logging if bucket exists
        if 'access_logs_bucket' in logging_resources:
            access_bucket = logging_resources['access_logs_bucket']
            load_balancer.log_access_logs(
                bucket=access_bucket,
                prefix=access_log_prefix
            )
            
        # Enable connection logging if bucket exists
        if 'connection_logs_bucket' in logging_resources:
            connection_bucket = logging_resources['connection_logs_bucket']
            
            # Connection logging requires setting load balancer attributes
            load_balancer.set_attribute(
                "connection_logs.s3.enabled", "true"
            )
            load_balancer.set_attribute(
                "connection_logs.s3.bucket", connection_bucket.bucket_name
            )
            load_balancer.set_attribute(
                "connection_logs.s3.prefix", connection_log_prefix
            )
    
    def apply_logging_to_existing_alb(
        self,
        load_balancer: elbv2.ApplicationLoadBalancer,
        access_logs_bucket: s3.Bucket,
        access_log_prefix: str = "access-logs",
        connection_log_prefix: str = "connection-logs"
    ) -> None:
        """
        Apply logging configuration to an existing ALB using a shared bucket.
        
        This is useful when you have a single S3 bucket for all ALB logs 
        (like the one created in VPC stack).
        
        Args:
            load_balancer: The ALB to configure logging for
            access_logs_bucket: S3 bucket for storing logs
            access_log_prefix: S3 prefix for access logs
            connection_log_prefix: S3 prefix for connection logs
        """
        # Enable access logging
        load_balancer.log_access_logs(
            bucket=access_logs_bucket,
            prefix=access_log_prefix
        )
        
        # Enable connection logging
        load_balancer.set_attribute(
            "connection_logs.s3.enabled", "true"
        )
        load_balancer.set_attribute(
            "connection_logs.s3.bucket", access_logs_bucket.bucket_name
        )
        load_balancer.set_attribute(
            "connection_logs.s3.prefix", connection_log_prefix
        )

    def configure_alb_logging(
        self,
        load_balancer: elbv2.ApplicationLoadBalancer,
        access_logs_bucket: s3.Bucket,
        prefix: str = "alb-logs"
    ) -> None:
        """
        Configure both access logging and connection logging for an Application Load Balancer.
        
        This method implements the AWS best practices from the official documentation:
        - https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-access-logging.html
        - https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-connection-logging.html
        
        Args:
            load_balancer: The ALB to configure logging for
            access_logs_bucket: S3 bucket for storing logs
            prefix: S3 prefix for both access and connection logs
        """
        # Enable access logging with proper prefix
        load_balancer.log_access_logs(
            bucket=access_logs_bucket,
            prefix=f"{prefix}-access"
        )
        
        # Enable connection logging with proper prefix
        load_balancer.set_attribute(
            "connection_logs.s3.enabled", "true"
        )
        load_balancer.set_attribute(
            "connection_logs.s3.bucket", access_logs_bucket.bucket_name
        )
        load_balancer.set_attribute(
            "connection_logs.s3.prefix", f"{prefix}-connection"
        )
    
    def _create_logging_bucket(
        self,
        scope: Construct,
        construct_id: str,
        log_type: str,
        custom_prefix: Optional[str],
        retention_days: int
    ) -> s3.Bucket:
        """
        Create an S3 bucket for load balancer logging with proper policies.
        
        Args:
            scope: The construct scope
            construct_id: Unique identifier for the bucket
            log_type: Type of logging ('access' or 'connection')
            custom_prefix: Optional custom prefix for bucket name
            retention_days: Number of days to retain logs
            
        Returns:
            The created S3 bucket
        """
        bucket_name_parts = []
        if custom_prefix:
            bucket_name_parts.append(custom_prefix)
        bucket_name_parts.extend([
            Stack.of(scope).stack_name.lower(),
            log_type,
            "logs",
            Stack.of(scope).account,
            Stack.of(scope).region
        ])
        
        bucket_name = "-".join(bucket_name_parts)
        
        # Create the S3 bucket
        bucket = s3.Bucket(
            scope,
            construct_id,
            bucket_name=bucket_name,
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id=f"{log_type}-logs-lifecycle",
                    enabled=True,
                    expiration=Duration.days(retention_days),
                    noncurrent_version_expiration=Duration.days(30),
                    abort_incomplete_multipart_upload_after=Duration.days(7)
                )
            ]
        )
        
        # Add basic tags for identification
        bucket.node.add_metadata("Purpose", f"ALB-{log_type}-logging")
        bucket.node.add_metadata("LogType", log_type)
            
        # Add ELB service account policy for the bucket
        self._add_elb_bucket_policy(bucket, log_type)
        
        return bucket
    
    def _add_elb_bucket_policy(self, bucket: s3.Bucket, log_type: str) -> None:
        """
        Add the necessary bucket policy to allow ELB service to write logs.
        
        According to AWS documentation, the ELB service account varies by region.
        This method adds the appropriate policy statement.
        
        Args:
            bucket: The S3 bucket to add the policy to
            log_type: Type of logging ('access' or 'connection')
        """
        # ELB service account IDs by region (as per AWS documentation)
        elb_service_accounts = {
            'us-east-1': '127311923021',
            'us-east-2': '033677994240',
            'us-west-1': '027434742980', 
            'us-west-2': '797873946194',
            'ca-central-1': '985666609251',
            'eu-west-1': '156460612806',
            'eu-central-1': '054676820928',
            'eu-west-2': '652711504416',
            'eu-west-3': '009996457667',
            'eu-north-1': '897822967062',
            'eu-south-1': '635631232127',
            'ap-northeast-1': '582318560864',
            'ap-northeast-2': '600734575887',
            'ap-northeast-3': '383597477331',
            'ap-southeast-1': '114774131450',
            'ap-southeast-2': '783225319266',
            'ap-south-1': '718504428378',
            'sa-east-1': '507241528517',
            'af-south-1': '098369216593',
            'ap-east-1': '754344448648',
            'me-south-1': '076674570225',
        }
        
        region = Stack.of(bucket).region
        elb_account_id = elb_service_accounts.get(region)
        
        if not elb_account_id:
            # For newer regions, use log delivery service principal
            elb_principal = iam.ServicePrincipal('logdelivery.elasticloadbalancing.amazonaws.com')
        else:
            elb_principal = iam.AccountPrincipal(elb_account_id)
        
        # Create policy statement for ELB to write logs
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid=f"AWSLogDeliveryWrite{log_type.capitalize()}",
                effect=iam.Effect.ALLOW,
                principals=[elb_principal],
                actions=["s3:PutObject"],
                resources=[f"{bucket.bucket_arn}/AWSLogs/{Stack.of(bucket).account}/*"],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control"
                    }
                }
            )
        )
        
        # Add policy statement for ELB to access the bucket
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid=f"AWSLogDeliveryAclCheck{log_type.capitalize()}",
                effect=iam.Effect.ALLOW,
                principals=[elb_principal],
                actions=["s3:GetBucketAcl"],
                resources=[bucket.bucket_arn]
            )
        )

    def update_vpc_bucket_policy_for_regions(self, bucket: s3.Bucket) -> None:
        """
        Update existing VPC bucket policy to support multiple regions properly.
        This method ensures the bucket policy follows AWS documentation requirements.
        
        Args:
            bucket: The existing S3 bucket to update policy for
        """
        region = Stack.of(bucket).region
        account = Stack.of(bucket).account
        
        # ELB service account IDs by region (as per AWS documentation)
        elb_service_accounts = {
            'us-east-1': '127311923021',
            'us-east-2': '033677994240',
            'us-west-1': '027434742980', 
            'us-west-2': '797873946194',
            'ca-central-1': '985666609251',
            'eu-west-1': '156460612806',
            'eu-central-1': '054676820928',
            'eu-west-2': '652711504416',
            'eu-west-3': '009996457667',
            'eu-north-1': '897822967062',
            'eu-south-1': '635631232127',
            'ap-northeast-1': '582318560864',
            'ap-northeast-2': '600734575887',
            'ap-northeast-3': '383597477331',
            'ap-southeast-1': '114774131450',
            'ap-southeast-2': '783225319266',
            'ap-south-1': '718504428378',
            'sa-east-1': '507241528517',
            'af-south-1': '098369216593',
            'ap-east-1': '754344448648',
            'me-south-1': '076674570225',
        }
        
        elb_account_id = elb_service_accounts.get(region)
        
        if not elb_account_id:
            # For newer regions, use log delivery service principal
            elb_principal = iam.ServicePrincipal('logdelivery.elasticloadbalancing.amazonaws.com')
        else:
            elb_principal = iam.AccountPrincipal(elb_account_id)
            
        # Remove old hardcoded policies if they exist and add proper ones
        
        # Add policy for access logs with proper AWS Logs path structure
        # This allows any prefix to be used, covering all ALB logging scenarios
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="UpdatedAWSLogDeliveryWriteAccess",
                effect=iam.Effect.ALLOW,
                principals=[elb_principal],
                actions=["s3:PutObject"],
                resources=[f"{bucket.bucket_arn}/*/AWSLogs/{account}/*"],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control"
                    }
                }
            )
        )
        
        # Add additional policy for connection logs with wildcard path structure  
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="UpdatedAWSLogDeliveryWriteConnection",
                effect=iam.Effect.ALLOW,
                principals=[elb_principal],
                actions=["s3:PutObject"],
                resources=[f"{bucket.bucket_arn}/*/AWSLogs/{account}/*"],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control"
                    }
                }
            )
        )
        
        # Add policy for any prefix structure that ALB might use
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AnyPrefixALBLogs",
                effect=iam.Effect.ALLOW,
                principals=[elb_principal],
                actions=["s3:PutObject"],
                resources=[f"{bucket.bucket_arn}/AWSLogs/{account}/*"],
                conditions={
                    "StringEquals": {
                        "s3:x-amz-acl": "bucket-owner-full-control"
                    }
                }
            )
        )
        
        # Add bucket ACL check permission
        bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="UpdatedAWSLogDeliveryAclCheck", 
                effect=iam.Effect.ALLOW,
                principals=[elb_principal],
                actions=["s3:GetBucketAcl"],
                resources=[bucket.bucket_arn]
            )
        )
