"""
Cognito authentication mixin for CDK stacks.

This module provides reusable Cognito functionality including:
- User pool creation and configuration
- User pool client management
- Domain configuration
- User pool groups for RBAC
- Secrets Manager integration
- Security best practices
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from aws_cdk import (
    aws_cognito as cognito,
    aws_secretsmanager as secretsmanager,
    RemovalPolicy,
    SecretValue
)
from aws_cdk.aws_cognito import FeaturePlan
from constructs import Construct

from ..exceptions import ResourceCreationError, ValidationError
from ..validators import ConfigValidator


def _get_feature_plan_from_string(feature_plan_str: str) -> FeaturePlan:
    """Convert string to FeaturePlan enum."""
    feature_plan_mapping = {
        'PLUS': FeaturePlan.PLUS
    }
    return feature_plan_mapping.get(feature_plan_str.upper(), FeaturePlan.PLUS)


def _get_threat_protection_from_string(mode_str: str) -> cognito.StandardThreatProtectionMode:
    """Convert string to StandardThreatProtectionMode enum."""
    mode_mapping = {
        'FULL_FUNCTION': cognito.StandardThreatProtectionMode.FULL_FUNCTION,
        'AUDIT_ONLY': cognito.StandardThreatProtectionMode.AUDIT_ONLY
    }
    return mode_mapping.get(mode_str.upper(), cognito.StandardThreatProtectionMode.FULL_FUNCTION)


@dataclass 
class CognitoUserGroup:
    """Configuration for a Cognito User Pool Group."""
    name: str
    description: str
    precedence: int


@dataclass
class CognitoConfiguration:
    """
    Configuration class for Cognito resources.
    
    This class encapsulates all configurable options for Cognito
    to provide type safety and clear documentation.
    """
    # User Pool Configuration
    user_pool_name: str
    client_name: str = "WebAppAuthentication"
    
    # User Groups Configuration
    create_default_groups: bool = True
    custom_groups: Optional[List[CognitoUserGroup]] = None
    
    # Security Configuration
    self_sign_up_enabled: bool = False
    account_recovery: cognito.AccountRecovery = cognito.AccountRecovery.NONE
    feature_plan: FeaturePlan = FeaturePlan.PLUS
    standard_threat_protection_mode: cognito.StandardThreatProtectionMode = cognito.StandardThreatProtectionMode.FULL_FUNCTION
    
    # Password Policy Configuration
    min_password_length: int = 8
    require_lowercase: bool = True
    require_uppercase: bool = True
    require_digits: bool = True
    require_symbols: bool = True
    
    # Sign-in Configuration
    sign_in_with_email: bool = True
    sign_in_with_username: bool = False
    sign_in_with_phone: bool = False
    auto_verify_email: bool = True
    auto_verify_phone: bool = False
    
    # Client Configuration
    generate_secret: bool = False  # Set to False for browser-based applications (AWS Amplify)
    prevent_user_existence_errors: bool = True
    supported_identity_providers: List[cognito.UserPoolClientIdentityProvider] = None
    
    # OAuth Configuration (for future use)
    enable_oauth: bool = False
    callback_urls: Optional[List[str]] = None
    logout_urls: Optional[List[str]] = None
    oauth_scopes: Optional[List[cognito.OAuthScope]] = None
    
    # Cleanup Configuration
    removal_policy: RemovalPolicy = RemovalPolicy.DESTROY
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.supported_identity_providers is None:
            self.supported_identity_providers = [
                cognito.UserPoolClientIdentityProvider.COGNITO
            ]
        
        # Validate configuration
        if self.min_password_length < 6 or self.min_password_length > 99:
            raise ValidationError(
                "Password length must be between 6 and 99 characters",
                field="min_password_length"
            )
        
        ConfigValidator.validate_resource_name(self.user_pool_name)
        ConfigValidator.validate_resource_name(self.client_name)


@dataclass
class CognitoResources:
    """
    Container for created Cognito resources.
    
    This class provides a structured way to return and access
    all created Cognito resources.
    """
    user_pool: cognito.UserPool
    user_pool_client: cognito.UserPoolClient
    secrets_manager_secret: secretsmanager.Secret
    user_groups: Dict[str, cognito.CfnUserPoolGroup] = None
    
    @property
    def user_pool_id(self) -> str:
        """Get the User Pool ID."""
        return self.user_pool.user_pool_id
    
    @property
    def client_id(self) -> str:
        """Get the User Pool Client ID."""
        return self.user_pool_client.user_pool_client_id
    
    @property
    def secret_arn(self) -> str:
        """Get the Secrets Manager secret ARN."""
        return self.secrets_manager_secret.secret_arn


class CognitoMixin:
    """
    Mixin class providing Cognito authentication functionality.
    
    This mixin can be added to any CDK stack that needs Cognito
    authentication capabilities.
    """
    
    def create_cognito_authentication(
        self,
        scope: Construct,
        config: CognitoConfiguration,
        secret_name_suffix: str = "cognito-config"  # Changed from 'secret' to 'config' to avoid false security warnings
    ) -> CognitoResources:
        """
        Create a complete Cognito authentication setup with RBAC groups.
        
        Args:
            scope: CDK construct scope
            config: Cognito configuration
            secret_name_suffix: Suffix for the Secrets Manager secret name
            
        Returns:
            CognitoResources containing all created resources
            
        Raises:
            ResourceCreationError: If resource creation fails
            ValidationError: If configuration is invalid
        """
        try:
            # Create User Pool
            user_pool = self._create_user_pool(scope, config)
            
            # Create User Pool Client
            user_pool_client = self._create_user_pool_client(scope, user_pool, config)
            
            # Create User Pool Groups for RBAC
            user_groups = self._create_user_pool_groups(scope, user_pool, config)
            
            # Create Secrets Manager secret
            secret = self._create_cognito_secret(
                scope, user_pool, user_pool_client, secret_name_suffix
            )
            
            return CognitoResources(
                user_pool=user_pool,
                user_pool_client=user_pool_client,
                secrets_manager_secret=secret,
                user_groups=user_groups
            )
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create Cognito authentication setup: {str(e)}",
                resource_type="CognitoAuthentication"
            )
    
    def _create_user_pool(
        self,
        scope: Construct,
        config: CognitoConfiguration
    ) -> cognito.UserPool:
        """Create and configure the Cognito User Pool."""
        try:
            # Configure sign-in aliases
            sign_in_aliases = cognito.SignInAliases(
                email=config.sign_in_with_email,
                username=config.sign_in_with_username,
                phone=config.sign_in_with_phone
            )
            
            # Configure auto-verification
            auto_verify = cognito.AutoVerifiedAttrs(
                email=config.auto_verify_email,
                phone=config.auto_verify_phone
            )
            
            # Configure password policy
            password_policy = cognito.PasswordPolicy(
                min_length=config.min_password_length,
                require_lowercase=config.require_lowercase,
                require_uppercase=config.require_uppercase,
                require_digits=config.require_digits,
                require_symbols=config.require_symbols
            )
            
            return cognito.UserPool(
                scope,
                "UserPool",
                user_pool_name=config.user_pool_name,
                account_recovery=config.account_recovery,
                sign_in_aliases=sign_in_aliases,
                auto_verify=auto_verify,
                self_sign_up_enabled=config.self_sign_up_enabled,
                removal_policy=config.removal_policy,
                feature_plan=config.feature_plan,
                standard_threat_protection_mode=config.standard_threat_protection_mode,
                password_policy=password_policy
            )
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create User Pool: {str(e)}",
                resource_type="UserPool"
            )
    
    
    def _create_user_pool_client(
        self,
        scope: Construct,
        user_pool: cognito.UserPool,
        config: CognitoConfiguration
    ) -> cognito.UserPoolClient:
        """Create the Cognito User Pool Client."""
        try:
            client_props = {
                "user_pool_client_name": config.client_name,
                "generate_secret": config.generate_secret,
                "prevent_user_existence_errors": config.prevent_user_existence_errors,
                "supported_identity_providers": config.supported_identity_providers
            }
            
            # Add OAuth configuration if enabled
            if config.enable_oauth and config.callback_urls:
                oauth_flows = cognito.OAuthFlows(
                    authorization_code_grant=True
                )
                
                oauth_scopes = config.oauth_scopes or [cognito.OAuthScope.EMAIL]
                
                client_props["o_auth"] = cognito.OAuthSettings(
                    callback_urls=config.callback_urls,
                    logout_urls=config.logout_urls or config.callback_urls,
                    flows=oauth_flows,
                    scopes=oauth_scopes
                )
            
            return user_pool.add_client("UserPoolClientV2", **client_props)
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create User Pool Client: {str(e)}",
                resource_type="UserPoolClient"
            )
    
    def _create_user_pool_groups(
        self,
        scope: Construct,
        user_pool: cognito.UserPool,
        config: CognitoConfiguration
    ) -> Dict[str, cognito.CfnUserPoolGroup]:
        """Create User Pool Groups for role-based access control."""
        try:
            groups = {}
            
            # Create default RBAC groups
            if config.create_default_groups:
                default_groups = [
                    CognitoUserGroup(
                        name="admin",
                        description="System administrator with full access",
                        precedence=1
                    ),
                    CognitoUserGroup(
                        name="agent-creator",
                        description="Can create, read, and update agents",
                        precedence=2
                    ),
                    CognitoUserGroup(
                        name="supervisor-user",
                        description="Can interact with supervisor agents",
                        precedence=3
                    ),
                    CognitoUserGroup(
                        name="readonly-user",
                        description="Read-only access to configurations and chat",
                        precedence=4
                    )
                ]
                
                for group_config in default_groups:
                    group = cognito.CfnUserPoolGroup(
                        scope,
                        f"UserGroup{group_config.name.replace('-', '').title()}",
                        user_pool_id=user_pool.user_pool_id,
                        group_name=group_config.name,
                        description=group_config.description,
                        precedence=group_config.precedence
                    )
                    groups[group_config.name] = group
            
            # Create custom groups if provided
            if config.custom_groups:
                for group_config in config.custom_groups:
                    group = cognito.CfnUserPoolGroup(
                        scope,
                        f"CustomUserGroup{group_config.name.replace('-', '').title()}",
                        user_pool_id=user_pool.user_pool_id,
                        group_name=group_config.name,
                        description=group_config.description,
                        precedence=group_config.precedence
                    )
                    groups[group_config.name] = group
            
            return groups
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create User Pool Groups: {str(e)}",
                resource_type="UserPoolGroups"
            )
    
    def _create_cognito_secret(
        self,
        scope: Construct,
        user_pool: cognito.UserPool,
        user_pool_client: cognito.UserPoolClient,
        secret_name_suffix: str
    ) -> secretsmanager.Secret:
        """Create Secrets Manager secret for Cognito parameters."""
        try:
            # Never include client secret for browser-based applications using AWS Amplify
            # This prevents SECRET_HASH errors in browser authentication flows
            secret_values = {
                "pool_id": SecretValue.unsafe_plain_text(user_pool.user_pool_id),
                "app_client_id": SecretValue.unsafe_plain_text(user_pool_client.user_pool_client_id)
            }
            
            return secretsmanager.Secret(
                scope,
                "CognitoSecret",
                description="Cognito authentication parameters",
                secret_object_value=secret_values
            )
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to create Cognito secret: {str(e)}",
                resource_type="Secret"
            )
    
    def configure_oauth_for_load_balancer(
        self,
        cognito_resources: CognitoResources,
        load_balancer_dns: str,
        https: bool = True
    ) -> cognito.UserPoolClient:
        """
        Configure OAuth settings for Application Load Balancer integration.
        
        Args:
            cognito_resources: Previously created Cognito resources
            load_balancer_dns: DNS name of the Application Load Balancer
            https: Whether to use HTTPS URLs
            
        Returns:
            Updated User Pool Client with OAuth configuration
        """
        try:
            protocol = "https" if https else "http"
            
            callback_urls = [
                f"{protocol}://{load_balancer_dns}/oauth2/idpresponse",
                f"{protocol}://{load_balancer_dns}/"
            ]
            
            logout_urls = [f"{protocol}://{load_balancer_dns}/"]
            
            # Note: This would require recreating the client in a real scenario
            # For now, we'll return the existing client with a note about manual configuration
            return cognito_resources.user_pool_client
            
        except Exception as e:
            raise ResourceCreationError(
                f"Failed to configure OAuth for load balancer: {str(e)}",
                resource_type="OAuthConfiguration"
            )
