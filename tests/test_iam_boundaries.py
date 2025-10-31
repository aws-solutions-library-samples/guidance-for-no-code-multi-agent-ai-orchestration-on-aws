"""
Unit tests for IAM permissions boundaries implementation.

This module validates boundary policy creation, content, and application
to IAM roles across different service types.
"""

import pytest
from unittest.mock import Mock, patch
import aws_cdk as cdk
from aws_cdk import aws_iam as iam

from helper.config import Config
from stacks.iam_boundaries.stack import IAMBoundariesStack
from stacks.iam_boundaries.policies import BoundaryPolicyFactory, PermissionsBoundaryConfig
from stacks.iam_boundaries.constants import (
    ServiceType,
    FULL_AGENT_SERVICE_BOUNDARY_POLICY_NAME,
    FULL_CONFIGURATION_API_BOUNDARY_POLICY_NAME,
    FULL_SUPERVISOR_AGENT_BOUNDARY_POLICY_NAME,
    AGENT_SERVICE_ALLOWED_SERVICES,
    CONFIGURATION_API_ALLOWED_SERVICES,
    SUPERVISOR_AGENT_ALLOWED_SERVICES,
    RESTRICTED_ACTIONS
)


class TestBoundaryPolicyFactory:
    """Test boundary policy factory functionality."""
    
    def test_agent_service_boundary_policy_creation(self):
        """Test that agent service boundary policy is created with correct permissions."""
        policy_doc = BoundaryPolicyFactory.create_agent_service_boundary_policy()
        
        # Verify policy document exists and has statements
        assert policy_doc is not None
        assert len(policy_doc.statements) >= 2  # At least allow and deny statements
        
        # Check that allowed services are included
        allow_statements = [stmt for stmt in policy_doc.statements if stmt.effect == iam.Effect.ALLOW]
        assert len(allow_statements) >= 1
        
        # Verify allowed services are in the policy
        for service in AGENT_SERVICE_ALLOWED_SERVICES:
            service_action = f"{service}:*"
            found = False
            for stmt in allow_statements:
                if service_action in stmt.actions:
                    found = True
                    break
            assert found, f"Service {service} not found in agent boundary policy"
    
    def test_configuration_api_boundary_policy_creation(self):
        """Test that configuration API boundary policy is created with correct permissions."""
        policy_doc = BoundaryPolicyFactory.create_configuration_api_boundary_policy()
        
        # Verify policy document exists and has statements
        assert policy_doc is not None
        assert len(policy_doc.statements) >= 2  # At least allow and deny statements
        
        # Check that allowed services are included
        allow_statements = [stmt for stmt in policy_doc.statements if stmt.effect == iam.Effect.ALLOW]
        assert len(allow_statements) >= 1
        
        # Verify CloudFormation operations are allowed for Configuration API
        cloudformation_found = False
        for stmt in allow_statements:
            if "cloudformation:*" in stmt.actions:
                cloudformation_found = True
                break
        assert cloudformation_found, "CloudFormation operations not found in Configuration API boundary policy"
    
    def test_supervisor_agent_boundary_policy_creation(self):
        """Test that supervisor agent boundary policy is created with correct permissions."""
        policy_doc = BoundaryPolicyFactory.create_supervisor_agent_boundary_policy()
        
        # Verify policy document exists and has statements
        assert policy_doc is not None
        assert len(policy_doc.statements) >= 2  # At least allow and deny statements
        
        # Check that Bedrock operations are allowed
        allow_statements = [stmt for stmt in policy_doc.statements if stmt.effect == iam.Effect.ALLOW]
        assert len(allow_statements) >= 1
        
        bedrock_found = False
        for stmt in allow_statements:
            if "bedrock:*" in stmt.actions:
                bedrock_found = True
                break
        assert bedrock_found, "Bedrock operations not found in supervisor boundary policy"
    
    def test_restricted_actions_are_denied(self):
        """Test that restricted actions are explicitly denied in all boundary policies."""
        policies = [
            BoundaryPolicyFactory.create_agent_service_boundary_policy(),
            BoundaryPolicyFactory.create_configuration_api_boundary_policy(),
            BoundaryPolicyFactory.create_supervisor_agent_boundary_policy()
        ]
        
        for policy_doc in policies:
            deny_statements = [stmt for stmt in policy_doc.statements if stmt.effect == iam.Effect.DENY]
            assert len(deny_statements) >= 1, "No deny statements found in boundary policy"
            
            # Verify restricted actions are denied
            restricted_actions_denied = False
            for stmt in deny_statements:
                for action in RESTRICTED_ACTIONS[:3]:  # Check first few restricted actions
                    if action in stmt.actions:
                        restricted_actions_denied = True
                        break
                if restricted_actions_denied:
                    break
            
            assert restricted_actions_denied, "Restricted actions not properly denied in boundary policy"
    
    def test_cross_region_access_denied(self):
        """Test that cross-region access is denied in all boundary policies."""
        policies = [
            BoundaryPolicyFactory.create_agent_service_boundary_policy(),
            BoundaryPolicyFactory.create_configuration_api_boundary_policy(),
            BoundaryPolicyFactory.create_supervisor_agent_boundary_policy()
        ]
        
        for policy_doc in policies:
            # Look for cross-region denial statements
            cross_region_deny_found = False
            for stmt in policy_doc.statements:
                if stmt.effect == iam.Effect.DENY and stmt.conditions:
                    for condition_key, condition_value in stmt.conditions.items():
                        if "aws:RequestedRegion" in str(condition_value):
                            cross_region_deny_found = True
                            break
                if cross_region_deny_found:
                    break
            
            assert cross_region_deny_found, "Cross-region access not properly restricted"
    
    def test_get_boundary_policy_for_service_type(self):
        """Test service type to policy mapping."""
        # Test valid service types
        agent_policy = BoundaryPolicyFactory.get_boundary_policy_for_service_type(ServiceType.AGENT_SERVICE)
        assert agent_policy is not None
        
        config_policy = BoundaryPolicyFactory.get_boundary_policy_for_service_type(ServiceType.CONFIGURATION_API)
        assert config_policy is not None
        
        supervisor_policy = BoundaryPolicyFactory.get_boundary_policy_for_service_type(ServiceType.SUPERVISOR_AGENT)
        assert supervisor_policy is not None
        
        # Test invalid service type
        with pytest.raises(ValueError):
            BoundaryPolicyFactory.get_boundary_policy_for_service_type("invalid_service_type")


