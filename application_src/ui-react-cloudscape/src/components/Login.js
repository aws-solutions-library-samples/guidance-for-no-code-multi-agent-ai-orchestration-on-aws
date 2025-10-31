import React, { useState } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Form from '@cloudscape-design/components/form';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Button from '@cloudscape-design/components/button';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Alert from '@cloudscape-design/components/alert';
import Box from '@cloudscape-design/components/box';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Icon from '@cloudscape-design/components/icon';
import Grid from '@cloudscape-design/components/grid';
import authService from '../services/auth';

const Login = ({ onLogin, onAuthenticationComplete, error }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [needsNewPassword, setNeedsNewPassword] = useState(false);
  const [localError, setLocalError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username || !password) return;

    setIsLoading(true);
    setLocalError('');
    
    try {
      const signInResult = await authService.login(username, password);
      
      if (signInResult.isSignedIn) {
        await onLogin(username, password);
      } else if (signInResult.nextStep?.signInStep === 'CONFIRM_SIGN_IN_WITH_NEW_PASSWORD_REQUIRED') {
        setNeedsNewPassword(true);
      } else {
        setLocalError('Login requires additional steps that are not yet supported.');
      }
    } catch (error) {// Set proper error message based on error type
      if (error.message?.includes('NotAuthorizedException') || error.message?.includes('Incorrect username or password')) {
        setLocalError('Incorrect username or password. Please try again.');
      } else if (error.message?.includes('UserNotFoundException')) {
        setLocalError('User not found. Please check your username.');
      } else if (error.message?.includes('TooManyRequestsException')) {
        setLocalError('Too many failed login attempts. Please wait and try again.');
      } else if (error.message?.includes('NetworkError') || error.message?.includes('fetch')) {
        setLocalError('Network connection error. Please check your internet connection.');
      } else {
        setLocalError(error.message || 'Login failed. Please try again.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleNewPasswordSubmit = async (e) => {
    e.preventDefault();
    
    if (!newPassword || !confirmPassword) {
      setLocalError('Please fill in both password fields.');
      return;
    }
    
    if (newPassword !== confirmPassword) {
      setLocalError('Passwords do not match.');
      return;
    }
    
    if (newPassword.length < 8) {
      setLocalError('Password must be at least 8 characters long.');
      return;
    }

    setIsLoading(true);
    setLocalError('');
    
    try {
      const confirmResult = await authService.confirmNewPassword(newPassword);
      
      if (confirmResult.isSignedIn) {
        await onAuthenticationComplete();
      } else {
        setLocalError('Failed to confirm new password. Please try again.');
      }
    } catch (error) {setLocalError(error.message || 'Failed to set new password. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div style={{ 
      minHeight: '100vh', 
      display: 'flex', 
      alignItems: 'center', 
      justifyContent: 'center',
      padding: '2rem 1rem'
    }}>
      <Container
        variant="stacked"
        maxWidth="500px"
      >
        <SpaceBetween size="xl" alignItems="center">
          {/* AWS Foundation Visual Style - Brand Identity - Consistent with main app */}
          <Box textAlign="center" key="brand-header">
            <SpaceBetween size="l" alignItems="center">
              <Icon name="settings" size="large" key="brand-icon" />
              <SpaceBetween size="s" alignItems="center">
                <Header variant="h1" key="brand-title">
                  Agentic AI Platform
                </Header>
                <Box variant="p" color="text-body-secondary" textAlign="center" key="brand-description">
                  Intelligent agent platform for enterprise AI workflows
                </Box>
              </SpaceBetween>
            </SpaceBetween>
          </Box>

          {/* AWS Foundation GenAI Affordance - Authentication Context */}
          <Container variant="stacked" key="auth-context">
            <SpaceBetween size="s" alignItems="center">
              <StatusIndicator type="info" iconAriaLabel="Information" key="auth-status">
                Secure Authentication Required
              </StatusIndicator>
              <Box variant="small" color="text-body-secondary" textAlign="center" key="auth-description">
                Access to AI agents requires authenticated session
              </Box>
            </SpaceBetween>
          </Container>
            
          {/* AWS Foundation Visual Context - Error Handling */}
          {(error || localError) && (
            <Alert
              key="error-alert"
              type="error"
              header="Authentication Error"
              dismissible={!!localError}
              onDismiss={() => setLocalError('')}
              statusIconAriaLabel="Error"
            >
              <Box variant="p">{error || localError}</Box>
              {(error || localError).includes('credentials') && (
                <Box variant="small" color="text-body-secondary">
                  Please verify your username and password are correct.
                </Box>
              )}
            </Alert>
          )}

          {/* AWS Foundation Layout - Primary Authentication Form */}
          {!needsNewPassword ? (
            <Container
              key="login-form"
              header={
                <Header 
                  variant="h2"
                  description="Enter your credentials to access the platform"
                >
                  Sign In
                </Header>
              }
              variant="default"
            >
              <Form
                actions={
                  <SpaceBetween direction="horizontal" size="s" justifyContent="center">
                    <Button
                      variant="primary"
                      onClick={handleSubmit}
                      loading={isLoading}
                      disabled={!username || !password}
                      iconName="unlocked"
                      size="large"
                      fullWidth={true}
                      ariaLabel="Sign in to Agentic AI Platform"
                    >
                      {isLoading ? 'Authenticating...' : 'Sign In'}
                    </Button>
                  </SpaceBetween>
                }
              >
                <SpaceBetween size="l">
                  {/* AWS Foundation Typography - Form Fields */}
                  <FormField 
                    label="Username"
                    constraintText="Your AWS/corporate username"
                    description="Enter the username provided by your administrator"
                  >
                    <Input
                      value={username}
                      onChange={({ detail }) => setUsername(detail.value)}
                      placeholder="Enter your username"
                      disabled={isLoading}
                      type="text"
                      inputMode="text"
                      autoComplete="username"
                      ariaLabel="Username input"
                      ariaRequired={true}
                    />
                  </FormField>

                  <FormField 
                    label="Password"
                    constraintText="Your secure password"
                    description="Enter your password to authenticate"
                  >
                    <Input
                      type="password"
                      value={password}
                      onChange={({ detail }) => setPassword(detail.value)}
                      placeholder="Enter your password"
                      disabled={isLoading}
                      autoComplete="current-password"
                      ariaLabel="Password input"
                      ariaRequired={true}
                    />
                  </FormField>
                </SpaceBetween>
              </Form>
            </Container>
          ) : (
            /* AWS Foundation Visual Context - Password Change Flow */
            <Container
              key="password-change-form"
              header={
                <Header 
                  variant="h2"
                  description="Security policy requires a new password"
                >
                  Password Change Required
                </Header>
              }
              variant="default"
            >
              <SpaceBetween size="l">
                <Alert 
                  type="warning" 
                  header="Secure Password Required"
                  statusIconAriaLabel="Warning"
                >
                  <SpaceBetween size="s">
                    <Box variant="p">
                      Your current password has expired or needs to be updated for security compliance.
                    </Box>
                    <Box variant="small" color="text-body-secondary">
                      Choose a secure password with at least 8 characters including uppercase, lowercase, numbers, and special characters.
                    </Box>
                  </SpaceBetween>
                </Alert>
                
                <Form
                  actions={
                    <SpaceBetween direction="horizontal" size="s" justifyContent="center">
                      <Button
                        variant="primary"
                        onClick={handleNewPasswordSubmit}
                        loading={isLoading}
                        disabled={!newPassword || !confirmPassword}
                        iconName="key"
                        size="large"
                        fullWidth={true}
                        ariaLabel="Set new password"
                      >
                        {isLoading ? 'Setting Password...' : 'Set New Password'}
                      </Button>
                    </SpaceBetween>
                  }
                  errorText={localError}
                >
                  <SpaceBetween size="l">
                    {/* AWS Foundation Typography - Password Fields */}
                    <FormField 
                      label="New Password"
                      constraintText="Minimum 8 characters required"
                      description="Create a strong password with mixed case, numbers, and special characters"
                    >
                      <Input
                        type="password"
                        value={newPassword}
                        onChange={({ detail }) => setNewPassword(detail.value)}
                        placeholder="Enter your new secure password"
                        disabled={isLoading}
                        autoComplete="new-password"
                        ariaLabel="New password input"
                        ariaRequired={true}
                      />
                    </FormField>

                    <FormField 
                      label="Confirm New Password"
                      constraintText="Must match the password above"
                      description="Re-enter your new password to confirm"
                    >
                      <Input
                        type="password"
                        value={confirmPassword}
                        onChange={({ detail }) => setConfirmPassword(detail.value)}
                        placeholder="Confirm your new password"
                        disabled={isLoading}
                        autoComplete="new-password"
                        ariaLabel="Confirm password input"
                        ariaRequired={true}
                        invalid={newPassword && confirmPassword && newPassword !== confirmPassword}
                      />
                    </FormField>
                  </SpaceBetween>
                </Form>
              </SpaceBetween>
            </Container>
          )}

          {/* AWS Foundation Visual Context - Authentication Information */}
          <Container variant="stacked" key="auth-info">
            <SpaceBetween size="s" alignItems="center">
              <StatusIndicator type="info" iconAriaLabel="Information" key="cognito-status">
                Powered by AWS Cognito Authentication
              </StatusIndicator>
              <Box variant="small" color="text-body-secondary" textAlign="center" key="cognito-description">
                Your credentials are securely managed through AWS identity services
              </Box>
            </SpaceBetween>
          </Container>
        </SpaceBetween>
      </Container>
    </div>
  );
};

export default Login;
