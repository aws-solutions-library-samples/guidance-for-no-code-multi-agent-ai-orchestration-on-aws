import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import './SystemPromptManager.css';

const SystemPromptManager = ({ agentConfig, onConfigUpdate, editMode, widgetKeySuffix }) => {
  const { t } = useTranslation();
  const [mode, setMode] = useState('select'); // 'select' or 'create' or 'edit'
  const [availableTemplates, setAvailableTemplates] = useState([]);
  const [crossAgentTemplates, setCrossAgentTemplates] = useState([]);
  const [globalTemplates, setGlobalTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [customPrompt, setCustomPrompt] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTemplate, setNewTemplate] = useState({
    name: '',
    description: '',
    content: '',
    category: 'custom'
  });
  const [loading, setLoading] = useState(false);
  const [previewTemplate, setPreviewTemplate] = useState(null);

  // Load available templates on component mount
  useEffect(() => {
    if (editMode) {
      loadAvailableTemplates();
    }
  }, [editMode, agentConfig.agent_name]);

  // Initialize with current system prompt
  useEffect(() => {
    if (agentConfig.system_prompt) {
      setCustomPrompt(agentConfig.system_prompt);
      // Try to match with existing template
      if (agentConfig.system_prompt_name) {
        setSelectedTemplate(agentConfig.system_prompt_name);
        setMode('select');
      } else {
        setMode('select'); // Default to select mode but allow custom
      }
    }
  }, [agentConfig.system_prompt, agentConfig.system_prompt_name]);

  const loadAvailableTemplates = async () => {
    if (!agentConfig.agent_name) return;
    
    setLoading(true);
    try {
      // Load templates from multiple sources
      const [agentTemplates, globalTemplates, crossAgentTemplates] = await Promise.all([
        fetch(`/api/config/system-prompts/available/${agentConfig.agent_name}`).then(r => r.json()),
        fetch('/api/config/system-prompts/templates').then(r => r.json()),
        fetch('/api/config/system-prompts/all-across-agents').then(r => r.json())
      ]);

      setAvailableTemplates(agentTemplates.prompts || []);
      setGlobalTemplates(globalTemplates.templates || []);
      setCrossAgentTemplates(crossAgentTemplates.prompts || []);
    } catch (error) {} finally {
      setLoading(false);
    }
  };

  const handleModeChange = (newMode) => {
    setMode(newMode);
    if (newMode === 'create') {
      setShowCreateModal(true);
    }
  };

  const handleTemplateSelect = async (templateName, source = 'agent') => {
    setSelectedTemplate(templateName);
    
    if (templateName === '') {
      // Custom mode
      setMode('edit');
      onConfigUpdate({ 
        system_prompt: customPrompt,
        system_prompt_name: null
      });
      return;
    }

    try {
      let contentUrl;
      if (source === 'agent') {
        contentUrl = `/api/config/system-prompts/content/${agentConfig.agent_name}/${templateName}`;
      } else if (source === 'global') {
        contentUrl = `/api/config/system-prompts/templates/${templateName}`;
      } else if (source === 'cross-agent') {
        // Handle cross-agent template loading
        const template = crossAgentTemplates.find(t => t.name === templateName);
        if (template) {
          contentUrl = `/api/config/system-prompts/content/${template.agent}/${templateName}`;
        }
      }

      if (contentUrl) {
        const response = await fetch(contentUrl);
        const data = await response.json();
        
        setCustomPrompt(data.content || '');
        onConfigUpdate({ 
          system_prompt: data.content || '',
          system_prompt_name: templateName
        });
      }
    } catch (error) {}
  };

  const handleCustomPromptChange = (e) => {
    const value = e.target.value;
    setCustomPrompt(value);
    if (mode === 'edit') {
      onConfigUpdate({ 
        system_prompt: value,
        system_prompt_name: null // Clear template name for custom content
      });
    }
  };

  const handleCreateTemplate = async () => {
    if (!newTemplate.name.trim() || !newTemplate.content.trim()) {// TODO: Replace with proper UI error state/notification instead of alert
      return;
    }

    try {
      const response = await fetch(`/api/config/system-prompts/create/${agentConfig.agent_name}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          prompt_name: newTemplate.name.trim(),
          prompt_content: newTemplate.content.trim(),
          description: newTemplate.description.trim(),
          category: newTemplate.category
        }),
      });

      if (response.ok) {
        // Success - refresh templates and select the new one
        await loadAvailableTemplates();
        setSelectedTemplate(newTemplate.name.trim());
        setCustomPrompt(newTemplate.content.trim());
        onConfigUpdate({
          system_prompt: newTemplate.content.trim(),
          system_prompt_name: newTemplate.name.trim()
        });
        
        // Reset and close modal
        setNewTemplate({ name: '', description: '', content: '', category: 'custom' });
        setShowCreateModal(false);
        setMode('select');
      } else {
        const errorData = await response.json();// TODO: Replace with proper UI error state/notification instead of alert
      }
    } catch (error) {// TODO: Replace with proper UI error state/notification instead of alert
    }
  };

  const handlePreview = async (templateName, source = 'agent') => {
    try {
      let contentUrl;
      if (source === 'agent') {
        contentUrl = `/api/config/system-prompts/content/${agentConfig.agent_name}/${templateName}`;
      } else if (source === 'global') {
        contentUrl = `/api/config/system-prompts/templates/${templateName}`;
      } else if (source === 'cross-agent') {
        const template = crossAgentTemplates.find(t => t.name === templateName);
        if (template) {
          contentUrl = `/api/config/system-prompts/content/${template.agent}/${templateName}`;
        }
      }

      if (contentUrl) {
        const response = await fetch(contentUrl);
        const data = await response.json();
        setPreviewTemplate({
          name: templateName,
          content: data.content || '',
          description: data.description || '',
          source: source
        });
      }
    } catch (error) {}
  };

  const renderTemplateOptions = () => {
    const allTemplates = [];
    
    // Add agent-specific templates
    if (availableTemplates.length > 0) {
      allTemplates.push({
        label: `${agentConfig.agent_name || 'Current'} Agent Templates`,
        options: availableTemplates.map(template => ({
          value: template.name,
          label: template.name,
          description: template.description,
          source: 'agent'
        }))
      });
    }

    // Add global templates
    if (globalTemplates.length > 0) {
      allTemplates.push({
        label: 'Global Templates',
        options: globalTemplates.map(template => ({
          value: template.name,
          label: template.name,
          description: template.description,
          source: 'global'
        }))
      });
    }

    // Add cross-agent templates
    if (crossAgentTemplates.length > 0) {
      const groupedByAgent = crossAgentTemplates.reduce((acc, template) => {
        if (!acc[template.agent]) acc[template.agent] = [];
        acc[template.agent].push(template);
        return acc;
      }, {});

      Object.entries(groupedByAgent).forEach(([agentName, templates]) => {
        if (agentName !== agentConfig.agent_name) { // Don't duplicate current agent templates
          allTemplates.push({
            label: `From ${agentName} Agent`,
            options: templates.map(template => ({
              value: template.name,
              label: template.name,
              description: template.description,
              source: 'cross-agent'
            }))
          });
        }
      });
    }

    return allTemplates;
  };

  if (!editMode) {
    return (
      <div className="system-prompt-manager readonly">
        <div className="form-group">
          <label>{t('prompts.system.system_prompt')}</label>
          <div className="readonly-prompt">
            {agentConfig.system_prompt_name && (
              <div className="template-info">
                <strong>{t('prompts.system.template')}</strong> {agentConfig.system_prompt_name}
              </div>
            )}
            <div className="prompt-content">
              {agentConfig.system_prompt || 'No system prompt configured'}
            </div>
          </div>
        </div>
      </div>
    );
  }

  const templateOptions = renderTemplateOptions();

  return (
    <div className="system-prompt-manager">
      <div className="prompt-header">
          <label>{t('prompts.system.system_prompt_config')}</label>
        <div className="mode-selector">
          <button
            type="button"
            className={`mode-btn ${mode === 'select' ? 'active' : ''}`}
            onClick={() => handleModeChange('select')}
          >
            {t('prompts.system.select_template')}
          </button>
          <button
            type="button"
            className={`mode-btn ${mode === 'edit' ? 'active' : ''}`}
            onClick={() => handleModeChange('edit')}
          >
            {t('prompts.system.custom_prompt')}
          </button>
          <button
            type="button"
            className="mode-btn create-btn"
            onClick={() => handleModeChange('create')}
          >
            + {t('prompts.system.create_new_template')}
          </button>
        </div>
      </div>

      {mode === 'select' && (
        <div className="template-selection">
          <div className="form-group">
            <label htmlFor={`template-select-${widgetKeySuffix}`}>{t('agent.management.choose_template')}</label>
            <select
              id={`template-select-${widgetKeySuffix}`}
              value={selectedTemplate}
              onChange={(e) => {
                const [value, source] = e.target.value.split('|');
                handleTemplateSelect(value, source || 'agent');
              }}
              disabled={loading}
            >
              <option value="">{t('prompts.system.custom_write_own')}</option>
              {templateOptions.map((group, groupIndex) => (
                <optgroup key={groupIndex} label={group.label}>
                  {group.options.map((option, optionIndex) => (
                    <option
                      key={optionIndex}
                      value={`${option.value}|${option.source}`}
                    >
                      {option.label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>

          {templateOptions.length > 0 && (
            <div className="template-preview-section">
              <div className="template-grid">
                {templateOptions.map((group, groupIndex) => (
                  <div key={groupIndex} className="template-group">
                    <h4>{group.label}</h4>
                    <div className="template-cards">
                      {group.options.slice(0, 3).map((template, templateIndex) => (
                        <div
                          key={templateIndex}
                          className={`template-card ${selectedTemplate === template.value ? 'selected' : ''}`}
                        >
                          <div className="card-header">
                            <h5>{template.label}</h5>
                            <div className="card-actions">
                              <button
                                type="button"
                                className="preview-btn"
                                onClick={() => handlePreview(template.value, template.source)}
                              >
                                👁 Preview
                              </button>
                              <button
                                type="button"
                                className="select-btn"
                                onClick={() => handleTemplateSelect(template.value, template.source)}
                              >
                                Select
                              </button>
                            </div>
                          </div>
                          {template.description && (
                            <p className="card-description">{template.description}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="form-group">
        <label htmlFor={`prompt-content-${widgetKeySuffix}`}>
          {selectedTemplate ? `Content (${selectedTemplate})` : 'System Prompt Content'}
        </label>
        <textarea
          id={`prompt-content-${widgetKeySuffix}`}
          value={customPrompt}
          onChange={handleCustomPromptChange}
          rows={12}
          placeholder="Enter the system prompt for the agent..."
          className={selectedTemplate ? 'template-content' : 'custom-content'}
        />
        <div className="prompt-info">
          <small>
            {selectedTemplate ? (
              <>Template: <strong>{selectedTemplate}</strong> (you can modify the content above)</>
            ) : (
              'Custom prompt - not saved as template'
            )}
          </small>
        </div>
      </div>

      {/* Create Template Modal */}
      {showCreateModal && (
        <div className="modal-overlay">
          <div className="modal">
            <div className="modal-header">
              <h3>{t('prompts.system.create_new_template')}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => {
                  setShowCreateModal(false);
                  setNewTemplate({ name: '', description: '', content: '', category: 'custom' });
                }}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>{t('agent.management.template_name_required')}</label>
                <input
                  type="text"
                  value={newTemplate.name}
                  onChange={(e) => setNewTemplate({ ...newTemplate, name: e.target.value })}
                  placeholder="e.g., 'Customer Service Assistant', 'Technical Expert'"
                />
              </div>
              <div className="form-group">
                <label>{t('common.ui.description')}</label>
                <input
                  type="text"
                  value={newTemplate.description}
                  onChange={(e) => setNewTemplate({ ...newTemplate, description: e.target.value })}
                  placeholder="Brief description of this template's purpose"
                />
              </div>
              <div className="form-group">
                <label>{t('common.ui.category')}</label>
                <select
                  value={newTemplate.category}
                  onChange={(e) => setNewTemplate({ ...newTemplate, category: e.target.value })}
                >
                  <option value="custom">{t('prompts.system.custom')}</option>
                  <option value="customer-service">{t('prompts.system.customer_service')}</option>
                  <option value="technical">{t('prompts.system.technical')}</option>
                  <option value="creative">{t('prompts.system.creative')}</option>
                  <option value="analytical">{t('prompts.system.analytical')}</option>
                </select>
              </div>
              <div className="form-group">
                <label>{t('agent.management.template_content_required')}</label>
                <textarea
                  value={newTemplate.content}
                  onChange={(e) => setNewTemplate({ ...newTemplate, content: e.target.value })}
                  rows={10}
                  placeholder="Enter the system prompt content..."
                />
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="cancel-btn"
                onClick={() => {
                  setShowCreateModal(false);
                  setNewTemplate({ name: '', description: '', content: '', category: 'custom' });
                }}
              >
                {t('common.ui.cancel')}
              </button>
              <button
                type="button"
                className="create-btn"
                onClick={handleCreateTemplate}
                disabled={!newTemplate.name.trim() || !newTemplate.content.trim()}
              >
                {t('agent.management.create_template')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {previewTemplate && (
        <div className="modal-overlay">
          <div className="modal preview-modal">
            <div className="modal-header">
              <h3>{t('common.ui.preview')}{previewTemplate.name}</h3>
              <button
                type="button"
                className="close-btn"
                onClick={() => setPreviewTemplate(null)}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              {previewTemplate.description && (
                <div className="template-description">
                  <strong>{t('common.ui.description')}</strong> {previewTemplate.description}
                </div>
              )}
              <div className="template-source">
                <strong>{t('common.ui.source')}</strong> {previewTemplate.source === 'agent' ? `${agentConfig.agent_name} Agent` : 
                                        previewTemplate.source === 'global' ? 'Global Templates' : 'Cross-Agent Templates'}
              </div>
              <div className="template-content-preview">
                <pre>{previewTemplate.content}</pre>
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="cancel-btn"
                onClick={() => setPreviewTemplate(null)}
              >
                {t('common.ui.close')}
              </button>
              <button
                type="button"
                className="select-btn"
                onClick={() => {
                  handleTemplateSelect(previewTemplate.name, previewTemplate.source);
                  setPreviewTemplate(null);
                }}
              >
                {t('prompts.system.use_this_template')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default SystemPromptManager;