class TestPermissionsBoundaryConfig:
    """Test permissions boundary configuration functionality."""
    
    def test_config_initialization(self):
        """Test boundary configuration initialization."""
        config = PermissionsBoundaryConfig(
            service_type=ServiceType.AGENT_SERVICE,
            allowed_services=["bedrock", "ssm"],
            additional_allowed_actions=["bedrock:InvokeModel"],
            additional_restricted_actions=["iam:CreateUser"]
        )
        
        assert config.service_type == ServiceType.AGENT_SERVICE
        assert "bedrock" in config.allowed_services
        assert "ssm" in config.allowed_services
        assert "bedrock:InvokeModel" in config.additional_allowed_actions
        assert "iam:CreateUser" in config.additional_restricted_actions
    
    def test_get_allowed_actions(self):
        """Test allowed actions generation from configuration."""
        config = PermissionsBoundaryConfig(
            service_type=ServiceType.AGENT_SERVICE,
            allowed_services=["bedrock", "ssm"],
            additional_allowed_actions=["bedrock:InvokeModel"]
        )
        
        allowed_actions = config.get_allowed_actions()
        
        assert "bedrock:*" in allowed_actions
        assert "ssm:*" in allowed_actions
        assert "bedrock:InvokeModel" in allowed_actions
    
    def test_restricted_actions_include_base_and_additional(self):
        """Test that restricted actions include both base and additional restrictions."""
        config = PermissionsBoundaryConfig(
            service_type=ServiceType.AGENT_SERVICE,
            additional_restricted_actions=["custom:RestrictedAction"]
        )
        
        # Should include base restricted actions
        assert any(action in RESTRICTED_ACTIONS for action in config.restricted_actions)
        
        # Should include additional restricted actions
        assert "custom:RestrictedAction" in config.restricted_actions


