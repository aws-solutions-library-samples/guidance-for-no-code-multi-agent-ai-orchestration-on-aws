"""
Authentication Stack - Decoupled Cognito User Pool Infrastructure

This stack creates and manages the Cognito User Pool and related authentication
resources independently from the UI stack, allowing for better modularity and
independent lifecycle management.
"""

from constructs import Construct
from aws_cdk import Stack, RemovalPolicy

from helper.config import Config
from stacks.common.base import BaseStack
from stacks.common.mixins import CognitoMixin, CognitoConfiguration, CognitoResources
from stacks.common.mixins.cognito import _get_feature_plan_from_string
from stacks.common.constants import (
    DEFAULT_COGNITO_USER_POOL_SUFFIX,
    DEFAULT_COGNITO_DOMAIN_SUFFIX,
    DEFAULT_COGNITO_CLIENT_NAME,
    DEFAULT_COGNITO_PASSWORD_MIN_LENGTH
)


class AuthenticationStack(BaseStack, CognitoMixin):
    """
    Decoupled Authentication Stack for Cognito User Pool infrastructure.
    
    This stack manages authentication infrastructure independently, allowing:
    - Independent deployment and updates of authentication resources
    - Reuse of authentication across multiple application stacks
    - Better separation of concerns and lifecycle management
    - Easier migration to alternative identity providers in the future
    """
    
    def __init__(self, 
                 scope: Construct,
                 construct_id: str,
                 config: Config,
                 **kwargs) -> None:
        # Add solution ID and description
        kwargs['description'] = "Cognito User Pool for secure user authentication and authorization - (Solution ID - SO9637)"
        super().__init__(scope, construct_id, config, **kwargs)
        
        # Get configuration values
        project_name = self.get_required_config('ProjectName')
        user_suffix = self.get_optional_config('UserSuffix', 'user')
        
        # Create Cognito authentication resources
        self.cognito_resources = self._create_cognito_authentication(
            project_name, user_suffix
        )
        
        # Export outputs for use in other stacks
        from aws_cdk import CfnOutput
        
        CfnOutput(
            self,
            "CognitoUserPoolId",
            value=self.cognito_resources.user_pool.user_pool_id,
            description="Cognito User Pool ID for authentication",
            export_name=f"{project_name}-CognitoUserPoolId"
        )
        
        CfnOutput(
            self,
            "CognitoUserPoolArn",
            value=self.cognito_resources.user_pool.user_pool_arn,
            description="Cognito User Pool ARN for authentication",
            export_name=f"{project_name}-CognitoUserPoolArn"
        )
        
        CfnOutput(
            self,
            "CognitoClientId",
            value=self.cognito_resources.user_pool_client.user_pool_client_id,
            description="Cognito App Client ID for frontend authentication",
            export_name=f"{project_name}-CognitoClientId"
        )
        
        CfnOutput(
            self,
            "CognitoSecretArn",
            value=self.cognito_resources.secret_arn,
            description="Secrets Manager ARN containing Cognito configuration",
            export_name=f"{project_name}-CognitoSecretArn"
        )
        
        CfnOutput(
            self,
            "CognitoSecretName",
            value=f"{project_name}-cognito-secret",
            description="Cognito secret name in Secrets Manager",
            export_name=f"{project_name}-CognitoSecretName"
        )
    
    def _create_cognito_authentication(self,
                                      project_name: str,
                                      user_suffix: str) -> CognitoResources:
        """
        Create Cognito User Pool and authentication resources.
        
        Returns:
            CognitoResources: Created Cognito resources including User Pool, Client, and Secret
        """
        user_pool_name = f"{project_name}-{DEFAULT_COGNITO_USER_POOL_SUFFIX}"
        
        # Get Cognito configuration from config file or use defaults
        # Skip domain creation to avoid global naming conflicts across AWS accounts
        cognito_config = CognitoConfiguration(
            user_pool_name=user_pool_name,
            client_name=self.get_optional_config('CognitoClientName', DEFAULT_COGNITO_CLIENT_NAME),
            
            # Security configuration
            self_sign_up_enabled=self.get_optional_config('CognitoSelfSignUpEnabled', False),
            feature_plan=_get_feature_plan_from_string(
                self.get_optional_config('CognitoFeaturePlan', 'PLUS')
            ),
            
            # Password policy
            min_password_length=self.get_optional_config(
                'CognitoPasswordMinLength', 
                DEFAULT_COGNITO_PASSWORD_MIN_LENGTH
            ),
            require_lowercase=self.get_optional_config('CognitoRequireLowercase', True),
            require_uppercase=self.get_optional_config('CognitoRequireUppercase', True),
            require_digits=self.get_optional_config('CognitoRequireDigits', True),
            require_symbols=self.get_optional_config('CognitoRequireSymbols', True),
            
            # Sign-in configuration
            sign_in_with_email=self.get_optional_config('CognitoSignInWithEmail', True),
            sign_in_with_username=self.get_optional_config('CognitoSignInWithUsername', False),
            sign_in_with_phone=self.get_optional_config('CognitoSignInWithPhone', False),
            auto_verify_email=self.get_optional_config('CognitoAutoVerifyEmail', True),
            
            # Client configuration
            # False for browser-based applications using AWS Amplify
            generate_secret=self.get_optional_config('CognitoGenerateSecret', False),
            prevent_user_existence_errors=self.get_optional_config(
                'CognitoPreventUserExistenceErrors', 
                True
            ),
            
            # Cleanup configuration
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # Create Cognito resources using mixin
        return self.create_cognito_authentication(
            self, 
            cognito_config, 
            f"{project_name}-cognito-secret"
        )
