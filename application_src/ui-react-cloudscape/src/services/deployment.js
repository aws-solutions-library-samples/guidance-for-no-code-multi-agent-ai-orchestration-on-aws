/**
 * Deployment Service
 * 
 * Handles dynamic agent deployment through the Configuration API
 * with status polling and agent URL refresh functionality.
 */

import apiClient from './apiClient.js';

class DeploymentService {
  constructor() {
    // Use authenticated API client
    this.api = apiClient.getInstance();
    
    // In production, the backend serves the React app, so use relative URLs
    // In development, use the explicit backend URL
    const isProduction = process.env.NODE_ENV === 'production';
    this.backendUrl = isProduction ? '' : (process.env.REACT_APP_BACKEND_URL || 'http://localhost:3001');
    this.baseURL = `${this.backendUrl}/api/deployment`;
    this.maxPollingTime = 10 * 60 * 1000; // 10 minutes in milliseconds
    this.pollingInterval = 10 * 1000; // 10 seconds between polls
  }

  /**
   * Create a new agent stack deployment
   * @param {Object} agentConfig - Complete agent configuration object
   * @returns {Promise<Object>} Deployment response with stack name and deployment ID
   */
  async createAgentStack(agentConfig) {
    try {
      const response = await this.api.post('/api/deployment/create-agent', agentConfig, {
        timeout: 600000 // 10 minutes timeout
      });

      return response.data;
    } catch (error) {
      throw new Error(
        error.response?.data?.detail || 
        error.response?.data?.details || 
        error.response?.data?.error || 
        'Failed to create agent stack'
      );
    }
  }

  /**
   * Get the status of a specific stack deployment
   * @param {string} agentName - The name of the agent (not full stack name)
   * @returns {Promise<Object>} Stack status information
   */
  async getStackStatus(agentName) {
    try {
      const response = await this.api.get(`/api/deployment/stack-status/${agentName}`, {
        timeout: 30000 // 30 seconds timeout
      });

      return response.data;
    } catch (error) {
      throw new Error(
        error.response?.data?.details || 
        error.response?.data?.error || 
        'Failed to get stack status'
      );
    }
  }

  /**
   * Refresh agent URLs in the supervisor agent
   * @returns {Promise<Object>} Refresh response
   */
  async refreshAgentUrls() {
    try {
      const response = await this.api.post('/api/deployment/refresh-agent-urls', {}, {
        timeout: 30000 // 30 seconds timeout
      });

      return response.data;
    } catch (error) {
      throw new Error(
        error.response?.data?.details || 
        error.response?.data?.error || 
        'Failed to refresh agent URLs'
      );
    }
  }

  /**
   * Poll stack status with timeout and progress callbacks
   * @param {string} stackName - The name of the stack to monitor
   * @param {Function} onProgress - Callback for progress updates
   * @param {Function} onStatusChange - Callback for status changes
   * @returns {Promise<Object>} Final stack status
   */
  async pollStackStatus(stackName, onProgress = null, onStatusChange = null) {
    const startTime = Date.now();
    let lastStatus = null;

    return new Promise((resolve, reject) => {
      const poll = async () => {
        const elapsedTime = Date.now() - startTime;

        // Check if we've exceeded the maximum polling time
        if (elapsedTime >= this.maxPollingTime) {
          const timeoutError = new Error(`Deployment timeout after ${this.maxPollingTime / 1000} seconds`);
          timeoutError.code = 'DEPLOYMENT_TIMEOUT';
          reject(timeoutError);
          return;
        }

        try {
          const status = await this.getStackStatus(stackName);
          
          // Call progress callback with elapsed time
          if (onProgress) {
            const progressPercentage = Math.min((elapsedTime / this.maxPollingTime) * 100, 95);
            onProgress({
              elapsedTime,
              remainingTime: this.maxPollingTime - elapsedTime,
              progressPercentage,
              status: status.status
            });
          }

          // Check if status changed
          if (status.status !== lastStatus && onStatusChange) {
            onStatusChange(status);
            lastStatus = status.status;
          }

          // Check for completion states
          if (status.status === 'CREATE_COMPLETE' || status.status === 'UPDATE_COMPLETE') {
            resolve(status);
            return;
          }

          // Check for failure states
          if (status.status && (
            status.status.includes('FAILED') || 
            status.status.includes('ROLLBACK') ||
            status.status === 'DELETE_COMPLETE'
          )) {
            const error = new Error(`Stack deployment failed with status: ${status.status}`);
            error.code = 'DEPLOYMENT_FAILED';
            error.status = status;
            reject(error);
            return;
          }

          // Continue polling for in-progress states
          if (status.status && (
            status.status.includes('IN_PROGRESS') || 
            status.status.includes('PENDING') ||
            status.status === 'CREATE_IN_PROGRESS' ||
            status.status === 'UPDATE_IN_PROGRESS'
          )) {
            setTimeout(poll, this.pollingInterval);
            return;
          }

          // Unknown status, continue polling
          setTimeout(poll, this.pollingInterval);

        } catch (error) {
          // For network errors, continue polling unless we've timed out
          if (elapsedTime < this.maxPollingTime) {
            setTimeout(poll, this.pollingInterval);
          } else {
            reject(error);
          }
        }
      };

      // Start polling immediately
      poll();
    });
  }

