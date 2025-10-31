import React from 'react';
import { useTranslation } from 'react-i18next';

const KnowledgeBase = ({ agentConfig, onConfigUpdate, editMode, widgetKeySuffix }) => {
  const { t } = useTranslation();
  
  const handleKnowledgeBaseProviderChange = (e) => {
    if (editMode) {
      onConfigUpdate({ knowledge_base_provider: e.target.value });
    }
  };

  const kbProviderDetails = agentConfig.knowledge_base_provider_details || [];
  const currentProvider = agentConfig.knowledge_base_provider || '';

  const getProviderConfig = (providerName) => {
    const detail = kbProviderDetails.find(d => d.name === providerName);
    return detail?.config || {};
  };

  const renderProviderFields = (config) => {
    return Object.entries(config).map(([key, value]) => (
      <div key={key} className="form-group">
        <label htmlFor={`kb-${key}-${widgetKeySuffix}`}>
          {key.replace('_', ' ').split(' ').map(word => 
            word.charAt(0).toUpperCase() + word.slice(1)
          ).join(' ')}
        </label>
        <input
          id={`kb-${key}-${widgetKeySuffix}`}
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
      <div className="form-group">
        <label htmlFor={`kb-provider-${widgetKeySuffix}`}>{t('knowledge_base.ui.provider')}</label>
        <select
          id={`kb-provider-${widgetKeySuffix}`}
          value={currentProvider}
          onChange={handleKnowledgeBaseProviderChange}
          disabled={!editMode}
        >
          {kbProviderDetails.map((detail) => (
            <option key={detail.name} value={detail.name}>
              {detail.name}
            </option>
          ))}
        </select>
      </div>

      {currentProvider && renderProviderFields(getProviderConfig(currentProvider))}
    </div>
  );
};

export default KnowledgeBase;
