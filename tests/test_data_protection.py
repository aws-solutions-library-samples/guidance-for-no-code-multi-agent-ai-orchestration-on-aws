"""
Comprehensive test suite for AWS CloudWatch Logs data protection functionality.

This module tests log group-level data protection policies, data identifier configurations,
policy generation, validation, and integration with the BaseStack infrastructure.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import re
import logging
from typing import Dict, List, Any

# Import modules to test
from stacks.data_protection import (
    ManagedDataIdentifierRegistry,
    CustomDataIdentifierBuilder,
    DataIdentifierValidator,
    get_credentials_identifiers,
    get_pii_identifiers,
    get_custom_platform_identifiers,
    DataProtectionPolicyConfig,
    DataProtectionPolicyType,
    LogGroupDataProtectionPolicyBuilder,
    create_account_policy_document,
    validate_policy_size
)
from stacks.data_protection.identifiers import (
    ManagedDataIdentifier,
    CustomDataIdentifier,
    ManagedDataIdentifierCategory
)
from application_src.common.data_protection_utils import (
    DataProtectionManager,
    SensitiveDataDetector,
    is_data_protection_enabled,
    validate_sensitive_data_patterns,
    mask_sensitive_data_for_logging,
    create_safe_log_message
)
from helper.config import Config


class TestManagedDataIdentifiers(unittest.TestCase):
    """Test AWS managed data identifier functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.region = "us-east-1"
        self.registry = ManagedDataIdentifierRegistry()
    
    def test_get_identifier_by_name_success(self):
        """Test successful retrieval of managed identifier by name."""
        identifier = self.registry.get_identifier_by_name("aws-access-key", self.region)
        
        self.assertIsNotNone(identifier)
        self.assertEqual(identifier.category, ManagedDataIdentifierCategory.CREDENTIALS)
        self.assertIn("aws-access-key", identifier.arn)
        self.assertIn(self.region, identifier.arn)
        self.assertTrue(identifier.description)
    
    def test_get_identifier_by_name_not_found(self):
        """Test retrieval of non-existent managed identifier."""
        identifier = self.registry.get_identifier_by_name("non-existent-identifier", self.region)
        self.assertIsNone(identifier)
    
    def test_get_identifiers_by_category_credentials(self):
        """Test retrieval of all credential identifiers."""
        identifiers = self.registry.get_identifiers_by_category(
            ManagedDataIdentifierCategory.CREDENTIALS, self.region
        )
        
        self.assertTrue(len(identifiers) > 0)
        for identifier in identifiers:
            self.assertEqual(identifier.category, ManagedDataIdentifierCategory.CREDENTIALS)
            self.assertIn(self.region, identifier.arn)
    
    def test_get_identifiers_by_category_pii(self):
        """Test retrieval of all PII identifiers."""
        identifiers = self.registry.get_identifiers_by_category(
            ManagedDataIdentifierCategory.PII, self.region
        )
        
        self.assertTrue(len(identifiers) > 0)
        for identifier in identifiers:
            self.assertEqual(identifier.category, ManagedDataIdentifierCategory.PII)
    
    def test_get_all_identifiers(self):
        """Test retrieval of all managed identifiers."""
        identifiers = self.registry.get_all_identifiers(self.region)
        
        self.assertTrue(len(identifiers) > 0)
        
        # Check we have different categories
        categories = {identifier.category for identifier in identifiers}
        self.assertTrue(len(categories) > 1)
    
    def test_get_credentials_identifiers(self):
        """Test helper function for getting credential identifiers."""
        identifiers = get_credentials_identifiers(self.region)
        
        self.assertTrue(len(identifiers) > 0)
        for identifier in identifiers:
            self.assertEqual(identifier.category, ManagedDataIdentifierCategory.CREDENTIALS)
    
    def test_get_pii_identifiers(self):
        """Test helper function for getting PII identifiers."""
        identifiers = get_pii_identifiers(self.region)
        
        self.assertTrue(len(identifiers) > 0)
        for identifier in identifiers:
            self.assertEqual(identifier.category, ManagedDataIdentifierCategory.PII)


