"""
Role-based access control (RBAC) manager service.

This module implements comprehensive role and permission management for the
authentication system, including dynamic role creation for agents and
multi-supervisor agent support.
"""

import logging
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError

from .interfaces import RoleManager
from .types import (
    Role,
    Permission,
    SystemRoles,
    SystemPermissions,
    AuthenticationError,
    get_supervisor_role_name,
    get_supervisor_permissions
)

logger = logging.getLogger(__name__)


class RoleManagerService(RoleManager):
    """
    AWS Cognito-based role manager implementation.
    
    This service manages roles and permissions using AWS Cognito User Pool Groups
    and custom attributes. It supports dynamic role creation for agents and
    provides comprehensive permission checking.
    """
    
    def __init__(self, user_pool_id: str, region: str):
        self.user_pool_id = user_pool_id
        self.region = region
        self.cognito_client = None
        self.is_initialized = False
        self._role_cache: Dict[str, Role] = {}
        self._user_roles_cache: Dict[str, List[Role]] = {}
        
    async def initialize_roles(self) -> bool:
        """
        Initialize role management system with AWS Cognito and default roles.
        
        Returns:
            bool: True if initialization successful
        """
        # Prevent recursive initialization
        if self.is_initialized:
            return True
            
        try:
            # Initialize Cognito client
            self.cognito_client = boto3.client('cognito-idp', region_name=self.region)
            
            # Mark as initialized BEFORE creating roles to prevent recursion
            self.is_initialized = True
            
            # Create system roles if they don't exist
            await self._create_system_roles()
            
            logger.info("Role manager initialized successfully")
            return True
            
        except Exception as e:
            # Reset initialization flag on failure
            self.is_initialized = False
            logger.error(f"Failed to initialize role manager: {str(e)}")
            return False
    
    async def get_user_roles(self, user_id: str) -> List[Role]:
        """
        Get all roles assigned to a user from Cognito groups.
        
        Args:
            user_id: User identifier (username)
            
        Returns:
            List[Role]: List of user's roles
        """
        if not self.is_initialized:
            await self.initialize_roles()
            
        try:
            # Check cache first
            if user_id in self._user_roles_cache:
                return self._user_roles_cache[user_id]
            
            # Get user's groups from Cognito
            response = self.cognito_client.admin_list_groups_for_user(
                UserPoolId=self.user_pool_id,
                Username=user_id
            )
            
            roles = []
            for group in response.get('Groups', []):
                group_name = group.get('GroupName')
                role = await self.get_role(group_name)
                if role:
                    roles.append(role)
            
            # Cache the result
            self._user_roles_cache[user_id] = roles
            
            return roles
            
        except ClientError as e:
            logger.error(f"Failed to get user roles for {user_id}: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error getting user roles: {str(e)}")
            return []
    
    async def get_user_permissions(self, user_id: str) -> List[Permission]:
        """
        Get all permissions for a user from their roles.
        
        Args:
            user_id: User identifier
            
        Returns:
            List[Permission]: List of user's permissions
        """
        roles = await self.get_user_roles(user_id)
        permissions = []
        
        for role in roles:
            permissions.extend(role.permissions)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_permissions = []
        for perm in permissions:
            perm_str = str(perm)
            if perm_str not in seen:
                seen.add(perm_str)
                unique_permissions.append(perm)
        
        return unique_permissions
    
    async def check_permission(self, user_id: str, resource: str, action: str) -> bool:
        """
        Check if user has specific permission.
        
        Args:
            user_id: User identifier
            resource: Resource being accessed
            action: Action being performed
            
        Returns:
            bool: True if user has permission
        """
        permissions = await self.get_user_permissions(user_id)
        
        # Check for wildcard admin permission
        for perm in permissions:
            if perm.resource == '*' and perm.action == '*':
                return True
            if perm.matches(resource, action):
                return True
        
        return False
    
    async def assign_role(self, user_id: str, role_name: str) -> bool:
        """
        Assign role to user by adding them to Cognito group.
        
        Args:
            user_id: User identifier
            role_name: Name of role to assign
            
        Returns:
            bool: True if assignment successful
        """
        if not self.is_initialized:
            await self.initialize_roles()
            
        try:
            # Ensure the role/group exists
            await self._ensure_cognito_group_exists(role_name)
            
            # Add user to group
            self.cognito_client.admin_add_user_to_group(
                UserPoolId=self.user_pool_id,
                Username=user_id,
                GroupName=role_name
            )
            
            # Clear cache for this user
            if user_id in self._user_roles_cache:
                del self._user_roles_cache[user_id]
            
            logger.info(f"Assigned role {role_name} to user {user_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to assign role {role_name} to user {user_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error assigning role: {str(e)}")
            return False
    
    async def remove_role(self, user_id: str, role_name: str) -> bool:
        """
        Remove role from user by removing them from Cognito group.
        
        Args:
            user_id: User identifier
            role_name: Name of role to remove
            
        Returns:
            bool: True if removal successful
        """
        if not self.is_initialized:
            await self.initialize_roles()
            
        try:
            self.cognito_client.admin_remove_user_from_group(
                UserPoolId=self.user_pool_id,
                Username=user_id,
                GroupName=role_name
            )
            
            # Clear cache for this user
            if user_id in self._user_roles_cache:
                del self._user_roles_cache[user_id]
            
            logger.info(f"Removed role {role_name} from user {user_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to remove role {role_name} from user {user_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error removing role: {str(e)}")
            return False
    
    async def create_role(self, role: Role) -> bool:
        """
        Create new role as Cognito User Pool Group.
        
        Args:
            role: Role definition
            
        Returns:
            bool: True if creation successful
        """
        # Don't reinitialize during system role creation to prevent recursion
        if not self.is_initialized and not hasattr(self, '_initializing'):
            await self.initialize_roles()
            
        try:
            # Ensure we have a Cognito client
            if not self.cognito_client:
                self.cognito_client = boto3.client('cognito-idp', region_name=self.region)
                
            # Create Cognito User Pool Group
            self.cognito_client.create_group(
                GroupName=role.name,
                UserPoolId=self.user_pool_id,
                Description=role.description,
                Precedence=0  # Default precedence
            )
            
            # Cache the role
            self._role_cache[role.name] = role
            
            logger.info(f"Created role: {role.name}")
            return True
            
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'UNKNOWN_ERROR')
            if error_code == 'GroupExistsException':
                logger.info(f"Role {role.name} already exists")
                return True
            logger.error(f"Failed to create role {role.name}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error creating role: {str(e)}")
            return False
    
    async def update_role(self, role_name: str, role: Role) -> bool:
        """
        Update existing role (limited support in Cognito).
        
        Args:
            role_name: Current role name
            role: Updated role definition
            
        Returns:
            bool: True if update successful
        """
        if not self.is_initialized:
            await self.initialize_roles()
            
        try:
            # Update Cognito group description
            self.cognito_client.update_group(
                GroupName=role_name,
                UserPoolId=self.user_pool_id,
                Description=role.description
            )
            
            # Update cached role
            self._role_cache[role_name] = role
            
            logger.info(f"Updated role: {role_name}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to update role {role_name}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error updating role: {str(e)}")
            return False
    
    async def delete_role(self, role_name: str) -> bool:
        """
        Delete role from Cognito User Pool.
        
        Args:
            role_name: Name of role to delete
            
        Returns:
            bool: True if deletion successful
        """
        if not self.is_initialized:
            await self.initialize_roles()
            
        try:
            self.cognito_client.delete_group(
                GroupName=role_name,
                UserPoolId=self.user_pool_id
            )
            
            # Remove from cache
            if role_name in self._role_cache:
                del self._role_cache[role_name]
            
            logger.info(f"Deleted role: {role_name}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete role {role_name}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Error deleting role: {str(e)}")
            return False
    
    async def get_role(self, role_name: str) -> Optional[Role]:
        """
        Get role definition by name.
        
        Args:
            role_name: Name of role
            
        Returns:
            Optional[Role]: Role definition if found
        """
        # Check cache first
        if role_name in self._role_cache:
            return self._role_cache[role_name]
        
        # Get system role definition
        role = self._get_system_role_definition(role_name)
        if role:
            self._role_cache[role_name] = role
            return role
        
        # If not a system role, try to get from Cognito
        try:
            response = self.cognito_client.get_group(
                GroupName=role_name,
                UserPoolId=self.user_pool_id
            )
            
            group = response.get('Group', {})
            role = Role(
                name=group.get('GroupName', role_name),
                description=group.get('Description', ''),
                permissions=[],  # Permissions are defined by system role definitions
                is_system_role=False
            )
            
            self._role_cache[role_name] = role
            return role
            
        except ClientError:
            return None
        except Exception as e:
            logger.error(f"Error getting role {role_name}: {str(e)}")
            return None
    
    async def list_roles(self) -> List[Role]:
        """
        List all available roles from Cognito and system definitions.
        
        Returns:
            List[Role]: All roles in system
        """
        roles = []
        
        # Add system roles
        system_role_names = [
            SystemRoles.ADMIN,
            SystemRoles.AGENT_CREATOR,
            SystemRoles.SUPERVISOR_USER,
            SystemRoles.READONLY_USER
        ]
        
        for role_name in system_role_names:
            role = self._get_system_role_definition(role_name)
            if role:
                roles.append(role)
        
        # Get additional roles from Cognito
        try:
            response = self.cognito_client.list_groups(UserPoolId=self.user_pool_id)
            
            for group in response.get('Groups', []):
                group_name = group.get('GroupName')
                if group_name not in system_role_names:
                    role = Role(
                        name=group_name,
                        description=group.get('Description', ''),
                        permissions=[],
                        is_system_role=False
                    )
                    roles.append(role)
            
        except Exception as e:
            logger.error(f"Error listing Cognito groups: {str(e)}")
        
        return roles
    
    async def create_agent_group(self, agent_id: str, agent_type: str) -> bool:
        """
        Create role group for a specific agent.
        
        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent (generic, supervisor, hcls, risk-analysis, etc.)
            
        Returns:
            bool: True if group creation successful
        """
        try:
            group_name = f"agent-{agent_id}-users"
            description = f"Users with access to {agent_type} agent {agent_id}"
            
            # Create agent-specific permissions
            permissions = [
                Permission(
                    name=f"agent-{agent_id}-access",
                    description=f"Access to agent {agent_id}",
                    resource="agent",
                    action="access",
                    conditions={"agent_id": agent_id}
                ),
                Permission(
                    name=f"agent-{agent_id}-use",
                    description=f"Use agent {agent_id}",
                    resource="agent", 
                    action="use",
                    conditions={"agent_id": agent_id}
                )
            ]
            
            # Add supervisor-specific permissions if applicable
            if agent_type.startswith('supervisor'):
                supervisor_type = agent_type.replace('supervisor-', '')
                supervisor_permissions = get_supervisor_permissions(supervisor_type)
                for perm_name in supervisor_permissions:
                    resource, action = perm_name.split(':', 1)
                    permissions.append(
                        Permission(
                            name=perm_name,
                            description=f"Permission for {supervisor_type} supervisor",
                            resource=resource,
                            action=action
                        )
                    )
            
            # Create role
            agent_role = Role(
                name=group_name,
                description=description,
                permissions=permissions,
                is_system_role=False,
                metadata={"agent_id": agent_id, "agent_type": agent_type}
            )
            
            return await self.create_role(agent_role)
            
        except Exception as e:
            logger.error(f"Failed to create agent group for {agent_id}: {str(e)}")
            return False
    
    async def delete_agent_group(self, agent_id: str) -> bool:
        """
        Delete role group for a specific agent.
        
        Args:
            agent_id: Unique agent identifier
            
        Returns:
            bool: True if group deletion successful
        """
        try:
            group_name = f"agent-{agent_id}-users"
            return await self.delete_role(group_name)
            
        except Exception as e:
            logger.error(f"Failed to delete agent group for {agent_id}: {str(e)}")
            return False
    
    async def _create_system_roles(self):
        """Create default system roles if they don't exist."""
        system_roles = self._get_all_system_roles()
        
        for role in system_roles:
            try:
                # Check if group already exists
                self.cognito_client.get_group(
                    GroupName=role.name,
                    UserPoolId=self.user_pool_id
                )
                logger.info(f"System role {role.name} already exists")
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code')
                if error_code == 'ResourceNotFoundException':
                    # Group doesn't exist, create it
                    await self.create_role(role)
                else:
                    logger.error(f"Error checking system role {role.name}: {str(e)}")
    
    def _get_all_system_roles(self) -> List[Role]:
        """Get all system role definitions."""
        return [
            self._get_system_role_definition(SystemRoles.ADMIN),
            self._get_system_role_definition(SystemRoles.AGENT_CREATOR),
            self._get_system_role_definition(SystemRoles.SUPERVISOR_USER),
            self._get_system_role_definition(SystemRoles.READONLY_USER)
        ]
    
    def _get_system_role_definition(self, role_name: str) -> Optional[Role]:
        """
        Get system role definition with permissions.
        
        Args:
            role_name: System role name
            
        Returns:
            Optional[Role]: Role definition if it's a system role
        """
        if role_name == SystemRoles.ADMIN:
            return Role(
                name=SystemRoles.ADMIN,
                description="System administrator with full access",
                permissions=[
                    Permission("admin-all", "Full system access", "*", "*")
                ],
                is_system_role=True
            )
        elif role_name == SystemRoles.AGENT_CREATOR:
            return Role(
                name=SystemRoles.AGENT_CREATOR,
                description="Can create and manage agents",
                permissions=[
                    Permission("agent-create", "Create agents", "agent", "create"),
                    Permission("agent-read", "Read agent info", "agent", "read"),
                    Permission("agent-update", "Update agents", "agent", "update"),
                    Permission("agent-delete", "Delete agents", "agent", "delete"),
                    Permission("agent-deploy", "Deploy agents", "agent", "deploy"),
                    Permission("config-read", "Read configuration", "config", "read"),
                    Permission("config-update", "Update configuration", "config", "update")
                ],
                is_system_role=True
            )
        elif role_name == SystemRoles.SUPERVISOR_USER:
            return Role(
                name=SystemRoles.SUPERVISOR_USER,
                description="Can access supervisor agents",
                permissions=[
                    Permission("supervisor-access", "Access supervisor agents", "supervisor", "access"),
                    Permission("agent-read", "Read agent info", "agent", "read"),
                    Permission("config-read", "Read configuration", "config", "read")
                ],
                is_system_role=True
            )
        elif role_name == SystemRoles.READONLY_USER:
            return Role(
                name=SystemRoles.READONLY_USER,
                description="Read-only access to system",
                permissions=[
                    Permission("agent-read", "Read agent info", "agent", "read"),
                    Permission("config-read", "Read configuration", "config", "read")
                ],
                is_system_role=True
            )
        
        return None
    
    async def _ensure_cognito_group_exists(self, group_name: str):
        """
        Ensure Cognito group exists, create if it doesn't.
        
        Args:
            group_name: Name of group to ensure exists
        """
        try:
            self.cognito_client.get_group(
                GroupName=group_name,
                UserPoolId=self.user_pool_id
            )
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code')
            if error_code == 'ResourceNotFoundException':
                # Create the group
                self.cognito_client.create_group(
                    GroupName=group_name,
                    UserPoolId=self.user_pool_id,
                    Description=f"Auto-created group for {group_name}"
                )
                logger.info(f"Created Cognito group: {group_name}")
    
    def clear_cache(self):
        """Clear all cached role data."""
        self._role_cache.clear()
        self._user_roles_cache.clear()
    
    def get_cached_user_roles(self, user_id: str) -> Optional[List[Role]]:
        """Get cached user roles without hitting AWS."""
        return self._user_roles_cache.get(user_id)


