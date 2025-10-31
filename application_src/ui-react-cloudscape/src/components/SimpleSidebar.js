import React from 'react';
import { useTranslation } from 'react-i18next';

const SimpleSidebar = ({ children }) => {
  const { t } = useTranslation();
  
  return (
    <div className="simple-sidebar">
      <div className="sidebar-header">
        <h2>{t('simple_sidebar.ui.genai_assistant')}</h2>
      </div>
      <div className="sidebar-content">
        {children}
      </div>
    </div>
  );
};

export default SimpleSidebar;
