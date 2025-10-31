"""
IAM Permissions Boundaries package.

This package provides IAM permissions boundary policies that limit the maximum
permissions that can be granted to IAM roles created by compute resources.
"""

from .stack import IAMBoundariesStack
from .policies import BoundaryPolicyFactory, PermissionsBoundaryConfig
from .constants import (
    AGENT_SERVICE_BOUNDARY_POLICY_NAME,
    CONFIGURATION_API_BOUNDARY_POLICY_NAME,
    SUPERVISOR_AGENT_BOUNDARY_POLICY_NAME
)

__all__ = [
    "IAMBoundariesStack",
    "BoundaryPolicyFactory", 
    "PermissionsBoundaryConfig",
    "AGENT_SERVICE_BOUNDARY_POLICY_NAME",
    "CONFIGURATION_API_BOUNDARY_POLICY_NAME",
    "SUPERVISOR_AGENT_BOUNDARY_POLICY_NAME"
]
