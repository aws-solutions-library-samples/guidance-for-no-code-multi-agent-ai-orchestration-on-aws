import React, { useState, useEffect } from 'react';
import Modal from '@cloudscape-design/components/modal';
import Wizard from '@cloudscape-design/components/wizard';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Box from '@cloudscape-design/components/box';
import FormField from '@cloudscape-design/components/form-field';
import Input from '@cloudscape-design/components/input';
import Textarea from '@cloudscape-design/components/textarea';
import Select from '@cloudscape-design/components/select';
import Button from '@cloudscape-design/components/button';
import Alert from '@cloudscape-design/components/alert';
import Toggle from '@cloudscape-design/components/toggle';
import Spinner from '@cloudscape-design/components/spinner';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Badge from '@cloudscape-design/components/badge';
import KeyValuePairs from '@cloudscape-design/components/key-value-pairs';
import Icon from '@cloudscape-design/components/icon';
import Link from '@cloudscape-design/components/link';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import HelpPanel from '@cloudscape-design/components/help-panel';
import configService from '../services/configuration';
import DeploymentStatus from './DeploymentStatus';
import ToolManager from './ToolManager';
import MultiSelectModelDropdown from './MultiSelectModelDropdown';
import { helpContent, getHelpBite, getHelpSnack, getHelpMeal } from './HelpContent';

