import React from 'react';
import { useTranslation } from 'react-i18next';

const Memory = ({ agentConfig, onConfigUpdate, editMode, widgetKeySuffix }) => {
  const { t } = useTranslation();
  const handleMemoryEnabledChange = (e) => {
    if (editMode) {
      onConfigUpdate({ memory: e.target.checked ? 'True' : 'False' });
    }
  };

  const handleMemoryProviderChange = (e) => {
    if (editMode) {
      onConfigUpdate({ memory_provider: e.target.value });
    }
  };

  const memoryEnabled = agentConfig.memory === 'True';
  const memoryProviderDetails = agentConfig.memory_provider_details || [];
  const currentProvider = agentConfig.memory_provider || '';

  const getProviderConfig = (providerName) => {
    const detail = memoryProviderDetails.find(d => d.name === providerName);
    return detail?.config || {};
  };

  const renderProviderFields = (config) => {
    return Object.entries(config).map(([key, value]) => (
      <div key={key} className="form-group">
        <label htmlFor={`memory-${key}-${widgetKeySuffix}`}>
          {key.replace('_', ' ').split(' ').map(word => 
            word.charAt(0).toUpperCase() + word.slice(1)
          ).join(' ')}
        </label>
        <input
          id={`memory-${key}-${widgetKeySuffix}`}
          type={key.endsWith('_key') || key.endsWith('_password') ? 'password' : 'text'}
          value={key.endsWith('_key') || key.endsWith('_password') ? '********' : value}
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
          id={`memory-enabled-${widgetKeySuffix}`}
          type="checkbox"
          checked={memoryEnabled}
          onChange={handleMemoryEnabledChange}
          disabled={!editMode}
        />
        <label htmlFor={`memory-enabled-${widgetKeySuffix}`}>{t('memory.ui.memory_enabled')}</label>
      </div>

      {memoryEnabled && (
        <>
          <div className="form-group">
            <label htmlFor={`memory-provider-${widgetKeySuffix}`}>{t('common.ui.provider')}</label>
            <select
              id={`memory-provider-${widgetKeySuffix}`}
              value={currentProvider}
              onChange={handleMemoryProviderChange}
              disabled={!editMode}
            >
              {memoryProviderDetails.map((detail) => (
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

export default Memory;