class TestCustomDataIdentifiers(unittest.TestCase):
    """Test custom data identifier functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.builder = CustomDataIdentifierBuilder()
    
    def test_build_agent_config_identifier(self):
        """Test building agent configuration secrets identifier."""
        identifier = self.builder.build_agent_config_identifier()
        
        self.assertEqual(identifier.name, "agent-config-secrets")
        self.assertTrue(identifier.regex)
        self.assertTrue(identifier.keywords)
        self.assertIn("observability", identifier.keywords)
        self.assertIn("api", identifier.keywords)
    
    def test_build_ssm_parameter_identifier(self):
        """Test building SSM parameter values identifier."""
        identifier = self.builder.build_ssm_parameter_identifier()
        
        self.assertEqual(identifier.name, "ssm-parameter-values")
        self.assertTrue(identifier.regex)
        self.assertTrue(identifier.keywords)
        self.assertIn("parameter", identifier.keywords)
        self.assertIn("ssm", identifier.keywords)
    
    def test_build_bedrock_token_identifier(self):
        """Test building Bedrock AI tokens identifier."""
        identifier = self.builder.build_bedrock_token_identifier()
        
        self.assertEqual(identifier.name, "bedrock-ai-tokens")
        self.assertTrue(identifier.regex)
        self.assertTrue(identifier.keywords)
        self.assertIn("bedrock", identifier.keywords)
        self.assertIn("ai", identifier.keywords)
    
    def test_build_database_connection_identifier(self):
        """Test building database connection strings identifier."""
        identifier = self.builder.build_database_connection_identifier()
        
        self.assertEqual(identifier.name, "database-connections")
        self.assertTrue(identifier.regex)
        self.assertTrue(identifier.keywords)
        self.assertIn("connection", identifier.keywords)
        self.assertIn("database", identifier.keywords)
    
    def test_build_jwt_token_identifier(self):
        """Test building JWT tokens identifier."""
        identifier = self.builder.build_jwt_token_identifier()
        
        self.assertEqual(identifier.name, "jwt-tokens")
        self.assertTrue(identifier.regex)
        self.assertTrue(identifier.keywords)
        self.assertIn("jwt", identifier.keywords)
        self.assertIn("bearer", identifier.keywords)
    
    def test_get_custom_platform_identifiers(self):
        """Test getting all platform-specific custom identifiers."""
        identifiers = get_custom_platform_identifiers()
        
        self.assertTrue(len(identifiers) > 0)
        
        identifier_names = {identifier.name for identifier in identifiers}
        expected_names = {
            "agent-config-secrets",
            "ssm-parameter-values", 
            "bedrock-ai-tokens",
            "database-connections",
            "jwt-tokens"
        }
        
        self.assertEqual(identifier_names, expected_names)


class TestDataIdentifierValidation(unittest.TestCase):
    """Test data identifier validation functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.validator = DataIdentifierValidator()
        
        # Create valid test identifiers
        self.valid_managed_identifier = ManagedDataIdentifier(
            arn="arn:aws:dataprotection::us-east-1:data-identifier/aws-access-key",
            category=ManagedDataIdentifierCategory.CREDENTIALS,
            description="AWS Access Key ID patterns"
        )
        
        self.valid_custom_identifier = CustomDataIdentifier(
            name="test-identifier",
            regex=r'(?i)(test[_-]?key)\s*[:=]\s*["\']?([a-zA-Z0-9\-_]{8,})["\']?',
            keywords=["test", "key"],
            ignore_words=["example"],
            maximum_match_distance=50
        )
    
    def test_validate_managed_identifier_valid(self):
        """Test validation of valid managed identifier."""
        result = self.validator.validate_managed_identifier(self.valid_managed_identifier)
        self.assertTrue(result)
    
    def test_validate_managed_identifier_invalid_arn(self):
        """Test validation with invalid ARN format."""
        invalid_identifier = ManagedDataIdentifier(
            arn="invalid-arn-format",
            category=ManagedDataIdentifierCategory.CREDENTIALS,
            description="Test description"
        )
        
        result = self.validator.validate_managed_identifier(invalid_identifier)
        self.assertFalse(result)
    
    def test_validate_managed_identifier_empty_description(self):
        """Test validation with empty description."""
        invalid_identifier = ManagedDataIdentifier(
            arn="arn:aws:dataprotection::us-east-1:data-identifier/test",
            category=ManagedDataIdentifierCategory.CREDENTIALS,
            description=""
        )
        
        result = self.validator.validate_managed_identifier(invalid_identifier)
        self.assertFalse(result)
    
    def test_validate_custom_identifier_valid(self):
        """Test validation of valid custom identifier."""
        result = self.validator.validate_custom_identifier(self.valid_custom_identifier)
        self.assertTrue(result)
    
    def test_validate_custom_identifier_empty_name(self):
        """Test validation with empty name."""
        invalid_identifier = CustomDataIdentifier(
            name="",
            regex=r'test-pattern',
            keywords=["test"]
        )
        
        result = self.validator.validate_custom_identifier(invalid_identifier)
        self.assertFalse(result)
    
    def test_validate_custom_identifier_invalid_regex(self):
        """Test validation with invalid regex pattern."""
        invalid_identifier = CustomDataIdentifier(
            name="test-identifier",
            regex=r'[invalid-regex(',  # Unclosed bracket
            keywords=["test"]
        )
        
        result = self.validator.validate_custom_identifier(invalid_identifier)
        self.assertFalse(result)
    
    def test_validate_policy_config_valid(self):
        """Test validation of valid policy configuration."""
        config = DataProtectionPolicyConfig(
            policy_type=DataProtectionPolicyType.LOG_GROUP_LEVEL,
            managed_identifiers=[self.valid_managed_identifier],
            custom_identifiers=[self.valid_custom_identifier],
            enable_audit_findings=True
        )
        
        result = self.validator.validate_policy_config(config)
        self.assertTrue(result)


