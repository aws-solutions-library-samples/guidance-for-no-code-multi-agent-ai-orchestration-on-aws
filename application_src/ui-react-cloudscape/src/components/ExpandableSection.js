import React, { useState } from 'react';

const ExpandableSection = ({ title, children, expanded = false }) => {
  const [isExpanded, setIsExpanded] = useState(expanded);

  const toggleExpanded = () => {
    setIsExpanded(!isExpanded);
  };

  return (
    <div className="expandable-section">
      <div className="expandable-header" onClick={toggleExpanded}>
        <span>{title}</span>
        <span>{isExpanded ? '▼' : '▶'}</span>
      </div>
      {isExpanded && (
        <div className="expandable-content">
          {children}
        </div>
      )}
    </div>
  );
};

export default ExpandableSection;
