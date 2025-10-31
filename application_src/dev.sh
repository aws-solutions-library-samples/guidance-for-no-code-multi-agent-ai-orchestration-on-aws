#!/bin/bash

# Development helper script for GenAI-in-a-Box
set -e

# Configuration file to store settings
CONFIG_FILE=".dev-config"

# Load configuration from file
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
    fi
}

# Save configuration to file
save_config() {
    cat > "$CONFIG_FILE" << EOF
# GenAI-in-a-Box Development Configuration
# This file is auto-generated. You can delete it to reconfigure.
AWS_ACCOUNT_ID="$AWS_ACCOUNT_ID"
AWS_REGION="$AWS_REGION"
SECRETS_MANAGER_ARN="$SECRETS_MANAGER_ARN"
AUTH_PROVIDER_TYPE="$AUTH_PROVIDER_TYPE"
S3_TEMPLATE_BUCKET="$S3_TEMPLATE_BUCKET"
EOF
    echo "💾 Configuration saved to $CONFIG_FILE"
}

# Get AWS account ID from user
get_account_id() {
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        echo "🏦 AWS Account ID not found in configuration."
        read -p "Please enter your AWS Account ID: " AWS_ACCOUNT_ID
        if [ -z "$AWS_ACCOUNT_ID" ]; then
            echo "❌ AWS Account ID is required"
            exit 1
        fi
    fi
}

# Get AWS region
get_region() {
    if [ -z "$AWS_REGION" ]; then
        AWS_REGION="us-east-1"
        echo "🌍 Using default region: $AWS_REGION"
    fi
}

