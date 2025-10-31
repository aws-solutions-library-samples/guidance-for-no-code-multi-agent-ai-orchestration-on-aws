import React, { useState, useEffect } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import ProgressBar from '@cloudscape-design/components/progress-bar';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Button from '@cloudscape-design/components/button';
import Alert from '@cloudscape-design/components/alert';
import deploymentService from '../services/deployment';

const DeploymentStatus = ({ 
  agentName, 
  isDeploying, 
  onDeploymentComplete, 
  onDeploymentError,
  onClose 
}) => {
  const [deploymentStage, setDeploymentStage] = useState('idle');
  const [progress, setProgress] = useState(0);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [currentStatus, setCurrentStatus] = useState('');
  const [statusHistory, setStatusHistory] = useState([]);
  const [error, setError] = useState(null);
  const [deploymentResult, setDeploymentResult] = useState(null);
  const [startTime, setStartTime] = useState(null);
  const [statusCounter, setStatusCounter] = useState(0);
  const [deploymentId, setDeploymentId] = useState(null);

  // Timer for real-time elapsed time updates
  useEffect(() => {
    let interval = null;
    
    if (startTime && (deploymentStage === 'deploying' || deploymentStage === 'refreshing')) {
      interval = setInterval(() => {
        const elapsed = Date.now() - startTime;
        setElapsedTime(elapsed);
      }, 1000);
    }
    
    return () => {
      if (interval) {
        clearInterval(interval);
      }
    };
  }, [startTime, deploymentStage]);

  useEffect(() => {
    if (isDeploying && agentName) {
      startDeployment();
    }
  }, [isDeploying, agentName]);

  const startDeployment = async () => {
    setError(null);
    setProgress(0);
    setElapsedTime(0);
    setStatusHistory([]);
    setStatusCounter(0);
    setDeploymentStage('initiating');
    const now = Date.now();
    setStartTime(now);
    setDeploymentId(`${agentName}-${now.toString().slice(-6)}`); // Fixed deployment ID

    try {
      addStatusToHistory('Checking deployment service availability...', 'info');
      
      const result = await deploymentService.deployAgent(agentName, {
        onDeploymentStart: (data) => {
          setDeploymentStage('deploying');
          addStatusToHistory('Initiating deployment...', 'info');
        },
        
        onProgress: (progressData) => {
          setProgress(progressData.progressPercentage);
          setElapsedTime(progressData.elapsedTime);
          setCurrentStatus(progressData.status);
        },
        
        onStatusChange: (statusData) => {
          const statusDisplay = deploymentService.getStatusDisplay(statusData.status);
          addStatusToHistory(
            `${statusDisplay.text}: ${statusDisplay.description}`,
            statusDisplay.color
          );
        },
        
        onDeploymentComplete: (data) => {
          setDeploymentStage('refreshing');
          addStatusToHistory('Deployment completed successfully!', 'green');
          addStatusToHistory('Refreshing agent URLs...', 'info');
        },
        
        onRefreshStart: (data) => {
          addStatusToHistory('Updating supervisor agent with new agent URLs...', 'info');
        },
        
        onRefreshComplete: (data) => {
          setDeploymentStage('complete');
          setProgress(100);
          addStatusToHistory('Agent deployment completed successfully!', 'green');
          setDeploymentResult(data);
          
          if (onDeploymentComplete) {
            onDeploymentComplete(data);
          }
        },
        
        onError: (error) => {
          setError(error);
          setDeploymentStage('error');
          addStatusToHistory(`Deployment failed: ${error.message}`, 'red');
          
          if (onDeploymentError) {
            onDeploymentError(error);
          }
        }
      });
      
    } catch (error) {
      setError(error);
      setDeploymentStage('error');
      addStatusToHistory(`Deployment failed: ${error.message}`, 'red');
      
      if (onDeploymentError) {
        onDeploymentError(error);
      }
    }
  };

  const addStatusToHistory = (message, type = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    const newEntry = {
      id: `status-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      timestamp,
      message,
      type
    };
    
    setStatusHistory(prevHistory => [...prevHistory, newEntry]);
    setStatusCounter(prev => prev + 1);
  };

  const formatElapsedTime = (milliseconds) => {
    return deploymentService.formatElapsedTime(milliseconds);
  };

  const getStageInfo = () => {
    switch (deploymentStage) {
      case 'idle':
        return { title: 'Ready to Deploy', description: 'Waiting to start deployment...' };
      case 'initiating':
        return { title: 'Starting Deployment', description: 'Initializing agent stack creation...' };
      case 'deploying':
        return { title: 'Deploying Agent', description: 'Creating AWS infrastructure and deploying agent...' };
      case 'refreshing':
        return { title: 'Finalizing Setup', description: 'Updating agent registry and refreshing URLs...' };
      case 'complete':
        return { title: 'Deployment Complete', description: `Agent "${agentName}" is now ready for use!` };
      case 'error':
        return { title: 'Deployment Failed', description: 'An error occurred during deployment.' };
      default:
        return { title: 'Unknown Stage', description: 'Processing...' };
    }
  };

  const getStatusType = () => {
    switch (deploymentStage) {
      case 'complete':
        return 'success';
      case 'error':
        return 'error';
      case 'deploying':
      case 'refreshing':
        return 'in-progress';
      case 'initiating':
        return 'pending';
      default:
        return 'pending';
    }
  };

  const getProgressVariant = () => {
    switch (deploymentStage) {
      case 'complete':
        return 'success';
      case 'error':
        return 'error';
      default:
        return 'standalone';
    }
  };

  const canClose = deploymentStage === 'complete' || deploymentStage === 'error' || deploymentStage === 'idle';
  const stageInfo = getStageInfo();

  if (!isDeploying && deploymentStage === 'idle') {
    return null;
  }

  return (
    <Modal
      visible={isDeploying || deploymentStage !== 'idle'}
      onDismiss={canClose ? onClose : undefined}
      header={stageInfo.title}
      size="large"
      closeAriaLabel="Close deployment status"
      dismissAriaLabel="Close deployment modal"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="s">
            {deploymentStage === 'error' && (
              <Button
                onClick={() => startDeployment()}
                iconName="refresh"
                ariaLabel="Retry agent deployment"
                loading={deploymentStage === 'initiating'}
              >
                Retry Deployment
              </Button>
            )}
            
            {canClose && (
              <Button 
                variant="primary"
                onClick={onClose}
                iconName={deploymentStage === 'complete' ? "status-positive" : "close"}
                ariaLabel={deploymentStage === 'complete' ? "Finish deployment" : "Close deployment status"}
              >
                {deploymentStage === 'complete' ? 'Finish' : 'Close'}
              </Button>
            )}
          </SpaceBetween>
        </Box>
      }
    >
      <SpaceBetween size="l">
        {/* Enhanced Agent Information - AWS Foundation Pattern */}
        <Container
          header={
            <Header 
              variant="h3"
              description={stageInfo.description}
              info={
                <Box variant="small" color="text-body-secondary">
                  Deployment ID: {deploymentId || `${agentName}-pending`}
                </Box>
              }
            >
              Agent: {agentName}
            </Header>
          }
          variant="stacked"
        >
          <SpaceBetween direction="horizontal" size="s" alignItems="center">
            <StatusIndicator 
              type={getStatusType()}
              iconAriaLabel={`Deployment status: ${getStatusType()}`}
            >
              {currentStatus || stageInfo.title}
            </StatusIndicator>
            
            {elapsedTime > 0 && (
              <Box variant="small" color="text-body-secondary">
                Elapsed: {formatElapsedTime(elapsedTime)}
              </Box>
            )}
          </SpaceBetween>
        </Container>

        {/* Enhanced Progress Bar - AWS Foundation Pattern */}
        <Container variant="stacked">
          <SpaceBetween size="s">
            <ProgressBar
              value={progress}
              label={`Deployment Progress: ${Math.round(progress)}%`}
              description={
                elapsedTime > 0 
                  ? `Duration: ${formatElapsedTime(elapsedTime)} • ${statusHistory.length} status updates`
                  : 'Preparing deployment...'
              }
              variant={getProgressVariant()}
              status={deploymentStage === 'error' ? 'error' : deploymentStage === 'complete' ? 'success' : 'in-progress'}
              additionalInfo={deploymentStage === 'complete' ? "Deployment completed successfully" : undefined}
              ariaLabel={`Agent ${agentName} deployment progress`}
            />
            
            {/* Stage Indicators - AWS Foundation Pattern */}
            <SpaceBetween direction="horizontal" size="xs">
              <StatusIndicator 
                type={deploymentStage === 'idle' ? 'pending' : deploymentStage === 'initiating' || deploymentStage === 'deploying' || deploymentStage === 'refreshing' || deploymentStage === 'complete' ? 'success' : 'pending'}
                iconAriaLabel="Infrastructure deployment"
                variant="subtle"
              >
                Infrastructure
              </StatusIndicator>
              <StatusIndicator 
                type={deploymentStage === 'refreshing' || deploymentStage === 'complete' ? 'success' : deploymentStage === 'error' ? 'error' : 'pending'}
                iconAriaLabel="Service registration"
                variant="subtle"
              >
                Registration
              </StatusIndicator>
              <StatusIndicator 
                type={deploymentStage === 'complete' ? 'success' : deploymentStage === 'error' ? 'error' : 'pending'}
                iconAriaLabel="Agent activation"
                variant="subtle"
              >
                Activation
              </StatusIndicator>
            </SpaceBetween>
          </SpaceBetween>
        </Container>

        {/* Enhanced Deployment Log - AWS Foundation Pattern */}
        <Container
          header={
            <Header 
              variant="h3"
              counter={statusHistory.length > 0 ? `(${statusHistory.length})` : undefined}
              description="Real-time deployment activities and status updates"
              info={statusHistory.length > 0 && (
                <Box variant="small" color="text-body-secondary">
                  Last update: {statusHistory[statusHistory.length - 1]?.timestamp}
                </Box>
              )}
            >
              Deployment Log
            </Header>
          }
          variant="default"
        >
          <Box 
            padding="s"
            variant="code"
            style={{ 
              maxHeight: '300px', 
              overflowY: 'auto',
              backgroundColor: '#fafbfc',
              border: '1px solid #e1e4e8',
              borderRadius: '6px'
            }}
          >
            <SpaceBetween size="xs">
              {statusHistory.length === 0 ? (
                <Box 
                  textAlign="center" 
                  padding="m"
                  variant="p" 
                  color="text-body-secondary"
                >
                  <SpaceBetween size="s" alignItems="center">
                    <StatusIndicator type="pending" iconAriaLabel="Waiting">
                      Waiting for deployment to begin...
                    </StatusIndicator>
                    <Box variant="small">
                      Deployment activities will appear here in real-time
                    </Box>
                  </SpaceBetween>
                </Box>
              ) : (
                statusHistory.map(entry => (
                  <Box 
                    key={entry.id}
                    fontSize="body-s"
                    fontFamily="monospace"
                  >
                    <SpaceBetween direction="horizontal" size="s" alignItems="flex-start">
                      <Box variant="small" color="text-body-secondary" style={{ minWidth: '80px' }}>
                        [{entry.timestamp}]
                      </Box>
                      <StatusIndicator 
                        type={entry.type === 'green' ? 'success' : entry.type === 'red' ? 'error' : 'info'}
                        iconAriaLabel={entry.type}
                        variant="subtle"
                      />
                      <Box style={{ flex: 1 }}>{entry.message}</Box>
                    </SpaceBetween>
                  </Box>
                ))
              )}
            </SpaceBetween>
          </Box>
        </Container>

        {/* Enhanced Error Alert - AWS Foundation Error Pattern */}
        {error && (
          <Alert
            type="error"
            header="Deployment Error"
            statusIconAriaLabel="Error"
            dismissible={false}
            action={
              <Button
                onClick={() => {
                  setError(null);
                  setDeploymentStage('idle');
                }}
                iconName="close"
                variant="link"
                ariaLabel="Dismiss error"
              >
                Dismiss
              </Button>
            }
          >
            <SpaceBetween size="m">
              <Box variant="p">
                The deployment process encountered an issue and could not complete successfully.
              </Box>
              <Container variant="stacked">
                <SpaceBetween size="s">
                  <Box>
                    <Box variant="strong">Error Message:</Box> {error.message}
                  </Box>
                  {error.code && (
                    <Box>
                      <Box variant="strong">Error Code:</Box> {error.code}
                    </Box>
                  )}
                  <Box variant="small" color="text-body-secondary">
                    Try retrying the deployment or contact support if the issue persists.
                  </Box>
                </SpaceBetween>
              </Container>
            </SpaceBetween>
          </Alert>
        )}

        {/* Enhanced Success Message - AWS Foundation Success Pattern */}
        {deploymentStage === 'complete' && deploymentResult && (
          <Alert
            type="success"
            header="Deployment Completed Successfully"
            statusIconAriaLabel="Success"
            dismissible={false}
          >
            <SpaceBetween size="m">
              <Box variant="p">
                Agent <Box variant="strong">"{agentName}"</Box> has been successfully deployed and is ready to handle requests.
              </Box>
              <Container variant="stacked">
                <SpaceBetween size="s">
                  {deploymentResult.stackName && (
                    <Box>
                      <Box variant="strong">AWS Stack:</Box> {deploymentResult.stackName}
                    </Box>
                  )}
                  <Box>
                    <Box variant="strong">Deployment Time:</Box> {formatElapsedTime(elapsedTime)}
                  </Box>
                  <Box>
                    <Box variant="strong">Status:</Box> Operational and ready for conversations
                  </Box>
                  <Box variant="small" color="text-body-secondary">
                    You can now start using this agent through the chat interface.
                  </Box>
                </SpaceBetween>
              </Container>
            </SpaceBetween>
          </Alert>
        )}
      </SpaceBetween>
    </Modal>
  );
};

export default DeploymentStatus;