class TestPolicyGeneration(unittest.TestCase):
    """Test data protection policy generation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.region = "us-east-1"
        self.builder = LogGroupDataProtectionPolicyBuilder(self.region)
        
        self.managed_identifiers = [
            ManagedDataIdentifier(
                arn="arn:aws:dataprotection::us-east-1:data-identifier/aws-access-key",
                category=ManagedDataIdentifierCategory.CREDENTIALS,
                description="AWS Access Key patterns"
            )
        ]
        
        self.custom_identifiers = [
            CustomDataIdentifier(
                name="test-identifier",
                regex=r'(?i)(test[_-]?key)\s*[:=]\s*["\']?([a-zA-Z0-9\-_]{8,})["\']?',
                keywords=["test", "key"]
            )
        ]
    
    def test_build_policy_document_with_managed_identifiers(self):
        """Test building policy document with managed identifiers."""
        self.builder.add_managed_identifiers(self.managed_identifiers)
        policy_json = self.builder.build_policy_document()
        
        policy = json.loads(policy_json)
        self.assertEqual(policy["Version"], "2012-10-17")
        self.assertTrue("Statement" in policy)
    
    def test_build_policy_document_with_custom_identifiers(self):
        """Test building policy document with custom identifiers."""
        self.builder.add_custom_identifiers(self.custom_identifiers)
        policy_json = self.builder.build_policy_document()
        
        policy = json.loads(policy_json)
        self.assertEqual(policy["Version"], "2012-10-17")
        self.assertTrue("Statement" in policy)
    
    def test_build_policy_document_with_audit_findings(self):
        """Test building policy document with audit findings enabled."""
        s3_bucket_arn = "arn:aws:s3:::test-audit-bucket"
        
        self.builder.add_managed_identifiers(self.managed_identifiers)
        self.builder.set_audit_findings_destination(s3_bucket_arn)
        self.builder.enable_audit_findings(True)
        
        policy_json = self.builder.build_policy_document()
        policy = json.loads(policy_json)
        
        self.assertEqual(policy["Version"], "2012-10-17")
        self.assertTrue("Statement" in policy)
    
    def test_create_account_policy_document(self):
        """Test creating account-level policy document."""
        managed_arns = ["arn:aws:dataprotection::us-east-1:data-identifier/aws-access-key"]
        custom_identifiers = [{
            "name": "test-identifier",
            "regex": r"test-pattern",
            "keywords": ["test"],
            "ignore_words": ["example"],
            "maximum_match_distance": 50
        }]
        
        policy_doc = create_account_policy_document(managed_arns, custom_identifiers)
        
        self.assertTrue("Name" in policy_doc)
        self.assertEqual(policy_doc["Version"], "2021-06-01")
        self.assertTrue("Statement" in policy_doc)
        self.assertTrue(len(policy_doc["Statement"]) > 0)
    
    def test_validate_policy_size_under_limit(self):
        """Test policy size validation under 30KB limit."""
        small_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "logs:*",
                    "Resource": "*"
                }
            ]
        }
        
        result = validate_policy_size(small_policy)
        self.assertTrue(result)
    
    def test_validate_policy_size_over_limit(self):
        """Test policy size validation over 30KB limit."""
        # Create artificially large policy
        large_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "logs:*",
                    "Resource": "a" * 35000  # Over 30KB
                }
            ]
        }
        
        result = validate_policy_size(large_policy)
        self.assertFalse(result)


class TestSensitiveDataDetection(unittest.TestCase):
    """Test sensitive data detection and masking functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.detector = SensitiveDataDetector()
    
    def test_detect_aws_access_key(self):
        """Test detection of AWS access keys."""
        test_text = "AWS_ACCESS_KEY_ID=THISISMOCKED" # gitleaks:allow
        findings = self.detector.detect_sensitive_data(test_text)
        
        self.assertIn('aws_access_key', findings)
        self.assertTrue(len(findings['aws_access_key']) > 0)
    
    def test_detect_aws_secret_key(self):
        """Test detection of AWS secret keys."""
        test_text = "aws_secret_access_key=THISISMOCKED" # gitleaks:allow
        findings = self.detector.detect_sensitive_data(test_text)
        
        self.assertIn('aws_secret_key', findings)
        self.assertTrue(len(findings['aws_secret_key']) > 0)
    
    def test_detect_email_addresses(self):
        """Test detection of email addresses."""
        test_text = "User email is john.doe@example.com for contact"
        findings = self.detector.detect_sensitive_data(test_text)
        
        self.assertIn('email', findings)
        self.assertTrue(len(findings['email']) > 0)
    
    def test_detect_phone_numbers(self):
        """Test detection of phone numbers."""
        test_text = "Call us at (555) 123-4567 for support"
        findings = self.detector.detect_sensitive_data(test_text)
        
        self.assertIn('phone', findings)
        self.assertTrue(len(findings['phone']) > 0)
    
    def test_detect_jwt_tokens(self):
        """Test detection of JWT tokens."""
        test_text = "Authorization: Bearer THISISMOCKED" # gitleaks:allow
        findings = self.detector.detect_sensitive_data(test_text)
        
        self.assertIn('jwt_tokens', findings)
        self.assertTrue(len(findings['jwt_tokens']) > 0)
    
    def test_mask_sensitive_data(self):
        """Test masking of sensitive data."""
        test_text = "AWS_ACCESS_KEY_ID=THISISMOCKED and password=THISISMOCKED" # gitleaks:allow
        masked_text = self.detector.mask_sensitive_data(test_text)
        
        # Verify original sensitive data is not present
        self.assertNotIn("THISISMOCKED", masked_text) # gitleaks:allow
        self.assertNotIn("secret123", masked_text) # gitleaks:allow
        
        # Verify masking characters are present
        self.assertIn("*", masked_text)
    
    def test_validate_sensitive_patterns_helper_function(self):
        """Test the helper function for validating patterns."""
        test_text = "api_key=THISISMOCKED and email=test@example.com" # gitleaks:allow
        patterns = validate_sensitive_data_patterns(test_text)
        
        self.assertTrue(len(patterns) > 0)
        self.assertIn('api_key', patterns)
        self.assertIn('email', patterns)
    
    def test_mask_sensitive_data_helper_function(self):
        """Test the helper function for masking sensitive data."""
        test_text = "password=THISISMOCKED" # gitleaks:allow
        masked_text = mask_sensitive_data_for_logging(test_text)
        
        self.assertNotIn("THISISMOCKED", masked_text)
        self.assertIn("*", masked_text)
    
    def test_create_safe_log_message(self):
        """Test creating safe log messages with context."""
        message = "User login with password=THISISMOCKED" # gitleaks:allow
        context = {"user_id": "12345", "api_key": "abc123def456"} # gitleaks:allow
        
        safe_message = create_safe_log_message(message, context)
        
        self.assertNotIn("secret1THISISMOCKED23", safe_message) # gitleaks:allow
        self.assertNotIn("THISISMOCKED", safe_message)
        self.assertIn("*", safe_message)


