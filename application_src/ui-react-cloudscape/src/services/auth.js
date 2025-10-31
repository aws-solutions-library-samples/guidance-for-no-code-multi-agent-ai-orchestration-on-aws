import { Amplify } from 'aws-amplify';
import { signIn, signOut, getCurrentUser, fetchAuthSession, confirmSignIn } from '@aws-amplify/auth';
import { getApiUrl } from '../config/environment';

class AuthService {
  constructor() {
    this.isInitialized = false;
    this.currentUser = null;
    
    // Load user from localStorage on initialization
    this.loadUserFromStorage();
  }

  loadUserFromStorage() {
    try {
      const storedUser = localStorage.getItem('currentUser');
      if (storedUser) {
        this.currentUser = JSON.parse(storedUser);
      }
    } catch (error) {
      // Clear corrupted storage entry
      localStorage.removeItem('currentUser');
    }
  }

  saveUserToStorage() {
    try {
      if (this.currentUser) {
        localStorage.setItem('currentUser', JSON.stringify(this.currentUser));
      } else {
        localStorage.removeItem('currentUser');
      }
    } catch (error) {
      // Ignore storage errors
    }
  }

  async initialize() {
    try {
      // Get Cognito configuration from AWS Secrets Manager
      const cognitoConfig = await this.getCognitoConfig();

      // Configure Amplify
      Amplify.configure({
        Auth: {
          Cognito: {
            userPoolId: cognitoConfig.userPoolId,
            userPoolClientId: cognitoConfig.clientId,
            loginWith: {
              oauth: {
                domain: cognitoConfig.domain || `${cognitoConfig.userPoolId}.auth.${process.env.REACT_APP_AWS_REGION}.amazoncognito.com`,
                scopes: ['openid', 'email', 'profile'],
                redirectSignIn: window.location.origin,
                redirectSignOut: window.location.origin,
                responseType: 'code'
              }
            }
          }
        }
      });

      this.isInitialized = true;

      // Check if user is already signed in
      try {
        this.currentUser = await getCurrentUser();
      } catch (error) {
        // User not signed in, which is fine
        this.currentUser = null;
      }

      return true;
    } catch (error) {
      throw error;
    }
  }

  async getCognitoConfig() {
    try {
      // Get Cognito configuration from Express backend server
      // Use environment-aware URL configuration for development/production compatibility
      const apiUrl = getApiUrl('/api/auth/cognito-config');
      const response = await fetch(apiUrl);
      
      if (!response.ok) {
        throw new Error(`Failed to fetch Cognito config: ${response.status} ${response.statusText}`);
      }
      
      const config = await response.json();
      
      return {
        userPoolId: config.userPoolId,
        clientId: config.clientId,
        region: config.region
      };
    } catch (error) {
      throw error;
    }
  }

  async login(username, password) {
    try {
      if (!this.isInitialized) {
        await this.initialize();
      }

      // Check if user is already authenticated
      // AWS Amplify throws UserAlreadyAuthenticatedException if you try to sign in while already signed in
      try {
        const existingUser = await getCurrentUser();
        const session = await fetchAuthSession();
        
        
        // If same user with valid session, just return success
        if (existingUser && session?.tokens?.accessToken) {
          if (existingUser.username === username || existingUser.signInDetails?.loginId === username) {
            this.currentUser = existingUser;
            this.saveUserToStorage();
            return { isSignedIn: true };
          } else {
            // Different user - need to logout first
            await this.logout();
          }
        } else {
          // User exists but no valid session - logout to clean state
          await this.logout();
        }
      } catch (error) {
        // No existing user, which is fine - proceed with login
      }
      
      const signInResult = await signIn({ username, password });

      // Handle different sign-in states
      if (signInResult.isSignedIn) {
        // User is fully signed in, we can get the current user
        try {
          this.currentUser = await getCurrentUser();
          this.saveUserToStorage();
        } catch (error) {
          // Set basic user info from sign-in result if available
          this.currentUser = { username: username };
          this.saveUserToStorage();
        }
      } else if (signInResult.nextStep?.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        // User needs to set a new password// Store the sign-in result for the password change flow
        this.pendingSignInResult = signInResult;
      } else {
        // Handle other challenges (MFA, etc.) if needed
      }

      return signInResult;
    } catch (error) {
      throw error;
    }
  }

