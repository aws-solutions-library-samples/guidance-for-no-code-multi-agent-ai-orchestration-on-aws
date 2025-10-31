import React, { useState, useEffect } from 'react';
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
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Spinner from '@cloudscape-design/components/spinner';
import Cards from '@cloudscape-design/components/cards';
import Badge from '@cloudscape-design/components/badge';
import Toggle from '@cloudscape-design/components/toggle';
import Tabs from '@cloudscape-design/components/tabs';
import Expandable from '@cloudscape-design/components/expandable-section';
import KeyValuePairs from '@cloudscape-design/components/key-value-pairs';
import configService from '../services/configuration';
import { getHelpBite } from './HelpContent';
import Link from '@cloudscape-design/components/link';

// AWS Foundation ToolManager Implementation
const ToolManager = ({ 
  agentData, 
  updateAgentData, 
  componentType = 'tools', 
  isEnabled = false 
}) => {
  const [toolCategories, setToolCategories] = useState({});
  const [availableTools, setAvailableTools] = useState({});
  const [selectedTools, setSelectedTools] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [activeTabId, setActiveTabId] = useState('builtin');
  const [expandedTools, setExpandedTools] = useState(new Set());

  // Load tool categories and available tools on component mount
  useEffect(() => {
    if (isEnabled) {
      loadToolData();
    }
  }, [isEnabled]);

  // Parse existing tools from agentData when component loads
  useEffect(() => {
    if (isEnabled && Object.keys(availableTools).length > 0) {
      parseExistingTools().catch(err => {setError(`Failed to load existing tool configurations: ${err.message}`);
      });
    }
  }, [isEnabled, availableTools, agentData]);

  const loadToolData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load tool categories
      const categories = await configService.getToolCategories();
      setToolCategories(categories);

      // Load available tools for each category
      const toolsByCategory = {};
      for (const categoryName of Object.keys(categories)) {
        try {
          const categoryResponse = await configService.getAvailableToolsByCategory(categoryName);
          // Handle different response structures
          let tools = [];
          if (Array.isArray(categoryResponse)) {
            tools = categoryResponse;
          } else if (categoryResponse && Array.isArray(categoryResponse.tools)) {
            tools = categoryResponse.tools;
          } else if (categoryResponse && typeof categoryResponse === 'object') {
            // Handle case where response is an object with tool names as keys
            tools = Object.entries(categoryResponse).map(([key, value]) => {
              if (typeof value === 'object' && value !== null) {
                return {
                  name: key,
                  label: value.label || key,
                  description: value.description || `${key} tool`
                };
              }
              return {
                name: key,
                label: key,
                description: `${key} tool`
              };
            });
          }
          
          toolsByCategory[categoryName] = tools;
        } catch (err) {toolsByCategory[categoryName] = [];
        }
      }
      setAvailableTools(toolsByCategory);

    } catch (err) {
      setError(`Failed to load tool data: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const parseExistingTools = async () => {
    const existingTools = [];

    // Parse builtin tools from the current agentData format
    const builtinTools = ['http_request', 'use_aws', 'load_tool', 'mcp_client', 'retrieve'];
    builtinTools.forEach(toolName => {
      const toolKey = `${componentType}_builtin_${toolName}_enabled`;
      if (agentData[toolKey]) {
        const toolConfig = {};
        // Extract configuration for this tool
        Object.keys(agentData).forEach(key => {
          if (key.startsWith(`${componentType}_builtin_${toolName}_`) && key !== toolKey) {
            const configKey = key.replace(`${componentType}_builtin_${toolName}_`, '');
            toolConfig[configKey] = agentData[key];
          }
        });

        existingTools.push({
          id: `builtin_${toolName}`,
          category: 'builtin',
          name: toolName,
          displayName: toolName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
          config: toolConfig,
          enabled: true,
          schema: null
        });
      }
    });

    // Parse MCP tools
    const mcpEnabled = agentData[`${componentType}_mcp_enabled`];
    const mcpServers = agentData[`${componentType}_mcp_servers`];
    if (mcpEnabled && mcpServers) {
      try {
        const servers = JSON.parse(mcpServers);
        if (Array.isArray(servers)) {
          servers.forEach((server, index) => {
            existingTools.push({
              id: `mcp_${server.name || index}`,
              category: 'mcp',
              name: server.name || `mcp_server_${index}`,
              displayName: server.name || `MCP Server ${index + 1}`,
              config: {
                url: server.url,
                auth_type: server.auth_type || 'none',
                auth_token: server.auth_token || '',
                description: server.description || ''
              },
              enabled: server.enabled !== false
            });
          });
        }
      } catch (err) {}
    }

    // Parse custom tools
    const customEnabled = agentData[`${componentType}_custom_enabled`];
    const customModules = agentData[`${componentType}_custom_tool_modules`];
    if (customEnabled && customModules) {
      try {
        const modules = JSON.parse(customModules);
        if (Array.isArray(modules)) {
          modules.forEach((module, index) => {
            existingTools.push({
              id: `custom_${module.name || index}`,
              category: 'custom',
              name: module.name || `custom_tool_${index}`,
              displayName: module.name || `Custom Tool ${index + 1}`,
              config: module.config || {},
              enabled: module.enabled !== false
            });
          });
        }
      } catch (err) {}
    }

    // Load schemas for all existing tools
    for (const tool of existingTools) {
      try {
        const toolSchema = await configService.getToolSchema(tool.category, tool.name);
        tool.schema = toolSchema;
      } catch (err) {tool.schema = { config_fields: [] };
      }
    }

    setSelectedTools(existingTools);
  };

  const addTool = async (category, toolName) => {
    try {
      // Get tool schema for configuration
      const toolSchema = await configService.getToolSchema(category, toolName);
      
      const newTool = {
        id: `${category}_${toolName}_${Date.now()}`,
        category,
        name: toolName,
        displayName: toolSchema.label || toolName.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
        config: {},
        enabled: true,
        schema: toolSchema
      };

      // Set default values from schema
      if (toolSchema.config_fields) {
        toolSchema.config_fields.forEach(field => {
          const defaultVal = field.default_value !== undefined ? field.default_value : field.default;
          if (defaultVal !== undefined) {
            newTool.config[field.name] = defaultVal;
          }
        });
      }

      const updatedTools = [...selectedTools, newTool];
      setSelectedTools(updatedTools);
      updateAgentDataFromTools(updatedTools);
      
      // Auto-expand the newly added tool for configuration
      setExpandedTools(prev => new Set([...prev, newTool.id]));

    } catch (err) {
      setError(`Failed to add tool: ${err.message}`);
    }
  };

  const removeTool = (toolId) => {
    const updatedTools = selectedTools.filter(tool => tool.id !== toolId);
    setSelectedTools(updatedTools);
    updateAgentDataFromTools(updatedTools);
    
    // Remove from expanded tools
    setExpandedTools(prev => {
      const newSet = new Set(prev);
      newSet.delete(toolId);
      return newSet;
    });
  };

  const toggleTool = (toolId) => {
    const updatedTools = selectedTools.map(tool => 
      tool.id === toolId ? { ...tool, enabled: !tool.enabled } : tool
    );
    setSelectedTools(updatedTools);
    updateAgentDataFromTools(updatedTools);
  };

  const toggleToolExpansion = (toolId) => {
    setExpandedTools(prev => {
      const newSet = new Set(prev);
      if (newSet.has(toolId)) {
        newSet.delete(toolId);
      } else {
        newSet.add(toolId);
      }
      return newSet;
    });
  };

  const updateToolConfig = (toolId, configKey, value) => {
    const updatedTools = selectedTools.map(tool => 
      tool.id === toolId 
        ? { ...tool, config: { ...tool.config, [configKey]: value } }
        : tool
    );
    setSelectedTools(updatedTools);
    updateAgentDataFromTools(updatedTools);
  };

  const updateAgentDataFromTools = (tools) => {
    const updates = {};

    // Set the main tools_enabled flag based on whether any tools are selected
    updates[`${componentType}_enabled`] = tools.length > 0;

    // Clear all existing tool configuration
    Object.keys(agentData).forEach(key => {
      if (key.startsWith(`${componentType}_builtin_`) || 
          key.startsWith(`${componentType}_mcp_`) || 
          key.startsWith(`${componentType}_custom_`)) {
        updates[key] = undefined;
      }
    });

    // Group tools by category
    const toolsByCategory = tools.reduce((acc, tool) => {
      if (!acc[tool.category]) acc[tool.category] = [];
      acc[tool.category].push(tool);
      return acc;
    }, {});

    // Update builtin tools
    const builtinTools = toolsByCategory.builtin || [];
    builtinTools.forEach(tool => {
      const baseKey = `${componentType}_builtin_${tool.name}`;
      updates[`${baseKey}_enabled`] = tool.enabled;
      
      // Set configuration fields
      Object.entries(tool.config).forEach(([configKey, value]) => {
        updates[`${baseKey}_${configKey}`] = value;
      });
    });

    // Update MCP tools
    const mcpTools = toolsByCategory.mcp || [];
    updates[`${componentType}_mcp_enabled`] = mcpTools.length > 0;
    if (mcpTools.length > 0) {
      const mcpServers = mcpTools.map(tool => ({
        name: tool.name,
        url: tool.config.url || '',
        auth_type: tool.config.auth_type || 'none',
        auth_token: tool.config.auth_token || '',
        description: tool.config.description || '',
        enabled: tool.enabled
      }));
      updates[`${componentType}_mcp_servers`] = JSON.stringify(mcpServers, null, 2);
    }

    // Update custom tools
    const customTools = toolsByCategory.custom || [];
    updates[`${componentType}_custom_enabled`] = customTools.length > 0;
    if (customTools.length > 0) {
      const customModules = customTools.map(tool => ({
        name: tool.name,
        description: tool.config.description || `Custom tool: ${tool.name}`,
        enabled: tool.enabled,
        config: tool.config
      }));
      updates[`${componentType}_custom_tool_modules`] = JSON.stringify(customModules, null, 2);
    }

    // Set provider based on what tools are selected
    if (mcpTools.length > 0) {
      updates[`${componentType}_provider`] = 'mcp';
    } else if (customTools.length > 0) {
      updates[`${componentType}_provider`] = 'custom';
    } else if (builtinTools.length > 0) {
      updates[`${componentType}_provider`] = 'builtin';
    }

    updateAgentData(updates);
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
      
      // Authentication Environment Variables (SECURITY ISSUE FIX)
      'auth environment variable', 'auth_environment_variable',
      'auth environment', 'authentication environment',
      'auth env var', 'auth_env_var',
      
      // Headers (can contain sensitive auth tokens)
      'headers', 'header', 'http_headers', 'http headers',
      'default headers', 'default_headers',
      'request headers', 'request_headers',
      'authorization headers', 'auth headers',
      
      // Environment Variables (often contain sensitive data)
      'environment variable', 'environment_variable', 'env_var', 'env var',
      'environment variables', 'environment_variables', 'env_vars', 'env vars',
      
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

  const renderConfigField = (tool, field) => {
    const defaultVal = field.default_value !== undefined ? field.default_value : field.default;
    const value = tool.config[field.name] !== undefined ? tool.config[field.name] : (defaultVal !== undefined ? defaultVal : '');
    
    const fieldKey = `${tool.id}_${field.name}`;
    
    // Security: Check if this is a sensitive field (enhanced detection)
    const isSensitive = isSensitiveField(field.name) || 
                       field.type === 'password' || 
                       (field.label && isSensitiveField(field.label)) ||
                       (field.help_text && field.help_text.toLowerCase().includes('password')) ||
                       (field.help_text && field.help_text.toLowerCase().includes('secret'));
    
    switch (field.type) {
      case 'text':
      case 'url':
      case 'password':
      case 'None':
      case null:
      case undefined:
        return (
          <FormField
            label={field.label || field.name}
            constraintText={field.required ? "Required" : "Optional"}
            description={field.help_text}
            errorText={field.required && !value ? `${field.label || field.name} is required` : undefined}
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
                  value={value || ''}
                  onChange={({ detail }) => updateToolConfig(tool.id, field.name, detail.value)}
                  placeholder={field.placeholder || `Enter ${field.label || field.name} (hidden for security)`}
                  invalid={field.required && !value}
                  ariaLabel={`${field.label || field.name} for ${tool.displayName}`}
                />
                <Alert type="warning" header="🔒 Security Protection Active">
                  <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                    <Box variant="small">
                      Sensitive information (auth tokens, headers, environment variables) - masked for security
                    </Box>
                  </SpaceBetween>
                </Alert>
              </SpaceBetween>
            ) : (
              <Input
                type={field.type === 'url' ? 'url' : 'text'}
                value={value || ''}
                onChange={({ detail }) => updateToolConfig(tool.id, field.name, detail.value)}
                placeholder={field.placeholder || `Enter ${field.label || field.name}`}
                invalid={field.required && !value}
                ariaLabel={`${field.label || field.name} for ${tool.displayName}`}
              />
            )}
          </FormField>
        );
      
      case 'textarea':
        return (
          <FormField
            label={field.label || field.name}
            constraintText={field.required ? "Required" : "Optional"}
            description={field.help_text}
            info={
              <Link variant="info" onFollow={() => {}}>
                {getHelpBite(field.name) || "Additional information"}
              </Link>
            }
          >
            <Textarea
              value={value || ''}
              onChange={({ detail }) => updateToolConfig(tool.id, field.name, detail.value)}
              placeholder={field.placeholder || `Enter ${field.label || field.name}`}
              rows={field.rows || 3}
              ariaLabel={`${field.label || field.name} for ${tool.displayName}`}
            />
          </FormField>
        );
      
      case 'select':
        return (
          <FormField
            label={field.label || field.name}
            constraintText={field.required ? "Required" : "Optional"}
            description={field.help_text}
          >
            <Select
              selectedOption={value ? 
                field.options?.find(opt => opt.value === value) || { label: value, value: value } : null}
              onChange={({ detail }) => updateToolConfig(tool.id, field.name, detail.selectedOption.value)}
              options={field.options?.map(option => ({
                label: option.label || option.value,
                value: option.value
              })) || []}
              placeholder={`Select ${field.label || field.name}`}
              ariaLabel={`${field.label || field.name} for ${tool.displayName}`}
            />
          </FormField>
        );
      
      case 'number':
        return (
          <FormField
            label={field.label || field.name}
            constraintText={field.required ? "Required" : "Optional"}
            description={field.help_text}
          >
            <Input
              type="number"
              value={value || ''}
              onChange={({ detail }) => {
                const numValue = parseFloat(detail.value);
                updateToolConfig(tool.id, field.name, isNaN(numValue) ? detail.value : numValue);
              }}
              placeholder={field.placeholder || `Enter ${field.label || field.name}`}
              ariaLabel={`${field.label || field.name} for ${tool.displayName}`}
            />
          </FormField>
        );
      
      case 'boolean':
      case 'checkbox':
        return (
          <FormField
            label={field.label || field.name}
            description={field.help_text}
          >
            <Toggle
              onChange={({ detail }) => updateToolConfig(tool.id, field.name, detail.checked)}
              checked={value === true || value === 'true'}
              ariaLabel={`${field.label || field.name} for ${tool.displayName}`}
            >
              Enable {field.label || field.name}
            </Toggle>
          </FormField>
        );
      
      default:
        return (
          <FormField
            label={field.label || field.name}
            constraintText={field.required ? "Required" : "Optional"}
            description={field.help_text}
          >
            {isSensitive ? (
              <SpaceBetween size="s">
                <Input
                  type="password"
                  value={value || ''}
                  onChange={({ detail }) => updateToolConfig(tool.id, field.name, detail.value)}
                  placeholder={field.placeholder || `Enter ${field.label || field.name} (hidden for security)`}
                  ariaLabel={`${field.label || field.name} for ${tool.displayName}`}
                />
                <Alert type="warning" header="🔒 Security Protection Active">
                  <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                    <Box variant="small">
                      Sensitive information (auth tokens, headers, environment variables) - masked for security
                    </Box>
                  </SpaceBetween>
                </Alert>
              </SpaceBetween>
            ) : (
              <Input
                value={value || ''}
                onChange={({ detail }) => updateToolConfig(tool.id, field.name, detail.value)}
                placeholder={field.placeholder || `Enter ${field.label || field.name}`}
                ariaLabel={`${field.label || field.name} for ${tool.displayName}`}
              />
            )}
          </FormField>
        );
    }
  };

  const renderToolCard = (tool) => {
    const isExpanded = expandedTools.has(tool.id);
    
    return {
      name: tool.displayName,
      type: tool.category,
      description: `${tool.category} tool`,
      status: tool.enabled ? 'active' : 'inactive'
    };
  };

  const getToolsByCategory = (category) => {
    return selectedTools.filter(tool => tool.category === category);
  };

  const getCategoryStatus = (category) => {
    const categoryTools = getToolsByCategory(category);
    if (categoryTools.length === 0) return { type: 'pending', text: 'No tools configured' };
    const enabledCount = categoryTools.filter(tool => tool.enabled).length;
    if (enabledCount === 0) return { type: 'warning', text: `${categoryTools.length} tools (all disabled)` };
    if (enabledCount === categoryTools.length) return { type: 'success', text: `${enabledCount} tools active` };
    return { type: 'info', text: `${enabledCount}/${categoryTools.length} tools active` };
  };

  if (!isEnabled) {
    return null;
  }

  if (loading) {
    return (
      <Container>
        <Box textAlign="center" padding="xl">
          <SpaceBetween size="m" alignItems="center">
            <Spinner size="large" />
            <StatusIndicator type="loading">
              Loading tool management interface...
            </StatusIndicator>
          </SpaceBetween>
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <Alert
          type="error"
          header="Tool Manager Error"
          action={
            <Button onClick={loadToolData} iconName="refresh">
              Retry
            </Button>
          }
        >
          {error}
        </Alert>
      </Container>
    );
  }

  const tabItems = Object.entries(toolCategories).map(([categoryKey, category]) => {
    const categoryStatus = getCategoryStatus(categoryKey);
    return {
      label: category.label,
      id: categoryKey,
      content: (
        <SpaceBetween size="l">
          {/* Category Description */}
          <Box variant="p" color="text-body-secondary">
            {category.description}
          </Box>

          {/* Selected Tools for this Category */}
          {getToolsByCategory(categoryKey).length > 0 && (
            <Container
              header={
                <Header 
                  variant="h4"
                  counter={`(${getToolsByCategory(categoryKey).length})`}
                  description="Configured tools in this category"
                >
                  Selected {category.label} Tools
                </Header>
              }
            >
              <Cards
                cardDefinition={{
                  header: item => (
                    <SpaceBetween direction="horizontal" size="s" alignItems="center">
                      <Box variant="strong">{item.displayName}</Box>
                      <Badge color={item.enabled ? 'green' : 'grey'}>
                        {item.enabled ? 'Active' : 'Disabled'}
                      </Badge>
                    </SpaceBetween>
                  ),
                  sections: [
                    {
                      id: "config",
                      content: item => (
                        <SpaceBetween size="m">
                          <SpaceBetween direction="horizontal" size="s">
                            <Toggle
                              onChange={() => toggleTool(item.id)}
                              checked={item.enabled}
                              ariaLabel={`Enable ${item.displayName}`}
                            >
                              Enabled
                            </Toggle>
                            <Button
                              variant="icon"
                              iconName="settings"
                              onClick={() => toggleToolExpansion(item.id)}
                              ariaLabel={`Configure ${item.displayName}`}
                            />
                            <Button
                              variant="icon"
                              iconName="close"
                              onClick={() => removeTool(item.id)}
                              ariaLabel={`Remove ${item.displayName}`}
                            />
                          </SpaceBetween>
                          
                          {expandedTools.has(item.id) && item.schema && (
                            <Expandable
                              headerText="Tool Configuration"
                              defaultExpanded={true}
                            >
                              <SpaceBetween size="m">
                                {item.schema.config_fields?.map(field => (
                                  <div key={field.name}>
                                    {renderConfigField(item, field)}
                                  </div>
                                ))}
                                {(!item.schema.config_fields || item.schema.config_fields.length === 0) && (
                                  <Box variant="p" color="text-body-secondary">
                                    This tool has no configuration options.
                                  </Box>
                                )}
                              </SpaceBetween>
                            </Expandable>
                          )}
                        </SpaceBetween>
                      )
                    }
                  ]
                }}
                items={getToolsByCategory(categoryKey)}
                trackBy="id"
                empty={
                  <Box textAlign="center" color="inherit">
                    <SpaceBetween size="m">
                      <Box variant="strong" textAlign="center" color="inherit">
                        No {category.label} tools configured
                      </Box>
                      <Box variant="p" textAlign="center" color="inherit">
                        Add tools from the available options below
                      </Box>
                    </SpaceBetween>
                  </Box>
                }
              />
            </Container>
          )}

          {/* Available Tools for this Category */}
          <Container
            header={
              <Header 
                variant="h4"
                description={`Add ${category.label} tools to your agent`}
              >
                Available {category.label} Tools
              </Header>
            }
          >
            {(availableTools[categoryKey] || []).length === 0 ? (
              <Box textAlign="center" padding="l">
                <StatusIndicator type="warning">
                  No {category.label} tools available
                </StatusIndicator>
              </Box>
            ) : (
              <Cards
                cardDefinition={{
                  header: item => item.label || item.name,
                  sections: [
                    {
                      id: "description",
                      content: item => (
                        <SpaceBetween size="s">
                          <Box variant="p">{item.description}</Box>
                          <Button
                            onClick={() => addTool(categoryKey, item.name)}
                            disabled={selectedTools.some(selectedTool => 
                              selectedTool.category === categoryKey && selectedTool.name === item.name
                            )}
                            iconName="add-plus"
                            variant="primary"
                            size="small"
                          >
                            {selectedTools.some(selectedTool => 
                              selectedTool.category === categoryKey && selectedTool.name === item.name
                            ) ? 'Added' : 'Add Tool'}
                          </Button>
                        </SpaceBetween>
                      )
                    }
                  ]
                }}
                items={availableTools[categoryKey] || []}
                trackBy="name"
                cardsPerRow={[
                  { cards: 1 },
                  { minWidth: 500, cards: 2 },
                  { minWidth: 800, cards: 3 }
                ]}
              />
            )}
          </Container>
        </SpaceBetween>
      )
    };
  });

  return (
    <Container
      header={
        <Header 
          variant="h3"
          counter={selectedTools.length > 0 ? `(${selectedTools.length} tools)` : undefined}
          description="Add and configure tools to enhance your agent's capabilities"
          info={
            <Box variant="small" color="text-body-secondary">
              Tools extend your agent with additional functions and integrations
            </Box>
          }
        >
          Tool Management
        </Header>
      }
    >
      <SpaceBetween size="l">
        {selectedTools.length > 0 && (
          <Alert type="info" header="Tool Configuration Summary">
            <SpaceBetween size="s">
              {Object.entries(toolCategories).map(([categoryKey, category]) => {
                const status = getCategoryStatus(categoryKey);
                return (
                  <SpaceBetween key={categoryKey} direction="horizontal" size="s" alignItems="center">
                    <Box variant="strong">{category.label}:</Box>
                    <StatusIndicator type={status.type} iconAriaLabel={status.type}>
                      {status.text}
                    </StatusIndicator>
                  </SpaceBetween>
                );
              })}
            </SpaceBetween>
          </Alert>
        )}

        <Tabs
          tabs={tabItems}
          activeTabId={activeTabId}
          onChange={({ detail }) => setActiveTabId(detail.activeTabId)}
          ariaLabel="Tool categories"
        />
      </SpaceBetween>
    </Container>
  );
};

export default ToolManager;
