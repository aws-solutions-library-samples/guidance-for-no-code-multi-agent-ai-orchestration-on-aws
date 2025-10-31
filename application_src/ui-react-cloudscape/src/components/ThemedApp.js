import React from 'react';
import { ThemeProvider, useTheme } from './ThemeProvider';
import App from '../App';

// Theme-aware App component with theme controls integrated into user menu
const ThemedAppContent = () => {
  const { theme, toggleColorMode, toggleDensity, toggleMotion } = useTheme();

  // Get theme controls for user menu integration (AWS Cloudscape best practice)
  const getThemeControls = () => {
    return {
      theme,
      toggleColorMode,
      toggleDensity,
      toggleMotion
    };
  };

  return <App themeControls={getThemeControls()} />;
};

// Main themed app component
const ThemedApp = () => {
  return (
    <ThemeProvider>
      <ThemedAppContent />
    </ThemeProvider>
  );
};

export default ThemedApp;