class TestDataProtectionManager(unittest.TestCase):
    """Test data protection manager runtime functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.manager = DataProtectionManager("us-east-1")
    
    @patch('boto3.client')
    def test_is_data_protection_enabled_success(self, mock_boto_client):
        """Test successful check of data protection enabled status."""
        mock_logs_client = Mock()
        mock_logs_client.describe_account_policies.return_value = {
            'accountPolicies': []
        }
        mock_boto_client.return_value = mock_logs_client
        
        # Reset client cache
        self.manager._logs_client = None
        
        result = self.manager.is_data_protection_enabled()
        self.assertTrue(result)
        mock_logs_client.describe_account_policies.assert_called_once()
    
    @patch('boto3.client')
    def test_is_data_protection_enabled_access_denied(self, mock_boto_client):
        """Test data protection check with access denied."""
        from botocore.exceptions import ClientError
        
        mock_logs_client = Mock()
        mock_logs_client.describe_account_policies.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException"}}, "DescribeAccountPolicies"
        )
        mock_boto_client.return_value = mock_logs_client
        
        # Reset client cache
        self.manager._logs_client = None
        
        result = self.manager.is_data_protection_enabled()
        self.assertFalse(result)
    
    @patch('boto3.client')
    def test_get_log_group_data_protection_policy_success(self, mock_boto_client):
        """Test successful retrieval of log group data protection policy."""
        mock_logs_client = Mock()
        expected_policy = {"Version": "2021-06-01", "Statement": []}
        mock_logs_client.get_data_protection_policy.return_value = {
            'policyDocument': expected_policy
        }
        mock_boto_client.return_value = mock_logs_client
        
        # Reset client cache
        self.manager._logs_client = None
        
        result = self.manager.get_log_group_data_protection_policy("test-log-group")
        self.assertEqual(result, expected_policy)
    
    @patch('boto3.client')
    def test_get_log_group_data_protection_policy_not_found(self, mock_boto_client):
        """Test retrieval of non-existent data protection policy."""
        from botocore.exceptions import ClientError
        
        mock_logs_client = Mock()
        mock_logs_client.get_data_protection_policy.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "GetDataProtectionPolicy"
        )
        mock_boto_client.return_value = mock_logs_client
        
        # Reset client cache
        self.manager._logs_client = None
        
        result = self.manager.get_log_group_data_protection_policy("test-log-group")
        self.assertIsNone(result)


class TestConfigurationIntegration(unittest.TestCase):
    """Test integration with configuration system."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock configuration data
        self.test_config_data = {
            'DataProtection': {
                'Enabled': True,
                'AuditFindingsEnabled': True,
                'AuditFindingsS3BucketName': 'test-audit-bucket',
                'ManagedIdentifiers': ['aws-access-key', 'api-key'],
                'CustomIdentifiers': ['agent-config-secrets'],
                'PolicyType': 'log_group'
            }
        }
        
        with patch('helper.config.Config.load') as mock_load:
            mock_load.return_value = self.test_config_data
            self.config = Config('development')
            self.config.data = self.test_config_data
    
    def test_get_data_protection_config(self):
        """Test getting data protection configuration."""
        dp_config = self.config.get_data_protection_config()
        
        self.assertTrue(dp_config['Enabled'])
        self.assertTrue(dp_config['AuditFindingsEnabled'])
        self.assertEqual(dp_config['AuditFindingsS3BucketName'], 'test-audit-bucket')
    
    def test_is_data_protection_enabled(self):
        """Test checking if data protection is enabled."""
        result = self.config.is_data_protection_enabled()
        self.assertTrue(result)
    
    def test_get_managed_identifiers(self):
        """Test getting managed identifiers from configuration."""
        identifiers = self.config.get_data_protection_managed_identifiers()
        self.assertEqual(identifiers, ['aws-access-key', 'api-key'])
    
    def test_get_custom_identifiers(self):
        """Test getting custom identifiers from configuration."""
        identifiers = self.config.get_data_protection_custom_identifiers()
        self.assertEqual(identifiers, ['agent-config-secrets'])
    
    def test_is_audit_findings_enabled(self):
        """Test checking if audit findings are enabled."""
        result = self.config.is_audit_findings_enabled()
        self.assertTrue(result)
    
    def test_get_audit_findings_s3_bucket_name(self):
        """Test getting audit findings S3 bucket name."""
        bucket_name = self.config.get_audit_findings_s3_bucket_name()
        self.assertEqual(bucket_name, 'test-audit-bucket')