# Get auth provider type from YAML config
get_auth_provider_type() {
    if [ -z "$AUTH_PROVIDER_TYPE" ]; then
        # Try to read from config/development.yaml
        CONFIG_YAML="../config/development.yaml"
        if [ -f "$CONFIG_YAML" ]; then
            # Use python to parse YAML since it's more reliable than grep/awk
            AUTH_PROVIDER_TYPE=$(python3 -c "
import yaml
import sys
try:
    with open('$CONFIG_YAML', 'r') as f:
        config = yaml.safe_load(f)
    provider = config.get('AuthProviderType', 'cognito')
    print(provider.lower())
except:
    print('cognito')
" 2>/dev/null)
            
            if [ -n "$AUTH_PROVIDER_TYPE" ]; then
                echo "🔐 Found auth provider from config: $AUTH_PROVIDER_TYPE"
            else
                AUTH_PROVIDER_TYPE="cognito"
                echo "⚠️  Could not read auth provider from config, defaulting to: $AUTH_PROVIDER_TYPE"
            fi
        else
            AUTH_PROVIDER_TYPE="cognito"
            echo "⚠️  Config file not found, defaulting auth provider to: $AUTH_PROVIDER_TYPE"
        fi
    fi
}

# Find Cognito secret automatically
find_cognito_secret() {
    if [ -z "$SECRETS_MANAGER_ARN" ]; then
        echo "🔍 Searching for Cognito secret in AWS Secrets Manager..."
        
        # Try to find the secret
        SECRET_ARN=$(aws secretsmanager list-secrets \
            --region "$AWS_REGION" \
            --query 'SecretList[?contains(Name, `CognitoSecret`)].ARN' \
            --output text 2>/dev/null | head -1)
        
        if [ -n "$SECRET_ARN" ] && [ "$SECRET_ARN" != "None" ]; then
            SECRETS_MANAGER_ARN="$SECRET_ARN"
            echo "✅ Found Cognito secret: $SECRETS_MANAGER_ARN"
        else
            echo "⚠️  Could not automatically find Cognito secret."
            echo "Please check that:"
            echo "  1. You have deployed the CDK stack"
            echo "  2. Your AWS credentials have SecretsManager permissions"
            echo "  3. The secret exists in region $AWS_REGION"
            read -p "Enter Cognito Secret ARN manually (or press Enter to continue without): " MANUAL_ARN
            if [ -n "$MANUAL_ARN" ]; then
                SECRETS_MANAGER_ARN="$MANUAL_ARN"
            else
                echo "⚠️  Continuing without Cognito secret (UI may not work properly)"
            fi
        fi
    fi
}

# Find S3 template bucket automatically
find_s3_template_bucket() {
    if [ -z "$S3_TEMPLATE_BUCKET" ]; then
        echo "🔍 Searching for agent template S3 bucket..."
        
        # Try to find the bucket (looking for templatestore or template-storage in name)
        BUCKET_NAME=$(aws s3api list-buckets \
            --query 'Buckets[?contains(Name, `templatestore`) || contains(Name, `template-storage`)].Name' \
            --output text 2>/dev/null | head -1)
        
        if [ -n "$BUCKET_NAME" ] && [ "$BUCKET_NAME" != "None" ]; then
            S3_TEMPLATE_BUCKET="$BUCKET_NAME"
            echo "✅ Found S3 template bucket: $S3_TEMPLATE_BUCKET"
        else
            echo "⚠️  Could not automatically find S3 template bucket."
            echo "Please check that:"
            echo "  1. You have deployed the CDK stack with TemplateStorage"
            echo "  2. Your AWS credentials have S3 permissions"
            echo "  3. The bucket exists in account $AWS_ACCOUNT_ID"
            read -p "Enter S3 bucket name manually (or press Enter to continue without): " MANUAL_BUCKET
            if [ -n "$MANUAL_BUCKET" ]; then
                S3_TEMPLATE_BUCKET="$MANUAL_BUCKET"
            else
                echo "⚠️  Continuing without S3 template bucket (agent deployment may not work)"
            fi
        fi
    fi
}

# Setup configuration
setup_config() {
    echo "🔧 Setting up development configuration..."
    load_config
    get_account_id
    get_region
    get_auth_provider_type
    find_cognito_secret
    find_s3_template_bucket
    save_config
    echo "✅ Configuration setup complete"
}

# Get AWS credentials
get_credentials() {
    # Load existing config
    load_config
    
    # Setup config if missing
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        setup_config
    fi
    
    echo "🔐 Getting AWS credentials for account: $AWS_ACCOUNT_ID"
    
    # Get AWS credentials - ensure they are set via your preferred credential provider
    if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        echo "❌ AWS credentials not found. Please ensure you have valid AWS credentials set."
        echo "💡 You can use any of these methods:"
        echo "   - AWS CLI: aws configure"
        echo "   - Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN"
        echo "   - IAM roles or instance profiles"
        exit 1
    fi
    
    if [ $? -ne 0 ]; then
        echo "❌ Failed to get AWS credentials"
        exit 1
    fi
    
    # Verify credentials are properly set
    if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ] || [ -z "$AWS_SESSION_TOKEN" ]; then
        echo "❌ Failed to export AWS credentials properly"
        exit 1
    fi
    
    # Get auth provider type from cached config or YAML
    get_auth_provider_type
    
    export AWS_REGION="$AWS_REGION"
    export AUTH_PROVIDER_TYPE="$AUTH_PROVIDER_TYPE"
    
    # Export SECRETS_MANAGER_ARN for all services
    if [ -n "$SECRETS_MANAGER_ARN" ]; then
        export SECRETS_MANAGER_ARN="$SECRETS_MANAGER_ARN"
    fi
    
    # Export S3_TEMPLATE_BUCKET for configuration-api
    if [ -n "$S3_TEMPLATE_BUCKET" ]; then
        export S3_TEMPLATE_BUCKET="$S3_TEMPLATE_BUCKET"
    fi
    
    echo "✅ AWS credentials set for region: $AWS_REGION"
    echo "🔐 OAuth 2.0 provider: $AUTH_PROVIDER_TYPE"
    echo "🔑 Secrets Manager ARN: ${SECRETS_MANAGER_ARN:-'Not set'}"
    echo "🪣 S3 Template Bucket: ${S3_TEMPLATE_BUCKET:-'Not set'}"
    echo "🔍 Debug: AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:0:20}..."
}

# Set build target for multi-stage builds
set_build_target() {
    local target=${1:-development}
    export BUILD_TARGET="$target"
    export NODE_ENV="$target"
    export RELOAD="true"
    echo "🎯 Build target set to: $target"
}