  /**
   * Complete agent deployment workflow
   * @param {string} agentName - The name of the new agent
   * @param {Object} callbacks - Callback functions for different stages
   * @returns {Promise<Object>} Final deployment result
   */
  async deployAgent(agentName, callbacks = {}) {
    const {
      onDeploymentStart = null,
      onProgress = null,
      onStatusChange = null,
      onDeploymentComplete = null,
      onRefreshStart = null,
      onRefreshComplete = null,
      onError = null
    } = callbacks;

    try {
      // Step 1: Initiate deployment
      if (onDeploymentStart) {
        onDeploymentStart({ agentName, stage: 'initiating' });
      }

      const deploymentResult = await this.createAgentStack({ new_agent_name: agentName });
      const stackName = deploymentResult.stack_name;

      // Step 2: Poll for completion (use agent name, not full stack name)
      const finalStatus = await this.pollStackStatus(
        agentName,
        onProgress,
        onStatusChange
      );

      if (onDeploymentComplete) {
        onDeploymentComplete({ 
          agentName, 
          stackName, 
          status: finalStatus,
          stage: 'deployment_complete'
        });
      }

      // Step 3: Refresh agent URLs
      if (onRefreshStart) {
        onRefreshStart({ agentName, stackName, stage: 'refreshing_urls' });
      }

      await this.refreshAgentUrls();

      if (onRefreshComplete) {
        onRefreshComplete({ 
          agentName, 
          stackName, 
          stage: 'complete'
        });
      }

      return {
        success: true,
        agentName,
        stackName,
        finalStatus,
        message: `Agent ${agentName} deployed successfully`
      };

    } catch (error) {
      if (onError) {
        onError(error);
      }

      throw error;
    }
  }

  /**
   * Format elapsed time for display
   * @param {number} milliseconds - Time in milliseconds
   * @returns {string} Formatted time string
   */
  formatElapsedTime(milliseconds) {
    const seconds = Math.floor(milliseconds / 1000);
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;

    if (minutes > 0) {
      return `${minutes}m ${remainingSeconds}s`;
    }
    return `${seconds}s`;
  }

  /**
   * Get deployment status display information
   * @param {string} status - CloudFormation stack status
   * @returns {Object} Display information with color and description
   */
  getStatusDisplay(status) {
    const statusMap = {
      'CREATE_IN_PROGRESS': { color: 'blue', text: 'Creating...', description: 'Stack resources are being created' },
      'CREATE_COMPLETE': { color: 'green', text: 'Created', description: 'Stack created successfully' },
      'CREATE_FAILED': { color: 'red', text: 'Failed', description: 'Stack creation failed' },
      'UPDATE_IN_PROGRESS': { color: 'blue', text: 'Updating...', description: 'Stack resources are being updated' },
      'UPDATE_COMPLETE': { color: 'green', text: 'Updated', description: 'Stack updated successfully' },
      'UPDATE_FAILED': { color: 'red', text: 'Failed', description: 'Stack update failed' },
      'ROLLBACK_IN_PROGRESS': { color: 'yellow', text: 'Rolling back...', description: 'Rolling back changes' },
      'ROLLBACK_COMPLETE': { color: 'yellow', text: 'Rolled back', description: 'Changes rolled back' },
      'DELETE_IN_PROGRESS': { color: 'red', text: 'Deleting...', description: 'Stack is being deleted' },
      'DELETE_COMPLETE': { color: 'red', text: 'Deleted', description: 'Stack deleted' }
    };

    return statusMap[status] || { 
      color: 'gray', 
      text: status || 'Unknown', 
      description: 'Unknown status' 
    };
  }
}

// Export singleton instance
export default new DeploymentService();
