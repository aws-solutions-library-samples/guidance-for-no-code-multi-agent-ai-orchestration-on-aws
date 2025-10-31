import React from 'react';
import { useTranslation } from 'react-i18next';

const Guardrails = ({ agentConfig, onConfigUpdate, editMode, widgetKeySuffix }) => {
  const { t } = useTranslation();
  const handleGuardrailsEnabledChange = (e) => {
    if (editMode) {
      onConfigUpdate({ guardrails: e.target.checked ? 'True' : 'False' });
    }
  };

  const handleProviderChange = (e) => {
    if (editMode) {
      onConfigUpdate({ guardrails_provider: e.target.value });
    }
  };

  const guardrailsEnabled = agentConfig.guardrails === 'True';
  const guardrailsDetails = agentConfig.guardrails_details || [];
  const currentProvider = agentConfig.guardrails_provider || '';

  const getProviderConfig = (providerName) => {
    const detail = guardrailsDetails.find(d => d.name === providerName);
    return detail?.config || {};
  };

  const renderProviderFields = (config) => {
    return Object.entries(config).map(([key, value]) => (
      <div key={key} className="form-group">
        <label htmlFor={`guardrails-${key}-${widgetKeySuffix}`}>
          {key.replace('_', ' ').split(' ').map(word => 
            word.charAt(0).toUpperCase() + word.slice(1)
          ).join(' ')}
        </label>
        <input
          id={`guardrails-${key}-${widgetKeySuffix}`}
          type="text"
          value={value || 'N/A'}
          disabled={!editMode}
          placeholder={!editMode ? value : ''}
        />
      </div>
    ));
  };

  return (
    <div>
      <div className="checkbox-group" style={{ marginBottom: '1rem' }}>
        <input
          id={`guardrails-enabled-${widgetKeySuffix}`}
          type="checkbox"
          checked={guardrailsEnabled}
          onChange={handleGuardrailsEnabledChange}
          disabled={!editMode}
        />
        <label htmlFor={`guardrails-enabled-${widgetKeySuffix}`}>
          {t('guardrails.ui.guardrails_enabled')}
        </label>
      </div>

      {guardrailsEnabled && (
        <>
          <div className="form-group">
            <label htmlFor={`guardrails-provider-${widgetKeySuffix}`}>{t('common.ui.provider')}</label>
            <select
              id={`guardrails-provider-${widgetKeySuffix}`}
              value={currentProvider}
              onChange={handleProviderChange}
              disabled={!editMode}
            >
              {guardrailsDetails.map((detail) => (
                <option key={detail.name} value={detail.name}>
                  {detail.name}
                </option>
              ))}
            </select>
          </div>

          {currentProvider && renderProviderFields(getProviderConfig(currentProvider))}
        </>
      )}
    </div>
  );
};

export default Guardrails;