// AWS Foundation Comprehensive Agent Wizard - Complete Issue #2 Solution
const AgentWizard = ({ 
  isOpen, 
  onClose, 
  onAgentCreated, 
  mode = 'create',
  selectedAgent = null
}) => {
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const [agentData, setAgentData] = useState({
    agent_name: '',
    agent_description: '',
    region_name: 'us-east-1'
  });
  
  const [selectedAgentForConfig, setSelectedAgentForConfig] = useState(selectedAgent);
  const [availableAgents, setAvailableAgents] = useState([]);
  const [formSchema, setFormSchema] = useState({});
  const [availableComponents, setAvailableComponents] = useState([]);
  const [providers, setProviders] = useState({});
  const [isLoading, setIsLoading] = useState(true);
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [validationErrors, setValidationErrors] = useState({});

  // System prompts state - Issue #2 System Prompt Templates
  const [systemPrompts, setSystemPrompts] = useState([]);
  const [globalTemplates, setGlobalTemplates] = useState({});
  const [crossAgentPrompts, setCrossAgentPrompts] = useState({});
  const [loadingPrompts, setLoadingPrompts] = useState(false);
  const [promptsLoaded, setPromptsLoaded] = useState(false);

  // Template creation modal state
  const [showCreateTemplateModal, setShowCreateTemplateModal] = useState(false);
  const [showPromptPreviewModal, setShowPromptPreviewModal] = useState(false);
  const [templateCreationData, setTemplateCreationData] = useState({
    name: '',
    description: '',
    content: ''
  });
  const [creatingTemplate, setCreatingTemplate] = useState(false);

  // Deployment state
  const [isDeploying, setIsDeploying] = useState(false);
  const [deployingAgentName, setDeployingAgentName] = useState(null);

  // Help system state
  const [showHelpPanel, setShowHelpPanel] = useState(false);
  const [currentHelpTopic, setCurrentHelpTopic] = useState('getting_started');

  // Steps for comprehensive wizard - Issue #2 Dynamic Form Generation
  const [steps, setSteps] = useState([]);

  // Reset state and load comprehensive data when wizard opens
  useEffect(() => {
    if (isOpen) {
      setActiveStepIndex(0);
      // Initialize with BOTH old and new field name patterns for compatibility
      setAgentData({
        // Old field names for backward compatibility
        agent_name: '',
        agent_description: '',
        region_name: 'us-east-1',
        // New dynamic field names (agent component with basic provider)
        agent_basic_agent_name: '',
        agent_basic_agent_description: '',
        agent_basic_region_name: 'us-east-1',
        agent_basic_system_prompt_name: '',
        agent_basic_system_prompt: ''
      });
      setAvailableAgents([]);
      setSelectedAgentForConfig(selectedAgent);
      setFormSchema({});
      setAvailableComponents([]);
      setProviders({});
      setIsLoading(true);
      setIsCreating(false);
      setError(null);
      setSuccess(false);
      setSteps([]);
      setValidationErrors({});
      setHasUnsavedChanges(false);
      setPromptsLoaded(false); // Reset prompts loaded flag
      
      loadInitialData();
    }
  }, [isOpen, mode, selectedAgent]);

  // Track unsaved changes
  useEffect(() => {
    const hasChanges = Object.values(agentData).some(value => 
      value && value !== '' && value !== 0.7 && value !== 0.9 && value !== 'us-east-1'
    );
    setHasUnsavedChanges(hasChanges);
  }, [agentData]);

  // Load system prompts when agent is selected or when creating new agent - Issue #2 System Prompt Templates
  useEffect(() => {
    // Prevent infinite loops with multiple guards
    if (loadingPrompts || promptsLoaded) return;
    
    const agentName = selectedAgentForConfig;
    if (agentName && mode === 'configure') {
      loadSystemPrompts(agentName);
    } else if (mode === 'create' && !promptsLoaded) {
      loadGlobalTemplatesOnly();
    }
  }, [selectedAgentForConfig, mode, loadingPrompts, promptsLoaded]);

  // Load system prompts functionality - Issue #2 System Prompt Templates
  const loadSystemPrompts = async (agentName) => {
    try {
      setLoadingPrompts(true);
      
      // Try multiple approaches to load templates
      let availablePrompts = [];
      let templates = {};
      
      try {
        // Load available system prompts for the agent
        const promptsResponse = await configService.getAvailableSystemPrompts(agentName);
        availablePrompts = promptsResponse?.prompts || promptsResponse || [];
      } catch (promptError) {
        // Continue with empty array
      }
      
      try {
        // Load global prompt templates 
        const templatesResponse = await configService.getGlobalPromptTemplates();
        templates = templatesResponse?.templates || templatesResponse || {};
        } catch (templateError) {
          // Continue with empty object
        }
      
      try {
        // Load cross-agent system prompts for reusability (in both create and configure modes)
        const crossAgentData = await configService.getAllSystemPromptsAcrossAgents();
        setCrossAgentPrompts(crossAgentData?.prompts_by_agent || {});
        } catch (crossAgentError) {
          setCrossAgentPrompts({});
        }
      
      // Fallback to form schema if other methods fail
      if (Object.keys(templates).length === 0 && availablePrompts.length === 0) {
        try {
          const agentSchema = await configService.getFormSchema('agent');
          const systemPromptField = agentSchema?.providers?.basic?.fields?.find(f => f.name === 'system_prompt_name');
          if (systemPromptField?.options) {
            availablePrompts = systemPromptField.options.map(opt => ({
              name: opt.label || opt.value,
              value: opt.value,
              content: `System prompt template: ${opt.label || opt.value}`
            }));
          }
        } catch (schemaError) {
          // Continue without schema data
        }
      }
      
      // Add default templates if none found
      if (Object.keys(templates).length === 0 && availablePrompts.length === 0) {
        templates = {
          'general_assistant': {
            name: 'General AI Assistant',
            content: 'You are a helpful AI assistant. Provide accurate, helpful, and concise responses to user queries.',
            category: 'General'
          },
          'technical_expert': {
            name: 'Technical Expert',
            content: 'You are a technical expert AI assistant. Provide detailed, accurate technical information and guidance.',
            category: 'Technical'
          },
          'customer_support': {
            name: 'Customer Support',
            content: 'You are a customer support AI assistant. Be helpful, professional, and solution-oriented.',
            category: 'Support'
          }
        };
      }
      
      setSystemPrompts(availablePrompts);
      setGlobalTemplates(templates);
      setPromptsLoaded(true); // Mark as loaded to prevent re-runs
      
    } catch (error) {
      // Provide fallback templates
      setSystemPrompts([]);
      setGlobalTemplates({
        'default': {
          name: 'Default Template',
          content: 'You are a helpful AI assistant.',
          category: 'General'
        }
      });
      setPromptsLoaded(true); // Mark as loaded even on error
    } finally {
      setLoadingPrompts(false);
    }
  };

  const loadGlobalTemplatesOnly = async () => {
    // Prevent duplicate calls
    if (loadingPrompts) return;
    
    try {
      setLoadingPrompts(true);
      
      let templates = {};
      let crossAgentData = {};
      
      try {
        // Load global prompt templates once
        const templatesResponse = await configService.getGlobalPromptTemplates();
        templates = templatesResponse?.templates || templatesResponse || {};
      } catch (templateError) {
        console.log('Template loading error:', templateError);
      }
      
      try {
        // Load cross-agent system prompts once
        const crossAgentResponse = await configService.getAllSystemPromptsAcrossAgents();
        crossAgentData = crossAgentResponse?.prompts_by_agent || {};
      } catch (crossAgentError) {
        console.log('Cross-agent prompts loading error:', crossAgentError);
      }
      
      // Add default templates if none found  
      if (Object.keys(templates).length === 0) {
        templates = {
          'general_assistant': {
            name: 'General AI Assistant',
            content: 'You are a helpful AI assistant.',
            category: 'General'
          }
        };
      }
      
      // Set state only once at the end
      setSystemPrompts([]);
      setGlobalTemplates(templates);
      setCrossAgentPrompts(crossAgentData);
      setPromptsLoaded(true); // Mark as loaded to prevent re-runs
      
    } catch (error) {
      setSystemPrompts([]);
      setGlobalTemplates({
        'default': {
          name: 'Default Template', 
          content: 'You are a helpful AI assistant.',
          category: 'General'
        }
      });
      setCrossAgentPrompts({});
      setPromptsLoaded(true); // Mark as loaded even on error
    } finally {
      setLoadingPrompts(false);
    }
  };

  // Load system prompt content helper
  const loadSystemPromptContent = async (agentName, promptName) => {
    try {
      const content = await configService.getSystemPromptContent(agentName, promptName);
      
      if (content?.prompt_content) {
        // Update the system prompt textarea with the selected content
        const fieldKey = `agent_basic_system_prompt`;
        updateAgentData({ [fieldKey]: content.prompt_content });
      }
      
    } catch (error) {
      // Don't show error - let user manually type prompt
    }
  };

  // Template creation handlers
  const handleCreateTemplate = async () => {
    if (!templateCreationData.name || !templateCreationData.content) {
      setError('Please provide both template name and content');
      return;
    }

    setCreatingTemplate(true);
    try {
      // Get agent name for the template creation
      const agentName = agentData.agent_basic_agent_name || selectedAgentForConfig || 'default';
      
      // Create the template using the API
      await configService.createSystemPrompt(
        agentName,
        templateCreationData.name,
        templateCreationData.content
      );

      // Refresh the system prompts to include the new template
      await loadSystemPrompts(agentName);

      // Set the newly created template as selected
      const fieldKey = `agent_basic_system_prompt_name`;
      const uiSelectionKey = `${fieldKey}_ui_selection`;
      updateAgentData({ 
        [fieldKey]: templateCreationData.name,
        [uiSelectionKey]: templateCreationData.name
      });

      // Auto-load the template content
      const systemPromptKey = `agent_basic_system_prompt`;
      updateAgentData({ [systemPromptKey]: templateCreationData.content });

      // Close modal and reset form
      setShowCreateTemplateModal(false);
      setTemplateCreationData({ name: '', description: '', content: '' });
      
      // Show success message
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);

    } catch (error) {
      setError(`Failed to create template: ${error.message}`);
    } finally {
      setCreatingTemplate(false);
    }
  };

  const handleCloseCreateTemplateModal = () => {
    setShowCreateTemplateModal(false);
    setTemplateCreationData({ name: '', description: '', content: '' });
    setError(null);
  };

  const getSelectedTemplatePreview = () => {
    const fieldKey = 'agent_basic_system_prompt_name';
    const uiSelectionKey = `${fieldKey}_ui_selection`;
    const selectedPrompt = agentData[uiSelectionKey];

    if (!selectedPrompt || selectedPrompt === 'create_new') {
      return null;
    }

    // Check if it's a global template
    if (selectedPrompt.startsWith('template:')) {
      const templateKey = selectedPrompt.replace('template:', '');
      const template = globalTemplates[templateKey];
      return {
        name: template?.name || templateKey,
        description: template?.description || 'Global template',
        content: template?.content || 'No content available',
        source: 'Global Template'
      };
    }

    // Check if it's a cross-agent prompt
    if (selectedPrompt.startsWith('cross:')) {
      const [, sourceAgent, promptName] = selectedPrompt.split(':');
      const agentData = crossAgentPrompts[sourceAgent];
      const prompt = agentData?.prompts.find(p => p.name === promptName);
      return {
        name: prompt?.display_name || promptName,
        description: `From ${sourceAgent}`,
        content: 'Content will be loaded when selected',
        source: `Cross-Agent (${sourceAgent})`
      };
    }

    // Check if it's an agent-specific prompt
    const prompt = systemPrompts.find(p => p.name === selectedPrompt);
    if (prompt) {
      return {
        name: prompt.name,
        description: 'Agent-specific prompt',
        content: 'Content will be loaded when selected',
        source: 'Agent Prompt'
      };
    }

    return null;
  };

  const loadInitialData = async () => {
    try {
      setIsLoading(true);
      setError(null);
      
      // Add timeout wrapper for all async operations
      const withTimeout = (promise, timeoutMs = 10000) => {
        return Promise.race([
          promise,
          new Promise((_, reject) => 
            setTimeout(() => reject(new Error('Operation timed out')), timeoutMs)
          )
        ]);
      };
      
      // Load available agents if in configure mode
      let firstAgent = null;
      if (mode === 'configure') {
        try {
          const agents = await withTimeout(configService.listAvailableAgents(), 5000);
          setAvailableAgents(agents || []);
          
          if (agents && agents.length > 0) {
            firstAgent = selectedAgentForConfig || agents[0];
            setSelectedAgentForConfig(firstAgent);
          }
        } catch (agentError) {
          console.error('Failed to load agents:', agentError);
          setAvailableAgents([]);
        }
      }
      
      // System prompts will be loaded by separate useEffect hook to prevent conflicts
      
      // Get available components - Issue #2 Dynamic Form Generation
      let componentArray = [];
      try {
        const components = await withTimeout(configService.getAvailableComponents(), 5000);
        const componentTypes = Object.keys(components);
        componentArray = componentTypes.map(type => ({
          type: type,
          display_name: type.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
          description: `Configure ${type.replace(/_/g, ' ')} settings`,
          required: type === 'agent' || type === 'models'
        }));
      } catch (componentError) {
        console.error('Failed to load components:', componentError);
        // Use fallback minimal components to allow wizard to function
        componentArray = [
          { type: 'agent', display_name: 'Agent', description: 'Configure agent settings', required: true },
          { type: 'models', display_name: 'Models', description: 'Configure model settings', required: true }
        ];
      }
      
      setAvailableComponents(componentArray);
      
      // Load form schema for each component - Issue #2 Provider-specific Configurations
      const schemaData = {};
      const providerData = {};
      
      // Valid component types that have form schemas - exclude 'agent' as it's handled separately
      const validSchemaComponents = componentArray.filter(comp => comp.type !== 'agent');
      
      // Load schemas in parallel with individual timeouts
      const schemaPromises = validSchemaComponents.map(async (component) => {
        try {
          const componentSchema = await withTimeout(
            configService.getFormSchema(component.type), 
            5000
          );
          
          schemaData[component.type] = componentSchema;
          
          const providersList = Object.keys(componentSchema.providers || {}).map(providerName => {
            const provider = componentSchema.providers[providerName];
            return {
              name: providerName,
              display_name: provider.provider_label || providerName,
              description: provider.description || `${providerName} provider`
            };
          });
          
          providerData[component.type] = providersList;
        } catch (componentError) {
          console.warn(`Failed to load schema for ${component.type}:`, componentError);
          // Provide minimal fallback schema
          schemaData[component.type] = {
            providers: {
              default: {
                provider_label: 'Default',
                description: 'Default provider',
                fields: []
              }
            }
          };
          providerData[component.type] = [{
            name: 'default',
            display_name: 'Default',
            description: 'Default provider'
          }];
        }
      });
      
      // Wait for all schemas with overall timeout
      try {
        await withTimeout(Promise.allSettled(schemaPromises), 15000);
      } catch (timeoutError) {
        console.warn('Schema loading timed out, continuing with partial data');
      }
      
      setFormSchema(schemaData);
      setProviders(providerData);
      
      // Generate dynamic steps
      const dynamicSteps = [];
      
      if (mode === 'configure') {
        dynamicSteps.push({
          id: 'agent_selection',
          title: 'Select Agent',
          subtitle: 'Choose an existing agent to configure',
          required: true
        });
      }
      
      // Add ALL components dynamically - Issue #2 Complete Coverage
      componentArray.forEach((component) => {
        dynamicSteps.push({
          id: component.type,
          title: component.display_name,
          subtitle: component.description,
          required: component.required
        });
      });
      
      // Add review step
      dynamicSteps.push({
        id: 'review',
        title: mode === 'create' ? 'Review & Create' : 'Review & Save',
        subtitle: 'Review configuration and create/save agent',
        required: true
      });
      
      setSteps(dynamicSteps);
      
      // Auto-load first agent configuration in configure mode
      if (mode === 'configure' && firstAgent) {
        await loadAgentConfiguration(firstAgent);
      }
      
      // Mark initial data as loaded - this will trigger system prompts loading via useEffect
      setPromptsLoaded(false);
      
    } catch (error) {
      setError(`Failed to load data: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  const loadAgentConfiguration = async (agentName) => {
    try {
      setError(null);
      
      const config = await configService.loadAgentConfig(agentName);
      
      const transformedData = {
        // Agent fields
        agent_basic_agent_name: config.agent_name || agentName,
        agent_basic_agent_description: config.agent_description || '',
        agent_basic_system_prompt_name: config.system_prompt_name || '',
        agent_basic_system_prompt: config.system_prompt || '',
        agent_basic_region_name: config.region_name || 'us-east-1',
        
        // Backward compatibility
        agent_name: config.agent_name || agentName,
        agent_description: config.agent_description || '',
        system_prompt_name: config.system_prompt_name || '',
        system_prompt: config.system_prompt || '',
        region_name: config.region_name || 'us-east-1'
      };
      
      // Map model configuration
      if (config.model_id !== undefined) {
        transformedData['models_bedrock_model_id'] = config.model_id;
      }
      if (config.embedding_model_id !== undefined) {
        transformedData['models_bedrock_embedding_model_id'] = config.embedding_model_id;
      }
      if (config.temperature !== undefined) {
        transformedData['models_bedrock_temperature'] = config.temperature;
      }
      if (config.top_p !== undefined) {
        transformedData['models_bedrock_top_p'] = config.top_p;
      }
      
      // Handle model_ids array for multi-select dropdown - Issue #2
      if (config.model_ids && Array.isArray(config.model_ids)) {
        transformedData['models_bedrock_model_ids'] = config.model_ids;
      }
      
      transformedData['models_enabled'] = true;
      transformedData['models_provider'] = 'bedrock';
      
      // Handle other components
      ['tools', 'knowledge_base', 'memory', 'observability', 'guardrail'].forEach(componentType => {
        const enabledValue = config[componentType];
        
        if (componentType === 'tools' && Array.isArray(enabledValue)) {
          transformedData[`${componentType}_enabled`] = enabledValue.length > 0;
        } else {
          transformedData[`${componentType}_enabled`] = 
            enabledValue === 'True' || enabledValue === true || enabledValue === 'enabled';
        }
        
        if (config[`${componentType}_provider`]) {
          transformedData[`${componentType}_provider`] = config[`${componentType}_provider`];
        }
      });
      
      setAgentData(transformedData);
      
    } catch (error) {
      setError(`Failed to load agent config: ${error.message}`);
    }
  };

  const updateAgentData = (updates) => {
    setAgentData(prev => {
      const newData = { ...prev, ...updates };
      
      // Synchronize old and new field name patterns for backward compatibility
      // When new pattern is updated, sync to old pattern
      if (updates.agent_basic_agent_name !== undefined) {
        newData.agent_name = updates.agent_basic_agent_name;
      }
      if (updates.agent_basic_agent_description !== undefined) {
        newData.agent_description = updates.agent_basic_agent_description;
      }
      if (updates.agent_basic_region_name !== undefined) {
        newData.region_name = updates.agent_basic_region_name;
      }
      if (updates.agent_basic_system_prompt_name !== undefined) {
        newData.system_prompt_name = updates.agent_basic_system_prompt_name;
      }
      if (updates.agent_basic_system_prompt !== undefined) {
        newData.system_prompt = updates.agent_basic_system_prompt;
      }
      
      // When old pattern is updated, sync to new pattern
      if (updates.agent_name !== undefined) {
        newData.agent_basic_agent_name = updates.agent_name;
      }
      if (updates.agent_description !== undefined) {
        newData.agent_basic_agent_description = updates.agent_description;
      }
      if (updates.region_name !== undefined) {
        newData.agent_basic_region_name = updates.region_name;
      }
      if (updates.system_prompt_name !== undefined) {
        newData.agent_basic_system_prompt_name = updates.system_prompt_name;
      }
      if (updates.system_prompt !== undefined) {
        newData.agent_basic_system_prompt = updates.system_prompt;
      }
      
      return newData;
    });
  };

  const validateStep = (stepIndex) => {
    const errors = {};
    
    if (!steps || steps.length === 0 || stepIndex >= steps.length) {
      return true;
    }
    
    const step = steps[stepIndex];
    
    switch (step.id) {
      case 'agent_selection':
        if (!selectedAgentForConfig) {
          errors.selectedAgent = 'Agent selection is required';
        }
        break;
        
      case 'agent':
        if (mode === 'create' && !agentData.agent_basic_agent_name?.trim()) {
          errors.agent_name = 'Agent name is required';
        }
        if (!agentData.agent_basic_agent_description?.trim()) {
          errors.agent_description = 'Agent description is required';
        }
        break;
        
      case 'models':
        // Check multiple possible model fields to ensure proper validation
        const hasModelId = agentData.models_bedrock_model_id && agentData.models_bedrock_model_id.trim();
        const hasModelFromProvider = (() => {
          const modelsProvider = agentData['models_provider'] || 'bedrock';
          const modelsData = extractProviderConfig('models', modelsProvider);
          return modelsData.model_id && modelsData.model_id.trim();
        })();
        
        if (!hasModelId && !hasModelFromProvider) {
          errors.model_id = 'Please select a primary model';
        }
        break;
    }
    
    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleNavigate = ({ detail }) => {
    const { requestedStepIndex } = detail;
    
    if (requestedStepIndex > activeStepIndex) {
      if (!validateStep(activeStepIndex)) {
        return;
      }
    }
    
    setActiveStepIndex(requestedStepIndex);
  };

  const handleSubmit = async () => {
    if (!validateStep(activeStepIndex)) {
      return;
    }

    setIsCreating(true);
    setError(null);

    try {
      if (mode === 'create') {
        await handleCreateAgent();
      } else {
        await handleSaveConfiguration();
      }
    } catch (error) {
      setError(`Failed to ${mode} agent: ${error.message}`);
    } finally {
      setIsCreating(false);
    }
  };

  // Helper function to extract provider configuration from form data
  const extractProviderConfig = (componentType, providerName) => {
    const config = {};
    const prefix = `${componentType}_${providerName}_`;
    
    // Extract all fields that match the component and provider
    Object.keys(agentData).forEach(key => {
      if (key.startsWith(prefix)) {
        const fieldName = key.replace(prefix, '');
        const fieldValue = agentData[key];
        config[fieldName] = fieldValue;
      }
    });
    
    return config;
  };

  // Helper function to extract MCP configuration for root-level agent config
  const getMCPConfig = () => {
    const mcpConfig = {
      mcp_enabled: false,
      mcp_servers: ""
    };
    // Check if tools component is enabled and uses MCP provider
    const toolsEnabled = agentData['tools_enabled'];
    const selectedProvider = agentData['tools_provider'];
    const mcpEnabled = agentData['tools_mcp_enabled'];
    const mcpServersField = agentData['tools_mcp_servers'];
    if (toolsEnabled && selectedProvider === 'mcp' && mcpEnabled && mcpServersField) {
      try {
        // Parse and transform the MCP servers from nested format to flat format
        const mcpServers = JSON.parse(mcpServersField);
        if (Array.isArray(mcpServers)) {
          const transformedServers = [];
          
          mcpServers.forEach((server, index) => {
            if (typeof server === 'object' && server !== null) {
              const serverKeys = Object.keys(server);
              
              // Handle nested structure: {github: {type: "http", url: "...", headers: {...}}}
              if (serverKeys.length === 1 && !server.name && !server.url) {
                const serverName = serverKeys[0];
                const serverConfig = server[serverName];
                if (serverConfig && typeof serverConfig === 'object' && serverConfig.url) {
                  // Transform to flat structure expected by MCP client
                  const flatServer = {
                    name: serverName,
                    url: serverConfig.url,
                    description: serverConfig.description || `${serverName} MCP server`,
                    auth_type: serverConfig.headers?.Authorization ? 'bearer' : 'none',
                    enabled: true
                  };
                  
                  // Extract bearer token from Authorization header if present
                  if (serverConfig.headers?.Authorization) {
                    const authHeader = serverConfig.headers.Authorization;
                    if (authHeader.startsWith('Bearer ')) {
                      flatServer.auth_token = authHeader.replace('Bearer ', '');
                    } else {
                      flatServer.auth_token = authHeader;
                    }
                  }
                  
                  transformedServers.push(flatServer);
                }
              }
              // Handle flat structure: {name: "github", type: "http", url: "...", headers: {...}}
              else if (server.name && server.url) {
                const flatServer = {
                  name: server.name,
                  url: server.url,
                  description: server.description || `${server.name} MCP server`,
                  auth_type: server.headers?.Authorization ? 'bearer' : 'none',
                  enabled: true
                };
                
                // Extract bearer token from Authorization header if present
                if (server.headers?.Authorization) {
                  const authHeader = server.headers.Authorization;
                  if (authHeader.startsWith('Bearer ')) {
                    flatServer.auth_token = authHeader.replace('Bearer ', '');
                  } else {
                    flatServer.auth_token = authHeader;
                  }
                }
                
                transformedServers.push(flatServer);
              }
            }
          });
          
          if (transformedServers.length > 0) {
            mcpConfig.mcp_enabled = true;
            mcpConfig.mcp_servers = JSON.stringify(transformedServers);
          }
        }
      } catch (error) {}
    }
    return mcpConfig;
  };

  // Helper function to extract tools configuration from form data
  const extractToolsConfig = () => {
    const tools = [];
    
    // Check if tools component is enabled
    const toolsEnabled = agentData['tools_enabled'];
    if (!toolsEnabled) {
      return tools;
    }
    
    // Get selected provider for tools
    const selectedProvider = agentData['tools_provider'];
    if (!selectedProvider) {
      return tools;
    }
    
    // Skip MCP provider - MCP is handled at root config level, not as individual tools
    if (selectedProvider === 'mcp') {
      // MCP configuration will be handled in getMCPConfig() function
      return tools;
    }
    
    // Handle builtin provider
    else if (selectedProvider === 'builtin') {
      // Look for individual builtin tool configurations
      Object.keys(agentData).forEach(key => {
        if (key.startsWith('tools_builtin_') && key.endsWith('_enabled') && agentData[key]) {
          // Extract tool name from key
          const toolName = key.replace('tools_builtin_', '').replace('_enabled', '');
          // Collect all individual config fields for this tool
          const toolConfig = { enabled: 'Yes' };
          Object.keys(agentData).forEach(key => {
            if (key.startsWith(`tools_builtin_${toolName}_`) && !key.endsWith('_enabled')) {
              const configKey = key.replace(`tools_builtin_${toolName}_`, '');
              toolConfig[configKey] = agentData[key];
            }
          });
          // Create tool entry in expected format
          const toolEntry = {
            name: toolName,
            config: toolConfig
          };
          tools.push(toolEntry);
        }
      });
    }
    
    // Handle custom provider
    else if (selectedProvider === 'custom') {
      const customEnabled = agentData['tools_custom_enabled'];
      const toolModulesField = agentData['tools_custom_tool_modules'];
      if (customEnabled && toolModulesField) {
        try {
          // Parse the custom tools JSON from the textarea
          const toolModules = JSON.parse(toolModulesField);
          // Convert custom tools to tools format
          if (Array.isArray(toolModules)) {
            toolModules.forEach((tool, index) => {
              if (tool.name && tool.enabled) {
                const toolConfig = {
                  name: tool.name,
                  type: 'custom',
                  config: tool.config || { enabled: 'Yes' }
                };
                tools.push(toolConfig);
              }
            });
          }
        } catch (error) {
          // Continue without custom tools
        }
      }
    }
    return tools;
  };

  const handleCreateAgent = async () => {
    const agentName = agentData.agent_basic_agent_name || agentData.agent_name;
    
    // Validate agent name is provided
    if (!agentName || !agentName.trim()) {
      throw new Error('Agent name is required');
    }// Transform dynamic form data into the proper AgentConfigRequest format matching expected structure
    const agentConfigRequest = {
      // Basic information - extract from agent component fields
      agent_name: agentName,
      agent_description: agentData.agent_basic_agent_description || agentData.agent_description || `${agentName} agent`,
      region_name: agentData.agent_basic_region_name || agentData.region_name || 'us-east-1',
      
      // System prompt configuration - use actual form data
      system_prompt_name: agentData.agent_basic_system_prompt_name || agentData.system_prompt_name || `${agentName}_system_prompt`,
      system_prompt: agentData.agent_basic_system_prompt || agentData.system_prompt || `You are ${agentName}, ${agentData.agent_basic_agent_description || agentData.agent_description || 'a helpful AI assistant'}`,
      
      // Extract model configuration dynamically from form fields (same as other components)
      ...((() => {
        const modelsConfig = {};
        const modelsProvider = agentData['models_provider'] || 'bedrock';
        const modelsData = extractProviderConfig('models', modelsProvider);
        
        // Map extracted model fields to expected API format - ensure proper types
        modelsConfig.model_id = modelsData.model_id || agentData.models_bedrock_model_id || 'anthropic.claude-3-5-sonnet-20241022-v2:0';
        modelsConfig.judge_model_id = modelsData.judge_model_id || agentData.models_bedrock_judge_model_id || modelsConfig.model_id;
        modelsConfig.embedding_model_id = modelsData.embedding_model_id || agentData.models_bedrock_embedding_model_id || 'amazon.titan-embed-text-v2:0';
        
        // Handle multi-select model IDs for ALL agents
        if (modelsData.model_ids && Array.isArray(modelsData.model_ids)) {
          modelsConfig.model_ids = modelsData.model_ids;
        } else if (agentData.models_bedrock_model_ids && Array.isArray(agentData.models_bedrock_model_ids)) {
          modelsConfig.model_ids = agentData.models_bedrock_model_ids;
        }
        
        // Ensure numeric fields are proper numbers, not empty strings
        modelsConfig.temperature = modelsData.temperature !== undefined && modelsData.temperature !== '' ? 
          Number(modelsData.temperature) : (agentData.models_bedrock_temperature ? Number(agentData.models_bedrock_temperature) : 0.7);
        modelsConfig.top_p = modelsData.top_p !== undefined && modelsData.top_p !== '' ? 
          Number(modelsData.top_p) : (agentData.models_bedrock_top_p ? Number(agentData.models_bedrock_top_p) : 0.9);
        
        return modelsConfig;
      })()),
      
      // Configuration flags - use expected format
      streaming: 'True',
      cache_prompt: 'default',
      cache_tools: 'default',
      
      // Thinking configuration - use expected format
      thinking: {
        type: 'enabled',
        budget_tokens: 4096
      },
      
      // Tools configuration
      tools: extractToolsConfig(),
      
      // MCP configuration at root level - required for MCP integration
      ...getMCPConfig()
    };

    // Only process components that exist in AgentConfigRequest model - skip 'agent', 'models', 'tools'
    const validComponents = availableComponents.filter(component => 
      !['agent', 'models', 'tools'].includes(component.type)
    );
    
    // Dynamically build provider details for valid components
    validComponents.forEach(component => {
      const componentType = component.type;
      const isEnabled = agentData[`${componentType}_enabled`];
      const selectedProvider = agentData[`${componentType}_provider`];
      
      // Set enabled/disabled status
      agentConfigRequest[componentType] = isEnabled ? 'True' : 'False';
      
      // Set provider (always required)
      const componentProviders = providers[componentType] || [];
      const defaultProvider = componentProviders.length > 0 ? componentProviders[0].name : 'default';
      agentConfigRequest[`${componentType}_provider`] = selectedProvider || defaultProvider;
      
      // For knowledge base, always set provider type (required field)
      if (componentType === 'knowledge_base') {
        agentConfigRequest[`${componentType}_provider_type`] = 'custom';
      }
      
      if (isEnabled && selectedProvider) {
        // Build provider details array dynamically
        const providerDetails = [];
        
        // Get all available providers for this component
        componentProviders.forEach(provider => {
          const providerConfig = extractProviderConfig(componentType, provider.name);
          
          // Only include configuration if this is the selected provider or if there are values
          const hasValues = Object.values(providerConfig).some(value => value && value !== '');
          
          if (provider.name === selectedProvider || hasValues) {
            providerDetails.push({
              name: provider.name,
              config: providerConfig
            });
          } else {
            // Include empty config for non-selected providers to maintain structure
            providerDetails.push({
              name: provider.name,
              config: {}
            });
          }
        });
        
        // Use correct field name for provider details - knowledge_base uses different naming
        const detailsFieldName = componentType === 'knowledge_base' 
          ? `${componentType}_details` 
          : `${componentType}_provider_details`;
        agentConfigRequest[detailsFieldName] = providerDetails;
      } else {
        // Component is disabled - include empty provider details structure
        const emptyProviderDetails = componentProviders.map(provider => ({
          name: provider.name,
          config: {}
        }));
        
        // Use correct field name for provider details
        const detailsFieldName = componentType === 'knowledge_base' 
          ? `${componentType}_details` 
          : `${componentType}_provider_details`;
        agentConfigRequest[detailsFieldName] = emptyProviderDetails;
      }
    });try {
      // Step 1: Create the agent configuration (saves to SSM)
      const result = await configService.createAgent(agentConfigRequest);// Step 2: Refresh supervisor agent cache so new agent is discoverable immediately
      try {
        const supervisorRefreshResult = await configService.refreshSupervisorAgentCache();
      } catch (refreshError) {
        // Don't fail creation if supervisor refresh fails
      }
      
      setSuccess(true);
      setHasUnsavedChanges(false);
      
      // Step 3: After successful agent creation and supervisor refresh, start deployment process
      setDeployingAgentName(agentName);
      setIsDeploying(true);
      
    } catch (createError) {
      throw createError;
    }
  };

  const handleSaveConfiguration = async () => {
    // Use the same structure as handleCreateAgent to ensure all required fields are included
    const agentConfigRequest = {
      // Basic information - REQUIRED FIELDS - use actual form data
      agent_name: selectedAgentForConfig,
      agent_description: agentData.agent_basic_agent_description || agentData.agent_description || `${selectedAgentForConfig} agent`,
      region_name: agentData.agent_basic_region_name || agentData.region_name || 'us-east-1',
      
      // System prompt configuration - REQUIRED FIELDS - use actual form data
      system_prompt_name: agentData.agent_basic_system_prompt_name || agentData.system_prompt_name || `${selectedAgentForConfig}_system_prompt`,
      system_prompt: agentData.agent_basic_system_prompt || agentData.system_prompt || `You are ${selectedAgentForConfig}, ${agentData.agent_basic_agent_description || agentData.agent_description || 'a helpful AI assistant'}`,
      
      // Initialize ALL required component fields with defaults - CRITICAL FIX for 422 error
      memory: 'False',
      memory_provider: 'default',
      knowledge_base: 'False',
      knowledge_base_provider: 'default',
      knowledge_base_provider_type: 'custom',
      observability: 'False',
      observability_provider: 'default',
      guardrail: 'False',
      guardrail_provider: 'default',
      
      // Model configuration - extract dynamically from form fields
      ...((() => {
        const modelsConfig = {};
        const modelsProvider = agentData['models_provider'] || 'bedrock';
        const modelsData = extractProviderConfig('models', modelsProvider);
        
        // Map extracted model fields to expected API format - no hardcoded defaults
        modelsConfig.model_id = modelsData.model_id || agentData.models_bedrock_model_id || '';
        modelsConfig.judge_model_id = modelsData.judge_model_id || agentData.models_bedrock_judge_model_id || modelsConfig.model_id;
        modelsConfig.embedding_model_id = modelsData.embedding_model_id || agentData.models_bedrock_embedding_model_id || '';
        
        // Handle multi-select model IDs for ALL agents
        if (modelsData.model_ids && Array.isArray(modelsData.model_ids)) {
          modelsConfig.model_ids = modelsData.model_ids;
        } else if (agentData.models_bedrock_model_ids && Array.isArray(agentData.models_bedrock_model_ids)) {
          modelsConfig.model_ids = agentData.models_bedrock_model_ids;
        }
        
        modelsConfig.temperature = modelsData.temperature !== undefined ? Number(modelsData.temperature) : (agentData.models_bedrock_temperature ? Number(agentData.models_bedrock_temperature) : 0.7);
        modelsConfig.top_p = modelsData.top_p !== undefined ? Number(modelsData.top_p) : (agentData.models_bedrock_top_p ? Number(agentData.models_bedrock_top_p) : 0.9);
        
        return modelsConfig;
      })()),
      
      // Configuration flags - REQUIRED FIELDS
      streaming: 'True',
      cache_prompt: 'default',
      cache_tools: 'default',
      
      // Thinking configuration - REQUIRED FIELDS
      thinking: {
        type: 'enabled',
        budget_tokens: 4096
      },
      
      // Tools configuration - extract from form data
      tools: extractToolsConfig(),
      
      // MCP configuration at root level - required for MCP integration
      ...getMCPConfig()
    };

    // Only process components that exist in AgentConfigRequest model - skip 'agent', 'models', 'tools'
    const validComponents = availableComponents.filter(component => 
      !['agent', 'models', 'tools'].includes(component.type)
    );
    
    validComponents.forEach(componentType => {
      const isEnabled = agentData[`${componentType}_enabled`];
      const selectedProvider = agentData[`${componentType}_provider`];
      
      // Set enabled/disabled status
      agentConfigRequest[componentType] = isEnabled ? 'True' : 'False';
      
      // Set provider (always required)
      const componentProviders = providers[componentType] || [];
      const defaultProvider = componentProviders.length > 0 ? componentProviders[0].name : 'default';
      agentConfigRequest[`${componentType}_provider`] = selectedProvider || defaultProvider;
      
      // For knowledge base, always set provider type (required field)
      if (componentType === 'knowledge_base') {
        agentConfigRequest[`${componentType}_provider_type`] = 'custom';
      }
      
      if (isEnabled && selectedProvider) {
        // Build provider details array - only include selected provider with values
        const providerDetails = [];
        
        // Get all available providers for this component
        componentProviders.forEach(provider => {
          const providerConfig = extractProviderConfig(componentType, provider.name);
          
          // Only include configuration if this is the selected provider AND has values
          if (provider.name === selectedProvider) {
            const hasValues = Object.values(providerConfig).some(value => value && value !== '');
            if (hasValues) {
              providerDetails.push({
                name: provider.name,
                config: providerConfig
              });
            }
          }
        });
        
        // Use correct field name for provider details - knowledge_base uses different naming
        const detailsFieldName = componentType === 'knowledge_base' 
          ? `${componentType}_details` 
          : `${componentType}_provider_details`;
        agentConfigRequest[detailsFieldName] = providerDetails;
      } else {
        // Component is disabled - include empty provider details structure
        const emptyProviderDetails = componentProviders.map(provider => ({
          name: provider.name,
          config: {}
        }));
        
        // Use correct field name for provider details
        const detailsFieldName = componentType === 'knowledge_base' 
          ? `${componentType}_details` 
          : `${componentType}_provider_details`;
        agentConfigRequest[detailsFieldName] = emptyProviderDetails;
      }
    });try {
      // Step 1: Save the configuration to SSM - this now includes automatic agent refresh
      const result = await configService.saveAgentConfig(agentConfigRequest);setSuccess(true);
      setHasUnsavedChanges(false);
      
      // Show reload message if available from the service result
      if (result.agentRefresh) {
        const reloadMessage = result.agentRefresh.success 
          ? `🔄 Configuration saved and agent refreshed successfully`
          : `⚠️ Configuration saved but agent reload failed: ${result.agentRefresh.message}`;
        
        // You could add a toast notification here similar to the original
      }
      
      setTimeout(() => onClose(), 2000);
      
    } catch (saveError) {
      throw saveError;
    }
  };

  const handleCancel = () => {
    if (hasUnsavedChanges && !window.confirm('You have unsaved changes. Are you sure you want to close?')) {
      return;
    }
    onClose();
  };

  // Security: Identify sensitive fields that should be masked
  const isSensitiveField = (fieldName) => {
    const sensitivePatterns = [
      // Passwords
      'password', 'passwd', 'pwd',
      'cluster_password', 'db_password', 'database_password',
      
      // Keys and Secrets
      'secret', 'key', 'token', 'credential',
      'private_key', 'private-key', 'privatekey',
      'private key content', 'private_key_content',
      'passphrase', 'pass_phrase', 'pass-phrase',
      
      // API and Authentication
      'api_key', 'api-key', 'apikey',
      'auth_token', 'auth-token', 'authtoken',
      'access_key', 'access-key', 'accesskey',
      'bearer_token', 'bearer-token',
      
      // Connection Strings and URIs
      'connection_string', 'conn_str', 'connection_str',
      'cluster_uri', 'cluster uri', 'mongodb_uri', 'mongo_uri',
      'atlas_uri', 'database_uri', 'db_uri',
      'mongodb atlas cluster uri',
      
      // Certificates and Keys
      'cert', 'certificate', 'pem', 'p12', 'pfx',
      'ssl_cert', 'tls_cert', 'client_cert'
    ];
    
    const fieldNameLower = fieldName.toLowerCase();
    return sensitivePatterns.some(pattern => fieldNameLower.includes(pattern));
  };

  // Security: Mask sensitive values for display
  const maskSensitiveValue = (value, fieldName) => {
    if (!value || !isSensitiveField(fieldName)) {
      return value;
    }
    
    // Mask the value but show some indication of length
    const maskedLength = Math.min(value.length, 20);
    return '*'.repeat(maskedLength);
  };

  // Dynamic field rendering for comprehensive form schemas - Issue #2 Dynamic Form Generation + Security
  const renderDynamicField = (field, componentType, providerName = null) => {
    const fieldKey = providerName ? `${componentType}_${providerName}_${field.name}` : `${componentType}_${field.name}`;
    
    // Special handling for agent_name field - should be editable in create mode, disabled in configure mode
    const isAgentNameField = componentType === 'agent' && field.name === 'agent_name';
    const shouldDisableField = isAgentNameField ? (mode === 'configure') : field.disabled;
    
    // Check for validation errors - map field names to validation error keys
    const getValidationError = () => {
      if (componentType === 'agent') {
        if (field.name === 'agent_name') {
          return validationErrors.agent_name;
        }
        if (field.name === 'agent_description') {
          return validationErrors.agent_description;
        }
      }
      if (componentType === 'models') {
        if (field.name === 'model_id') {
          return validationErrors.model_id;
        }
      }
      return undefined;
    };
    
    const validationError = getValidationError();
    
    // Security: Check if this is a sensitive field (enhanced detection)
    const isSensitive = isSensitiveField(field.name) || 
                       field.type === 'password' || 
                       (field.label && isSensitiveField(field.label)) ||
                       (field.help_text && field.help_text.toLowerCase().includes('password')) ||
                       (field.help_text && field.help_text.toLowerCase().includes('secret'));
    
    const defaultVal = field.default_value !== undefined ? field.default_value : field.default;
    const currentValue = agentData[fieldKey] !== undefined ? agentData[fieldKey] : (defaultVal || '');
    
    
    switch (field.type) {
      case 'text':
      case 'url':
      case 'password':
      case 'None':
      case null:
      case undefined:
        return (
          <FormField
            key={fieldKey}
            label={field.label || field.name}
            constraintText={field.required ? "Required" : "Optional"}
            description={field.help_text}
            errorText={validationError || (field.required && !currentValue ? `${field.label || field.name} is required` : undefined)}
            info={
              <Link variant="info" onFollow={() => {}}>
                {getHelpBite(field.name) || "Additional information"}
              </Link>
            }
          >
            {isSensitive ? (
              <SpaceBetween size="s">
                <Input
                  type="password"
                  value={currentValue}
                  onChange={({ detail }) => updateAgentData({ [fieldKey]: detail.value })}
                  placeholder={field.placeholder || `Enter ${field.name} (hidden for security)`}
                  disabled={shouldDisableField}
                  invalid={!!validationError || (field.required && !currentValue)}
                />
                <Alert type="warning" header="🔒 Security Protection Active">
                  <Box variant="small">
                    This field contains sensitive information and is protected with password masking.
                  </Box>
                </Alert>
              </SpaceBetween>
            ) : (
              <Input
                type={field.type === 'url' ? 'url' : 'text'}
                value={currentValue}
                onChange={({ detail }) => updateAgentData({ [fieldKey]: detail.value })}
                placeholder={field.placeholder || `Enter ${field.name}`}
                disabled={shouldDisableField}
                invalid={!!validationError || (field.required && !currentValue)}
              />
            )}
          </FormField>
        );
      
      case 'textarea':
        return (
          <FormField
            key={fieldKey}
            label={field.label || field.name}
            description={field.help_text}
          >
            <Textarea
              value={currentValue}
              onChange={({ detail }) => updateAgentData({ [fieldKey]: detail.value })}
              placeholder={field.placeholder || `Enter ${field.name}`}
              rows={field.rows || 3}
              disabled={field.disabled}
            />
          </FormField>
        );
      
      case 'select':
        // Multi-select model dropdown - Issue #2 Multi-select Model Options
        if (field.name === 'model_ids') {
          return (
            <div key={fieldKey}>
              <MultiSelectModelDropdown
                selectedModels={agentData[fieldKey] || []}
                onChange={(selectedModels) => updateAgentData({ [fieldKey]: selectedModels })}
                maxSelections={field.max_selections || 5}
                label={field.label || 'Multi-Model Selection'}
                description={field.help_text || "Select multiple models for dynamic switching"}
              />
            </div>
          );
        }
        
        // System prompt template dropdown - Issue #2 System Prompt Templates (Complete Implementation)
        if (field.name === 'system_prompt_name') {
          // Create a UI selection field key to track the full dropdown identifier
          const uiSelectionKey = `${fieldKey}_ui_selection`;
          
          // Function to get the display value for the dropdown
          const getDisplayValue = () => {
            // First check if we have a UI selection stored
            if (agentData[uiSelectionKey]) {
              return agentData[uiSelectionKey];
            }
            
            // If no UI selection, try to reconstruct it from the saved prompt name
            const savedPromptName = agentData[fieldKey];
            if (savedPromptName) {
              // Check if it matches any agent-specific prompt
              if (systemPrompts.some(prompt => prompt.name === savedPromptName)) {
                return savedPromptName;
              }
              
              // Check if it matches any global template
              if (Object.keys(globalTemplates).includes(savedPromptName)) {
                return `template:${savedPromptName}`;
              }
              
              // Check if it matches any cross-agent prompt
              for (const [agentName, agentData] of Object.entries(crossAgentPrompts)) {
                if (agentData.prompts && agentData.prompts.some(prompt => prompt.name === savedPromptName)) {
                  return `cross:${agentName}:${savedPromptName}`;
                }
              }
              
              // If we can't find it, just return the saved name
              return savedPromptName;
            }
            
            return field.default_value || '';
          };

          const systemPromptOptions = [];
          
          // Create New Template Option
          systemPromptOptions.push({
            label: '➕ Create New Template',
            value: 'create_new',
            description: 'Create a custom system prompt template'
          });
          
          // Agent-specific prompts
          if (!loadingPrompts && systemPrompts.length > 0) {
            systemPrompts.forEach(prompt => {
              systemPromptOptions.push({
                label: `${prompt.name} (${prompt.length || 0} chars)`,
                value: prompt.name,
                description: 'Agent-specific template'
              });
            });
          }
          
          // Cross-agent prompts (available in both create and configure modes)
          if (!loadingPrompts && Object.keys(crossAgentPrompts).length > 0) {
            Object.entries(crossAgentPrompts).forEach(([agentName, agentData]) => {
              if (agentData.prompts) {
                agentData.prompts.forEach(prompt => {
                  systemPromptOptions.push({
                    label: `${prompt.display_name} (From ${agentName})`,
                    value: `cross:${agentName}:${prompt.name}`,
                    description: `Cross-agent prompt from ${agentName}`
                  });
                });
              }
            });
          }
          
          // Global templates
          if (!loadingPrompts && Object.keys(globalTemplates).length > 0) {
            Object.entries(globalTemplates).forEach(([key, template]) => {
              systemPromptOptions.push({
                label: `${template.name || key} - ${template.description || template.category || 'Global template'}`,
                value: `template:${key}`,
                description: template.category || 'Global template'
              });
            });
          }
          
          return (
            <SpaceBetween key={fieldKey} size="s">
              <SpaceBetween direction="horizontal" size="s" alignItems="flex-end">
                <FormField
                  label={field.label || field.name}
                  description={field.help_text || "Select an existing template or create a new one"}
                  stretch={true}
                >
                  <Select
                    selectedOption={getDisplayValue() ? 
                      systemPromptOptions.find(opt => opt.value === getDisplayValue()) || { label: getDisplayValue(), value: getDisplayValue() } : null}
                    onChange={async ({ detail }) => {
                      const selectedPrompt = detail.selectedOption.value;
                      
                      // Handle "Create New Template" option
                      if (selectedPrompt === 'create_new') {
                        setShowCreateTemplateModal(true);
                        return;
                      }
                      
                      // Store the full dropdown identifier for UI display
                      updateAgentData({ [uiSelectionKey]: selectedPrompt });
                      
                      // Extract the actual prompt name to save (not the dropdown identifier)
                      let actualPromptName = selectedPrompt;
                      
                      if (selectedPrompt.startsWith('template:')) {
                        // For templates, use the template key as the prompt name
                        actualPromptName = selectedPrompt.replace('template:', '');
                      } else if (selectedPrompt.startsWith('cross:')) {
                        // For cross-agent prompts, extract just the prompt name (last part after second colon)
                        const [, sourceAgent, promptName] = selectedPrompt.split(':');
                        actualPromptName = promptName;
                      }
                      // For agent-specific prompts, use as-is (no prefix)
                      
                      // Save the actual prompt name (not the dropdown identifier)
                      updateAgentData({ [fieldKey]: actualPromptName });
                      
                      // Auto-load prompt content if selection is made
                      if (selectedPrompt && (agentData.agent_basic_agent_name || selectedAgentForConfig)) {
                        const agentName = agentData.agent_basic_agent_name || selectedAgentForConfig;
                        
                        // Check if it's a global template (starts with 'template:')
                        if (selectedPrompt.startsWith('template:')) {
                          const templateKey = selectedPrompt.replace('template:', '');
                          const template = globalTemplates[templateKey];
                          if (template?.content) {
                            const systemPromptKey = `agent_basic_system_prompt`;
                            updateAgentData({ [systemPromptKey]: template.content });
                          }
                        } 
                        // Check if it's a cross-agent prompt (starts with 'cross:')
                        else if (selectedPrompt.startsWith('cross:')) {
                          const [, sourceAgent, promptName] = selectedPrompt.split(':');
                          await loadSystemPromptContent(sourceAgent, promptName);
                        } 
                        else {
                          // Load agent-specific prompt content
                          await loadSystemPromptContent(agentName, selectedPrompt);
                        }
                      }
                    }}
                    options={systemPromptOptions}
                    placeholder="Select system prompt template"
                    disabled={field.disabled || loadingPrompts}
                    loadingText="Loading templates..."
                  />
                </FormField>
                
                {/* Quick Preview Button */}
                <Button
                  onClick={() => setShowPromptPreviewModal(true)}
                  disabled={!getDisplayValue() || getDisplayValue() === 'create_new'}
                  iconName="view"
                  variant="icon"
                  ariaLabel="Preview selected template"
                />
              </SpaceBetween>
              
              {/* Show template preview if selected */}
              {getDisplayValue() && getDisplayValue().startsWith('template:') && (() => {
                const templateKey = getDisplayValue().replace('template:', '');
                const template = globalTemplates[templateKey];
                return template?.content ? (
                  <Alert type="info" header="Template Preview">
                    <Box variant="code" padding="s" style={{ 
                      backgroundColor: '#f6f6f6', 
                      borderRadius: '4px',
                      fontSize: '14px',
                      maxHeight: '100px',
                      overflow: 'auto'
                    }}>
                      {template.content}
                    </Box>
                  </Alert>
                ) : null;
              })()}
              
              {/* Show loading indicator */}
              {loadingPrompts && (
                <Alert type="info">
                  <SpaceBetween direction="horizontal" size="s" alignItems="center">
                    <Spinner size="normal" />
                    <Box>Loading system prompt templates...</Box>
                  </SpaceBetween>
                </Alert>
              )}
              
              {/* Show available template counts */}
              {!loadingPrompts && (systemPrompts.length > 0 || Object.keys(globalTemplates).length > 0 || Object.keys(crossAgentPrompts).length > 0) && (
                <Alert type="success" header="Available Templates">
                  <SpaceBetween size="xs">
                    {systemPrompts.length > 0 && <Box variant="small">Agent-specific: {systemPrompts.length} templates</Box>}
                    {Object.keys(crossAgentPrompts).length > 0 && (
                      <Box variant="small">
                        Cross-agent: {Object.values(crossAgentPrompts).reduce((total, agentData) => total + (agentData.prompts?.length || 0), 0)} templates from {Object.keys(crossAgentPrompts).length} agents
                      </Box>
                    )}
                    {Object.keys(globalTemplates).length > 0 && <Box variant="small">Global: {Object.keys(globalTemplates).length} templates</Box>}
                  </SpaceBetween>
                </Alert>
              )}
              
              {/* Show empty state */}
              {!loadingPrompts && systemPrompts.length === 0 && Object.keys(globalTemplates).length === 0 && Object.keys(crossAgentPrompts).length === 0 && (
                <Alert type="warning" header="No Templates Available">
                  <Box variant="p">No system prompt templates found. You can create a new template using the dropdown above.</Box>
                </Alert>
              )}
            </SpaceBetween>
          );
        }
        
        return (
          <FormField
            key={fieldKey}
            label={field.label || field.name}
            constraintText={field.required ? "Required" : "Optional"}
            description={field.help_text}
            errorText={validationError || (field.required && !currentValue ? `${field.label || field.name} is required` : undefined)}
            info={
              <Link variant="info" onFollow={() => {}}>
                {getHelpBite(field.name) || "Additional information"}
              </Link>
            }
          >
            <Select
              selectedOption={currentValue ? 
                field.options?.find(opt => opt.value === currentValue) || { label: currentValue, value: currentValue } : null}
              onChange={({ detail }) => updateAgentData({ [fieldKey]: detail.selectedOption.value })}
              options={field.options?.map(option => ({
                label: option.label || option.value,
                value: option.value
              })) || []}
              placeholder={`Select ${field.label || field.name}`}
              invalid={!!validationError || (field.required && !currentValue)}
            />
          </FormField>
        );
      
      case 'boolean':
        return (
          <FormField
            key={fieldKey}
            label={field.label || field.name}
            description={field.help_text}
            info={
              <Link variant="info" onFollow={() => {}}>
                {getHelpBite(field.name) || "Additional information"}
              </Link>
            }
          >
            <Toggle
              onChange={({ detail }) => updateAgentData({ [fieldKey]: detail.checked })}
              checked={currentValue === true || currentValue === 'true'}
              disabled={field.disabled}
            >
              Enable {field.label || field.name}
            </Toggle>
          </FormField>
        );
      
      case 'range':
        return (
          <FormField
            key={fieldKey}
            label={`${field.label || field.name}: ${currentValue}`}
            description={field.help_text}
            info={
              <Link variant="info" onFollow={() => {}}>
                {getHelpBite(field.name) || "Additional information"}
              </Link>
            }
          >
            <input
              type="range"
              min={field.min_value || 0}
              max={field.max_value || 1}
              step={field.step || 0.1}
              value={currentValue}
              onChange={(e) => updateAgentData({ [fieldKey]: parseFloat(e.target.value) })}
              style={{ width: '100%', accentColor: '#0972d3' }}
            />
          </FormField>
        );
      
      default:
        return (
          <FormField
            key={fieldKey}
            label={field.label || field.name}
            description={field.help_text}
            info={
              <Link variant="info" onFollow={() => {}}>
                {getHelpBite(field.name) || "Additional information"}
              </Link>
            }
          >
            {isSensitive ? (
              <SpaceBetween size="s">
                <Input
                  type="password"
                  value={currentValue}
                  onChange={({ detail }) => updateAgentData({ [fieldKey]: detail.value })}
                  placeholder={field.placeholder || `Enter ${field.name} (hidden for security)`}
                  disabled={field.disabled}
                />
                <Alert type="warning" header="🔒 Security Protection Active">
                  <Box variant="small">
                    This field contains sensitive information and is protected with password masking.
                  </Box>
                </Alert>
              </SpaceBetween>
            ) : (
              <Input
                value={currentValue}
                onChange={({ detail }) => updateAgentData({ [fieldKey]: detail.value })}
                placeholder={field.placeholder || `Enter ${field.name}`}
                disabled={field.disabled}
              />
            )}
          </FormField>
        );
    }
  };

  const renderStepContent = () => {
    if (!steps || steps.length === 0 || activeStepIndex >= steps.length) {
      return (
        <Container>
          <Box textAlign="center" padding="xl">
            <StatusIndicator type="loading">Loading step content...</StatusIndicator>
          </Box>
        </Container>
      );
    }
    
    const step = steps[activeStepIndex];
    
    if (step.id === 'agent_selection') {
      return (
        <Container header={<Header variant="h3">Agent Selection</Header>}>
          <FormField 
            label="Select Agent" 
            constraintText="Required"
            errorText={validationErrors.selectedAgent}
          >
            <Select
              selectedOption={selectedAgentForConfig ? 
                { label: selectedAgentForConfig, value: selectedAgentForConfig } : null}
              onChange={async ({ detail }) => {
                const agentName = detail.selectedOption.value;
                setSelectedAgentForConfig(agentName);
                await loadAgentConfiguration(agentName);
                setValidationErrors({});
              }}
              options={availableAgents.map(agent => ({ label: agent, value: agent }))}
              placeholder="Choose an agent to configure"
              invalid={!!validationErrors.selectedAgent}
            />
          </FormField>
        </Container>
      );
    }
    
    // Handle agent step with hardcoded fields (bypass schema check)
    if (step.id === 'agent') {
      return (
        <Container
          header={
            <Header 
              variant="h3" 
              description="Configure basic agent settings"
              actions={
                <Button
                  iconName="status-info"
                  variant="icon"
                  onClick={() => {
                    setCurrentHelpTopic('getting_started');
                    setShowHelpPanel(true);
                  }}
                  ariaLabel="Get help with Agent Configuration"
                />
              }
            >
              Agent Configuration
            </Header>
          }
        >
          <SpaceBetween size="l">
            <Alert type="info" header="Agent Basics">
              <Box variant="p">
                Configure the fundamental settings for your AI agent, including name, description, and system prompt.
              </Box>
            </Alert>
            
            <SpaceBetween size="m">
              <FormField
                label="Agent Name"
                constraintText="Required"
                description="A unique identifier for your agent"
                errorText={validationErrors.agent_name}
              >
                <Input
                  type="text"
                  value={agentData.agent_basic_agent_name || agentData.agent_name || ''}
                  onChange={({ detail }) => updateAgentData({ 
                    agent_basic_agent_name: detail.value,
                    agent_name: detail.value 
                  })}
                  placeholder="Enter agent name"
                  disabled={mode === 'configure'}
                  invalid={!!validationErrors.agent_name}
                />
              </FormField>

              <FormField
                label="Agent Description"
                constraintText="Required"
                description="Describe the purpose and capabilities of this agent"
                errorText={validationErrors.agent_description}
              >
                <Textarea
                  value={agentData.agent_basic_agent_description || agentData.agent_description || ''}
                  onChange={({ detail }) => updateAgentData({ 
                    agent_basic_agent_description: detail.value,
                    agent_description: detail.value 
                  })}
                  placeholder="Enter agent description"
                  rows={3}
                  invalid={!!validationErrors.agent_description}
                />
              </FormField>

              <FormField
                label="AWS Region"
                description="Select the AWS region for this agent"
              >
                <Select
                  selectedOption={{ 
                    label: agentData.agent_basic_region_name || agentData.region_name || 'us-east-1', 
                    value: agentData.agent_basic_region_name || agentData.region_name || 'us-east-1' 
                  }}
                  onChange={({ detail }) => updateAgentData({ 
                    agent_basic_region_name: detail.selectedOption.value,
                    region_name: detail.selectedOption.value 
                  })}
                  options={[
                    { label: 'us-east-1', value: 'us-east-1' },
                    { label: 'us-east-2', value: 'us-east-2' },
                    { label: 'us-west-1', value: 'us-west-1' },
                    { label: 'us-west-2', value: 'us-west-2' },
                    { label: 'eu-west-1', value: 'eu-west-1' },
                    { label: 'eu-central-1', value: 'eu-central-1' },
                    { label: 'ap-southeast-1', value: 'ap-southeast-1' },
                    { label: 'ap-northeast-1', value: 'ap-northeast-1' }
                  ]}
                />
              </FormField>

              {/* System Prompt Name - with template dropdown */}
              <SpaceBetween size="s">
                <SpaceBetween direction="horizontal" size="s" alignItems="flex-end">
                  <FormField
                    label="System Prompt Template"
                    description="Select an existing template or create a new one"
                    stretch={true}
                  >
                    <Select
                      selectedOption={(() => {
                        const fieldKey = 'agent_basic_system_prompt_name';
                        const uiSelectionKey = `${fieldKey}_ui_selection`;
                        const displayValue = agentData[uiSelectionKey] || agentData[fieldKey] || '';
                        
                        const systemPromptOptions = [
                          { label: '➕ Create New Template', value: 'create_new', description: 'Create a custom system prompt template' },
                          ...systemPrompts.map(p => ({ label: p.name, value: p.name, description: 'Agent-specific' })),
                          ...Object.entries(crossAgentPrompts).flatMap(([agentName, agentData]) => 
                            (agentData.prompts || []).map(prompt => ({
                              label: `${prompt.display_name} (From ${agentName})`,
                              value: `cross:${agentName}:${prompt.name}`,
                              description: `From ${agentName}`
                            }))
                          ),
                          ...Object.entries(globalTemplates).map(([key, template]) => ({
                            label: `${template.name || key} - ${template.description || template.category || 'Global'}`,
                            value: `template:${key}`,
                            description: template.category || 'Global'
                          }))
                        ];
                        
                        return displayValue ? 
                          systemPromptOptions.find(opt => opt.value === displayValue) || 
                          { label: displayValue, value: displayValue } : null;
                      })()}
                      onChange={async ({ detail }) => {
                        const selectedPrompt = detail.selectedOption.value;
                        const fieldKey = 'agent_basic_system_prompt_name';
                        const uiSelectionKey = `${fieldKey}_ui_selection`;
                        
                        if (selectedPrompt === 'create_new') {
                          setShowCreateTemplateModal(true);
                          return;
                        }
                        
                        updateAgentData({ [uiSelectionKey]: selectedPrompt });
                        
                        let actualPromptName = selectedPrompt;
                        if (selectedPrompt.startsWith('template:')) {
                          actualPromptName = selectedPrompt.replace('template:', '');
                        } else if (selectedPrompt.startsWith('cross:')) {
                          const [, , promptName] = selectedPrompt.split(':');
                          actualPromptName = promptName;
                        }
                        
                        updateAgentData({ [fieldKey]: actualPromptName });
                        
                        // Auto-load content
                        if (selectedPrompt.startsWith('template:')) {
                          const templateKey = selectedPrompt.replace('template:', '');
                          const template = globalTemplates[templateKey];
                          if (template?.content) {
                            updateAgentData({ agent_basic_system_prompt: template.content });
                          }
                        } else if (selectedPrompt.startsWith('cross:')) {
                          const [, sourceAgent, promptName] = selectedPrompt.split(':');
                          await loadSystemPromptContent(sourceAgent, promptName);
                        } else {
                          const agentName = agentData.agent_basic_agent_name || selectedAgentForConfig;
                          if (agentName) {
                            await loadSystemPromptContent(agentName, selectedPrompt);
                          }
                        }
                      }}
                      options={[
                        { label: '➕ Create New Template', value: 'create_new', description: 'Create a custom system prompt template' },
                        ...systemPrompts.map(p => ({ label: p.name, value: p.name, description: 'Agent-specific' })),
                        ...Object.entries(crossAgentPrompts).flatMap(([agentName, agentData]) => 
                          (agentData.prompts || []).map(prompt => ({
                            label: `${prompt.display_name} (From ${agentName})`,
                            value: `cross:${agentName}:${prompt.name}`,
                            description: `From ${agentName}`
                          }))
                        ),
                        ...Object.entries(globalTemplates).map(([key, template]) => ({
                          label: `${template.name || key} - ${template.description || template.category || 'Global'}`,
                          value: `template:${key}`,
                          description: template.category || 'Global'
                        }))
                      ]}
                      placeholder="Select system prompt template"
                      disabled={loadingPrompts}
                      loadingText="Loading templates..."
                    />
                  </FormField>
                  
                  <Button
                    onClick={() => setShowPromptPreviewModal(true)}
                    disabled={!agentData.agent_basic_system_prompt_name || agentData.agent_basic_system_prompt_name === 'create_new'}
                    iconName="view"
                    variant="icon"
                    ariaLabel="Preview selected template"
                  />
                </SpaceBetween>
                
                {loadingPrompts && (
                  <Alert type="info">
                    <SpaceBetween direction="horizontal" size="s" alignItems="center">
                      <Spinner size="normal" />
                      <Box>Loading system prompt templates...</Box>
                    </SpaceBetween>
                  </Alert>
                )}
              </SpaceBetween>

              <FormField
                label="System Prompt"
                description="The instructions that guide the agent's behavior"
              >
                <Textarea
                  value={agentData.agent_basic_system_prompt || agentData.system_prompt || ''}
                  onChange={({ detail }) => updateAgentData({ 
                    agent_basic_system_prompt: detail.value,
                    system_prompt: detail.value 
                  })}
                  placeholder="Enter system prompt instructions"
                  rows={6}
                />
              </FormField>
            </SpaceBetween>
          </SpaceBetween>
        </Container>
      );
    }
    
    if (step.id === 'review') {
      return (
        <Container>
          <SpaceBetween size="l">
            <Header variant="h3">Review Configuration</Header>
            
            <Alert type="info">
              Please review your agent configuration before {mode === 'create' ? 'creating' : 'saving'}.
            </Alert>

            <Container header={<Header variant="h4">Agent Details</Header>}>
              <KeyValuePairs
                columns={2}
                items={[
                  {
                    label: 'Name',
                    value: mode === 'create' ? (agentData.agent_basic_agent_name || agentData.agent_name) : selectedAgentForConfig
                  },
                  {
                    label: 'Description', 
                    value: agentData.agent_basic_agent_description || agentData.agent_description || 'Not specified'
                  },
                  {
                    label: 'Region',
                    value: agentData.agent_basic_region_name || agentData.region_name || 'us-east-1'
                  }
                ]}
              />
            </Container>

            <Container header={<Header variant="h4">Model Configuration</Header>}>
              <KeyValuePairs
                columns={2}
                items={[
                  {
                    label: 'Primary Model',
                    value: agentData.models_bedrock_model_id || 'Not configured'
                  },
                  {
                    label: 'Temperature',
                    value: agentData.models_bedrock_temperature || 'Default (0.7)'
                  },
                  {
                    label: 'Top P',
                    value: agentData.models_bedrock_top_p || 'Default (0.9)'
                  },
                  ...(agentData.models_bedrock_model_ids && agentData.models_bedrock_model_ids.length > 0 ? [{
                    label: 'Multi-Model Selection',
                    value: `${agentData.models_bedrock_model_ids.length} models selected for dynamic switching`
                  }] : [])
                ]}
              />
            </Container>

            {/* Show enabled components - Issue #2 All Components Summary with Security */}
            {availableComponents.filter(comp => 
              agentData[`${comp.type}_enabled`] && !['agent', 'models'].includes(comp.type)
            ).map(component => (
              <Container key={component.type} header={<Header variant="h4">{component.display_name}</Header>}>
                <SpaceBetween size="m">
                  <KeyValuePairs
                    columns={2}
                    items={[
                      {
                        label: 'Status',
                        value: <Badge color="green">Enabled</Badge>
                      },
                      {
                        label: 'Provider',
                        value: agentData[`${component.type}_provider`] || 'Default'
                      }
                    ]}
                  />
                  
                  {/* Security: Show configured fields with sensitive data masked */}
                  {(() => {
                    const componentPrefix = `${component.type}_${agentData[`${component.type}_provider`] || 'default'}_`;
                    const configuredFields = Object.entries(agentData)
                      .filter(([key, value]) => key.startsWith(componentPrefix) && value && value !== '')
                      .map(([key, value]) => {
                        const fieldName = key.replace(componentPrefix, '').replace(/_/g, ' ');
                        const displayValue = isSensitiveField(key) ? 
                          maskSensitiveValue(value, key) : 
                          (typeof value === 'string' && value.length > 50 ? `${value.substring(0, 47)}...` : value);
                        
                        return {
                          label: fieldName.charAt(0).toUpperCase() + fieldName.slice(1),
                          value: displayValue
                        };
                      });
                    
                    if (configuredFields.length > 0) {
                      return (
                        <Container header={<Header variant="h5">Configuration Details</Header>}>
                          <KeyValuePairs
                            columns={1}
                            items={configuredFields}
                          />
                        </Container>
                      );
                    }
                    return null;
                  })()}
                  
                  {/* Security warning for sensitive configurations */}
                  {Object.keys(agentData).some(key => 
                    key.startsWith(`${component.type}_${agentData[`${component.type}_provider`] || 'default'}_`) && 
                    isSensitiveField(key) && 
                    agentData[key]
                  ) && (
                    <Alert type="info" header="Security Notice">
                      <Box variant="small">
                        🔒 Sensitive configuration values are masked for security. All credentials are encrypted when saved.
                      </Box>
                    </Alert>
                  )}
                </SpaceBetween>
              </Container>
            ))}

            {success && (
              <Alert type="success">
                {mode === 'create' ? 'Agent created successfully!' : 'Configuration saved successfully!'}
              </Alert>
            )}

            {error && (
              <Alert type="error" dismissible onDismiss={() => setError(null)}>
                {error}
              </Alert>
            )}
          </SpaceBetween>
        </Container>
      );
    }

    // Tools step - Issue #2 ToolManager Integration
    if (step.id === 'tools') {
      return (
        <Container header={<Header variant="h3">Tools Configuration</Header>}>
          <SpaceBetween size="l">
            <Alert type="info" header="Tools Enhancement">
              <Box variant="p">
                Configure tools to extend your agent's capabilities with additional functions and integrations.
              </Box>
            </Alert>
            
            <Toggle
              onChange={({ detail }) => updateAgentData({ [`${step.id}_enabled`]: detail.checked })}
              checked={agentData[`${step.id}_enabled`] || false}
            >
              Enable Tools
            </Toggle>
            
            {agentData[`${step.id}_enabled`] && (
              <ToolManager
                agentData={agentData}
                updateAgentData={updateAgentData}
                componentType="tools"
                isEnabled={true}
              />
            )}
          </SpaceBetween>
        </Container>
      );
    }
    
    // Dynamic component step - Issue #2 All Other Components
    const componentSchema = formSchema[step.id];
    if (!componentSchema) {
      return (
        <Container>
          <Box textAlign="center" padding="xl">
            <StatusIndicator type="loading">Loading {step.title} configuration...</StatusIndicator>
          </Box>
        </Container>
      );
    }
    
    const isAlwaysEnabled = step.id === 'models' || step.id === 'agent';
    const isComponentEnabled = isAlwaysEnabled || agentData[`${step.id}_enabled`];
    
    // Get contextual help for this step
    const getContextualHelp = () => {
      const helpKey = step.id === 'agent' ? 'agent_configuration' : 
                     step.id === 'models' ? 'model_configuration' :
                     step.id === 'knowledge_base' ? 'knowledge_integration' :
                     step.id === 'tools' ? 'tools_integration' :
                     'advanced_features';
      return getHelpSnack(helpKey);
    };
    
    return (
      <Container
        header={
          <Header 
            variant="h3" 
            description={componentSchema.description || `Configure ${step.title} settings`}
            actions={
              <Button
                iconName="status-info"
                variant="icon"
                onClick={() => {
                  const helpTopic = step.id === 'agent' ? 'getting_started' :
                                   step.id === 'models' ? 'model_selection' :
                                   step.id === 'tools' ? 'tools_and_capabilities' :
                                   step.id === 'knowledge_base' ? 'knowledge_base_setup' :
                                   'advanced_configuration';
                  setCurrentHelpTopic(helpTopic);
                  setShowHelpPanel(true);
                }}
                ariaLabel={`Get help with ${step.title}`}
              />
            }
          >
            {step.title}
          </Header>
        }
      >
        <SpaceBetween size="l">
          {/* SNACKS: Contextual help section */}
          {getContextualHelp() && (
            <Alert type="info" header={getContextualHelp().title}>
              <Box variant="p">{getContextualHelp().content}</Box>
            </Alert>
          )}
          
          {!isAlwaysEnabled && (
            <Toggle
              onChange={({ detail }) => updateAgentData({ [`${step.id}_enabled`]: detail.checked })}
              checked={isComponentEnabled || false}
            >
              Enable {step.title}
            </Toggle>
          )}

          {isComponentEnabled && (
            <SpaceBetween size="m">
              {/* Provider selection - show if providers available - Issue #2 Provider-specific Configurations */}
              {providers[step.id]?.length > 0 && (() => {
                // Ensure default provider is set in agentData if not already present
                const providerKey = `${step.id}_provider`;
                const currentProvider = agentData[providerKey];
                const defaultProvider = providers[step.id][0];
                
                // Auto-initialize the provider selection if not set
                if (!currentProvider && defaultProvider && !agentData[`${providerKey}_initialized`]) {
                  // Use setTimeout to avoid state updates during render
                  setTimeout(() => {
                    updateAgentData({ 
                      [providerKey]: defaultProvider.name,
                      [`${providerKey}_initialized`]: true
                    });
                  }, 0);
                }

                return (
                  <FormField label={`${step.title} Provider`}>
                    <Select
                      selectedOption={currentProvider ? 
                        { 
                          label: providers[step.id].find(p => p.name === currentProvider)?.display_name || currentProvider,
                          value: currentProvider
                        } : 
                        defaultProvider ? { label: defaultProvider.display_name, value: defaultProvider.name } : null}
                      onChange={({ detail }) => updateAgentData({ [providerKey]: detail.selectedOption.value })}
                      options={providers[step.id].map(provider => ({
                        label: provider.display_name || provider.name,
                        value: provider.name,
                        description: provider.description
                      }))}
                    />
                  </FormField>
                );
              })()}
              
              {/* Render provider-specific fields - Issue #2 Provider-specific Configurations */}
              {(() => {
                const selectedProvider = agentData[`${step.id}_provider`] || providers[step.id]?.[0]?.name;
                if (selectedProvider && componentSchema.providers?.[selectedProvider]?.fields) {
                  return (
                    <SpaceBetween size="m">
                      {componentSchema.providers[selectedProvider].fields.map(field => 
                        renderDynamicField(field, step.id, selectedProvider)
                      )}
                    </SpaceBetween>
                  );
                }
                return null;
              })()}
            </SpaceBetween>
          )}
        </SpaceBetween>
      </Container>
    );
  };

  // Wizard Steps Definition - Multi-page Create Pattern - Issue #2 Dynamic Steps
  const wizardSteps = steps.map((step) => ({
    title: step.title,
    content: renderStepContent(),
    isOptional: !step.required,
    description: step.subtitle
  }));

  // Loading States Pattern
  if (isLoading) {
    return (
      <Modal visible={isOpen} header="Loading..." size="large">
        <Box textAlign="center" padding="xl">
          <SpaceBetween size="m" alignItems="center">
            <Spinner size="large" />
            <StatusIndicator type="loading">
              Loading comprehensive wizard configuration...
            </StatusIndicator>
          </SpaceBetween>
        </Box>
      </Modal>
    );
  }

  if (!isOpen) return null;

  return (
    <>
      <Modal
        visible={isOpen}
        onDismiss={handleCancel}
        header={mode === 'create' ? 'Create Agent (Comprehensive)' : 'Configure Agent (Comprehensive)'}
        size="max"
        closeAriaLabel="Close comprehensive wizard"
      >
        <Wizard
          steps={wizardSteps}
          activeStepIndex={activeStepIndex}
          onNavigate={handleNavigate}
          onSubmit={handleSubmit}
          onCancel={handleCancel}
          submitButtonText={mode === 'create' ? 'Create Agent' : 'Save Configuration'}
          cancelButtonText={hasUnsavedChanges ? 'Cancel (Unsaved Changes)' : 'Cancel'}
          isLoadingNextStep={isCreating}
          allowSkipTo={false}
          i18nStrings={{
            stepNumberLabel: stepNumber => `Step ${stepNumber}`,
            collapsedStepsLabel: (stepNumber, stepsCount) => `Step ${stepNumber} of ${stepsCount}`,
            navigationAriaLabel: "Wizard steps",
            cancelButton: "Cancel",
            previousButton: "Previous",
            nextButton: "Next",
            submitButton: mode === 'create' ? 'Create Agent' : 'Save Configuration',
            optional: "optional"
          }}
        />
      </Modal>

      {/* Deployment Status Modal - Issue #2 Enhanced Deployment */}
      <DeploymentStatus
        agentName={deployingAgentName}
        isDeploying={isDeploying}
        onDeploymentComplete={(result) => {
          setIsDeploying(false);
          setDeployingAgentName(null);
          if (onAgentCreated) {
            onAgentCreated(result.agentName);
          }
          // Don't auto-close - let user review results and close manually per AWS Cloudscape UX guidelines
        }}
        onDeploymentError={(error) => {
          setIsDeploying(false);
          setDeployingAgentName(null);
          setError(`Deployment failed: ${error.message}`);
        }}
        onClose={() => {
          setIsDeploying(false);
          setDeployingAgentName(null);
          onClose(); // Close the entire wizard when deployment modal is closed
        }}
      />

      {/* Template Creation Modal */}
      {showCreateTemplateModal && (
        <Modal
          visible={showCreateTemplateModal}
          onDismiss={handleCloseCreateTemplateModal}
          header="➕ Create New System Prompt Template"
          size="large"
          footer={
            <Box float="right">
              <SpaceBetween direction="horizontal" size="s">
                <Button
                  onClick={handleCloseCreateTemplateModal}
                  disabled={creatingTemplate}
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleCreateTemplate}
                  variant="primary"
                  disabled={!templateCreationData.name || !templateCreationData.content || creatingTemplate}
                  loading={creatingTemplate}
                >
                  {creatingTemplate ? 'Creating...' : 'Create Template'}
                </Button>
              </SpaceBetween>
            </Box>
          }
        >
          <SpaceBetween size="l">
            <FormField
              label="Template Name"
              constraintText="Required"
              description="Enter a unique template name"
            >
              <Input
                value={templateCreationData.name}
                onChange={({ detail }) => setTemplateCreationData(prev => ({ ...prev, name: detail.value }))}
                placeholder="Enter a unique template name..."
              />
            </FormField>

            <FormField
              label="Description"
              description="Brief description of this template (optional)"
            >
              <Input
                value={templateCreationData.description}
                onChange={({ detail }) => setTemplateCreationData(prev => ({ ...prev, description: detail.value }))}
                placeholder="Brief description of this template (optional)..."
              />
            </FormField>

            <FormField
              label="Template Content"
              constraintText="Required"
              description="Enter the system prompt content"
            >
              <Textarea
                value={templateCreationData.content}
                onChange={({ detail }) => setTemplateCreationData(prev => ({ ...prev, content: detail.value }))}
                placeholder="Enter the system prompt content here..."
                rows={8}
              />
            </FormField>

            {error && (
              <Alert type="error" dismissible onDismiss={() => setError(null)}>
                {error}
              </Alert>
            )}
          </SpaceBetween>
        </Modal>
      )}

      {/* Template Preview Modal */}
      {showPromptPreviewModal && (
        <Modal
          visible={showPromptPreviewModal}
          onDismiss={() => setShowPromptPreviewModal(false)}
          header="👁️ Template Preview"
          size="large"
          footer={
            <Box float="right">
              <Button
                onClick={() => setShowPromptPreviewModal(false)}
                variant="primary"
              >
                Close Preview
              </Button>
            </Box>
          }
        >
          <SpaceBetween size="l">
            {(() => {
              const preview = getSelectedTemplatePreview();
              if (!preview) {
                return (
                  <Box textAlign="center" padding="xl" color="text-body-secondary">
                    No template selected for preview.
                  </Box>
                );
              }

              return (
                <SpaceBetween size="l">
                  <Container
                    header={
                      <Header variant="h3" description={preview.description}>
                        {preview.name}
                      </Header>
                    }
                  >
                    <KeyValuePairs
                      columns={2}
                      items={[
                        {
                          label: 'Source',
                          value: <Badge color="blue">{preview.source}</Badge>
                        },
                        {
                          label: 'Content Length',
                          value: `${preview.content.length} characters`
                        }
                      ]}
                    />
                  </Container>

                  <FormField label="Template Content">
                    <Textarea
                      value={preview.content}
                      readOnly
                      rows={12}
                    />
                  </FormField>

                  {preview.content === 'Content will be loaded when selected' && (
                    <Alert type="info" header="Note">
                      <Box variant="p">
                        This template's content will be automatically loaded when you select it from the dropdown.
                      </Box>
                    </Alert>
                  )}
                </SpaceBetween>
              );
            })()}
          </SpaceBetween>
        </Modal>
      )}

      {/* MEALS: Comprehensive Help Panel */}
      {showHelpPanel && (
        <HelpPanel
          header={
            <Header
              variant="h2"
              actions={
                <Button
                  iconName="close"
                  variant="icon"
                  onClick={() => setShowHelpPanel(false)}
                  ariaLabel="Close help panel"
                />
              }
            >
              Agent Configuration Help
            </Header>
          }
          visible={showHelpPanel}
          onDismiss={() => setShowHelpPanel(false)}
        >
          <SpaceBetween size="l">
            {/* Help Topic Navigation */}
            <Container header={<Header variant="h3">Help Topics</Header>}>
              <SpaceBetween size="s">
                {Object.entries(helpContent.meals).map(([key, meal]) => (
                  <Button
                    key={key}
                    variant={currentHelpTopic === key ? "primary" : "normal"}
                    onClick={() => setCurrentHelpTopic(key)}
                    fullWidth
                  >
                    {meal.title}
                  </Button>
                ))}
              </SpaceBetween>
            </Container>

            {/* Current Help Content */}
            {(() => {
              const helpMeal = getHelpMeal(currentHelpTopic);
              if (!helpMeal) return null;

              return (
                <Container
                  header={
                    <Header variant="h3" description="Comprehensive documentation and guidance">
                      {helpMeal.title}
                    </Header>
                  }
                >
                  <SpaceBetween size="l">
                    {helpMeal.sections.map((section, index) => (
                      <ExpandableSection
                        key={index}
                        headerText={section.heading}
                        defaultExpanded={index === 0}
                      >
                        <SpaceBetween size="s">
                          {Array.isArray(section.content) ? (
                            section.content.map((item, itemIndex) => (
                              <Box key={itemIndex} variant="p" color="text-body-secondary">
                                {item}
                              </Box>
                            ))
                          ) : (
                            <Box variant="p" color="text-body-secondary">
                              {section.content}
                            </Box>
                          )}
                        </SpaceBetween>
                      </ExpandableSection>
                    ))}
                  </SpaceBetween>
                </Container>
              );
            })()}

            {/* Quick Links */}
            <Container header={<Header variant="h3">Quick Actions</Header>}>
              <SpaceBetween direction="horizontal" size="s">
                <Button
                  iconName="status-info"
                  onClick={() => setCurrentHelpTopic('best_practices')}
                >
                  Best Practices
                </Button>
                <Button
                  iconName="notification"
                  onClick={() => setCurrentHelpTopic('troubleshooting')}
                >
                  Troubleshooting
                </Button>
                <Button
                  iconName="settings"
                  onClick={() => setCurrentHelpTopic('getting_started')}
                >
                  Getting Started
                </Button>
              </SpaceBetween>
            </Container>
          </SpaceBetween>
        </HelpPanel>
      )}
    </>
  );
};

export default AgentWizard;
