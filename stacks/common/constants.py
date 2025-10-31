"""
Constants used across CDK stacks.
"""

# Service Configuration
DEFAULT_CPU = 2048
DEFAULT_MEMORY = 4096
DEFAULT_DESIRED_COUNT = 1

# Port Configuration
API_PORT = 8000
AGENT_PORT = 8080  # Unified internal port for all agent instances
AGENT_SUPERVISOR_PORT = 9003
UI_PORT = 3001

# Health Check Paths
API_HEALTH_CHECK_PATH = "/health"
AGENT_HEALTH_CHECK_PATH = "/.well-known/agent-card.json"
AGENT_SUPERVISOR_HEALTH_CHECK_PATH = "/health"
UI_HEALTH_CHECK_PATH = "/api/health"

# Logging
DEFAULT_LOG_REMOVAL_POLICY = "DESTROY"

# VPC Configuration
DEFAULT_MAX_AZS = 2
DEFAULT_CIDR_MASK = 24

# Security
WAF_METRIC_NAME_PREFIX = "waf-metrics"  # Will be prefixed with project name where used

# Service Names (configurable via config)
DEFAULT_ECS_CLUSTER_SUFFIX = "cluster"
DEFAULT_VPC_LATTICE_SERVICE_NETWORK_SUFFIX = "svc-net"
DEFAULT_API_SERVICE_SUFFIX = "config-api"
DEFAULT_UI_SERVICE_SUFFIX = "ui"
DEFAULT_COGNITO_USER_POOL_SUFFIX = "pool"

# Container Image Paths - ✅ HYBRID APPROACH: Shared context with .dockerignore optimization
CONFIGURATION_API_IMAGE_PATH = "./application_src"  # Shared context with optimized .dockerignore
AGENT_INSTANCE_IMAGE_PATH = "./application_src"  # Shared context with optimized .dockerignore
AGENT_SUPERVISOR_IMAGE_PATH = "./application_src"  # Shared context with optimized .dockerignore

# Dockerfile Paths (relative to shared build context) - ✅ RESTORED
AGENT_INSTANCE_DOCKERFILE_PATH = "multi-agent/agent-instance/Dockerfile"
AGENT_SUPERVISOR_DOCKERFILE_PATH = "multi-agent/agent-supervisor/Dockerfile"

# Platform Configuration
DEFAULT_CONTAINER_PLATFORM = "LINUX_ARM64"  # Changed from AMD64 to ARM64

# UI Configuration
UI_CPU = 1024
UI_MEMORY = 2048
UI_DESIRED_COUNT = 1
UI_MIN_HEALTHY_PERCENT = 50
UI_DEREGISTRATION_DELAY = 10
DEFAULT_UI_LOAD_BALANCER_SUFFIX = "alb"
DEFAULT_COGNITO_DOMAIN_SUFFIX = "pool"

# ECS Deployment Configuration
# Native Blue-Green deployment for faster deployments
DEFAULT_MINIMUM_HEALTHY_PERCENT_BLUE_GREEN = 50  # Blue-green: keep 50% healthy during deployment
DEFAULT_MAXIMUM_PERCENT_BLUE_GREEN = 200  # Blue-green: allow 200% capacity (double capacity for blue+green environments)
DEFAULT_MINIMUM_HEALTHY_PERCENT_ROLLING = 0  # Rolling: allow all tasks to be replaced for speed
DEFAULT_MAXIMUM_PERCENT_ROLLING = 200  # Rolling: standard maximum capacity

# Blue-Green Deployment Configuration
DEFAULT_HEALTH_CHECK_GRACE_PERIOD = 30  # 30 seconds for faster deployments (reduced from 60)
DEFAULT_DEREGISTRATION_DELAY = 5  # 5 seconds bake time as requested

# Health Check Configuration for Target Groups
DEFAULT_HEALTHY_THRESHOLD_COUNT = 2    # AWS minimum requirement: at least 2
DEFAULT_UNHEALTHY_THRESHOLD_COUNT = 2  # Keep as 2 for reliability
DEFAULT_HEALTH_CHECK_INTERVAL = 30     # 30 seconds interval
DEFAULT_HEALTH_CHECK_TIMEOUT = 10      # 10 seconds timeout (increased from 5)

# CloudFront Configuration
DEFAULT_CLOUDFRONT_DISTRIBUTION_SUFFIX = "cf-dist"
DEFAULT_VPC_ORIGIN_SUFFIX = "vpc-origin"
# CloudFront managed prefix list is looked up dynamically by name
CLOUDFRONT_MANAGED_PREFIX_LIST_NAME = "com.amazonaws.global.cloudfront.origin-facing"
# Price class defaults to global distribution - can be configured via CloudFrontPriceClass parameter
DEFAULT_CLOUDFRONT_PRICE_CLASS = "PriceClass_All"  # Global distribution by default
DEFAULT_CLOUDFRONT_HTTP_VERSION = "http2"
DEFAULT_CLOUDFRONT_IPV6_ENABLED = False
DEFAULT_CLOUDFRONT_COMMENT_SUFFIX = "Distribution"

# CloudFront Cache Configuration
DEFAULT_CACHE_POLICY_NAME_SUFFIX = "cache-policy"
DEFAULT_ORIGIN_REQUEST_POLICY_NAME_SUFFIX = "origin-request-policy"

# UI Access Modes
UI_ACCESS_MODE_PUBLIC = "public"
UI_ACCESS_MODE_PRIVATE = "private"

# Cognito Configuration
DEFAULT_COGNITO_PASSWORD_MIN_LENGTH = 8
DEFAULT_COGNITO_FEATURE_PLAN = "PLUS"
DEFAULT_COGNITO_CLIENT_NAME = "WebAppAuthentication"
