import React, { useState, useEffect, useCallback } from 'react';
import TopNavigation from '@cloudscape-design/components/top-navigation';
import AppLayout from '@cloudscape-design/components/app-layout';
import Flashbar from '@cloudscape-design/components/flashbar';
import Spinner from '@cloudscape-design/components/spinner';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Badge from '@cloudscape-design/components/badge';
import Icon from '@cloudscape-design/components/icon';
import Alert from '@cloudscape-design/components/alert';
import authService from './services/auth';
import configService from './services/configuration';
import Login from './components/Login';
import AgentWizard from './components/AgentWizard';
import ChatInterface from './components/ChatInterface';
import AgentMapping from './components/AgentMapping';
import { ThemeProvider, useTheme } from './components/ThemeProvider';
import { useAuth } from './hooks/useAuth';
import { 
  CanCreateAgents, 
  CanUpdateAgents, 
  CanAccessChat,
  CanRefreshAgent 
} from './components/PermissionGate';

function App({ themeControls = null }) {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [userEmail, setUserEmail] = useState('');
  const [error, setError] = useState(null);

  // Agent and configuration state
  const [availableAgents, setAvailableAgents] = useState([]);
  const [currentAgent, setCurrentAgent] = useState(null);
  const [agentConfig, setAgentConfig] = useState({});
  const [originalConfig, setOriginalConfig] = useState({});

  // Chat state
  const [messages, setMessages] = useState([]);
  const [isLoadingMessage, setIsLoadingMessage] = useState(false);

  // Widget key for forcing re-renders
  const [widgetKeySuffix, setWidgetKeySuffix] = useState(0);

  // Wizard state
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [isCreateWizardOpen, setIsCreateWizardOpen] = useState(false);
  
  // Agent mapping state
  const [isMappingOpen, setIsMappingOpen] = useState(false);
  const [selectedAgentFromMapping, setSelectedAgentFromMapping] = useState(null);

  // Check authentication status on mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  // Load available agents when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      loadAvailableAgents();
    }
  }, [isAuthenticated]);

  const checkAuthStatus = async () => {
    try {
      const authenticated = await authService.isAuthenticated();
      setIsAuthenticated(authenticated);
      
      if (authenticated) {
        const email = await authService.getEmail();
        setUserEmail(email);
      }
    } catch (error) {setError('Authentication check failed');
    } finally {
      setIsLoading(false);
    }
  };

  const loadAvailableAgents = async () => {
    try {
      const agents = await configService.listAvailableAgents();
      setAvailableAgents(agents);
      
      // Auto-select first agent if none is selected
      if (agents.length > 0 && !currentAgent) {
        await handleAgentSelect(agents[0]);
      }
    } catch (error) {setError('Failed to load available agents');
    }
  };

  const handleLogin = async (username, password) => {
    try {
      setError(null);
      await authService.login(username, password);
      const email = await authService.getEmail();
      setUserEmail(email);
      setIsAuthenticated(true);
    } catch (error) {setError('Login failed. Please check your credentials.');
      throw error;
    }
  };

  const handleAuthenticationComplete = async () => {
    try {
      setError(null);
      const email = await authService.getEmail();
      setUserEmail(email);
      setIsAuthenticated(true);
    } catch (error) {setError('Failed to complete authentication.');
      throw error;
    }
  };

  const handleLogout = async () => {
    try {
      await authService.logout();
      setIsAuthenticated(false);
      setUserEmail('');
      setCurrentAgent(null);
      setAgentConfig({});
      setOriginalConfig({});
      setMessages([]);
    } catch (error) {}
  };

  const handleAgentSelect = async (agentName) => {
    if (agentName && agentName !== currentAgent) {
      try {
        const loadedConfig = await configService.loadAgentConfig(agentName);
        setAgentConfig(loadedConfig);
        setOriginalConfig({ ...loadedConfig });
        setCurrentAgent(agentName);
        setMessages([]);
      } catch (error) {setError(`Failed to load agent config: ${error.message}`);
      }
    }
  };

  const handleConfigUpdate = useCallback((updates) => {
    setAgentConfig(prev => ({
      ...prev,
      ...updates
    }));
  }, []);

  const handleSaveConfig = async () => {
    try {
      await configService.saveAgentConfig(agentConfig);
      setOriginalConfig({ ...agentConfig });
      setWidgetKeySuffix(prev => prev + 1);
      setError(null);
      return { success: true, message: 'Configuration saved successfully!' };
    } catch (error) {setError(`Error saving configuration: ${error.message}`);
      return { success: false, message: error.message };
    }
  };

  const handleCancelConfig = () => {
    setAgentConfig({ ...originalConfig });
    setWidgetKeySuffix(prev => prev + 1);
  };

  // Add streaming state
  const [streamingPreview, setStreamingPreview] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);

  const handleSendMessage = async (message) => {
    if (!message.trim()) return;

    const timestamp = new Date().toLocaleTimeString();
    const userMessage = {
      role: 'user',
      content: message,
      timestamp
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoadingMessage(true);
    setIsStreaming(true);
    setStreamingPreview('');

    try {
      const agentToUse = currentAgent || 'supervisor_agent';
      const startTime = Date.now();
      
      const handleStreamChunk = (chunk, completeResponse) => {
        setStreamingPreview(completeResponse);
      };
      
      const response = await configService.sendChatToSupervisorSimple(
        message, 
        userEmail || "default_user",
        handleStreamChunk
      );
      
      const endTime = Date.now();
      const responseTime = ((endTime - startTime) / 1000).toFixed(2);
      
      const assistantMessage = {
        role: 'assistant',
        content: response,
        timestamp: `${responseTime}s`
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {const errorMessage = {
        role: 'assistant',
        content: "Sorry, I couldn't process your request at the moment.",
        timestamp: 'Error'
      };
      setMessages(prev => [...prev, errorMessage]);
      setError(`Failed to get response from supervisor agent: ${error.message}`);
    } finally {
      setIsLoadingMessage(false);
      setIsStreaming(false);
      setStreamingPreview('');
    }
  };

  const handleClearChat = () => {
    setMessages([]);
  };

  const handleOpenWizard = () => {
    setIsWizardOpen(true);
  };

  const handleCloseWizard = () => {
    setIsWizardOpen(false);
    setSelectedAgentFromMapping(null);
  };

  const handleCreateAgent = () => {
    setIsCreateWizardOpen(true);
  };

  const handleCloseCreateWizard = () => {
    setIsCreateWizardOpen(false);
  };

  const handleAgentCreated = async (newAgentName) => {
    await loadAvailableAgents();
    if (newAgentName) {
      await handleAgentSelect(newAgentName);
    }
  };

  const handleOpenMapping = () => {
    setIsMappingOpen(true);
  };

  const handleCloseMapping = () => {
    setIsMappingOpen(false);
    setSelectedAgentFromMapping(null);
  };

  const handleOpenAgentWizardFromMapping = (agentName) => {
    setSelectedAgentFromMapping(agentName);
    setIsMappingOpen(false);
    setIsWizardOpen(true);
  };

  const handleRefreshAgents = () => {
    loadAvailableAgents();
  };

  // Enhanced Loading State - AWS Foundation Visual Foundation Pattern
  if (isLoading) {
    return (
      <Box 
        textAlign="center" 
        padding={{ vertical: 'xxxl', horizontal: 'xl' }}
        minHeight="100vh"
        display="flex"
        justifyContent="center"
        alignItems="center"
      >
        <Container
          variant="stacked"
          maxWidth="600px"
        >
          <SpaceBetween size="xl" alignItems="center">
            {/* AWS Foundation Visual Style - Brand Identity */}
            <SpaceBetween size="m" alignItems="center">
              <Icon name="settings" size="large" />
              <Box variant="h1" color="text-body-secondary">
                Agentic AI Platform
              </Box>
            </SpaceBetween>
            
            {/* AWS Foundation Layout - Loading Content */}
            <SpaceBetween size="l" alignItems="center">
              <Spinner size="large" />
              <SpaceBetween size="s" alignItems="center">
                <StatusIndicator type="loading" iconAriaLabel="Loading">
                  Initializing application components...
                </StatusIndicator>
                <Box variant="small" color="text-body-secondary" textAlign="center">
                  Setting up secure connections and loading agent configurations
                </Box>
              </SpaceBetween>
            </SpaceBetween>
          </SpaceBetween>
        </Container>
      </Box>
    );
  }

  // Login page - wrapped with theme context
  if (!isAuthenticated) {
    return (
      <ThemeProvider>
        <Login onLogin={handleLogin} onAuthenticationComplete={handleAuthenticationComplete} error={error} />
      </ThemeProvider>
    );
  }

  // Build utilities array for TopNavigation - AWS Foundation Iconography & Visual Context
  const utilities = [];

  // Configure Agent button - RBAC: CanUpdateAgents permission
  utilities.push({
    type: "button",
    text: "Configure Agent",
    title: "Configure agent settings and behavior",
    iconName: "settings",
    disabled: !currentAgent,
    onClick: handleOpenWizard,
    disabledReason: !currentAgent ? "No agent selected" : undefined
  });

  // Create Agent button - RBAC: CanCreateAgents permission
  utilities.push({
    type: "button",
    text: "Create Agent",
    title: "Create a new AI agent",
    iconName: "add-plus",
    variant: "primary",
    onClick: handleCreateAgent
  });

  // Agent Mapping button - Available to all authenticated users
  utilities.push({
    type: "button",
    text: "Network Map",
    title: "View agent network topology",
    iconName: "share",
    onClick: handleOpenMapping
  });

  // Clear Chat button - RBAC: CanAccessChat permission
  utilities.push({
    type: "button",
    text: "Clear Chat",
    title: "Clear conversation history",
    iconName: "remove",
    onClick: handleClearChat
  });

  // User menu dropdown with theme controls - AWS Foundation Visual Context (user identity)
  const userMenuItems = [
    { 
      id: "logout", 
      text: "Sign Out", 
      iconName: "close",
      description: "End current session"
    }
  ];

  // Add theme controls to user menu (AWS Cloudscape best practice)
  if (themeControls) {
    userMenuItems.unshift(
      {
        id: "theme-separator",
        text: "Theme Settings",
        disabled: true
      },
      {
        id: "color-mode",
        text: `${themeControls.theme.colorMode === 'light' ? 'Dark' : 'Light'} Mode`,
        iconName: themeControls.theme.colorMode === 'light' ? 'contrast' : 'view-full',
        description: `Switch to ${themeControls.theme.colorMode === 'light' ? 'dark' : 'light'} mode`
      },
      {
        id: "density",
        text: `${themeControls.theme.density === 'comfortable' ? 'Compact' : 'Comfortable'} View`,
        iconName: themeControls.theme.density === 'comfortable' ? 'view-vertical' : 'view-horizontal',
        description: `Switch to ${themeControls.theme.density === 'comfortable' ? 'compact' : 'comfortable'} density`
      },
      {
        id: "motion",
        text: `${themeControls.theme.motion === 'enabled' ? 'Disable' : 'Enable'} Animations`,
        iconName: themeControls.theme.motion === 'enabled' ? 'pause' : 'play',
        description: `${themeControls.theme.motion === 'enabled' ? 'Disable' : 'Enable'} interface animations`
      },
      {
        id: "separator",
        text: "Account",
        disabled: true
      }
    );
  }

  utilities.push({
    type: "menu-dropdown",
    text: userEmail,
    description: "User account and theme settings",
    iconName: "user-profile",
    items: userMenuItems,
    onItemClick: ({ detail }) => {
      switch (detail.id) {
        case "logout":
          handleLogout();
          break;
        case "color-mode":
          if (themeControls) themeControls.toggleColorMode();
          break;
        case "density":
          if (themeControls) themeControls.toggleDensity();
          break;
        case "motion":
          if (themeControls) themeControls.toggleMotion();
          break;
        default:
          break;
      }
    }
  });

  // Enhanced Error Handling - AWS Foundation Pattern
  const flashbarItems = error ? [
    {
      type: "error",
      header: "Application Error",
      content: error,
      dismissible: true,
      dismissLabel: "Dismiss error message",
      onDismiss: () => setError(null),
      id: "error-notification",
      action: error.includes('Authentication') ? {
        buttonText: "Retry Login",
        onClick: () => {
          setError(null);
          handleLogout();
        }
      } : undefined
    }
  ] : [];

  return (
    <>
      {/* AWS Foundation Layout - Top Navigation with Visual Foundation */}
      <TopNavigation
        identity={{
          href: "/",
          title: "Agentic AI Platform"
          // Removed logo to fix duplication and broken image issue
        }}
        utilities={utilities}
        data-id="top-navigation"
        i18nStrings={{
          searchIconAriaLabel: "Search",
          searchDismissIconAriaLabel: "Close search",
          overflowMenuTriggerText: "More options",
          overflowMenuTitleText: "Additional utilities",
          overflowMenuBackIconAriaLabel: "Back to main menu",
          overflowMenuDismissIconAriaLabel: "Close utilities menu"
        }}
      />
      
      {/* AWS Foundation Layout - Application Layout with Help System */}
      <AppLayout
        navigationHide={true}
        toolsHide={false}
        toolsWidth={320}
        headerSelector="[data-id='top-navigation']"
        tools={
          /* AWS Foundation Help System - Contextual Assistance */
          <Container
            header={
              <Header 
                variant="h2"
                description="Get help and guidance for using the Agentic AI Platform"
                actions={
                  <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                    <Icon name="status-info" />
                    <Badge color="blue" variant="subtle">
                      Help & Documentation
                    </Badge>
                  </SpaceBetween>
                }
              >
                Help & Support
              </Header>
            }
          >
            <SpaceBetween size="l">
              {/* Getting Started Section */}
              <Container
                header={<Header variant="h3">Getting Started</Header>}
                variant="stacked"
              >
                <SpaceBetween size="m">
                  <Box variant="p" color="text-body-secondary">
                    Welcome to the Agentic AI Platform. This intelligent system allows you to create, configure, and interact with AI agents.
                  </Box>
                  
                  <SpaceBetween size="s">
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                      <Icon name="status-positive" />
                      <Box variant="strong">Step 1:</Box>
                      <Box variant="small">Create or configure an AI agent</Box>
                    </SpaceBetween>
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                      <Icon name="status-positive" />
                      <Box variant="strong">Step 2:</Box>
                      <Box variant="small">Start a conversation in the chat interface</Box>
                    </SpaceBetween>
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                      <Icon name="status-positive" />
                      <Box variant="strong">Step 3:</Box>
                      <Box variant="small">Monitor agents in the network map</Box>
                    </SpaceBetween>
                  </SpaceBetween>
                </SpaceBetween>
              </Container>

              {/* Feature Guide Section */}
              <Container
                header={<Header variant="h3">Platform Features</Header>}
                variant="stacked"
              >
                <SpaceBetween size="m">
                  <SpaceBetween size="s">
                    <SpaceBetween direction="horizontal" size="s" alignItems="flex-start">
                      <Icon name="add-plus" />
                      <SpaceBetween size="xs">
                        <Box variant="strong">Create Agent</Box>
                        <Box variant="small" color="text-body-secondary">
                          Build new AI agents with custom configurations, models, and capabilities
                        </Box>
                      </SpaceBetween>
                    </SpaceBetween>
                    
                    <SpaceBetween direction="horizontal" size="s" alignItems="flex-start">
                      <Icon name="settings" />
                      <SpaceBetween size="xs">
                        <Box variant="strong">Configure Agent</Box>
                        <Box variant="small" color="text-body-secondary">
                          Modify existing agent settings, tools, knowledge bases, and behavior
                        </Box>
                      </SpaceBetween>
                    </SpaceBetween>
                    
                    <SpaceBetween direction="horizontal" size="s" alignItems="flex-start">
                      <Icon name="contact" />
                      <SpaceBetween size="xs">
                        <Box variant="strong">Chat Interface</Box>
                        <Box variant="small" color="text-body-secondary">
                          Engage in intelligent conversations with AI agents for analysis and assistance
                        </Box>
                      </SpaceBetween>
                    </SpaceBetween>
                    
                    <SpaceBetween direction="horizontal" size="s" alignItems="flex-start">
                      <Icon name="share" />
                      <SpaceBetween size="xs">
                        <Box variant="strong">Network Map</Box>
                        <Box variant="small" color="text-body-secondary">
                          Visualize agent network topology, health status, and capabilities
                        </Box>
                      </SpaceBetween>
                    </SpaceBetween>
                  </SpaceBetween>
                </SpaceBetween>
              </Container>

              {/* AI Capabilities Section */}
              <Container
                header={<Header variant="h3">AI Capabilities</Header>}
                variant="stacked"
              >
                <SpaceBetween size="m">
                  <Box variant="p" color="text-body-secondary">
                    Our AI agents are powered by AWS Bedrock and support various specialized tasks:
                  </Box>
                  
                  <SpaceBetween size="s">
                    <Box variant="small">• <Box variant="strong">Code Generation:</Box> Generate, review, and optimize code</Box>
                    <Box variant="small">• <Box variant="strong">Data Analysis:</Box> Process and analyze complex datasets</Box>
                    <Box variant="small">• <Box variant="strong">Technical Writing:</Box> Create documentation and explanations</Box>
                    <Box variant="small">• <Box variant="strong">Problem Solving:</Box> Tackle complex reasoning challenges</Box>
                    <Box variant="small">• <Box variant="strong">Research:</Box> Gather and synthesize information</Box>
                    <Box variant="small">• <Box variant="strong">Tool Integration:</Box> Execute actions via specialized tools</Box>
                  </SpaceBetween>
                </SpaceBetween>
              </Container>

              {/* Troubleshooting Section */}
              <Container
                header={<Header variant="h3">Troubleshooting</Header>}
                variant="stacked"
              >
                <SpaceBetween size="m">
                  <Alert type="info" header="Common Issues">
                    <SpaceBetween size="s">
                      <Box variant="small">
                        <Box variant="strong">Agent not responding:</Box> Check network connectivity and agent health status
                      </Box>
                      <Box variant="small">
                        <Box variant="strong">Configuration errors:</Box> Verify all required fields are properly filled
                      </Box>
                      <Box variant="small">
                        <Box variant="strong">Network map empty:</Box> Use "Refresh Network" to retry discovery
                      </Box>
                    </SpaceBetween>
                  </Alert>
                  
                  <SpaceBetween direction="horizontal" size="s" alignItems="center">
                    <Icon name="external" />
                    <Box variant="small" color="text-body-secondary">
                      For technical support, contact your system administrator
                    </Box>
                  </SpaceBetween>
                </SpaceBetween>
              </Container>

              {/* Theme Settings Section */}
              <Container
                header={<Header variant="h3">Theme Settings</Header>}
                variant="stacked"
              >
                <SpaceBetween size="m">
                  <Box variant="p" color="text-body-secondary">
                    Customize your interface appearance using your user menu (click your email address) in the top navigation.
                  </Box>
                  
                  <Alert type="info" header="Available Theme Options">
                    <SpaceBetween size="s">
                      <Box variant="small">
                        <Box variant="strong">Dark/Light Mode:</Box> Switch between light and dark color schemes
                      </Box>
                      <Box variant="small">
                        <Box variant="strong">Compact/Comfortable View:</Box> Adjust layout density and spacing
                      </Box>
                      <Box variant="small">
                        <Box variant="strong">Enable/Disable Animations:</Box> Control interface motion and transitions
                      </Box>
                    </SpaceBetween>
                  </Alert>
                  
                  {themeControls && (
                    <Alert type="success" header="Current Theme Settings">
                      <SpaceBetween size="s">
                        <Box variant="small">
                          <Box variant="strong">Color Mode:</Box> {themeControls.theme.colorMode}
                        </Box>
                        <Box variant="small">
                          <Box variant="strong">Density:</Box> {themeControls.theme.density}
                        </Box>
                        <Box variant="small">
                          <Box variant="strong">Motion:</Box> {themeControls.theme.motion}
                        </Box>
                      </SpaceBetween>
                    </Alert>
                  )}
                </SpaceBetween>
              </Container>

              {/* Technical Information */}
              <Container
                header={<Header variant="h3">System Information</Header>}
                variant="stacked"
              >
                <SpaceBetween size="s">
                  <SpaceBetween direction="horizontal" size="s" alignItems="center">
                    <Icon name="status-info" />
                    <Box variant="small">
                      <Box variant="strong">Platform:</Box> AWS Bedrock AI Platform
                    </Box>
                  </SpaceBetween>
                  <SpaceBetween direction="horizontal" size="s" alignItems="center">
                    <Icon name="status-info" />
                    <Box variant="small">
                      <Box variant="strong">UI Framework:</Box> AWS Cloudscape Design System
                    </Box>
                  </SpaceBetween>
                  <SpaceBetween direction="horizontal" size="s" alignItems="center">
                    <Icon name="status-info" />
                    <Box variant="small">
                      <Box variant="strong">Authentication:</Box> AWS Cognito
                    </Box>
                  </SpaceBetween>
                  <SpaceBetween direction="horizontal" size="s" alignItems="center">
                    <Icon name="user-profile" />
                    <Box variant="small">
                      <Box variant="strong">Signed in as:</Box> {userEmail}
                    </Box>
                  </SpaceBetween>
                </SpaceBetween>
              </Container>
            </SpaceBetween>
          </Container>
        }
        notifications={
          <Flashbar 
            items={flashbarItems} 
            stackItems={true}
            i18nStrings={{
              ariaLabel: "Application notifications",
              notificationBarAriaLabel: "View all notifications",
              notificationBarText: "Notifications",
              errorIconAriaLabel: "Error notification",
              warningIconAriaLabel: "Warning notification", 
              successIconAriaLabel: "Success notification",
              infoIconAriaLabel: "Information notification"
            }}
          />
        }
        contentType="default"
        disableContentPaddings={false}
        content={
          /* AWS Foundation Layout - Content Area with Proper Spacing */
          <Box padding={{ vertical: 'l', horizontal: 'l' }}>
            <SpaceBetween size="l">
              {/* AWS Foundation GenAI Affordance - Main Chat Interface */}
              <ChatInterface
                currentAgent={currentAgent}
                agentConfig={agentConfig}
                messages={messages}
                onSendMessage={handleSendMessage}
                isLoading={isLoadingMessage}
                streamingPreview={streamingPreview}
                isStreaming={isStreaming}
                userEmail={userEmail}
              />
            </SpaceBetween>
          </Box>
        }
        ariaLabels={{
          navigation: "Main navigation panel",
          navigationClose: "Close navigation panel",
          navigationToggle: "Open navigation panel",
          notifications: "Application notifications panel",
          tools: "Help and support panel",
          toolsClose: "Close help panel",
          toolsToggle: "Open help and support panel"
        }}
      />

      {/* Configuration Wizard - RBAC: CanUpdateAgents */}
      <CanUpdateAgents>
        <AgentWizard
          isOpen={isWizardOpen}
          onClose={handleCloseWizard}
          mode="configure"
          selectedAgent={selectedAgentFromMapping || currentAgent}
        />
      </CanUpdateAgents>

      {/* Create Agent Wizard - RBAC: CanCreateAgents */}
      <CanCreateAgents>
        <AgentWizard
          isOpen={isCreateWizardOpen}
          onClose={handleCloseCreateWizard}
          onAgentCreated={handleAgentCreated}
          mode="create"
        />
      </CanCreateAgents>

      {/* Agent Mapping Visualization */}
      <AgentMapping
        isOpen={isMappingOpen}
        onClose={handleCloseMapping}
        onOpenAgentWizard={handleOpenAgentWizardFromMapping}
        availableAgents={availableAgents}
        onRefreshAgents={handleRefreshAgents}
      />
    </>
  );
}

export default App;