# Utility functions for role management
def create_supervisor_role(supervisor_type: str) -> Role:
    """
    Create role definition for specific supervisor agent type.
    
    Args:
        supervisor_type: Type of supervisor (hcls, risk-analysis, etc.)
        
    Returns:
        Role: Role definition for supervisor type
    """
    role_name = get_supervisor_role_name(supervisor_type)
    permissions_list = get_supervisor_permissions(supervisor_type)
    
    permissions = []
    for perm_name in permissions_list:
        resource, action = perm_name.split(':', 1)
        permissions.append(
            Permission(
                name=perm_name,
                description=f"Permission for {supervisor_type} supervisor",
                resource=resource,
                action=action,
                conditions={"supervisor_type": supervisor_type}
            )
        )
    
    return Role(
        name=role_name,
        description=f"Access to {supervisor_type} supervisor agent",
        permissions=permissions,
        is_system_role=False,
        metadata={"supervisor_type": supervisor_type}
    )


async def create_role_manager(user_pool_id: str, region: str) -> RoleManagerService:
    """
    Factory function to create and initialize role manager.
    
    Args:
        user_pool_id: Cognito User Pool ID
        region: AWS region
        
    Returns:
        RoleManagerService: Initialized role manager
    """
    role_manager = RoleManagerService(user_pool_id, region)
    await role_manager.initialize_roles()
    return role_manager
