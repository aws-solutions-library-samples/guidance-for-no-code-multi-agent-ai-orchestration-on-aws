import React from 'react';
import { useTranslation } from 'react-i18next';

const Parameters = ({ agentConfig, onConfigUpdate, editMode, widgetKeySuffix }) => {
  const { t } = useTranslation();
  const handleTemperatureChange = (e) => {
    if (editMode) {
      onConfigUpdate({ temperature: parseFloat(e.target.value) });
    }
  };

  const handleTopPChange = (e) => {
    if (editMode) {
      onConfigUpdate({ top_p: parseFloat(e.target.value) });
    }
  };

  const handleThinkingTypeChange = (e) => {
    if (editMode) {
      const thinking = { ...agentConfig.thinking };
      thinking.type = e.target.value;
      onConfigUpdate({ thinking });
    }
  };

  const handleBudgetTokensChange = (e) => {
    if (editMode) {
      const thinking = { ...agentConfig.thinking };
      thinking.budget_tokens = parseInt(e.target.value);
      onConfigUpdate({ thinking });
    }
  };

  const thinking = agentConfig.thinking || {};

  return (
    <div>
      <div className="form-group">
        <label htmlFor={`temp-${widgetKeySuffix}`}>
          {t('ui.parameters.temperature')}{agentConfig.temperature || 0.7}
        </label>
        <input
          id={`temp-${widgetKeySuffix}`}
          type="range"
          min="0"
          max="2"
          step="0.1"
          value={agentConfig.temperature || 0.7}
          onChange={handleTemperatureChange}
          disabled={!editMode}
          className="range-input"
        />
      </div>

      <div className="form-group">
        <label htmlFor={`top-p-${widgetKeySuffix}`}>
          {t('ui.parameters.top_p')}{agentConfig.top_p || 0.8}
        </label>
        <input
          id={`top-p-${widgetKeySuffix}`}
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={agentConfig.top_p || 0.8}
          onChange={handleTopPChange}
          disabled={!editMode}
          className="range-input"
        />
      </div>

      {thinking && (
        <>
          <div className="form-group">
            <label htmlFor={`thinking-type-${widgetKeySuffix}`}>{t('ui.parameters.thinking')}</label>
            <select
              id={`thinking-type-${widgetKeySuffix}`}
              value={thinking.type || 'enabled'}
              onChange={handleThinkingTypeChange}
              disabled={!editMode}
            >
              <option value="enabled">{t('common.ui.enabled')}</option>
              <option value="disabled">{t('common.ui.disabled')}</option>
            </select>
          </div>

          {thinking.type === 'enabled' && (
            <div className="form-group">
              <label htmlFor={`budget-tokens-${widgetKeySuffix}`}>
                {t('ui.parameters.budget_tokens')}{thinking.budget_tokens || 1000}
              </label>
              <input
                id={`budget-tokens-${widgetKeySuffix}`}
                type="range"
                min="0"
                max="100000"
                step="100"
                value={thinking.budget_tokens || 1000}
                onChange={handleBudgetTokensChange}
                disabled={!editMode}
                className="range-input"
              />
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default Parameters;
