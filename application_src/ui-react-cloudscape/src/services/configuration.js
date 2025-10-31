import apiClient from './apiClient.js';

class ConfigurationService {
  constructor() {
    // Use authenticated API client
    this.api = apiClient.getInstance();
    
    // In production, the backend serves the React app, so use relative URLs
    // In development, use the explicit backend URL
    const isProduction = process.env.NODE_ENV === 'production';
    this.backendUrl = isProduction ? '' : (process.env.REACT_APP_BACKEND_URL || 'http://localhost:3001');
  }

  async listAvailableAgents() {
    try {
      const response = await this.api.get('/api/config/agents');
      return response.data.agents || [];
    } catch (error) {throw new Error(`Failed to load agents: ${error.message}`);
    }
  }

  async loadAgentConfig(agentName) {
    try {
      const response = await this.api.get(`/api/config/agent/${agentName}`);
      return response.data;
    } catch (error) {throw new Error(`Failed to load agent config: ${error.message}`);
    }
  }

  async saveAgentConfig(configData) {
    try {
      
      // Check for malformed field names and log them
      Object.keys(configData).forEach(key => {
        if (key.includes('[object Object]')) {
            }
      });
      
      // Step 1: Save the configuration to SSM
      const response = await this.api.post('/api/config/save', configData);
      // Step 2: Automatically refresh the specific agent instances using the new configuration
      let agentRefreshResult;
      try {
        const refreshResponse = await this.api.post(`/api/config/refresh-agent/${configData.agent_name}`);
        agentRefreshResult = {
          success: true,
          message: refreshResponse.data.message,
          summary: refreshResponse.data.summary,
          status: refreshResponse.data.status
        };
      } catch (refreshError) {agentRefreshResult = {
          success: false,
          message: `Failed to refresh agent instances: ${refreshError.response?.data?.detail || refreshError.message}`,
          error: refreshError.message,
          status: "error"
        };
      }
      
      // Step 3: Also refresh supervisor agent cache for immediate availability
      let supervisorRefreshResult;
      try {
        supervisorRefreshResult = await this.refreshSupervisorAgentCache();
      } catch (supervisorError) {supervisorRefreshResult = {
          success: false,
          message: `Failed to refresh supervisor cache: ${supervisorError.message}`,
          error: supervisorError.message
        };
      }
      
      // Return comprehensive result including refresh operations
      return {
        ...response.data,
        agentRefresh: agentRefreshResult,
        supervisorRefresh: supervisorRefreshResult,
        refreshOperationsCompleted: true
      };
      
    } catch (error) {throw new Error(`Failed to save configuration: ${error.message}`);
    }
  }

  async sendChatToAgent(prompt, userId, agentName = 'qa_agent') {
    try {
      const response = await this.api.post('/api/agent/chat-sync', {
        prompt,
        user_id: userId,
        agent_name: agentName
      });
      
      return response.data.response;
    } catch (error) {throw new Error(`Failed to get response from agent: ${error.message}`);
    }
  }

  async sendChatToAgentStreaming(prompt, userId, agentName = 'qa_agent') {
    try {
      const response = await this.api.post('/api/agent/chat', {
        prompt,
        user_id: userId,
        agent_name: agentName
      }, {
        responseType: 'stream'
      });
      
      return response.data;
    } catch (error) {throw new Error(`Failed to get streaming response from agent: ${error.message}`);
    }
  }

  async sendChatToSupervisor(prompt) {
    try {
      const response = await this.api.post('/api/agent/chat', {
        prompt
      }, {
        responseType: 'stream'
      });
      
      // For now, we'll collect the response as text
      // In a real streaming implementation, you'd handle this differently
      let completeResponse = '';
      
      return new Promise((resolve, reject) => {
        response.data.on('data', (chunk) => {
          completeResponse += chunk.toString();
        });
        
        response.data.on('end', () => {
          resolve(completeResponse);
        });
        
        response.data.on('error', (error) => {
          reject(error);
        });
      });
      
    } catch (error) {throw new Error(`Failed to get response from supervisor agent: ${error.message}`);
    }
  }

