import React, { createContext, useContext, useState, useEffect } from 'react';
import { applyTheme, loadStoredTheme, defaultTheme } from '../styles/theme';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export const ThemeProvider = ({ children }) => {
  const [theme, setTheme] = useState(defaultTheme);

  useEffect(() => {
    // Load and apply stored theme on mount
    const storedTheme = loadStoredTheme();
    setTheme(storedTheme);
    applyTheme(storedTheme);
  }, []);

  const updateTheme = (newTheme) => {
    setTheme(newTheme);
    applyTheme(newTheme);
    
    // Dispatch custom event for components that need to respond to theme changes
    const event = new CustomEvent('themeChange', { detail: newTheme });
    window.dispatchEvent(event);
  };

  const toggleColorMode = () => {
    const newTheme = {
      ...theme,
      colorMode: theme.colorMode === 'light' ? 'dark' : 'light'
    };
    updateTheme(newTheme);
  };

  const toggleDensity = () => {
    const newTheme = {
      ...theme,
      density: theme.density === 'comfortable' ? 'compact' : 'comfortable'
    };
    updateTheme(newTheme);
  };

  const toggleMotion = () => {
    const newTheme = {
      ...theme,
      motion: theme.motion === 'enabled' ? 'disabled' : 'enabled'
    };
    updateTheme(newTheme);
  };

  const value = {
    theme,
    updateTheme,
    toggleColorMode,
    toggleDensity,
    toggleMotion
  };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};
