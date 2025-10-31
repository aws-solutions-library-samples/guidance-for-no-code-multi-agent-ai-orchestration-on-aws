import React from 'react';
import { useTranslation } from 'react-i18next';

const Observability = ({ agentConfig, onConfigUpdate, editMode, widgetKeySuffix }) => {
  const { t } = useTranslation();
  const handleObservabilityEnabledChange = (e) => {
    if (editMode) {
      onConfigUpdate({ observability: e.target.checked ? 'True' : 'False' });
    }
  };

  const observabilityEnabled = agentConfig.observability === 'True';

  return (
    <div>
      <div className="checkbox-group">
        <input
          id={`observability-enabled-${widgetKeySuffix}`}
          type="checkbox"
          checked={observabilityEnabled}
          onChange={handleObservabilityEnabledChange}
          disabled={!editMode}
        />
        <label htmlFor={`observability-enabled-${widgetKeySuffix}`}>
          {t('observability.ui.observability_enabled')}
        </label>
      </div>

      {observabilityEnabled && (
        <div className="info-message" style={{ marginTop: '1rem' }}>
          <small>
            📊 Observability is enabled. Metrics and traces will be collected for this agent.
          </small>
        </div>
      )}
    </div>
  );
};

export default Observability;
