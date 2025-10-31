import React from 'react';
import { useTranslation } from 'react-i18next';

const AgentSelection = ({ availableAgents, currentAgent, onAgentSelect, agentConfig, onConfigUpdate, editMode, widgetKeySuffix }) => {
  const { t } = useTranslation();
  
  const handleAgentChange = (e) => {
    const selectedAgent = e.target.value;
    if (editMode && onAgentSelect) {
      onAgentSelect(selectedAgent);
    }
  };

  return (
    <div>
      <div className="form-group">
        <label htmlFor={`agent-select-${widgetKeySuffix}`}>{t('agent_selection.ui.select_agent')}</label>
        <select
          id={`agent-select-${widgetKeySuffix}`}
          value={currentAgent || ''}
          onChange={handleAgentChange}
          disabled={!editMode}
        >
          <option value="">{t('agent_selection.ui.select_agent_placeholder')}</option>
          {availableAgents.map(agent => (
            <option key={agent} value={agent}>
              {agent}
            </option>
          ))}
        </select>
        {(!availableAgents || availableAgents.length === 0) && (
          <div className="info-message">
            <small>{t('agent_selection.ui.no_agents_available')}</small>
          </div>
        )}
      </div>

      {/* Agent Model Information */}
      {agentConfig.model_id && (
        <div className="form-group">
          <label>{t('agent_selection.ui.model')}</label>
          <div className="info-value">
            {agentConfig.model_id}
          </div>
        </div>
      )}
    </div>
  );
};

export default AgentSelection;