case "$1" in
    "dev"|"start"|"up")
        echo "🚀 Starting development environment with auto-reload..."
        echo "✅ Features enabled:"
        echo "  - File watching & auto-restart"
        echo "  - Development dependencies"
        echo "  - Debug logging"
        echo "  - Hot reloading (React/Node)"
        echo ""
        get_credentials
        set_build_target "development"
        podman compose up --build
        ;;
    "prod")
        echo "🏭 Starting production environment..."
        echo "✅ Features enabled:"
        echo "  - Optimized runtime images"
        echo "  - No development dependencies"
        echo "  - Production configuration"
        echo "  - Minimal attack surface"
        echo ""
        get_credentials
        set_build_target "production"
        podman compose up --build
        ;;
    "quick"|"no-build")
        echo "⚡ Quick start (no rebuild, uses existing images)..."
        get_credentials
        set_build_target "development"
        podman compose up -d
        echo "✅ Services started. Check logs with: ./dev.sh logs"
        ;;
    "restart")
        echo "🔄 Restarting services with fresh AWS credentials..."
        
        # Get fresh credentials using the same pattern as aws-credentials-automation.md
        load_config
        if [ -z "$AWS_ACCOUNT_ID" ]; then
            setup_config
        fi
        
        echo "🔐 Getting fresh AWS credentials for account: $AWS_ACCOUNT_ID"
        
        # Ensure AWS credentials are available
        if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
            echo "❌ AWS credentials not found. Please ensure you have valid AWS credentials set."
            echo "💡 You can use any of these methods:"
            echo "   - AWS CLI: aws configure"
            echo "   - Environment variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN"
            echo "   - IAM roles or instance profiles"
            exit 1
        fi
        
        if [ $? -ne 0 ]; then
            echo "❌ Failed to get fresh AWS credentials"
            exit 1
        fi
        
        # Get auth provider type from cached config or YAML
        get_auth_provider_type
        
        export AWS_REGION="$AWS_REGION"
        export AUTH_PROVIDER_TYPE="$AUTH_PROVIDER_TYPE"
        
        # Export SECRETS_MANAGER_ARN for all services
        if [ -n "$SECRETS_MANAGER_ARN" ]; then
            export SECRETS_MANAGER_ARN="$SECRETS_MANAGER_ARN"
        fi
        
        # Export S3_TEMPLATE_BUCKET for configuration-api
        if [ -n "$S3_TEMPLATE_BUCKET" ]; then
            export S3_TEMPLATE_BUCKET="$S3_TEMPLATE_BUCKET"
        fi
        
        # Verify credentials are set
        if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ] || [ -z "$AWS_SESSION_TOKEN" ]; then
            echo "❌ Failed to export AWS credentials properly"
            exit 1
        fi
        
        echo "✅ Fresh AWS credentials obtained for region: $AWS_REGION"
        echo "🔐 OAuth 2.0 provider: $AUTH_PROVIDER_TYPE"
        echo "🔑 Secrets Manager ARN: ${SECRETS_MANAGER_ARN:-'Not set'}"
        echo "🪣 S3 Template Bucket: ${S3_TEMPLATE_BUCKET:-'Not set'}"
        echo "🔍 Debug: AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID:0:20}..."
        
        set_build_target "development"
        
        if [ -z "$2" ]; then
            # Restart all services with fresh credentials
            echo "🔄 Stopping all services..."
            podman compose down --remove-orphans
            echo "🚀 Starting all services with fresh credentials..."
            podman compose up -d --force-recreate --remove-orphans
            echo "✅ All services restarted with fresh credentials"
        else
            # Restart specific service but ensure ALL get new credentials
            echo "🔄 Restarting $2 with fresh credentials for ALL services..."
            echo "⚠️  Note: ALL containers will be recreated to ensure credential consistency"
            podman compose down --remove-orphans
            podman compose up -d --force-recreate --remove-orphans
            echo "✅ All services restarted (focused on $2) with fresh credentials"
        fi
        ;;
    "logs")
        if [ -z "$2" ]; then
            podman compose logs -f
        else
            podman compose logs -f $2
        fi
        ;;
    "stop"|"down")
        echo "⏹️  Stopping services..."
        podman compose down
        echo "✅ Services stopped"
        ;;
    "build")
        echo "🔨 Building services with development target..."
        get_credentials
        set_build_target "development"
        podman compose build $2
        echo "✅ Build complete"
        ;;
    "build-prod")
        echo "🔨 Building services with production target..."
        get_credentials
        set_build_target "production"
        podman compose build $2
        echo "✅ Production build complete"
        ;;
    "rebuild")
        echo "🔨 Rebuilding and starting development services..."
        get_credentials
        set_build_target "development"
        podman compose down
        podman compose build $2
        podman compose up -d
        echo "✅ Development rebuild complete"
        ;;
    "rebuild-prod")
        echo "🔨 Rebuilding and starting production services..."
        get_credentials
        set_build_target "production"
        podman compose down
        podman compose build $2
        podman compose up -d
        echo "✅ Production rebuild complete"
        ;;
    "shell")
        service=${2:-"agent-1"}
        echo "🐚 Opening shell in $service..."
        podman compose exec $service /bin/bash
        ;;
    "test")
        service=${2:-"agent-1"}
        echo "🧪 Running tests in $service..."
        podman compose exec $service python -m pytest
        ;;
    "status")
        echo "📊 Service status:"
        podman compose ps
        ;;
    "clean")
        echo "🧹 Cleaning up Docker resources..."
        podman compose down -v
        podman system prune -f
        echo "✅ Cleanup complete"
        ;;
    "snowflake-test")
        echo "❄️  Testing Snowflake connection..."
        get_credentials
        podman compose exec agent-1 python -c "
