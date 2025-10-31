import React from 'react';
import ReactDOM from 'react-dom/client';
import '@cloudscape-design/global-styles/index.css';
import './styles/custom-theme.css';
import { initializeTheme } from './styles/theme';
import ThemedApp from './components/ThemedApp';

// Initialize theme immediately before React renders
initializeTheme();

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <ThemedApp />
  </React.StrictMode>
);
