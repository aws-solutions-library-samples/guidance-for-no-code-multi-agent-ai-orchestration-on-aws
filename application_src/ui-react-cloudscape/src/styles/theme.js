// AWS Cloudscape Theme Configuration
// Based on AWS Visual Foundation theming patterns

export const themeConfig = {
  // Theme modes
  modes: {
    light: 'light',
    dark: 'dark'
  },
  
  // Density modes
  density: {
    comfortable: 'comfortable',
    compact: 'compact'
  },
  
  // Visual modes
  visual: {
    refresh: 'refresh'
  },
  
  // Motion preferences
  motion: {
    enabled: 'enabled',
    disabled: 'disabled'
  }
};

// Default theme settings
export const defaultTheme = {
  colorMode: themeConfig.modes.light,
  density: themeConfig.density.comfortable,
  visual: themeConfig.visual.refresh,
  motion: themeConfig.motion.enabled
};

// Theme application function
export const applyTheme = (theme = defaultTheme) => {
  const html = document.documentElement;
  
  // Apply color mode - this is the primary AWS Cloudscape theme attribute
  html.setAttribute('data-awsui-color-scheme', theme.colorMode);
  
  // Apply density mode
  html.setAttribute('data-awsui-density', theme.density);
  
  // Apply visual mode (always use refresh for modern AWS Cloudscape)
  html.setAttribute('data-awsui-visual-refresh', 'true');
  
  // Apply motion preference
  html.setAttribute('data-awsui-motion', theme.motion);
  
  // Add custom theme classes for additional styling
  html.className = html.className.replace(/theme-\w+/g, '');
  html.classList.add(`theme-${theme.colorMode}`);
  html.classList.add(`density-${theme.density}`);
  html.classList.add(`motion-${theme.motion}`);
  
  // Store theme preferences
  localStorage.setItem('cloudscape-theme', JSON.stringify(theme));
};

// Load theme from storage
export const loadStoredTheme = () => {
  try {
    const stored = localStorage.getItem('cloudscape-theme');
    return stored ? { ...defaultTheme, ...JSON.parse(stored) } : defaultTheme;
  } catch (error) {return defaultTheme;
  }
};

// Theme utility functions
export const toggleColorMode = (currentTheme) => {
  const newColorMode = currentTheme.colorMode === 'light' ? 'dark' : 'light';
  return { ...currentTheme, colorMode: newColorMode };
};

export const toggleDensity = (currentTheme) => {
  const newDensity = currentTheme.density === 'comfortable' ? 'compact' : 'comfortable';
  return { ...currentTheme, density: newDensity };
};

export const toggleMotion = (currentTheme) => {
  const newMotion = currentTheme.motion === 'enabled' ? 'disabled' : 'enabled';
  return { ...currentTheme, motion: newMotion };
};

// Brand colors following AWS design tokens
export const brandColors = {
  primary: {
    light: '#0972d3',
    dark: '#2196f3'
  },
  secondary: {
    light: '#545b64',
    dark: '#879596'
  },
  success: {
    light: '#037f03',
    dark: '#7aa116'
  },
  warning: {
    light: '#8d6605',
    dark: '#dfb52c'
  },
  error: {
    light: '#d13313',
    dark: '#ff9592'
  },
  info: {
    light: '#0972d3',
    dark: '#2196f3'
  }
};

// Typography scales
export const typography = {
  fontFamily: {
    default: 'Amazon Ember, Helvetica Neue, Roboto, Arial, sans-serif',
    monospace: 'Monaco, Menlo, Ubuntu Mono, monospace'
  },
  fontSizes: {
    'body-s': '12px',
    'body-m': '14px',
    'heading-xs': '16px',
    'heading-s': '18px',
    'heading-m': '20px',
    'heading-l': '28px',
    'heading-xl': '32px',
    'display-l': '42px'
  },
  lineHeights: {
    'body-s': '16px',
    'body-m': '20px',
    'heading-xs': '20px',
    'heading-s': '22px',
    'heading-m': '24px',
    'heading-l': '32px',
    'heading-xl': '40px',
    'display-l': '48px'
  }
};

// Spacing scale
export const spacing = {
  'xxxs': '2px',
  'xxs': '4px',
  'xs': '8px',
  's': '16px',
  'm': '20px',
  'l': '24px',
  'xl': '32px',
  'xxl': '40px',
  'xxxl': '48px'
};

// Border radius tokens
export const borderRadius = {
  none: '0',
  small: '2px',
  medium: '4px',
  large: '8px',
  'x-large': '16px',
  circular: '50%'
};

// Shadow tokens
export const shadows = {
  small: '0 1px 1px 0 rgba(0, 28, 36, 0.3)',
  medium: '0 4px 8px 0 rgba(0, 28, 36, 0.12), 0 2px 4px 0 rgba(0, 28, 36, 0.08)',
  large: '0 8px 16px 0 rgba(0, 28, 36, 0.12), 0 4px 8px 0 rgba(0, 28, 36, 0.08)',
  'sticky-embedded': '0 2px 4px 0 rgba(0, 28, 36, 0.12)',
  'sticky-page-header': '0 2px 4px 0 rgba(0, 28, 36, 0.12)'
};

// Initialize theme on module import
export const initializeTheme = () => {
  const theme = loadStoredTheme();
  applyTheme(theme);
  return theme;
};