class TestDataProtectionIntegration(unittest.TestCase):
    """Test integration scenarios for data protection functionality."""
    
    def test_end_to_end_policy_creation(self):
        """Test end-to-end policy creation process."""
        # Set up configuration
        test_config_data = {
            'DataProtection': {
                'Enabled': True,
                'ManagedIdentifiers': ['aws-access-key', 'api-key'],
                'CustomIdentifiers': ['agent-config-secrets'],
                'PolicyType': 'log_group'
            }
        }
        
        with patch('helper.config.Config.load') as mock_load:
            mock_load.return_value = test_config_data
            config = Config('development')
            config.data = test_config_data
            
            # Test that configuration is properly loaded
            self.assertTrue(config.is_data_protection_enabled())
            
            managed_ids = config.get_data_protection_managed_identifiers()
            self.assertEqual(len(managed_ids), 2)
            
            custom_ids = config.get_data_protection_custom_identifiers()
            self.assertEqual(len(custom_ids), 1)
    
    def test_helper_functions_integration(self):
        """Test integration of helper functions."""
        # Test is_data_protection_enabled helper
        with patch('application_src.common.data_protection_utils.DataProtectionManager') as mock_manager:
            mock_instance = Mock()
            mock_instance.is_data_protection_enabled.return_value = True
            mock_manager.return_value = mock_instance
            
            result = is_data_protection_enabled()
            self.assertTrue(result)
    
    def test_regex_pattern_compilation(self):
        """Test that all regex patterns compile successfully."""
        custom_identifiers = get_custom_platform_identifiers()
        
        for identifier in custom_identifiers:
            try:
                compiled_pattern = re.compile(identifier.regex)
                self.assertIsNotNone(compiled_pattern)
            except re.error as e:
                self.fail(f"Regex pattern failed to compile for {identifier.name}: {str(e)}")


if __name__ == '__main__':
    # Configure logging for tests
    logging.basicConfig(level=logging.INFO)
    
    # Run all tests
    unittest.main(verbosity=2)
