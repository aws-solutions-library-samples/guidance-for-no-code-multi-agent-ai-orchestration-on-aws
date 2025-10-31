import React from 'react';
import { useTranslation } from 'react-i18next';

const Tools = ({ agentConfig, onConfigUpdate, editMode, widgetKeySuffix }) => {
  const { t } = useTranslation();
  const handleToolsEnabledChange = (e) => {
    if (editMode) {
      onConfigUpdate({ tools: e.target.checked ? 'True' : 'False' });
    }
  };

  // Debug logging// Tools are enabled if there are tools configured
  const toolsEnabled = Array.isArray(agentConfig.tools) && agentConfig.tools.length > 0;
  const toolsList = agentConfig.tools || [];// Debug info for UI display
  const debugInfo = {
    tools_type: typeof agentConfig.tools,
    tools_value: JSON.stringify(agentConfig.tools),
    tools_is_array: Array.isArray(agentConfig.tools),
    tools_length: agentConfig.tools?.length,
    tools_enabled_computed: toolsEnabled
  };

  const renderToolsList = () => {
    if (!toolsList || toolsList.length === 0) {
      return (
        <div className="info-message">
          <small>{t('tools.ui.no_tools_configured')}</small>
        </div>
      );
    }

    return toolsList.map((tool, index) => (
      <div key={index} className="tool-item" style={{ 
        marginBottom: '0.5rem', 
        padding: '0.5rem', 
        backgroundColor: '#f8f9fa', 
        borderRadius: '4px',
        border: '1px solid #e9ecef'
      }}>
        <div style={{ fontWeight: '500', marginBottom: '0.25rem' }}>
          🔧 {tool.name}
        </div>
        {tool.config && Object.keys(tool.config).length > 0 && (
          <div style={{ fontSize: '0.8rem', color: '#888', marginTop: '0.25rem' }}>
            {t('tools.ui.config')}: {Object.keys(tool.config).join(', ')}
          </div>
        )}
      </div>
    ));
  };

  return (
    <div>
      <div className="checkbox-group" style={{ marginBottom: '1rem' }}>
        <input
          id={`tools-enabled-${widgetKeySuffix}`}
          type="checkbox"
          checked={toolsEnabled}
          onChange={handleToolsEnabledChange}
          disabled={!editMode}
        />
        <label htmlFor={`tools-enabled-${widgetKeySuffix}`}>
          {t('tools.ui.tools_enabled')}
        </label>
      </div>

      {/* Debug information visible in UI */}
      <div style={{ 
        backgroundColor: '#f8f9fa', 
        border: '1px solid #dee2e6', 
        borderRadius: '4px', 
        padding: '0.5rem', 
        fontSize: '0.75rem', 
        marginBottom: '1rem',
        fontFamily: 'monospace'
      }}>
        <strong>{t('tools.ui.debug_info')}:</strong><br/>
        Tools Type: {debugInfo.tools_type}<br/>
        Tools Value: {debugInfo.tools_value}<br/>
        Is Array: {debugInfo.tools_is_array ? 'Yes' : 'No'}<br/>
        Length: {debugInfo.tools_length}<br/>
        Checkbox Enabled: {debugInfo.tools_enabled_computed ? 'Yes' : 'No'}
      </div>

      {toolsEnabled && (
        <div>
          <div style={{ marginBottom: '0.5rem', fontWeight: '500', fontSize: '0.9rem' }}>
            {t('tools.ui.available_tools')}:
          </div>
          {renderToolsList()}
        </div>
      )}
    </div>
  );
};

export default Tools;
