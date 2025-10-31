import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import ExpandableSection from './ExpandableSection';
import AgentSelection from './AgentSelection';
import Parameters from './Parameters';
import SystemPromptManager from './SystemPromptManager';
import Memory from './Memory';
import KnowledgeBase from './KnowledgeBase';
import Observability from './Observability';
import Guardrails from './Guardrails';
import Tools from './Tools';

const Sidebar = ({
  userEmail,
  onLogout,
  availableAgents,
  currentAgent,
  onAgentSelect,
  agentConfig,
  onConfigUpdate,
  editMode,
  onEditModeChange,
  onSaveConfig,
  onCancelConfig,
  onClearChat,
  widgetKeySuffix,
  error,
  setError
}) => {
  const { t } = useTranslation();
  const [saveMessage, setSaveMessage] = useState(null);

  const handleSaveClick = async () => {
    const result = await onSaveConfig();
    setSaveMessage(result);
    setTimeout(() => setSaveMessage(null), 3000);
  };

  const handleCancelClick = () => {
    onCancelConfig();
    setSaveMessage(null);
  };

  return (
    <div className="sidebar">
      {/* User Info Section */}
      <div className="user-info">
        <h3 style={{ margin: '0 0 0.5rem 0' }}>👤 {t('sidebar.ui.user_info')}</h3>
        <p style={{ margin: '0 0 1rem 0', fontSize: '0.9rem' }}>
          {t('auth.ui.logged_in_as')}{userEmail}
        </p>
        <button 
          className="button button-secondary" 
          style={{ width: '100%' }}
          onClick={onLogout}
        >
          🚪 {t('common.ui.logout')}
        </button>
      </div>

      <div className="divider" />

      <h2 style={{ margin: '0 0 1rem 0' }}>🔧 {t('sidebar.ui.agent_configuration')}</h2>

      {/* Edit Mode Toggle */}
      <div style={{ marginBottom: '1rem' }}>
        <label className="toggle-switch">
          <input
            type="checkbox"
            checked={editMode}
            onChange={(e) => onEditModeChange(e.target.checked)}
          />
          <span className="toggle-slider"></span>
        </label>
        <span style={{ marginLeft: '0.5rem', fontWeight: '500' }}>
          ✏️ {t('sidebar.ui.edit_mode')}
        </span>
      </div>

      {/* Display any errors */}
      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {/* Display save messages */}
      {saveMessage && (
        <div className={saveMessage.success ? 'success-message' : 'error-message'}>
          {saveMessage.message}
        </div>
      )}

      {/* Agent Selection */}
      <ExpandableSection title={t('sidebar.ui.agent_selection')} expanded={true}>
        <AgentSelection
          availableAgents={availableAgents}
          currentAgent={currentAgent}
          onAgentSelect={onAgentSelect}
          agentConfig={agentConfig}
          onConfigUpdate={onConfigUpdate}
          editMode={editMode}
          widgetKeySuffix={widgetKeySuffix}
        />
      </ExpandableSection>

      {/* Parameters */}
      <ExpandableSection title={t('sidebar.ui.parameters')}>
        <Parameters
          agentConfig={agentConfig}
          onConfigUpdate={onConfigUpdate}
          editMode={editMode}
          widgetKeySuffix={widgetKeySuffix}
        />
      </ExpandableSection>

      {/* System Prompt */}
      <ExpandableSection title={t('sidebar.ui.system_prompt')}>
        <SystemPromptManager
          agentConfig={agentConfig}
          onConfigUpdate={onConfigUpdate}
          editMode={editMode}
          widgetKeySuffix={widgetKeySuffix}
        />
      </ExpandableSection>

      {/* Memory */}
      <ExpandableSection title={t('sidebar.ui.memory')}>
        <Memory
          agentConfig={agentConfig}
          onConfigUpdate={onConfigUpdate}
          editMode={editMode}
          widgetKeySuffix={widgetKeySuffix}
        />
      </ExpandableSection>

      {/* Knowledge Base */}
      {agentConfig.knowledge_base === 'True' && (
        <ExpandableSection title={t('sidebar.ui.knowledge_base')}>
          <KnowledgeBase
            agentConfig={agentConfig}
            onConfigUpdate={onConfigUpdate}
            editMode={editMode}
            widgetKeySuffix={widgetKeySuffix}
          />
        </ExpandableSection>
      )}

      {/* Observability */}
      <ExpandableSection title={t('sidebar.ui.observability')}>
        <Observability
          agentConfig={agentConfig}
          onConfigUpdate={onConfigUpdate}
          editMode={editMode}
          widgetKeySuffix={widgetKeySuffix}
        />
      </ExpandableSection>

      {/* Guardrails */}
      <ExpandableSection title={t('sidebar.ui.guardrails')}>
        <Guardrails
          agentConfig={agentConfig}
          onConfigUpdate={onConfigUpdate}
          editMode={editMode}
          widgetKeySuffix={widgetKeySuffix}
        />
      </ExpandableSection>

      {/* Tools */}
      <ExpandableSection title={t('sidebar.ui.tools')}>
        <Tools
          agentConfig={agentConfig}
          onConfigUpdate={onConfigUpdate}
          editMode={editMode}
          widgetKeySuffix={widgetKeySuffix}
        />
      </ExpandableSection>

      <div className="divider" />

      {/* Action Buttons */}
      {editMode && (
        <div className="button-group">
          <button
            className="button button-primary"
            style={{ flex: 1 }}
            onClick={handleSaveClick}
          >
            💾 {t('sidebar.ui.save_configuration')}
          </button>
          <button
            className="button button-secondary"
            style={{ flex: 1 }}
            onClick={handleCancelClick}
          >
            ❌ {t('common.ui.cancel')}
          </button>
        </div>
      )}

      <button
        className="button button-danger"
        style={{ width: '100%', marginTop: '0.5rem' }}
        onClick={onClearChat}
      >
        🗑️ {t('sidebar.ui.clear_chat')}
      </button>
    </div>
  );
};

export default Sidebar;