from common.knowledge_base.custom.snowflake import SnowflakeKnowledgeBaseProvider
import json
config = {'provider': 'snowflake', 'provider_type': 'custom', 'ssm_prefix': '/genai-in-a-box/anshrma/knowledge-base'}
provider = SnowflakeKnowledgeBaseProvider(config)
tools = provider.initialize()
print(f'Initialized {len(tools)} tools')
"
        ;;
    "config")
        echo "⚙️  Current development configuration:"
        load_config
        if [ -f "$CONFIG_FILE" ]; then
            echo "  📄 Config file: $CONFIG_FILE"
            echo "  🏦 AWS Account ID: ${AWS_ACCOUNT_ID:-'Not set'}"
            echo "  🌍 AWS Region: ${AWS_REGION:-'Not set'}"
            echo "  🔐 Secrets Manager ARN: ${SECRETS_MANAGER_ARN:-'Not set'}"
            echo "  🔐 Auth Provider Type: ${AUTH_PROVIDER_TYPE:-'Not set'}"
            echo "  🪣 S3 Template Bucket: ${S3_TEMPLATE_BUCKET:-'Not set'}"
        else
            echo "  ❌ No configuration file found. Run './dev.sh start' to create one."
        fi
        ;;
    "reconfigure")
        echo "🔄 Reconfiguring development environment..."
        if [ -f "$CONFIG_FILE" ]; then
            rm "$CONFIG_FILE"
            echo "🗑️  Removed existing configuration"
        fi
        setup_config
        ;;
    "help"|*)
        echo "🔥 GenAI-in-a-Box Development Helper - Multi-Stage Build Edition"
        echo ""
        echo "Usage: ./dev.sh <command> [service]"
        echo ""
        echo "🚀 Primary Commands:"
        echo "  dev, start, up   Start DEVELOPMENT environment (auto-reload, file watching)"
        echo "  prod             Start PRODUCTION environment (optimized, minimal)"
        echo "  quick, no-build  Quick start (no rebuild, uses existing images)"
        echo "  stop, down       Stop all services"
        echo ""
        echo "🔨 Build Commands:"
        echo "  build [svc]      Build service(s) with DEVELOPMENT target"
        echo "  build-prod [svc] Build service(s) with PRODUCTION target"
        echo "  rebuild [svc]    Rebuild and start DEVELOPMENT services"
        echo "  rebuild-prod [svc] Rebuild and start PRODUCTION services"
        echo ""
        echo "🛠️  Management Commands:"
        echo "  restart [svc]    Restart service(s) with fresh AWS credentials (bypasses health checks)"
        echo "  logs [svc]       Show logs (follow mode)"
        echo "  shell [svc]      Open shell in service (default: agent-1)"
        echo "  test [svc]       Run tests in service"
        echo "  status           Show service status"
        echo "  clean            Clean up Docker resources"
        echo ""
        echo "🔧 Configuration Commands:"
        echo "  config           Show current configuration"
        echo "  reconfigure      Reset and reconfigure development settings"
        echo "  snowflake-test   Test Snowflake connection"
        echo "  help             Show this help"
        echo ""
        echo "🎯 Multi-Stage Build Targets:"
        echo "  DEVELOPMENT      File watching, auto-restart, debug logging, hot reload"
        echo "  PRODUCTION       Optimized runtime, no dev deps, minimal attack surface"
        echo ""
        echo "⚙️  Configuration (auto-setup on first run):"
        echo "  - AWS Account ID (stored in .dev-config)"
        echo "  - AWS Region (defaults to us-east-1)"
        echo "  - Auth Provider Type (read from config/development.yaml)"
        echo "  - Secrets Manager ARN (auto-discovered or manual entry)"
        echo ""
        echo "📝 Development Examples:"
        echo "  ./dev.sh dev             # Start development with auto-reload (RECOMMENDED)"
        echo "  ./dev.sh quick           # Quick start without rebuild"
        echo "  ./dev.sh logs agent-1    # Follow logs for agent-1"
        echo "  ./dev.sh restart agent-1 # Restart just agent-1"
        echo "  ./dev.sh shell agent-1   # Open shell in agent-1"
        echo ""
        echo "🏭 Production Examples:"
        echo "  ./dev.sh prod            # Start production environment"
        echo "  ./dev.sh build-prod      # Build production images"
        echo "  ./dev.sh rebuild-prod    # Rebuild and start production"
        echo ""
        echo "💡 Tips:"
        echo "  - Use 'dev' for daily development (instant code changes)"
        echo "  - Use 'prod' to test production builds locally"
        echo "  - Use 'quick' to restart existing containers fast"
        echo "  - All commands handle AWS credentials automatically"
        echo "  - Auth provider type is read from config/development.yaml"
        echo "  - Single SECRETS_MANAGER_ARN used for all authentication services"
        ;;
esac