  async confirmNewPassword(newPassword) {
    try {
      if (!this.pendingSignInResult) {
        throw new Error('No pending sign-in result found');
      }

      const confirmResult = await confirmSignIn({
        challengeResponse: newPassword
      });

      if (confirmResult.isSignedIn) {
        // User is now fully signed in
        try {
          this.currentUser = await getCurrentUser();
          this.saveUserToStorage();
        } catch (error) {
          // Ignore user fetch errors
        }
        
        // Clear the pending sign-in result
        this.pendingSignInResult = null;
      }

      return confirmResult;
    } catch (error) {
      throw error;
    }
  }

  async logout() {
    try {
      // Sign out from AWS Amplify with global signout
      await signOut({ global: true });
      
      // Clear all local state
      this.currentUser = null;
      this.pendingSignInResult = null;
      
      // Clear localStorage completely
      localStorage.removeItem('currentUser');
      
      // Clear any other auth-related storage more aggressively
      const keysToRemove = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (
          key.startsWith('CognitoIdentityServiceProvider') || 
          key.startsWith('amplify') ||
          key.startsWith('aws-amplify') ||
          key.includes('cognito') ||
          key.includes('Cognito')
        )) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach(key => localStorage.removeItem(key));
      
      // Also clear sessionStorage
      const sessionKeysToRemove = [];
      for (let i = 0; i < sessionStorage.length; i++) {
        const key = sessionStorage.key(i);
        if (key && (
          key.startsWith('CognitoIdentityServiceProvider') || 
          key.startsWith('amplify') ||
          key.startsWith('aws-amplify') ||
          key.includes('cognito') ||
          key.includes('Cognito')
        )) {
          sessionKeysToRemove.push(key);
        }
      }
      sessionKeysToRemove.forEach(key => sessionStorage.removeItem(key));
    } catch (error) {
      // Even if signOut fails, clear local state aggressively
      this.currentUser = null;
      this.pendingSignInResult = null;
      localStorage.clear();
      sessionStorage.clear();
    }
  }

  async getCurrentUser() {
    try {
      // Ensure Amplify is initialized before calling getCurrentUser
      if (!this.isInitialized) {
        await this.initialize();
      }
      
      if (!this.currentUser) {
        this.currentUser = await getCurrentUser();
      }
      return this.currentUser;
    } catch (error) {
      this.currentUser = null;
      throw error;
    }
  }

  async isAuthenticated() {
    try {
      // Ensure Amplify is initialized before checking authentication
      if (!this.isInitialized) {
        await this.initialize();
      }
      
      // First try to get current user directly from AWS Amplify
      try {
        const user = await getCurrentUser();
        this.currentUser = user;
        this.saveUserToStorage();
        return true;
      } catch (error) {
        // If getCurrentUser fails, try to check if there's a valid session
        try {
          const session = await fetchAuthSession();
          if (session && session.tokens && session.tokens.accessToken) {
            // User has a valid session, update our state
            this.currentUser = { authenticated: true };
            this.saveUserToStorage();
            return true;
          }
        } catch (sessionError) {
          // Session validation failed
        }
        
        // Clear any stale state
        this.currentUser = null;
        this.saveUserToStorage();
        return false;
      }
    } catch (error) {
      this.currentUser = null;
      this.saveUserToStorage();
      return false;
    }
  }

  async getEmail() {
    try {
      const user = await this.getCurrentUser();
      
      // Try to get email from user attributes first
      if (user?.signInDetails?.loginId) {
        return user.signInDetails.loginId;
      }
      
      // Try to get from username if it's an email
      if (user?.username && user.username.includes('@')) {
        return user.username;
      }
      
      // Try to get from fetchAuthSession tokens
      try {
        const session = await fetchAuthSession();
        const email = session?.tokens?.idToken?.payload?.email;
        if (email) {
          return email;
        }
      } catch (sessionError) {
        // Session access failed
      }
      
      return 'unknown@example.com';
    } catch (error) {
      return 'unknown@example.com';
    }
  }

  async getAuthToken() {
    try {
      const session = await fetchAuthSession();
      const token = session.tokens?.accessToken?.toString();
      return token;
    } catch (error) {
      return null;
    }
  }
}

export default new AuthService();
