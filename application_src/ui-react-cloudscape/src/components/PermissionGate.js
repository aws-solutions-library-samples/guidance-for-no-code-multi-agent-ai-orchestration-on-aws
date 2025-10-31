/**
 * Permission Gate Component
 * 
 * Conditionally renders children based on user permissions
 * Implements visual controls based on AUTHENTICATION_API_COVERAGE permission matrix
 */

import React from 'react';
import useAuth from '../hooks/useAuth';

export const PermissionGate = ({ 
  children, 
  permissions = [], 
  roles = [],
  requireAll = false,
  fallback = null 
}) => {
  const auth = useAuth();

  if (auth.loading) {
    return fallback;
  }

  if (!auth.isAuthenticated) {
    return fallback;
  }

  let hasAccess = false;

  if (permissions.length > 0) {
    hasAccess = requireAll 
      ? permissions.every(p => auth.hasPermission(p))
      : auth.hasAnyPermission(permissions);
  } else if (roles.length > 0) {
    hasAccess = requireAll
      ? roles.every(r => auth.hasRole(r))
      : auth.hasAnyRole(roles);
  } else {
    hasAccess = true; // No restrictions
  }

  return hasAccess ? children : fallback;
};

// Convenience components for common permissions
export const AdminOnly = ({ children, fallback = null }) => (
  <PermissionGate roles={['admin']} fallback={fallback}>
    {children}
  </PermissionGate>
);

export const AgentCreatorOrAdmin = ({ children, fallback = null }) => (
  <PermissionGate roles={['admin', 'agent-creator']} fallback={fallback}>
    {children}
  </PermissionGate>
);

export const CanCreateAgents = ({ children, fallback = null }) => (
  <PermissionGate permissions={['create-agents']} fallback={fallback}>
    {children}
  </PermissionGate>
);

export const CanUpdateAgents = ({ children, fallback = null }) => (
  <PermissionGate permissions={['update-agents']} fallback={fallback}>
    {children}
  </PermissionGate>
);

export const CanDeleteAgents = ({ children, fallback = null }) => (
  <PermissionGate permissions={['delete-agents']} fallback={fallback}>
    {children}
  </PermissionGate>
);

export const CanDeployInfrastructure = ({ children, fallback = null }) => (
  <PermissionGate permissions={['deploy-infrastructure']} fallback={fallback}>
    {children}
  </PermissionGate>
);

/**
 * Show content only if user can view agent skills
 * Available to: admin, agent-creator, supervisor-user, readonly-user
 */
export const CanViewSkills = ({ children, fallback = null }) => (
  <PermissionGate permissions={['view-skills']} fallback={fallback}>
    {children}
  </PermissionGate>
);

/**
 * Show content only if user can refresh agents
 * Available to: admin, agent-creator
 */
export const CanRefreshAgent = ({ children, fallback = null }) => (
  <PermissionGate permissions={['refresh-agent']} fallback={fallback}>
    {children}
  </PermissionGate>
);

/**
 * Show content only if user can access chat interface
 * Available to: admin, agent-creator, supervisor-user
 */
export const CanAccessChat = ({ children, fallback = null }) => (
  <PermissionGate permissions={['access-chat']} fallback={fallback}>
    {children}
  </PermissionGate>
);

export default PermissionGate;