  // Browser-compatible streaming method with real-time callbacks (better UX)
  async sendChatToSupervisorSimple(prompt, userId = "default_user", onStreamChunk = null) {
    try {// Use authenticated fetch API for proper streaming support with JWT tokens
      const response = await apiClient.authenticatedFetch('/api/agent/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/plain',
        },
        body: JSON.stringify({
          prompt: prompt,
          user_id: userId,
          agent_name: "supervisor_agent"
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      // Handle streaming response using ReadableStream with real-time callbacks
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let completeResponse = '';
      let lastChunkTime = Date.now();
      
      try {
        while (true) {
          const { done, value } = await reader.read();
          
          if (done) {
            break;
          }
          
          const chunkText = decoder.decode(value, { stream: true });
          completeResponse += chunkText;
          lastChunkTime = Date.now();
          
          // Call real-time callback with chunk for UI preview
          if (onStreamChunk && chunkText) {
            try {
              onStreamChunk(chunkText, completeResponse);
            } catch (callbackError) {}
          }// Check for timeout
          if (Date.now() - lastChunkTime > 30000) { // 30 seconds without chunksbreak;
          }
        }return completeResponse || 'No response received';
        
      } finally {
        reader.releaseLock();
      }

    } catch (error) {// Fallback to sync if streaming fails
      try {
        const syncResponse = await this.api.post('/api/agent/chat-sync', {
          prompt: prompt,
          user_id: userId,
          agent_name: "supervisor_agent"
        });
        return syncResponse.data.response;
      } catch (syncError) {throw new Error(`Failed to get response from supervisor agent: ${error.message}`);
      }
    }
  }

  // Version that returns a streaming iterator for real-time UI updates
  async * sendChatToSupervisorStreaming(prompt, userId = "default_user") {
    try {// Use authenticated fetch API for proper streaming support with JWT tokens
      const response = await apiClient.authenticatedFetch('/api/agent/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/plain',
        },
        body: JSON.stringify({
          prompt: prompt,
          user_id: userId,
          agent_name: "supervisor_agent"
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      // Handle streaming response using ReadableStream with generator
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let completeResponse = '';
      let lastChunkTime = Date.now();
      
      try {
        while (true) {
          const { done, value } = await reader.read();
          
          if (done) {
            break;
          }
          
          const chunkText = decoder.decode(value, { stream: true });
          completeResponse += chunkText;
          lastChunkTime = Date.now();
          
          // Yield chunk for real-time UI updates
          if (chunkText) {
            yield {
              chunk: chunkText,
              complete: completeResponse,
              timestamp: new Date().toLocaleTimeString()
            };
          }// Check for timeout
          if (Date.now() - lastChunkTime > 30000) { // 30 seconds without chunksbreak;
          }
        }
        
        // Yield final complete response
        yield {
          chunk: null,
          complete: completeResponse,
          timestamp: new Date().toLocaleTimeString(),
          final: true
        };
        
      } finally {
        reader.releaseLock();
      }

    } catch (error) {// Yield error
      yield {
        chunk: null,
        complete: `Error: ${error.message}`,
        timestamp: new Date().toLocaleTimeString(),
        error: true
      };
    }
  }

  // Keep sync method available for specific use cases
  async sendChatToSupervisorSync(prompt) {
    try {const response = await this.api.post('/api/agent/chat-sync', {
        prompt: prompt,
        user_id: "default_user",
        agent_name: "supervisor_agent"
      });return response.data.response;
    } catch (error) {throw new Error(`Failed to get response from supervisor agent: ${error.message}`);
    }
  }

  async createAgent(agentData) {
    try {
      // Call through backend proxy to config API /save endpoint
      const response = await this.api.post('/api/config/save', agentData);
      return response.data;
    } catch (error) {
      // Handle 422 validation errors with detailed messages
      if (error.response?.status === 422) {
        const validationError = error.response?.data?.detail || error.response?.data?.message || 'Validation failed';
        throw new Error(`Validation error: ${validationError}`);
      }
      
      // Handle other HTTP errors
      if (error.response?.data) {
        const errorMessage = error.response.data.detail || error.response.data.error || error.response.data.message || error.message;
        throw new Error(`Failed to create agent: ${errorMessage}`);
      }
      
      throw new Error(`Failed to create agent: ${error.message}`);
    }
  }

  // Form schema methods for dynamic form generation (via backend proxy)
  async getFormSchema(componentType, providerName = null) {
    try {
      const endpoint = providerName 
        ? `/api/form-schema/providers/${componentType}/${providerName}`
        : `/api/form-schema/components/${componentType}`;
        
      const response = await this.api.get(endpoint);
      return response.data;
    } catch (error) {throw new Error(`Failed to load form schema: ${error.message}`);
    }
  }

  async getAvailableComponents() {
    try {
      const response = await this.api.get('/api/form-schema/components');
      return response.data;
    } catch (error) {throw new Error(`Failed to load available components: ${error.message}`);
    }
  }

  async getComponentProviders(componentType) {
    try {
      const response = await this.api.get(`/api/form-schema/providers/${componentType}`);
      // API returns {provider_name: ProviderFormSchema, ...}
      // Convert to array format expected by frontend
      const providers = Object.keys(response.data).map(providerName => ({
        name: providerName,
        display_name: response.data[providerName].provider_label,
        description: response.data[providerName].description
      }));
      return { providers };
    } catch (error) {throw new Error(`Failed to load providers: ${error.message}`);
    }
  }

  // System prompts API methods
  async getAvailableSystemPrompts(agentName) {
    try {
      const response = await this.api.get(`/api/config/system-prompts/available/${agentName}`);
      return response.data;
    } catch (error) {return { prompts: [] };
    }
  }

  async getSystemPromptContent(agentName, promptName) {
    try {
      const response = await this.api.get(`/api/config/system-prompts/content/${agentName}/${promptName}`);
      return response.data;
    } catch (error) {throw new Error(`Failed to load prompt content: ${error.message}`);
    }
  }

  async getGlobalPromptTemplates() {
    try {
      const response = await this.api.get('/api/config/system-prompts/templates');
      return response.data;
    } catch (error) {return { templates: {} };
    }
  }

  async getAllSystemPromptsAcrossAgents() {
    try {
      const response = await this.api.get('/api/config/system-prompts/all-across-agents');
      return response.data;
    } catch (error) {return { prompts_by_agent: {}, total_prompts: 0 };
    }
  }

  async createSystemPrompt(agentName, promptName, promptContent) {
    try {
      const response = await this.api.post(`/api/config/system-prompts/create/${agentName}`, {
        prompt_name: promptName,
        prompt_content: promptContent
      });
      return response.data;
    } catch (error) {throw new Error(`Failed to create prompt: ${error.message}`);
    }
  }

  // Tool Management API methods for ToolManager component
  async getToolCategories() {
    try {
      const response = await this.api.get('/api/form-schema/tools/categories');
      return response.data;
    } catch (error) {throw new Error(`Failed to load tool categories: ${error.message}`);
    }
  }

  async getAvailableToolsByCategory(categoryName) {
    try {
      const response = await this.api.get(`/api/form-schema/tools/${categoryName}/available`);
      return response.data;
    } catch (error) {throw new Error(`Failed to load available tools: ${error.message}`);
    }
  }

  async getToolSchema(category, toolName) {
    try {
      const response = await this.api.get(`/api/form-schema/tools/${category}/${toolName}`);
      return response.data;
    } catch (error) {throw new Error(`Failed to load tool schema: ${error.message}`);
    }
  }

  async validateToolConfiguration(toolConfig) {
    try {
      const response = await this.api.post('/api/form-schema/tools/validate', toolConfig);
      return response.data;
    } catch (error) {throw new Error(`Failed to validate tool configuration: ${error.message}`);
    }
  }

  // Agent Discovery API methods
  async discoverServices() {
    try {
      const response = await this.api.get('/api/config/discover');
      // The API returns a list of service URLs
      return response.data || [];
    } catch (error) {throw new Error(`Failed to discover services: ${error.message}`);
    }
  }

  async getAgentMapping() {
    try {
      const response = await this.api.get('/api/config/agent-mapping');
      
      // The API returns the full agent mapping response with detailed agent information
      return response.data || { agent_mapping: {}, summary: {} };
    } catch (error) {throw new Error(`Failed to get agent mapping: ${error.message}`);
    }
  }

  async refreshSupervisorAgentCache() {
    try {
      // Use proxy endpoint instead of direct calls
      const response = await this.api.post('/api/deployment/refresh-agent-urls');
      return {
        success: true,
        message: 'Supervisor agent cache refreshed successfully via proxy',
        responseData: response.data
      };
    } catch (error) {return {
        success: false,
        message: `Failed to refresh supervisor cache via proxy: ${error.response?.data?.error || error.message}`,
        error: error.message
      };
    }
  }

  async reloadAgentConfiguration(agentName) {
    try {
      // Step 1: Call the Configuration API's /config/load endpoint directly via proxy
      const response = await this.api.post('/api/config/load', {
        agent_name: agentName
      });
      // Step 2: Refresh supervisor agent cache so changes are immediately available
      let supervisorRefreshResult;
      try {
        supervisorRefreshResult = await this.refreshSupervisorAgentCache();
      } catch (refreshError) {supervisorRefreshResult = {
          success: false,
          message: `Failed to refresh supervisor cache: ${refreshError.message}`,
          error: refreshError.message
        };
      }
      
      return {
        success: true,
        message: `Agent '${agentName}' configuration loaded successfully`,
        agentData: response.data,
        supervisorCacheRefresh: supervisorRefreshResult
      };
    } catch (error) {if (error.response?.status === 404) {
        throw new Error(`Agent '${agentName}' configuration not found in SSM Parameter Store`);
      }
      
      throw new Error(`Failed to reload agent configuration: ${error.response?.data?.error || error.message}`);
    }
  }

  async getAgentCard(agentUrl) {
    try {
      // URL encode the agent URL for the path parameter
      const encodedUrl = encodeURIComponent(agentUrl);
      const response = await this.api.get(`/api/discover/agent-card/${encodedUrl}`);
      return response.data;
    } catch (error) {throw new Error(`Failed to fetch agent card: ${error.response?.data?.detail || error.message}`);
    }
  }

  // Agent Deletion Methods
  async deleteAgentConfiguration(agentName) {
    try {
      const response = await this.api.delete(`/api/config/delete/${agentName}`);
      return response.data;
    } catch (error) {throw new Error(`Failed to delete agent configuration: ${error.response?.data?.detail || error.message}`);
    }
  }

  async deleteAgentComplete(agentName, includeInfrastructure = true) {
    try {const response = await this.api.delete(`/api/config/delete-complete/${agentName}`, {
        params: {
          include_infrastructure: includeInfrastructure
        }
      });
      return response.data;
    } catch (error) {throw new Error(`Failed to delete agent completely: ${error.response?.data?.detail || error.message}`);
    }
  }

  async getDeletionStatus(agentName) {
    try {
      // Check if agent configuration still exists
      let configExists = true;
      try {
        await this.loadAgentConfig(agentName);
      } catch (error) {
        if (error.message.includes('not found') || error.message.includes('404')) {
          configExists = false;
        }
      }
      
      return {
        agent_name: agentName,
        config_exists: configExists,
        timestamp: new Date().toISOString()
      };
    } catch (error) {throw new Error(`Failed to check deletion status: ${error.message}`);
    }
  }

  // Supervisor Agent Configuration Methods
  async loadSupervisorConfig() {
    try {
      // Use the standard agent config endpoint for supervisor
      const response = await this.api.get('/api/config/agent/supervisor_agent');
      return response.data;
    } catch (error) {throw new Error(`Failed to load supervisor configuration: ${error.message}`);
    }
  }

  async saveSupervisorConfig(configData) {
    try {
      // Save supervisor configuration using the standard save endpoint
      // The agent_name should already be set to 'supervisor_agent'
      const response = await this.api.post('/api/config/save', configData);
      
      // Refresh supervisor configuration to pick up changes
      try {
        await this.refreshSupervisorConfig();
      } catch (refreshError) {}
      return response.data;
    } catch (error) {throw new Error(`Failed to save supervisor configuration: ${error.message}`);
    }
  }

  async refreshSupervisorConfig() {
    try {
      // Use the standard agent refresh endpoint for supervisor
      const response = await this.api.post('/api/config/refresh-agent/supervisor_agent');
      return response.data;
    } catch (error) {throw new Error(`Failed to refresh supervisor configuration: ${error.message}`);
    }
  }

  async getSupervisorSystemPrompts() {
    try {
      // Use the standard system prompts API for supervisor agent
      const response = await this.getAvailableSystemPrompts('supervisor_agent');
      
      return response;
    } catch (error) {return { prompts: [] };
    }
  }

  async isSupervisorAgent(agentName) {
    return agentName === 'supervisor_agent' || agentName === 'supervisor';
  }

}

export default new ConfigurationService();
