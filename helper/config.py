import yaml
import re
from yaml.loader import SafeLoader
from typing import Dict, List, Optional, Any


class ProjectNameValidationError(Exception):
    """Raised when ProjectName validation fails."""
    pass


class Config:

    _environment = 'development'
    data = []

    def __init__(self, environment) -> None:
        self._environment = environment
        self.load()
        self._validate_project_name()

    def load(self) -> dict:
        with open(f'config/{self._environment}.yaml', encoding='utf-8') as f:
            self.data = yaml.load(f, Loader=SafeLoader)
        return self.data

    def get(self, key):
        return self.data[key]
    
    def _validate_project_name(self) -> None:
        """
        Validate ProjectName against all AWS resource naming constraints.
        
        This validation covers the most restrictive naming requirements from all AWS services
        used in the platform based on AWS documentation.
        
        Raises:
            ProjectNameValidationError: If ProjectName doesn't meet requirements
        """
        project_name = self.data.get('ProjectName')
        
        if not project_name:
            raise ProjectNameValidationError("ProjectName is required in configuration")
        
        if not isinstance(project_name, str):
            raise ProjectNameValidationError("ProjectName must be a string")
        
        # Remove whitespace
        project_name = project_name.strip()
        
        if not project_name:
            raise ProjectNameValidationError("ProjectName cannot be empty or whitespace only")
        
        # **CRITICAL AWS RESOURCE NAMING ANALYSIS**
        # Based on AWS Documentation and components modified:
        
        # 1. LENGTH CONSTRAINTS (Most Restrictive: ALB Names = 32 chars max)
        # Our longest suffix pattern: "-generic-agent-api" = 18 chars + 1 hyphen = 19 chars
        # Therefore: ProjectName max = 32 - 19 = 13 characters for ALB compliance
        MAX_LENGTH = 13
        
        if len(project_name) > MAX_LENGTH:
            raise ProjectNameValidationError(
                f"ProjectName must be {MAX_LENGTH} characters or less. "
                f"Current length: {len(project_name)}. "
                f"Constraint: Application Load Balancer names (32 chars) - longest suffix ('-generic-agent-api' = 19 chars)"
            )
        
        # 2. MINIMUM LENGTH (VPC Lattice Service Network minimum = 3 chars)
        MIN_LENGTH = 3
        
        if len(project_name) < MIN_LENGTH:
            raise ProjectNameValidationError(
                f"ProjectName must be at least {MIN_LENGTH} characters long. "
                f"Current length: {len(project_name)}. "
                f"Constraint: VPC Lattice Service Network minimum length"
            )
        
        # 3. CHARACTER PATTERN (Most Restrictive: Combined S3 + CloudFormation)
        # CloudFormation stacks must start with letter, S3 buckets need lowercase
        # Combined: lowercase letters, numbers, hyphens, must start with letter
        combined_pattern = r'^[a-z]([a-z0-9-]*[a-z0-9])?$'
        
        if not re.match(combined_pattern, project_name):
            raise ProjectNameValidationError(
                f"ProjectName '{project_name}' contains invalid characters. "
                f"Must use only lowercase letters (a-z), numbers (0-9), and hyphens (-). "
                f"Must start with a letter and end with a letter or number. No consecutive hyphens. "
                f"Constraint: CloudFormation stack + S3 bucket naming compliance"
            )
        
        # 4. CONSECUTIVE HYPHENS CHECK (S3 requirement)
        if '--' in project_name:
            raise ProjectNameValidationError(
                f"ProjectName '{project_name}' contains consecutive hyphens. "
                f"S3 bucket naming does not allow consecutive hyphens"
            )
        
        # 5. RESERVED PATTERNS CHECK
        reserved_patterns = [
            'aws', 'amazon', 'amzn',  # AWS reserved
            'test', 'prod', 'dev',     # Common environment conflicts
            'api', 'ui', 'vpc', 'kms'  # Our suffix conflicts
        ]
        
        if project_name.lower() in reserved_patterns:
            raise ProjectNameValidationError(
                f"ProjectName '{project_name}' conflicts with reserved patterns: {reserved_patterns}"
            )
        
        # 6. CLOUDFORMATION STACK NAME VALIDATION
        # Must start with letter, contain letters, numbers, hyphens
        cf_pattern = r'^[a-zA-Z][a-zA-Z0-9-]*$'
        
        if not re.match(cf_pattern, project_name):
            raise ProjectNameValidationError(
                f"ProjectName '{project_name}' must start with a letter for CloudFormation stack compatibility. "
                f"Valid characters: letters, numbers, hyphens"
            )
        
        # 7. ECS NAMING VALIDATION (supports underscores, but we standardize on hyphens)
        # ECS allows: [a-zA-Z0-9\-_]{1,255}
        ecs_pattern = r'^[a-zA-Z0-9-]+$'
        
        if not re.match(ecs_pattern, project_name):
            raise ProjectNameValidationError(
                f"ProjectName '{project_name}' contains characters not supported by ECS services. "
                f"Valid characters: letters, numbers, hyphens"
            )
        
        # 8. COGNITO USER POOL NAME VALIDATION
        # Cognito: [a-zA-Z0-9\-_]{1,128}
        cognito_pattern = r'^[a-zA-Z0-9_-]+$'
        
        if not re.match(cognito_pattern, project_name):
            raise ProjectNameValidationError(
                f"ProjectName '{project_name}' contains characters not supported by Cognito User Pools. "
                f"Valid characters: letters, numbers, hyphens, underscores"
            )
        
        # 9. VPC LATTICE SERVICE NETWORK VALIDATION  
        # VPC Lattice: [a-zA-Z0-9\-_]{3,63}
        # Our pattern: {project_name}-svc-net (8 additional chars)
        vpc_lattice_max = 63 - 8  # 55 chars max for project name
        
        if len(project_name) > vpc_lattice_max:
            raise ProjectNameValidationError(
                f"ProjectName '{project_name}' too long for VPC Lattice Service Network. "
                f"Max length: {vpc_lattice_max} chars (63 total - 8 for '-svc-net' suffix)"
            )
        
        # 10. BEDROCK AGENTCORE MEMORY NAMESPACE VALIDATION
        # Memory namespaces: {project_name}/user/{user_id}/preferences
        # Must be valid path components, no special characters
        memory_pattern = r'^[a-zA-Z0-9-]+$'
        
        if not re.match(memory_pattern, project_name):
            raise ProjectNameValidationError(
                f"ProjectName '{project_name}' contains characters not supported by Bedrock AgentCore memory namespaces. "
                f"Valid characters: letters, numbers, hyphens"
            )
        
        # 11. CONTAINER NAME VALIDATION (Docker naming)
        # Docker container names: [a-zA-Z0-9][a-zA-Z0-9_.-]*
        docker_pattern = r'^[a-zA-Z0-9][a-zA-Z0-9_.-]*$'
        
        if not re.match(docker_pattern, project_name):
            raise ProjectNameValidationError(
                f"ProjectName '{project_name}' not compatible with Docker container naming. "
                f"Must start with alphanumeric, then letters, numbers, underscores, dots, hyphens"
            )
    
    def get_validated_project_name(self) -> str:
        """
        Get the validated project name.
        
        Returns:
            Validated project name
            
        Raises:
            ProjectNameValidationError: If validation fails
        """
        project_name = self.data.get('ProjectName')
        
        if not project_name:
            raise ProjectNameValidationError("ProjectName not found in configuration")
        
        # Re-run validation to ensure consistency
        self._validate_project_name()
        
        return project_name.strip()
    
    def get_project_name_constraints_info(self) -> Dict[str, Any]:
        """
        Get detailed information about ProjectName constraints for documentation.
        
        Returns:
            Dictionary with constraint information
        """
        return {
            "max_length": 13,
            "min_length": 3,
            "pattern": "^[a-z0-9]([a-z0-9-]*[a-z0-9])?$",
            "description": "Lowercase letters, numbers, and hyphens. Must start/end with letter or number.",
            "constraints": {
                "alb_names": {"max": 32, "suffix_overhead": 19},
                "target_group_names": {"max": 32, "suffix_overhead": 19},
                "vpc_lattice_networks": {"max": 63, "suffix_overhead": 8},
                "s3_buckets": {"max": 63, "pattern": "lowercase only"},
                "cloudformation_stacks": {"max": 128, "pattern": "must start with letter"},
                "ecs_services": {"max": 255, "pattern": "letters, numbers, hyphens, underscores"},
                "cognito_user_pools": {"max": 128, "pattern": "letters, numbers, hyphens, underscores"},
                "secrets_manager": {"max": 2048, "pattern": "very flexible"},
                "bedrock_knowledge_bases": {"max": 100, "pattern": "letters, numbers, hyphens, underscores"},
                "memory_namespaces": {"pattern": "path-safe characters only"}
            },
            "reserved_words": ["aws", "amazon", "amzn", "test", "prod", "dev", "api", "ui", "vpc", "kms"],
            "examples": {
                "valid": ["myapp", "acme-corp", "project1", "ai-platform"],
                "invalid": ["My App", "test", "aws-project", "app_name", "verylongprojectname"]
            }
        }
    
    def get_data_protection_config(self) -> Dict[str, Any]:
        """Get data protection configuration section."""
        return self.get('DataProtection') or {}
    
    def is_data_protection_enabled(self) -> bool:
        """Check if data protection is enabled - always returns True as it's enabled by default."""
        return True
    
    def get_data_protection_managed_identifiers(self) -> List[str]:
        """Get list of managed data identifiers to enable."""
        data_protection = self.get_data_protection_config()
        return data_protection.get('ManagedIdentifiers', [])
    
    def get_data_protection_custom_identifiers(self) -> List[str]:
        """Get list of custom data identifiers to enable."""
        data_protection = self.get_data_protection_config()
        return data_protection.get('CustomIdentifiers', [])
    
    def is_audit_findings_enabled(self) -> bool:
        """Check if audit findings delivery is enabled - always returns True as it's enabled by default."""
        return True
    
    def get_audit_findings_log_group_name(self) -> Optional[str]:
        """Get CloudWatch log group name for audit findings."""
        data_protection = self.get_data_protection_config()
        return data_protection.get('AuditFindingsLogGroupName')
    
    def get_data_protection_policy_type(self) -> str:
        """Get data protection policy type."""
        data_protection = self.get_data_protection_config()
        return data_protection.get('PolicyType', 'log_group')