class TestIAMBoundariesStack:
    """Test IAM boundaries stack functionality."""
    
    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration for testing."""
        config = Mock(spec=Config)
        config._environment = "test"
        config.get.return_value = "test-value"
        return config
    
    def test_stack_initialization(self, mock_config):
        """Test stack initialization and boundary policy creation."""
        app = cdk.App()
        
        stack = IAMBoundariesStack(
            app, 
            "test-iam-boundaries",
            config=mock_config
        )
        
        # Verify stack was created
        assert stack is not None
        assert len(stack.boundary_policies) == 3
        
        # Verify all service types have boundary policies
        assert ServiceType.AGENT_SERVICE in stack.boundary_policies
        assert ServiceType.CONFIGURATION_API in stack.boundary_policies
        assert ServiceType.SUPERVISOR_AGENT in stack.boundary_policies
    
    def test_boundary_policy_arn_retrieval(self, mock_config):
        """Test boundary policy ARN retrieval methods."""
        app = cdk.App()
        
        stack = IAMBoundariesStack(
            app,
            "test-iam-boundaries", 
            config=mock_config
        )
        
        # Test valid service types
        agent_arn = stack.get_boundary_policy_arn(ServiceType.AGENT_SERVICE)
        assert agent_arn is not None
        
        config_arn = stack.get_boundary_policy_arn(ServiceType.CONFIGURATION_API)
        assert config_arn is not None
        
        supervisor_arn = stack.get_boundary_policy_arn(ServiceType.SUPERVISOR_AGENT)
        assert supervisor_arn is not None
        
        # Test invalid service type
        with pytest.raises(ValueError):
            stack.get_boundary_policy_arn("invalid_service_type")
    
    def test_boundary_policy_object_retrieval(self, mock_config):
        """Test boundary policy object retrieval methods."""
        app = cdk.App()
        
        stack = IAMBoundariesStack(
            app,
            "test-iam-boundaries",
            config=mock_config
        )
        
        # Test valid service types
        agent_policy = stack.get_boundary_policy(ServiceType.AGENT_SERVICE)
        assert isinstance(agent_policy, iam.ManagedPolicy)
        
        config_policy = stack.get_boundary_policy(ServiceType.CONFIGURATION_API)
        assert isinstance(config_policy, iam.ManagedPolicy)
        
        supervisor_policy = stack.get_boundary_policy(ServiceType.SUPERVISOR_AGENT)
        assert isinstance(supervisor_policy, iam.ManagedPolicy)
        
        # Test invalid service type
        with pytest.raises(ValueError):
            stack.get_boundary_policy("invalid_service_type")


class TestIAMPolicyMixinBoundarySupport:
    """Test IAM policy mixin boundary support functionality."""
    
    @pytest.fixture
    def mock_stack(self):
        """Create a mock stack for testing mixin functionality."""
        from stacks.common.mixins.iam import IAMPolicyMixin
        
        class MockStack(IAMPolicyMixin):
            def __init__(self):
                pass
                
        return MockStack()
    
    @patch('aws_cdk.aws_iam.Role')
    @patch('aws_cdk.aws_iam.ManagedPolicy.from_managed_policy_arn')
    def test_create_role_with_boundary(self, mock_from_arn, mock_role, mock_stack):
        """Test role creation with permissions boundary."""
        boundary_arn = "arn:aws:iam::123456789012:policy/TestBoundary"
        role_name = "test-role"
        
        # Mock the boundary policy
        mock_boundary = Mock()
        mock_from_arn.return_value = mock_boundary
        
        # Mock the role
        mock_role_instance = Mock()
        mock_role.return_value = mock_role_instance
        
        # Create role with boundary
        result = mock_stack.create_role_with_boundary(
            role_name=role_name,
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            permissions_boundary_arn=boundary_arn,
            description="Test role with boundary"
        )
        
        # Verify role creation was called with boundary
        mock_role.assert_called_once()
        call_args = mock_role.call_args[1]
        assert call_args["role_name"] == f"{role_name}-role"
        assert call_args["permissions_boundary"] == mock_boundary
    
    @patch('aws_cdk.aws_iam.ManagedPolicy.from_managed_policy_arn')
    def test_apply_permissions_boundary(self, mock_from_arn, mock_stack):
        """Test applying boundary to existing role."""
        boundary_arn = "arn:aws:iam::123456789012:policy/TestBoundary"
        
        # Mock role with CfnRole child
        mock_role = Mock(spec=iam.Role)
        mock_role.role_name = "test-role"
        mock_cfn_role = Mock(spec=iam.CfnRole)
        mock_role.node.default_child = mock_cfn_role
        
        # Mock boundary policy
        mock_boundary = Mock()
        mock_boundary.managed_policy_arn = boundary_arn
        mock_from_arn.return_value = mock_boundary
        
        # Apply boundary
        mock_stack.apply_permissions_boundary(mock_role, boundary_arn)
        
        # Verify boundary was applied to CfnRole
        assert mock_cfn_role.permissions_boundary == boundary_arn
        
    def test_apply_permissions_boundary_invalid_role(self, mock_stack):
        """Test error handling when applying boundary to invalid role type."""
        boundary_arn = "arn:aws:iam::123456789012:policy/TestBoundary"
        
        # Mock role with non-CfnRole child
        mock_role = Mock(spec=iam.Role)
        mock_role.role_name = "test-role"
        mock_role.node.default_child = "not-a-cfn-role"  # Invalid type
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Expected CfnRole"):
            mock_stack.apply_permissions_boundary(mock_role, boundary_arn)


class TestIntegrationValidation:
    """Integration tests for boundary policy application."""
    
    @pytest.fixture
    def test_app_and_config(self):
        """Create test app and configuration."""
        app = cdk.App()
        config = Mock(spec=Config)
        config._environment = "test"
        config.get.return_value = "test-value"
        return app, config
    
    def test_iam_boundaries_stack_synthesis(self, test_app_and_config):
        """Test that IAM boundaries stack synthesizes without errors."""
        app, config = test_app_and_config
        
        try:
            stack = IAMBoundariesStack(
                app,
                "test-iam-boundaries",
                config=config
            )
            
            # Attempt to synthesize the template
            template = cdk.assertions.Template.from_stack(stack)
            
            # Verify managed policies are created
            template.resource_count_is("AWS::IAM::ManagedPolicy", 3)
            
            # Verify outputs are created
            template.has_output("agent-service-boundary-arn", {})
            template.has_output("configuration-api-boundary-arn", {})
            template.has_output("supervisor-agent-boundary-arn", {})
            
        except Exception as e:
            pytest.fail(f"Stack synthesis failed: {str(e)}")
    
    def test_boundary_policy_names_are_correct(self, test_app_and_config):
        """Test that boundary policies have correct names."""
        app, config = test_app_and_config
        
        stack = IAMBoundariesStack(
            app,
            "test-iam-boundaries",
            config=config
        )
        
        template = cdk.assertions.Template.from_stack(stack)
        
        # Check that managed policies have expected names
        template.has_resource_properties("AWS::IAM::ManagedPolicy", {
            "ManagedPolicyName": FULL_AGENT_SERVICE_BOUNDARY_POLICY_NAME
        })
        
        template.has_resource_properties("AWS::IAM::ManagedPolicy", {
            "ManagedPolicyName": FULL_CONFIGURATION_API_BOUNDARY_POLICY_NAME
        })
        
        template.has_resource_properties("AWS::IAM::ManagedPolicy", {
            "ManagedPolicyName": FULL_SUPERVISOR_AGENT_BOUNDARY_POLICY_NAME
        })
    
    def test_boundary_policies_have_proper_tags(self, test_app_and_config):
        """Test that boundary policies are tagged correctly."""
        app, config = test_app_and_config
        
        stack = IAMBoundariesStack(
            app,
            "test-iam-boundaries",
            config=config
        )
        
        template = cdk.assertions.Template.from_stack(stack)
        
        # Verify tags are applied to all managed policies
        managed_policies = template.find_resources("AWS::IAM::ManagedPolicy")
        
        for policy_id, policy_props in managed_policies.items():
            tags = policy_props.get("Properties", {}).get("Tags", [])
            tag_dict = {tag["Key"]: tag["Value"] for tag in tags}
            
            assert "Purpose" in tag_dict
            assert tag_dict["Purpose"] == "PermissionsBoundary"
            assert "RestrictPrivilegeEscalation" in tag_dict
            assert tag_dict["RestrictPrivilegeEscalation"] == "true"


class TestServiceTypeConstants:
    """Test service type constants and mappings."""
    
    def test_service_type_constants(self):
        """Test that service type constants are defined correctly."""
        assert ServiceType.AGENT_SERVICE == "agent_service"
        assert ServiceType.CONFIGURATION_API == "configuration_api"
        assert ServiceType.SUPERVISOR_AGENT == "supervisor_agent"
    
    def test_allowed_services_constants(self):
        """Test that allowed services constants are defined correctly."""
        # Agent service should have Bedrock and basic infrastructure
        assert "bedrock" in AGENT_SERVICE_ALLOWED_SERVICES
        assert "ssm" in AGENT_SERVICE_ALLOWED_SERVICES
        assert "logs" in AGENT_SERVICE_ALLOWED_SERVICES
        
        # Configuration API should have CloudFormation and IAM
        assert "cloudformation" in CONFIGURATION_API_ALLOWED_SERVICES
        assert "iam" in CONFIGURATION_API_ALLOWED_SERVICES
        
        # Supervisor should have coordination services
        assert "bedrock" in SUPERVISOR_AGENT_ALLOWED_SERVICES
        assert "ecs" in SUPERVISOR_AGENT_ALLOWED_SERVICES
    
    def test_restricted_actions_include_high_risk_operations(self):
        """Test that restricted actions include known high-risk operations."""
        # Should restrict account-level operations
        assert any("organizations:" in action for action in RESTRICTED_ACTIONS)
        assert any("account:" in action for action in RESTRICTED_ACTIONS)
        
        # Should restrict cross-account access
        assert any("sts:AssumeRole" in action for action in RESTRICTED_ACTIONS)
        
        # Should restrict high-risk IAM operations
        assert any("iam:CreateUser" in action for action in RESTRICTED_ACTIONS)
        assert any("iam:CreateAccessKey" in action for action in RESTRICTED_ACTIONS)


if __name__ == "__main__":
    pytest.main([__file__])
