import React, { useState, useEffect } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Button from '@cloudscape-design/components/button';
import Alert from '@cloudscape-design/components/alert';
import Spinner from '@cloudscape-design/components/spinner';
import Cards from '@cloudscape-design/components/cards';
import Badge from '@cloudscape-design/components/badge';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import ProgressBar from '@cloudscape-design/components/progress-bar';
import Checkbox from '@cloudscape-design/components/checkbox';
import KeyValuePairs from '@cloudscape-design/components/key-value-pairs';
import Icon from '@cloudscape-design/components/icon';
import { 
  CanCreateAgents, 
  CanUpdateAgents, 
  CanDeleteAgents,
  CanViewSkills,
  CanRefreshAgent 
} from './PermissionGate';

const AgentMapping = ({ 
  isOpen, 
  onClose, 
  onOpenAgentWizard,
  availableAgents,
  onRefreshAgents
}) => {
  const [agentMappingData, setAgentMappingData] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Enhanced refresh state
  const [refreshLoading, setRefreshLoading] = useState(false);
  const [refreshProgress, setRefreshProgress] = useState(null);
  
  // Agent management state
  const [selectedAgentForDeletion, setSelectedAgentForDeletion] = useState(null);
  const [isDeletingAgent, setIsDeletingAgent] = useState(false);
  const [agentSkills, setAgentSkills] = useState({});
  const [agentSkillDetails, setAgentSkillDetails] = useState({});
  const [agentTools, setAgentTools] = useState({});
  const [showDeleteConfirmation, setShowDeleteConfirmation] = useState(false);
  const [selectedSkillDetails, setSelectedSkillDetails] = useState(null);
  const [showSkillDetails, setShowSkillDetails] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadAgentMappings();
    }
  }, [isOpen, availableAgents]);

  const loadAgentMappings = async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const configService = await import('../services/configuration');
      const mappingResponse = await configService.default.getAgentMapping();
      setAgentMappingData(mappingResponse);
      
      // Load skills for all discovered agents - but don't wait and handle errors silently
      if (mappingResponse?.agent_mapping) {
        // Load skills in parallel but don't block on failures
        const skillLoadPromises = Object.entries(mappingResponse.agent_mapping).map(
          async ([url, agentInfo]) => {
            if (agentInfo.agent_name && agentInfo.status === 'active') {
              try {
                await loadAgentSkills(agentInfo.agent_name, url);
              } catch (error) {
                // Silently handle skill loading failures - don't block agent mapping display
                console.debug(`Failed to load skills for ${agentInfo.agent_name}:`, error.message);
              }
            }
          }
        );
        
        // Don't await - let skills load in background
        Promise.allSettled(skillLoadPromises).catch(() => {
          // Ignore any errors - skills are optional enhancement
        });
      }
      
    } catch (err) {setError(`Failed to load agent network topology: ${err.message}`);
      
      // Provide fallback visual map with mock data to ensure visual representation shows
      setAgentMappingData({
        agent_mapping: {
          'http://supervisor-agent:8000': {
            agent_name: 'supervisor-agent',
            agent_description: 'Multi-agent coordinator and supervisor (Mock Data)',
            status: 'unknown',
            tools_count: 3,
            streaming_enabled: true,
            uptime_seconds: 0,
            last_updated: new Date().toISOString(),
            skills: ['Agent Coordination', 'Request Routing', 'Load Balancing']
          },
          'http://agent-1:8080': {
            agent_name: 'agent-1',
            agent_description: 'Specialized AI agent instance (Mock Data)',
            status: 'unknown',
            tools_count: 5,
            streaming_enabled: false,
            uptime_seconds: 0,
            last_updated: new Date().toISOString(),
            skills: ['Data Analysis', 'Code Generation', 'Technical Writing', 'Problem Solving', 'Research']
          },
          'http://agent-2:8080': {
            agent_name: 'agent-2', 
            agent_description: 'Secondary AI agent instance (Mock Data)',
            status: 'unknown',
            tools_count: 2,
            streaming_enabled: false,
            uptime_seconds: 0,
            last_updated: new Date().toISOString(),
            skills: ['Customer Support', 'Q&A Processing']
          }
        },
        summary: {
          total_discovered: 3,
          successful_connections: 0,
          failed_connections: 3,
          discovery_source: 'fallback'
        }
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleEnhancedRefresh = async () => {
    setRefreshLoading(true);
    setRefreshProgress({ status: 'starting', step: 1, totalSteps: 3, message: 'Starting refresh...' });

    try {
      const configService = await import('../services/configuration');

      setRefreshProgress({ status: 'supervisor', step: 2, totalSteps: 3, message: 'Refreshing supervisor cache...' });
      await configService.default.refreshSupervisorAgentCache();

      setRefreshProgress({ status: 'discovery', step: 3, totalSteps: 3, message: 'Refreshing agent discovery...' });
      await onRefreshAgents();
      await loadAgentMappings();

      setRefreshProgress({ status: 'complete', step: 3, totalSteps: 3, message: 'Refresh completed!' });
      setTimeout(() => setRefreshProgress(null), 3000);

    } catch (error) {
      setRefreshProgress({ status: 'failed', message: `Refresh failed: ${error.message}` });
      setTimeout(() => setRefreshProgress(null), 5000);
    } finally {
      setRefreshLoading(false);
    }
  };

  // AWS Foundation Visual Context - Status Mapping
  const getStatusBadge = (status) => {
    const statusMap = {
      'active': { color: 'green', text: 'Active', icon: 'status-positive' },
      'timeout': { color: 'grey', text: 'Timeout', icon: 'status-stopped' },
      'error': { color: 'red', text: 'Error', icon: 'status-negative' },
      'unknown': { color: 'blue', text: 'Unknown', icon: 'status-info' }
    };
    
    const statusInfo = statusMap[status] || { color: 'blue', text: 'Unknown', icon: 'status-info' };
    
    return (
      <SpaceBetween direction="horizontal" size="xs" alignItems="center">
        <Icon name={statusInfo.icon} />
        <Badge color={statusInfo.color}>
          {statusInfo.text}
        </Badge>
      </SpaceBetween>
    );
  };

  // Convert mapping data to cards with skills and management capabilities
  const agentCards = agentMappingData?.agent_mapping ? 
    Object.entries(agentMappingData.agent_mapping).map(([url, agentInfo], index) => ({
      id: `agent-${index}`,
      name: agentInfo.agent_name || 'Unknown Agent',
      description: agentInfo.agent_description || 'No description available',
      url: url,
      status: agentInfo.status,
      toolsCount: agentInfo.tools_count || 0,
      streamingEnabled: agentInfo.streaming_enabled || false,
      uptime: agentInfo.uptime_seconds || 0,
      lastUpdated: agentInfo.last_updated,
      skills: agentInfo.skills || ['General AI Assistant'],
      canDelete: agentInfo.agent_name !== 'supervisor-agent' // Don't allow deleting supervisor
    })) : [];

  // Load agent skills/capabilities - enhanced with proper agent card API response parsing
  const loadAgentSkills = async (agentName, agentUrl = null) => {
    try {const configService = await import('../services/configuration');
      
      // Try multiple approaches to get agent skills
      let skills = [];
      let toolsList = [];
      
      // Method 1: Try to get agent card first - parse structured response format
      try {
        // Use passed agentUrl parameter or find from mapping data
        let targetAgentUrl = agentUrl;
        
        if (!targetAgentUrl && agentMappingData?.agent_mapping) {
          const agentEntry = Object.entries(agentMappingData.agent_mapping)
            .find(([url, info]) => info.agent_name === agentName);
          
          if (agentEntry) {
            targetAgentUrl = agentEntry[0];
          }
        }
        
        if (targetAgentUrl) {const agentCard = await configService.default.getAgentCard(targetAgentUrl);// The backend wraps the response, so look inside agent_card property
          const actualAgentCard = agentCard?.agent_card || agentCard;// Parse structured skills array from agent card - be true to API data only
          if (actualAgentCard?.skills && Array.isArray(actualAgentCard.skills)) {// Store complete skill details for later use
            setAgentSkillDetails(prev => ({
              ...prev,
              [agentName]: actualAgentCard.skills
            }));
            
            // Handle structured skills format: [{ name: "skill_name", description: "..." }, ...]
            skills = actualAgentCard.skills.map(skill => {
              if (typeof skill === 'object' && skill.name) {
                return skill.name;
              } else if (typeof skill === 'string') {
                return skill;
              }
              return 'Unknown Skill';
            });// Also extract tools information from skills if they appear to be tools
            toolsList = actualAgentCard.skills
              .filter(skill => typeof skill === 'object' && skill.id && (
                skill.id.includes('mcp_') || 
                skill.id.includes('tool') || 
                skill.name.toLowerCase().includes('tool')
              ))
              .map(tool => tool.name || tool.id);
              
            if (toolsList.length > 0) {
              // Tools list will be stored below
            }
          }
          
          // Note: Capabilities are metadata only, not skills - don't add them as skills
          if (actualAgentCard?.capabilities) {
            // Capabilities are metadata, not added as skills
          }
          
        }
      } catch (cardError) {
        // Silently continue with fallback methods if agent card fetch fails
        console.debug(`Agent card fetch failed for ${agentName}:`, cardError.message);
      }
      
      // Store tools information from agent card if any were found
      if (toolsList.length > 0) {
        setAgentTools(prev => ({
          ...prev,
          [agentName]: {
            count: toolsList.length,
            names: toolsList
          }
        }));
      }
      
      // Method 2: Fallback to configuration-based skills if agent card fails
      if (skills.length === 0) {
        try {const config = await configService.default.loadAgentConfig(agentName);
          
          // Extract skills from configuration
          // Add model capabilities
          if (config.model_id) {
            skills.push('Language Processing');
          }
          
          // Extract and store tools information from config if not from agent card
          if (toolsList.length === 0) {
            let configToolsList = [];
            if (config.tools && Array.isArray(config.tools) && config.tools.length > 0) {
              skills.push('Tool Integration');
              config.tools.forEach(tool => {
                skills.push(`${tool.name} Tool`);
                configToolsList.push(tool.name);
              });
            }
            
            // Store tools information from config
            if (configToolsList.length > 0) {
              setAgentTools(prev => ({
                ...prev,
                [agentName]: {
                  count: configToolsList.length,
                  names: configToolsList
                }
              }));
            }
          }
          
          // Add knowledge base skills
          if (config.knowledge_base === 'True' || config.knowledge_base === true) {
            skills.push('Knowledge Base Access');
          }
          
          // Add memory capabilities
          if (config.memory === 'True' || config.memory === true) {
            skills.push('Conversation Memory');
          }
          
          // Add observability
          if (config.observability === 'True' || config.observability === true) {
            skills.push('Performance Monitoring');
          }
          
          // Add guardrails
          if (config.guardrail === 'True' || config.guardrail === true) {
            skills.push('Content Safety');
          }
        } catch (configError) {
          // Continue with empty skills if config loading fails
        }
      }
      
      // Set final skills
      const finalSkills = skills.length > 0 ? skills : ['General AI Assistant'];setAgentSkills(prev => ({
        ...prev,
        [agentName]: finalSkills
      }));
      
    } catch (error) {setAgentSkills(prev => ({
        ...prev,
        [agentName]: ['General AI Assistant']
      }));
    }
  };

  // Delete agent functionality with Cloudscape confirmation
  const handleDeleteAgent = (agentName) => {
    if (agentName === 'supervisor-agent') {
      setError('Cannot delete supervisor agent - it is required for system operation');
      return;
    }
    
    setSelectedAgentForDeletion(agentName);
    setShowDeleteConfirmation(true);
  };

  const confirmDeleteAgent = async () => {
    if (!selectedAgentForDeletion) return;
    
    setIsDeletingAgent(true);
    setShowDeleteConfirmation(false);
    
    try {
      const configService = await import('../services/configuration');
      
      // Step 1: Initiate agent deletion and wait for completionconst deletionResult = await configService.default.deleteAgentComplete(selectedAgentForDeletion, true);// Step 2: Wait a moment for infrastructure cleanup to propagateawait new Promise(resolve => setTimeout(resolve, 2000)); // 2 second delay
      
      // Step 3: Refresh supervisor cache first
      try {
        await configService.default.refreshSupervisorAgentCache();
      } catch (supervisorError) {
        // Continue even if supervisor refresh fails
      }
      
      // Step 4: Refresh the local agent listawait onRefreshAgents();
      
      // Step 5: Finally reload the agent mapping to reflect changesawait loadAgentMappings();} catch (error) {setError(`Failed to delete agent "${selectedAgentForDeletion}": ${error.message}`);
    } finally {
      setIsDeletingAgent(false);
      setSelectedAgentForDeletion(null);
    }
  };

  const cancelDeleteAgent = () => {
    setShowDeleteConfirmation(false);
    setSelectedAgentForDeletion(null);
  };

  // Skill details functionality - AWS Cloudscape compliant
  const handleSkillDetailsClick = (agentName, skillName) => {
    const skillDetails = agentSkillDetails[agentName];
    if (skillDetails && Array.isArray(skillDetails)) {
      const selectedSkill = skillDetails.find(skill => 
        (typeof skill === 'object' && skill.name === skillName) ||
        (typeof skill === 'string' && skill === skillName)
      );
      
      if (selectedSkill) {
        setSelectedSkillDetails({
          agentName,
          skillName,
          skillData: selectedSkill
        });
        setShowSkillDetails(true);
      }
    }
  };

  const closeSkillDetails = () => {
    setShowSkillDetails(false);
    setSelectedSkillDetails(null);
  };

  return (
    <Modal
      visible={isOpen}
      onDismiss={onClose}
      header="Agent Network Topology"
      size="max"
      footer={
        /* AWS Foundation Layout - Modal Actions */
        <Box float="right">
          <SpaceBetween direction="horizontal" size="s">
            <Button
              onClick={handleEnhancedRefresh}
              disabled={isLoading || refreshLoading}
              loading={refreshLoading}
              iconName="refresh"
              ariaLabel="Refresh network topology"
            >
              Refresh Network
            </Button>
            <Button 
              variant="primary" 
              onClick={onClose}
              iconName="close"
              ariaLabel="Close network topology view"
            >
              Close
            </Button>
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween size="l">
        {/* Refresh Progress */}
        {refreshProgress && (
          <Alert
            type={refreshProgress.status === 'failed' ? 'error' : 'info'}
            header={refreshProgress.status === 'complete' ? 'Success' : 'Refreshing...'}
          >
            <SpaceBetween size="s">
              <Box>{refreshProgress.message}</Box>
              {refreshProgress.step && refreshProgress.totalSteps && (
                <ProgressBar 
                  value={(refreshProgress.step / refreshProgress.totalSteps) * 100}
                  label={`Step ${refreshProgress.step} of ${refreshProgress.totalSteps}`}
                />
              )}
            </SpaceBetween>
          </Alert>
        )}

        {error && (
          <Alert 
            type="error" 
            header="Network Discovery Error"
            dismissible 
            onDismiss={() => setError(null)}
            statusIconAriaLabel="Error"
          >
            <SpaceBetween size="s">
              <Box variant="p">{error}</Box>
              <Box variant="small" color="text-body-secondary">
                The network map below shows the expected topology structure. Use "Refresh Network" to retry discovery.
              </Box>
            </SpaceBetween>
          </Alert>
        )}

        {/* AWS Foundation Visual Context - Network Overview */}
        {agentMappingData?.summary && (
          <Container 
            header={
              <Header 
                variant="h2"
                description="Real-time network topology and connection status"
                info={
                  <Box variant="small" color="text-body-secondary">
                    Network discovery powered by {agentMappingData.discovery_source === 'local_mock' ? 'Local Discovery' : 'VPC Lattice Service Mesh'}
                  </Box>
                }
                actions={
                  <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                    <Icon name="share" />
                    <Badge 
                      color={agentMappingData.summary.failed_connections > 0 ? 'red' : 'green'} 
                      variant="subtle"
                    >
                      Network {agentMappingData.summary.failed_connections > 0 ? 'Issues' : 'Healthy'}
                    </Badge>
                  </SpaceBetween>
                }
              >
                Network Topology Overview
              </Header>
            }
            variant="stacked"
          >
            <KeyValuePairs
              columns={4}
              items={[
                {
                  label: "Discovered Agents",
                  value: (
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                      <Icon name="settings" />
                      <Box variant="strong">{agentMappingData.summary.total_discovered || 0}</Box>
                    </SpaceBetween>
                  )
                },
                {
                  label: "Active Connections", 
                  value: (
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                      <Icon name="status-positive" />
                      <Box variant="strong" color="text-status-success">{agentMappingData.summary.successful_connections || 0}</Box>
                    </SpaceBetween>
                  )
                },
                {
                  label: "Failed Connections",
                  value: (
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                      <Icon name="status-negative" />
                      <Box variant="strong" color={agentMappingData.summary.failed_connections > 0 ? "text-status-error" : "text-body-secondary"}>
                        {agentMappingData.summary.failed_connections || 0}
                      </Box>
                    </SpaceBetween>
                  )
                },
                {
                  label: "Discovery Method",
                  value: (
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                      <Icon name="share" />
                      <Box variant="code" fontSize="body-s">
                        {agentMappingData.discovery_source === 'local_mock' ? 'Local Discovery' : 'VPC Lattice'}
                      </Box>
                    </SpaceBetween>
                  )
                }
              ]}
            />
          </Container>
        )}

        {/* AWS Foundation Visual Context - Network Topology Diagram */}
        <Container
          header={
            <Header 
              variant="h2" 
              description="Visual network topology showing agent connections and data flow"
              actions={
                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                  <Icon name="share" />
                  <Badge color="blue" variant="subtle">
                    Live Topology
                  </Badge>
                </SpaceBetween>
              }
            >
              Network Architecture
            </Header>
          }
          variant="default"
        >
          <Box textAlign="center" padding="l">
            <SpaceBetween size="xl" alignItems="center">
              {/* Supervisor Agent at Top */}
              <Container variant="stacked">
                <SpaceBetween size="s" alignItems="center">
                  <Icon name="settings" size="large" />
                  <Box variant="h3">Supervisor Agent</Box>
                  <Badge color="green">Coordinator</Badge>
                  <Box variant="code" fontSize="body-s">:9003</Box>
                </SpaceBetween>
              </Container>
              
              {/* Connection Flow Indicators */}
              <SpaceBetween size="s" alignItems="center">
                <Box variant="small" color="text-body-secondary">↓ Routes Requests ↓</Box>
                <Box variant="small" color="text-body-secondary">↓ Manages Responses ↓</Box>
              </SpaceBetween>
              
              {/* Enhanced Agent Network with Visual Connections */}
              <Box>
                <SpaceBetween size="l">
                  <Container variant="stacked">
                    <Box variant="h4" color="text-body-secondary">
                      Connected Agent Network
                    </Box>
                  </Container>
                  
                  {/* Visual Connection Network */}
                  <Box style={{ position: 'relative', minHeight: '200px' }}>
                    {agentCards.filter(agent => agent.name !== 'supervisor-agent').length > 0 ? (
                      <SpaceBetween size="l" alignItems="center">
                        {/* Connection Lines and Agent Layout */}
                        <div style={{ 
                          display: 'grid', 
                          gridTemplateColumns: `repeat(${Math.min(3, agentCards.filter(agent => agent.name !== 'supervisor-agent').length)}, 1fr)`,
                          gap: '2rem',
                          width: '100%',
                          justifyItems: 'center'
                        }}>
                          {agentCards.filter(agent => agent.name !== 'supervisor-agent').map((agent, index) => (
                            <div key={agent.id} style={{ position: 'relative', textAlign: 'center' }}>
                              {/* Connection Line to Supervisor */}
                              <div style={{
                                position: 'absolute',
                                top: '-2rem',
                                left: '50%',
                                width: '2px',
                                height: '2rem',
                                backgroundColor: '#0972d3',
                                transform: 'translateX(-50%)'
                              }} />
                              
                              {/* Agent Node */}
                              <Box style={{ 
                                border: '2px solid #0972d3', 
                                borderRadius: '8px',
                                backgroundColor: '#fafbfc',
                                minWidth: '150px',
                                padding: '16px'
                              }}>
                                <SpaceBetween size="s" alignItems="center">
                                  <Icon name="contact" />
                                  <Box variant="strong">{agent.name}</Box>
                                  {getStatusBadge(agent.status)}
                                  <Box variant="code" fontSize="body-s">
                                    {agent.url.split('://')[1]?.split('/')[0] || agent.url}
                                  </Box>
                                  <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                                    <Badge color="blue" variant="subtle">
                                      {agentTools[agent.name]?.count ?? agent.toolsCount} tools
                                    </Badge>
                                    <Badge color="green" variant="subtle">
                                      {agentSkills[agent.name]?.length ?? agent.skills?.length ?? 0} skills
                                    </Badge>
                                  </SpaceBetween>
                                </SpaceBetween>
                              </Box>
                              
                              {/* Connection Status */}
                              <Box variant="small" color="text-body-secondary" style={{ marginTop: '0.5rem' }}>
                                {agent.status === 'active' ? '🟢 Connected' : 
                                 agent.status === 'error' ? '🔴 Disconnected' : 
                                 agent.status === 'timeout' ? '🟡 Timeout' : '🔵 Unknown'}
                              </Box>
                            </div>
                          ))}
                        </div>
                        
                        {/* Network Statistics */}
                        <Alert type="success" header="Network Status">
                          <SpaceBetween direction="horizontal" size="m" justifyContent="center">
                            <SpaceBetween size="xs" alignItems="center">
                              <Icon name="status-positive" />
                              <Box variant="small">
                                <Box variant="strong">{agentCards.filter(agent => agent.status === 'active').length}</Box> Active
                              </Box>
                            </SpaceBetween>
                            <SpaceBetween size="xs" alignItems="center">
                              <Icon name="status-negative" />
                              <Box variant="small">
                                <Box variant="strong">{agentCards.filter(agent => agent.status === 'error').length}</Box> Error
                              </Box>
                            </SpaceBetween>
                            <SpaceBetween size="xs" alignItems="center">
                              <Icon name="status-info" />
                              <Box variant="small">
                                <Box variant="strong">{agentCards.filter(agent => agent.status === 'unknown').length}</Box> Unknown
                              </Box>
                            </SpaceBetween>
                          </SpaceBetween>
                        </Alert>
                      </SpaceBetween>
                    ) : (
                      <Box variant="small" color="text-body-secondary" textAlign="center">
                        No managed agents discovered - supervisor operates in standalone mode
                      </Box>
                    )}
                  </Box>
                </SpaceBetween>
              </Box>
              
              {/* Data Flow Indicators */}
              <Alert type="info" header="Network Communication Flow">
                <SpaceBetween size="s">
                  <Box variant="small">
                    <Box variant="strong">1. Request Routing:</Box> Supervisor agent receives user requests and routes them to appropriate specialized agents
                  </Box>
                  <Box variant="small">
                    <Box variant="strong">2. Agent Processing:</Box> Specialized agents process requests using their configured tools and capabilities
                  </Box>
                  <Box variant="small">
                    <Box variant="strong">3. Response Coordination:</Box> Supervisor agent coordinates and formats responses back to the user
                  </Box>
                </SpaceBetween>
              </Alert>
            </SpaceBetween>
          </Box>
        </Container>

        {/* AWS Foundation Visual Context - Agent Discovery */}
        {isLoading ? (
          <Container
            header={
              <Header variant="h2" description="Scanning network for available AI agents">
                Network Discovery
              </Header>
            }
          >
            <Box textAlign="center" padding="xl">
              <SpaceBetween size="l" alignItems="center">
                {/* AWS Foundation Visual Style - Discovery Animation */}
                <SpaceBetween size="s" alignItems="center">
                  <Spinner size="large" />
                  <Icon name="share" />
                </SpaceBetween>
                
                {/* AWS Foundation Typography - Discovery Context */}
                <SpaceBetween size="s" alignItems="center">
                  <StatusIndicator type="loading" iconAriaLabel="Discovering">
                    Discovering agents across network topology...
                  </StatusIndicator>
                  <Box variant="small" color="text-body-secondary" textAlign="center">
                    Scanning VPC Lattice service mesh and local endpoints for available AI agents
                  </Box>
                </SpaceBetween>
              </SpaceBetween>
            </Box>
          </Container>
        ) : (
          /* AWS Foundation Layout - Agent Cards Display */
          <Container
            header={
              <Header
                variant="h2"
                counter={agentCards.length > 0 ? `(${agentCards.length})` : ''}
                description={agentCards.length > 0 ? "AI agents discovered in your network topology" : "No agents found in network scan"}
                info={agentCards.length > 0 && (
                  <Box variant="small" color="text-body-secondary">
                    Each agent provides specialized AI capabilities and can be configured independently
                  </Box>
                )}
                actions={
                  <SpaceBetween direction="horizontal" size="s">
                    <Button 
                      onClick={onRefreshAgents} 
                      iconName="refresh"
                      ariaLabel="Refresh agent discovery"
                    >
                      Refresh Discovery
                    </Button>
                    {agentCards.length > 0 && (
                      <Badge color="blue" variant="subtle">
                        Network Active
                      </Badge>
                    )}
                  </SpaceBetween>
                }
              >
                Discovered AI Agents
              </Header>
            }
            variant="default"
          >
            {agentCards.length === 0 ? (
              /* AWS Foundation Visual Context - Enhanced Empty State with Network Diagram */
              <Container
                header={
                  <Header variant="h3" description="Visual representation of expected network topology">
                    Network Architecture
                  </Header>
                }
              >
                <SpaceBetween size="l">
                  <Alert type="warning" header="Network Discovery Failed">
                    <SpaceBetween size="s">
                      <Box variant="p">
                        Unable to discover agents in the current network topology. Showing expected network structure for reference.
                      </Box>
                      <Box variant="small" color="text-body-secondary">
                        This visual map will populate with live data once agent services are accessible.
                      </Box>
                    </SpaceBetween>
                  </Alert>
                  
                  {/* AWS Foundation Visual Context - Network Diagram */}
                  <Box textAlign="center" padding="l">
                    <SpaceBetween size="l" alignItems="center">
                      <Box variant="h4" color="text-body-secondary">
                        Expected Network Topology
                      </Box>
                      
                      {/* Visual Network Representation */}
                      <Container variant="stacked">
                        <SpaceBetween size="m" alignItems="center">
                          {/* Supervisor Agent */}
                          <SpaceBetween size="s" alignItems="center">
                            <Icon name="settings" size="large" />
                            <Box variant="strong">Supervisor Agent</Box>
                            <Box variant="small" color="text-body-secondary">Coordinator & Router</Box>
                          </SpaceBetween>
                          
                          {/* Connection Lines */}
                          <Box variant="small" color="text-body-secondary">
                            ↓ Manages & Routes to ↓
                          </Box>
                          
                          {/* Agent Instances */}
                          <SpaceBetween direction="horizontal" size="xl">
                            <SpaceBetween size="s" alignItems="center">
                              <Icon name="contact" />
                              <Box variant="small">Agent-1</Box>
                              <Box variant="code" fontSize="body-s">:8080</Box>
                            </SpaceBetween>
                            
                            <SpaceBetween size="s" alignItems="center">
                              <Icon name="contact" />
                              <Box variant="small">Agent-2</Box>
                              <Box variant="code" fontSize="body-s">:8080</Box>
                            </SpaceBetween>
                          </SpaceBetween>
                        </SpaceBetween>
                      </Container>
                      
                      <Alert type="info" header="Network Troubleshooting">
                        <SpaceBetween size="s">
                          <Box variant="small">• Verify agent services are running: <Box variant="code">docker-compose ps</Box></Box>
                          <Box variant="small">• Check service connectivity and health endpoints</Box>
                          <Box variant="small">• Ensure VPC Lattice or local discovery is configured properly</Box>
                          <Box variant="small">• Try the "Refresh Network" button to retry discovery</Box>
                        </SpaceBetween>
                      </Alert>
                    </SpaceBetween>
                  </Box>
                </SpaceBetween>
              </Container>
            ) : (
              /* AWS Foundation Layout - Agent Cards Grid */
              <Cards
                key={`cards-${Object.keys(agentSkills).length}`} // Force re-render when skills load
                cardDefinition={{
                  header: item => (
                    /* AWS Foundation Visual Context - Agent Card Header */
                    <SpaceBetween direction="horizontal" size="s" alignItems="center">
                      <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                        <Icon name="settings" />
                        <Box variant="h3">{item.name}</Box>
                      </SpaceBetween>
                      <Box flex="1" />
                      {getStatusBadge(item.status)}
                    </SpaceBetween>
                  ),
                  sections: [
                    {
                      id: "description",
                      header: "Agent Description",
                      content: item => (
                        <Box variant="p" color="text-body-secondary">
                          {item.description}
                        </Box>
                      )
                    },
                    {
                      id: "skills",
                      header: "Agent Skills & Capabilities",
                      content: item => {
                        const skillsToShow = agentSkills[item.name] || item.skills || ['General AI Assistant'];return (
                          <SpaceBetween size="m">
                            {/* Skills Badges - Clickable for Details */}
                            <Container variant="stacked">
                              <SpaceBetween size="s">
                                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                                  <Box variant="h4">Available Skills</Box>
                                  <Button
                                    variant="icon"
                                    iconName="status-info"
                                    ariaLabel="Click skills for details"
                                  />
                                </SpaceBetween>
                                <SpaceBetween direction="horizontal" size="s" wrap={true}>
                                  {skillsToShow.map((skill, skillIndex) => (
                                    <Button
                                      key={`${item.name}-skill-${skillIndex}`}
                                      variant="normal"
                                      onClick={() => handleSkillDetailsClick(item.name, skill)}
                                      ariaLabel={`View details for ${skill} skill`}
                                      size="small"
                                    >
                                      <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                                        <Icon name="status-info" />
                                        <Box>{String(skill)}</Box>
                                      </SpaceBetween>
                                    </Button>
                                  ))}
                                </SpaceBetween>
                              </SpaceBetween>
                            </Container>
                            
                            {/* Skills Summary */}
                            <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                              <Icon name="status-info" />
                              <Box variant="small" color="text-body-secondary">
                                {skillsToShow.length} specialized capabilities
                                {agentSkills[item.name] && (
                                  <> • Loaded from live agent</>
                                )}
                              </Box>
                            </SpaceBetween>
                          </SpaceBetween>
                        );
                      }
                    },
                    {
                      id: "serviceUrl",
                      header: "Service Endpoint", 
                      content: item => (
                        <SpaceBetween size="xs">
                          <Box variant="code" fontSize="body-s">
                            {item.url}
                          </Box>
                          <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                            <Icon name="external" />
                            <Box variant="small" color="text-body-secondary">
                              Network accessible endpoint
                            </Box>
                          </SpaceBetween>
                        </SpaceBetween>
                      )
                    },
                    {
                      id: "tools",
                      header: "Agent Tools & Integrations", 
                      content: item => {
                        const agentToolsInfo = agentTools[item.name];
                        const toolsCount = agentToolsInfo?.count ?? item.toolsCount;
                        const toolNames = agentToolsInfo?.names || [];
                        
                        return (
                          <SpaceBetween size="m">
                            {/* Tools Display */}
                            {toolNames.length > 0 ? (
                              <SpaceBetween size="s">
                                <Box variant="h4">Available Tools</Box>
                                <SpaceBetween direction="horizontal" size="s" wrap={true}>
                                  {toolNames.map((tool, toolIndex) => (
                                    <Badge 
                                      key={`${item.name}-tool-${toolIndex}`} 
                                      color="orange" 
                                      variant="normal"
                                    >
                                      {String(tool)}
                                    </Badge>
                                  ))}
                                </SpaceBetween>
                              </SpaceBetween>
                            ) : (
                              <Box variant="small" color="text-body-secondary">
                                No tools configured for this agent
                              </Box>
                            )}
                          </SpaceBetween>
                        );
                      }
                    },
                    {
                      id: "stats",
                      header: "Agent Statistics",
                      content: item => (
                        /* AWS Foundation Typography - Statistics Display */
                        <KeyValuePairs
                          columns={2}
                          items={[
                            {
                              label: "Real-time Streaming",
                              value: (
                                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                                  <Icon name={item.streamingEnabled ? "status-positive" : "status-stopped"} />
                                  <Badge color={item.streamingEnabled ? 'green' : 'grey'} variant="subtle">
                                    {item.streamingEnabled ? 'Enabled' : 'Disabled'}
                                  </Badge>
                                </SpaceBetween>
                              )
                            },
                            {
                              label: "Service Uptime",
                              value: (
                                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                                  <Icon name="status-info" />
                                  <Box variant="code" fontSize="body-s">
                                    {Math.round(item.uptime / 60)} minutes
                                  </Box>
                                </SpaceBetween>
                              )
                            },
                            {
                              label: "Last Health Check",
                              value: (
                                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                                  <Icon name="calendar" />
                                  <Box variant="small" color="text-body-secondary">
                                    {item.lastUpdated ? new Date(item.lastUpdated).toLocaleString() : 'Unknown'}
                                  </Box>
                                </SpaceBetween>
                              )
                            },
                            {
                              label: "Agent Status",
                              value: (
                                <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                                  <Icon name="status-info" />
                                  <Box variant="small" color="text-body-secondary">
                                    Operational
                                  </Box>
                                </SpaceBetween>
                              )
                            }
                          ]}
                        />
                      )
                    },
                    {
                      id: "actions",
                      header: "Agent Management",
                      content: item => (
                        /* AWS Foundation Visual Context - Agent Actions */
                        <SpaceBetween size="s">
                          <SpaceBetween direction="horizontal" size="s">
                            <CanUpdateAgents>
                              <Button
                                onClick={() => onOpenAgentWizard(item.name)}
                                iconName="settings"
                                variant="normal"
                                size="small"
                                ariaLabel={`Configure ${item.name}`}
                              >
                                Configure
                              </Button>
                            </CanUpdateAgents>
                            
                            <CanDeleteAgents>
                              {item.canDelete !== false && (
                                <Button
                                  onClick={() => handleDeleteAgent(item.name)}
                                  iconName="remove"
                                  variant="normal" 
                                  size="small"
                                  loading={isDeletingAgent && selectedAgentForDeletion === item.name}
                                  disabled={isDeletingAgent}
                                  ariaLabel={`Delete ${item.name}`}
                                >
                                  {isDeletingAgent && selectedAgentForDeletion === item.name ? 'Deleting...' : 'Delete'}
                                </Button>
                              )}
                            </CanDeleteAgents>
                          </SpaceBetween>
                          
                          {item.name === 'supervisor-agent' && (
                            <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                              <Icon name="status-warning" />
                              <Box variant="small" color="text-status-warning">
                                System agent - cannot be deleted
                              </Box>
                            </SpaceBetween>
                          )}
                        </SpaceBetween>
                      )
                    }
                  ]
                }}
                cardsPerRow={[
                  { cards: 1 },
                  { minWidth: 500, cards: 2 },
                  { minWidth: 800, cards: 2 }
                ]}
                items={agentCards}
                selectionType="single"
                trackBy="id"
                onSelectionChange={({ detail }) => {
                  // Load skills for selected agents
                  detail.selectedItems.forEach(item => {
                    if (!agentSkills[item.name]) {
                      loadAgentSkills(item.name);
                    }
                  });
                }}
                visibleSections={["description", "skills", "tools", "serviceUrl", "stats", "actions"]}
                empty={
                  /* AWS Foundation Visual Context - Empty State */
                  <Box textAlign="center" color="text-body-secondary" padding="xl">
                    <SpaceBetween size="m" alignItems="center">
                      <Icon name="status-warning" />
                      <Box variant="h4">No Agents in Network</Box>
                      <Box variant="small">Network topology scan completed with no discoverable agents</Box>
                    </SpaceBetween>
                  </Box>
                }
                ariaLabels={{
                  itemSelectionLabel: (e, t) => `Select agent ${t.name}`,
                  selectionGroupLabel: "Agent selection"
                }}
              />
            )}
          </Container>
        )}
      </SpaceBetween>

      {/* AWS Cloudscape Delete Confirmation Modal */}
      {showDeleteConfirmation && (
        <Modal
          visible={showDeleteConfirmation}
          onDismiss={cancelDeleteAgent}
          header="Delete Agent"
          size="medium"
          closeAriaLabel="Cancel agent deletion"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="s">
                <Button 
                  variant="link" 
                  onClick={cancelDeleteAgent}
                  disabled={isDeletingAgent}
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  onClick={confirmDeleteAgent}
                  loading={isDeletingAgent}
                  loadingText="Deleting agent..."
                  ariaLabel={`Confirm deletion of ${selectedAgentForDeletion}`}
                >
                  {isDeletingAgent ? 'Deleting...' : 'Delete Agent'}
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="m">
            <Alert type="warning" header="Permanent Action">
              <Box variant="p">
                This action will permanently delete the agent and cannot be undone.
              </Box>
            </Alert>

            <Container
              header={
                <Header variant="h3" description="Agent to be deleted">
                  Deletion Details
                </Header>
              }
            >
              <KeyValuePairs
                columns={1}
                items={[
                  {
                    label: 'Agent Name',
                    value: <Box variant="strong">{selectedAgentForDeletion}</Box>
                  },
                  {
                    label: 'Impact',
                    value: 'Configuration will be removed from SSM Parameter Store and infrastructure will be deleted'
                  },
                  {
                    label: 'Recovery',
                    value: 'Agent can be recreated with the same name but will require reconfiguration'
                  }
                ]}
              />
            </Container>

            <Alert type="info" header="What will be deleted">
              <SpaceBetween size="s">
                <Box variant="small">• Agent configuration stored in AWS SSM Parameter Store</Box>
                <Box variant="small">• Associated AWS infrastructure (ECS tasks, services, etc.)</Box>
                <Box variant="small">• Agent registration in the supervisor network</Box>
                <Box variant="small">• All deployment artifacts and container images</Box>
              </SpaceBetween>
            </Alert>
          </SpaceBetween>
        </Modal>
      )}

      {/* AWS Cloudscape Skill Details Modal */}
      {showSkillDetails && selectedSkillDetails && (
        <Modal
          visible={showSkillDetails}
          onDismiss={closeSkillDetails}
          header={`Skill Details - ${selectedSkillDetails.skillName}`}
          size="medium"
          closeAriaLabel="Close skill details"
          footer={
            <Box float="right">
              <Button 
                variant="primary" 
                onClick={closeSkillDetails}
                iconName="close"
                ariaLabel="Close skill details"
              >
                Close
              </Button>
            </Box>
          }
        >
          <SpaceBetween size="l">
            <Container
              header={
                <Header
                  variant="h2"
                  description={`Detailed information about ${selectedSkillDetails.skillName} skill`}
                  actions={
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                      <Icon name="status-info" />
                      <Badge color="blue" variant="subtle">
                        Live Data
                      </Badge>
                    </SpaceBetween>
                  }
                >
                  {selectedSkillDetails.skillName}
                </Header>
              }
            >
              <SpaceBetween size="m">
                <KeyValuePairs
                  columns={1}
                  items={[
                    {
                      label: 'Agent',
                      value: (
                        <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                          <Icon name="settings" />
                          <Box variant="strong">{selectedSkillDetails.agentName}</Box>
                        </SpaceBetween>
                      )
                    },
                    {
                      label: 'Skill Name',
                      value: <Box variant="code">{selectedSkillDetails.skillData?.name || selectedSkillDetails.skillName}</Box>
                    },
                    {
                      label: 'Skill ID',
                      value: selectedSkillDetails.skillData?.id ? (
                        <Box variant="code">{selectedSkillDetails.skillData.id}</Box>
                      ) : (
                        <Box variant="small" color="text-body-secondary">Not available</Box>
                      )
                    },
                    {
                      label: 'Description',
                      value: selectedSkillDetails.skillData?.description ? (
                        <Box variant="p">{selectedSkillDetails.skillData.description}</Box>
                      ) : (
                        <Box variant="small" color="text-body-secondary">No description available</Box>
                      )
                    }
                  ]}
                />

                {/* Additional skill metadata */}
                {typeof selectedSkillDetails.skillData === 'object' && selectedSkillDetails.skillData && (
                  <Alert type="info" header="Skill Metadata">
                    <SpaceBetween size="s">
                      <Box variant="small">
                        <Box variant="strong">Data Source:</Box> Live agent card API
                      </Box>
                      <Box variant="small">
                        <Box variant="strong">Last Updated:</Box> {new Date().toLocaleString()}
                      </Box>
                      {Object.keys(selectedSkillDetails.skillData).filter(key => 
                        !['name', 'id', 'description'].includes(key)
                      ).length > 0 && (
                        <Box variant="small">
                          <Box variant="strong">Additional Properties:</Box> {
                            Object.keys(selectedSkillDetails.skillData)
                              .filter(key => !['name', 'id', 'description'].includes(key))
                              .join(', ')
                          }
                        </Box>
                      )}
                    </SpaceBetween>
                  </Alert>
                )}

                {/* Raw data for debugging */}
                <Container
                  header={
                    <Header variant="h3" description="Raw skill data from agent card API">
                      Technical Details
                    </Header>
                  }
                >
                  <Box variant="code" display="block">
                    <pre style={{ fontSize: '12px', whiteSpace: 'pre-wrap' }}>
                      {JSON.stringify(selectedSkillDetails.skillData, null, 2)}
                    </pre>
                  </Box>
                </Container>
              </SpaceBetween>
            </Container>
          </SpaceBetween>
        </Modal>
      )}
    </Modal>
  );
};

export default AgentMapping;
