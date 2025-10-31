/**
 * Authentication and Authorization React Hook
 * 
 * Provides user authentication state and role-based permission checking
 * based on the Recommended Permission Matrix from AUTHENTICATION_API_COVERAGE.md
 */

import { useState, useEffect } from 'react';
import AuthService from '../services/auth';

export const useAuth = () => {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);

  useEffect(() => {
    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
    try {
      const authenticated = await AuthService.isAuthenticated();
      setIsAuthenticated(authenticated);
      
      if (authenticated) {
        // Get user info from token
        const token = await AuthService.getAuthToken();
        if (token) {
          try {
            // SECURITY: Safe JWT payload extraction with proper validation
            // 1. Validate JWT structure before parsing
            const tokenParts = token.split('.');
            if (tokenParts.length !== 3) {
              throw new Error('Invalid JWT token structure');
            }
            
            // 2. Add padding if needed for proper base64 decoding
            let base64Payload = tokenParts[1];
            const padding = 4 - (base64Payload.length % 4);
            if (padding !== 4) {
              base64Payload += '='.repeat(padding);
            }
            
            // 3. Safely decode and parse with error handling
            const decodedPayload = atob(base64Payload);
            const payload = JSON.parse(decodedPayload);
            
            // 4. Validate payload structure and sanitize extracted data
            const userRoles = Array.isArray(payload['cognito:groups']) ? 
              payload['cognito:groups'].filter(role => typeof role === 'string') : [];
            const userEmail = typeof payload['email'] === 'string' ? payload['email'] : '';
            
            // 5. Additional validation for roles (whitelist approach)
            const allowedRoles = ['admin', 'agent-creator', 'supervisor-user', 'readonly-user'];
            const validatedRoles = userRoles.filter(role => allowedRoles.includes(role));
            
            setRoles(validatedRoles);
            setUser({ email: userEmail, roles: validatedRoles });
            setPermissions(derivePermissionsFromRoles(validatedRoles));
            
          } catch (jwtError) {// Clear authentication state if token is malformed
            setIsAuthenticated(false);
            setUser(null);
            setRoles([]);
            setPermissions([]);
            // Optionally redirect to login or show error
          }
        }
      }
    } catch (error) {setIsAuthenticated(false);
      setUser(null);
      setRoles([]);
      setPermissions([]);
    } finally {
      setLoading(false);
    }
  };

  const derivePermissionsFromRoles = (userRoles) => {
    const perms = new Set();
    
    userRoles.forEach(role => {
      switch (role) {
        case 'admin':
          // Admin has all permissions
          perms.add('view-agents');
          perms.add('create-agents');
          perms.add('update-agents');
          perms.add('delete-agents');
          perms.add('deploy-infrastructure');
          perms.add('access-debug');
          perms.add('manage-prompts');
          perms.add('use-supervisor');
          perms.add('view-skills');
          perms.add('refresh-agent');
          perms.add('access-chat');
          perms.add('access-discovery');
          perms.add('access-schemas');
          break;
          
        case 'agent-creator':
          perms.add('view-agents');
          perms.add('create-agents');
          perms.add('update-agents');
          perms.add('delete-agents');
          perms.add('deploy-infrastructure');
          perms.add('access-debug');
          perms.add('manage-prompts');
          perms.add('use-supervisor');
          perms.add('view-skills');
          perms.add('refresh-agent');
          perms.add('access-chat');
          perms.add('access-discovery');
          perms.add('access-schemas');
          break;
          
        case 'supervisor-user':
          perms.add('view-agents');
          perms.add('use-supervisor');
          perms.add('view-skills');
          perms.add('access-chat');
          perms.add('access-discovery');
          perms.add('access-schemas');
          break;
          
        case 'readonly-user':
          perms.add('view-agents');
          perms.add('use-supervisor');
          perms.add('view-skills');
          perms.add('access-chat');
          perms.add('access-discovery');
          perms.add('access-schemas');
          break;
          
        default:
          // Unknown role - no permissions
          break;
      }
    });
    
    return Array.from(perms);
  };

  const hasRole = (role) => {
    return roles.includes(role);
  };

  const hasAnyRole = (roleList) => {
    return roleList.some(role => roles.includes(role));
  };

  const hasPermission = (permission) => {
    return permissions.includes(permission);
  };

  const hasAnyPermission = (permissionList) => {
    return permissionList.some(perm => permissions.includes(perm));
  };

  const isAdmin = () => {
    return hasRole('admin');
  };

  const canCreateAgents = () => {
    return hasPermission('create-agents');
  };

  const canUpdateAgents = () => {
    return hasPermission('update-agents');
  };

  const canDeleteAgents = () => {
    return hasPermission('delete-agents');
  };

  const canDeployInfrastructure = () => {
    return hasPermission('deploy-infrastructure');
  };

  const canAccessDebug = () => {
    return hasPermission('access-debug');
  };

  const canManagePrompts = () => {
    return hasPermission('manage-prompts');
  };

  const canUseSupervisor = () => {
    return hasPermission('use-supervisor');
  };

  return {
    // Authentication state
    isAuthenticated,
    user,
    loading,
    roles,
    permissions,
    
    // Permission checks
    hasRole,
    hasAnyRole,
    hasPermission,
    hasAnyPermission,
    
    // Convenience methods
    isAdmin,
    canCreateAgents,
    canUpdateAgents,
    canDeleteAgents,
    canDeployInfrastructure,
    canAccessDebug,
    canManagePrompts,
    canUseSupervisor,
    
    // Refresh auth state
    refresh: checkAuthStatus
  };
};

export default useAuth;
