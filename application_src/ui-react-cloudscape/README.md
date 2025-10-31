# React UI for Generative AI Platform

A modern React-based user interface for the Generative AI with Snowflake and AWS platform.

## Features

- **AWS Cognito Authentication** - Secure login with AWS Cognito
- **Agent Configuration** - Interactive configuration management for AI agents
- **Real-time Chat** - Chat interface with supervisor agent
- **Modern UI** - Clean, responsive design with expandable sidebar
- **Configuration Management** - Edit and save agent configurations
- **Multi-Agent Support** - Support for multiple AI agents with different capabilities

## Technologies Used

- React 18
- AWS Amplify (for Cognito authentication)
- Axios (for API communication)
- CSS3 with modern styling
- Docker for containerization

## Getting Started

### Prerequisites

- Node.js 18 or higher
- npm or yarn
- Docker (for containerized deployment)

### Local Development

1. Install dependencies:
```bash
npm install
```

2. Set environment variables:
```bash
export REACT_APP_CONFIGURATION_API_ENDPOINT=localhost:8000
export REACT_APP_SUPERVISOR_AGENT_ENDPOINT=localhost:9003
export REACT_APP_COGNITO_USER_POOL_ID=your_user_pool_id
export REACT_APP_COGNITO_CLIENT_ID=your_client_id
export REACT_APP_AWS_REGION=us-east-1
```

3. Start development server:
```bash
npm start
```

The application will be available at `http://localhost:3000`

### Docker Deployment

Build and run with Docker:
```bash
docker build -t genai-ui-react .
docker run -p 3000:3000 genai-ui-react
```

Or use with Docker Compose:
```bash
docker-compose up ui-react
```

## Configuration

The application expects the following backend services:

- **Configuration API** - Running on port 8000 (for agent configuration)
- **Supervisor Agent** - Running on port 9003 (for chat functionality)
- **AWS Cognito** - For user authentication

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `REACT_APP_CONFIGURATION_API_ENDPOINT` | Configuration API endpoint | `localhost:8000` |
| `REACT_APP_SUPERVISOR_AGENT_ENDPOINT` | Supervisor agent endpoint | `localhost:9003` |
| `REACT_APP_COGNITO_USER_POOL_ID` | AWS Cognito User Pool ID | Required |
| `REACT_APP_COGNITO_CLIENT_ID` | AWS Cognito Client ID | Required |
| `REACT_APP_AWS_REGION` | AWS Region | `us-east-1` |

## Architecture

The React UI consists of several key components:

- **App.js** - Main application with authentication and state management
- **Login.js** - AWS Cognito login interface
- **Sidebar.js** - Configuration sidebar with expandable sections
- **ChatInterface.js** - Chat interface for agent interaction
- **Configuration Components** - Individual components for each config section

## API Integration

The UI integrates with:

1. **Configuration API** - For loading/saving agent configurations
2. **Supervisor Agent** - For chat functionality and agent coordination
3. **AWS Cognito** - For user authentication and authorization

## Styling

The application uses custom CSS with:
- Modern design system
- Responsive layout
- Dark/light theme support
- Smooth animations and transitions
- Accessible form controls

## Building for Production

```bash
npm run build
```

This creates an optimized production build in the `build/` directory.

## Troubleshooting

### Common Issues

1. **Authentication Errors** - Ensure Cognito credentials are correct
2. **API Connection Issues** - Verify backend services are running
3. **CORS Issues** - Ensure backend APIs allow requests from the UI domain

### Logs

Check browser console for client-side errors and backend service logs for API issues.
