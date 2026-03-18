"""
CloudFront constructs for VPC origins integration.
Provides secure content delivery from private ALBs without certificate management.
"""

from typing import List, Optional
from constructs import Construct
from aws_cdk import (
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as cloudfront_origins,
    aws_elasticloadbalancingv2 as elbv2,
    aws_s3 as s3,
    Duration,
)
from stacks.common.constants import (
    DEFAULT_CLOUDFRONT_DISTRIBUTION_SUFFIX,
    DEFAULT_VPC_ORIGIN_SUFFIX,
    DEFAULT_CLOUDFRONT_PRICE_CLASS,
    DEFAULT_CLOUDFRONT_HTTP_VERSION,
    DEFAULT_CLOUDFRONT_IPV6_ENABLED,
    DEFAULT_CLOUDFRONT_COMMENT_SUFFIX,
    CLOUDFRONT_MANAGED_PREFIX_LIST_NAME,
)


class CloudFrontVpcOriginConstruct(Construct):
    """
    CloudFront construct that creates a distribution with VPC origins
    pointing to an Application Load Balancer in private subnets.

    The WAF Web ACL must be created separately in us-east-1 (see
    ``stacks/user_interface/waf_stack.py``) and its ARN passed in via
    the ``web_acl_arn`` parameter.  This allows the main UI stack to be
    deployed in any region while WAF remains correctly pinned to us-east-1.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        project_name: str,
        load_balancer: elbv2.ApplicationLoadBalancer,
        access_logs_bucket,
        web_acl_arn: str,
        prefix_lists: Optional[List[str]] = None,
        geo_restriction_countries: Optional[List[str]] = None,
        price_class: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.project_name = project_name
        self.load_balancer = load_balancer
        self.prefix_lists = prefix_lists or []
        self.access_logs_bucket = access_logs_bucket
        self.geo_restriction_countries = geo_restriction_countries
        self.price_class = price_class or "PriceClass_All"
        # WAF ARN comes from the dedicated us-east-1 CloudFrontWAFStack
        self._web_acl_arn = web_acl_arn

        # Create CloudFront Distribution (VPC origin pattern implemented via security groups)
        self.distribution = self._create_distribution()

    def _get_cloudfront_price_class(self) -> cloudfront.PriceClass:
        """
        Get CloudFront price class from configuration.
        Provides cost vs performance control for CloudFront edge locations.
        
        Returns:
            CloudFront price class enum based on configuration
        """
        # Convert string price class to CDK enum
        price_class_map = {
            "PriceClass_All": cloudfront.PriceClass.PRICE_CLASS_ALL,
            "PriceClass_200": cloudfront.PriceClass.PRICE_CLASS_200,
            "PriceClass_100": cloudfront.PriceClass.PRICE_CLASS_100
        }
        
        return price_class_map.get(self.price_class, cloudfront.PriceClass.PRICE_CLASS_ALL)

    def _create_distribution(self) -> cloudfront.Distribution:
        """Create CloudFront distribution with VPC origins."""
        distribution_comment = f"{self.project_name} {DEFAULT_CLOUDFRONT_COMMENT_SUFFIX}"
        
        # Per AWS documentation: https://repost.aws/knowledge-center/cloudfront-authorization-header
        # "If caching is turned off, then you can use AllViewer and AllViewerExceptHostHeader 
        # origin request policies to forward an authorization header."
        #
        # AWS CloudFront Requirements for Authorization Header with VPC Origins:
        # ✅ Requirement 1: Caching must be DISABLED
        # ✅ Requirement 2: Must use managed ALL_VIEWER or ALL_VIEWER_EXCEPT_HOST_HEADER policy
        #
        # Note: CloudFront validation prevents "Authorization" in custom OriginRequestPolicy allow_list
        # Error: "you cannot pass `Authorization` or `Accept-Encoding` as header values; 
        #         use a CachePolicy to forward these headers instead"
        # This forces use of managed policies when caching is disabled.
        
        # CRITICAL FIX: Create custom Cache Policy with MINIMAL caching to allow cookie forwarding
        # AWS CloudFront constraint: CookieBehavior cannot be set when TTL=0 (caching disabled)
        # Solution: Use 1-second TTL (minimal caching) which allows explicit cookie forwarding
        # This ensures session cookies (sessionId) are forwarded to origin
        custom_cache_policy = cloudfront.CachePolicy(
            self,
            "CustomCachePolicyWithCookies",
            comment=f"{self.project_name} - Minimal caching (1s), forward all cookies for sessions",
            cache_policy_name=f"{self.project_name}-minimal-cache-all-cookies",
            min_ttl=Duration.seconds(1),      # ✅ Minimal caching allows cookie forwarding
            max_ttl=Duration.seconds(1),      # ✅ 1 second max cache
            default_ttl=Duration.seconds(1),  # ✅ 1 second default cache
            enable_accept_encoding_gzip=True,
            enable_accept_encoding_brotli=True,
            header_behavior=cloudfront.CacheHeaderBehavior.none(),
            query_string_behavior=cloudfront.CacheQueryStringBehavior.all(),
            cookie_behavior=cloudfront.CacheCookieBehavior.all()  # ✅ CRITICAL: Forward ALL cookies
        )
        
        # CRITICAL FIX: Use AWS managed policy that forwards ALL viewer AND CloudFront headers
        # CloudFront's own headers (CloudFront-Forwarded-Proto, CloudFront-Viewer-Protocol, etc.)
        # are ONLY forwarded when using the ALL_VIEWER_AND_CLOUDFRONT_2022 managed policy.
        # Custom policies with .all() only forward viewer headers, NOT CloudFront's own headers.
        # These CloudFront headers are essential for Express trust proxy to detect HTTPS correctly.
        custom_origin_request_policy = cloudfront.OriginRequestPolicy.ALL_VIEWER_AND_CLOUDFRONT_2022
        
        # Create proper VPC Origins with internal ALB
        # VPC Origins allows CloudFront to connect to private ALBs via service-managed ENIs
        default_behavior = cloudfront.BehaviorOptions(
            origin=cloudfront_origins.VpcOrigin.with_application_load_balancer(
                self.load_balancer,
                # VPC Origins configuration for internal ALB access
                http_port=80,  # ALB HTTP port in private subnet
                https_port=443,  # ALB HTTPS port (if available)
                origin_ssl_protocols=[cloudfront.OriginSslPolicy.TLS_V1_2],
                protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,  # ALB uses HTTP - no certificate required
                read_timeout=Duration.seconds(60),
                keepalive_timeout=Duration.seconds(5),  # CloudFront connection persistence
                vpc_origin_name=f"{self.project_name}-alb-vpc-origin"
            ),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
            cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
            cache_policy=custom_cache_policy,  # ✅ Use custom policy with cookie forwarding
            origin_request_policy=custom_origin_request_policy,  # ✅ Use managed policy with ALL headers (viewer + CloudFront)
            compress=True
        )

        # Configure geo-restriction based on configuration
        geo_restriction_config = None
        if self.geo_restriction_countries:
            geo_restriction_config = cloudfront.GeoRestriction.allowlist(*self.geo_restriction_countries)

        # Create S3 bucket reference for CloudFront logging
        # Handle the cross-stack S3 bucket reference properly
        log_bucket = None
        if self.access_logs_bucket:
            if isinstance(self.access_logs_bucket, str):
                # If bucket name is passed as string, create bucket reference
                log_bucket = s3.Bucket.from_bucket_name(
                    self, "CloudFrontLogsBucket", self.access_logs_bucket
                )
            else:
                # If bucket object is passed, use it directly
                log_bucket = self.access_logs_bucket

        # Create Response Headers Policy for CSP and security headers
        response_headers_policy = cloudfront.ResponseHeadersPolicy(
            self,
            "ResponseHeadersPolicy",
            comment=f"{self.project_name} security headers",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                content_security_policy=cloudfront.ResponseHeadersContentSecurityPolicy(
                    content_security_policy="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data: https:; connect-src 'self' https:; font-src 'self' data: https:; object-src 'none'; media-src 'self'; frame-src 'none'",
                    override=True
                ),
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(
                    override=True
                ),
                frame_options=cloudfront.ResponseHeadersFrameOptions(
                    frame_option=cloudfront.HeadersFrameOption.DENY,
                    override=True
                ),
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.STRICT_ORIGIN_WHEN_CROSS_ORIGIN,
                    override=True
                ),
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.seconds(63072000),
                    include_subdomains=True,
                    preload=True,
                    override=True
                ),
                xss_protection=cloudfront.ResponseHeadersXSSProtection(
                    protection=True,
                    mode_block=True,
                    override=True
                )
            )
        )

        # Update default behavior to include response headers policy
        default_behavior_with_headers = cloudfront.BehaviorOptions(
            origin=cloudfront_origins.VpcOrigin.with_application_load_balancer(
                self.load_balancer,
                # VPC Origins configuration for internal ALB access
                http_port=80,  # ALB HTTP port in private subnet
                https_port=443,  # ALB HTTPS port (if available)
                origin_ssl_protocols=[cloudfront.OriginSslPolicy.TLS_V1_2],
                protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,  # ALB uses HTTP - no certificate required
                read_timeout=Duration.seconds(60),
                keepalive_timeout=Duration.seconds(5),  # CloudFront connection persistence
                vpc_origin_name=f"{self.project_name}-alb-vpc-origin"
            ),
            viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
            cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD_OPTIONS,
            cache_policy=custom_cache_policy,  # ✅ Use custom policy with cookie forwarding
            origin_request_policy=custom_origin_request_policy,  # ✅ Use managed policy with ALL headers (viewer + CloudFront)
            compress=True,
            response_headers_policy=response_headers_policy  # Add CSP and security headers
        )

        distribution = cloudfront.Distribution(
            self,
            "Distribution",
            default_behavior=default_behavior_with_headers,
            price_class=self._get_cloudfront_price_class(),  # Configurable price class from config
            http_version=cloudfront.HttpVersion.HTTP2,
            enable_ipv6=DEFAULT_CLOUDFRONT_IPV6_ENABLED,
            comment=distribution_comment,
            web_acl_id=self._web_acl_arn,
            # Security improvements for CDK Nag compliance
            minimum_protocol_version=cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
            enable_logging=True,  # CloudFront access logging enabled with ACL-compatible S3 bucket
            log_bucket=log_bucket,
            log_file_prefix="cloudfront-access-logs/",
            geo_restriction=geo_restriction_config,  # Configurable geo-restriction
            # Explicit domain names configuration to ensure proper SSL/TLS handling
            domain_names=[],  # No custom domain names - use CloudFront default domain
            certificate=None  # Use CloudFront default certificate with proper TLS settings
        )

        # Add VPC origin after distribution creation
        self._associate_vpc_origin(distribution)
        
        return distribution

    def _associate_vpc_origin(self, distribution: cloudfront.Distribution) -> None:
        """Associate the VPC origin with the CloudFront distribution."""
        # This would be implemented using the VPC origin APIs
        # For now, we'll use the standard HTTP origin pointing to the ALB
        # The security is handled by restricting ALB security groups to CloudFront IPs
        pass

