import React, { useState, useRef, useEffect } from 'react';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Box from '@cloudscape-design/components/box';
import Input from '@cloudscape-design/components/input';
import Button from '@cloudscape-design/components/button';
import FormField from '@cloudscape-design/components/form-field';
import Alert from '@cloudscape-design/components/alert';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Spinner from '@cloudscape-design/components/spinner';
import Flashbar from '@cloudscape-design/components/flashbar';
import Badge from '@cloudscape-design/components/badge';
import Cards from '@cloudscape-design/components/cards';
import Icon from '@cloudscape-design/components/icon';
import TextContent from '@cloudscape-design/components/text-content';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

// Configure marked options for better rendering
marked.setOptions({
  breaks: true, // Convert line breaks to <br>
  gfm: true, // GitHub Flavored Markdown
  headerIds: false, // Disable header IDs for security
  mangle: false, // Don't escape autolinked email addresses
});

// SECURITY: Enhanced markdown formatter with proper parsing and sanitization
const formatMessage = (content) => {
  if (!content || typeof content !== 'string') {
    return '';
  }

  // Validate content length
  if (content.length > 50000) {
    content = content.substring(0, 50000) + '... (truncated)';
  }

  try {
    // Parse markdown to HTML using marked
    const rawHtml = marked.parse(content);
    
    // SECURITY: Sanitize HTML with DOMPurify to prevent XSS
    const cleanHtml = DOMPurify.sanitize(rawHtml, {
      ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'strong', 'em', 'u', 's', 'code', 'pre',
        'ul', 'ol', 'li', 'blockquote',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'a', 'img'
      ],
      ALLOWED_ATTR: ['href', 'target', 'rel', 'src', 'alt', 'title'],
      ALLOW_DATA_ATTR: false
    });
    
    return cleanHtml;
  } catch (error) {
    console.error('Error formatting markdown:', error);
    // Fallback to escaped plain text if parsing fails
    return DOMPurify.sanitize(content);
  }
};

const ChatInterface = ({ 
  currentAgent, 
  agentConfig, 
  messages, 
  onSendMessage, 
  isLoading,
  streamingPreview = '',
  isStreaming = false,
  userEmail = ''
}) => {
  const [inputMessage, setInputMessage] = useState('');
  const [inputError, setInputError] = useState('');
  const [messagesEndRef] = [useRef(null)];
  const [streamingPreviewRef] = [useRef(null)];
  const [notifications, setNotifications] = useState([]);
  const [isInputFocused, setIsInputFocused] = useState(false);

  const scrollToBottom = () => {
    // Only scroll if user is near bottom to avoid interrupting reading
    const container = messagesEndRef.current?.parentElement;
    if (container) {
      const isNearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 100;
      if (isNearBottom) {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
      }
    }
  };

  const scrollStreamingToBottom = () => {
    // Only scroll streaming if actively streaming and user hasn't scrolled up
    if (isStreaming && streamingPreviewRef.current) {
      const container = streamingPreviewRef.current.parentElement;
      if (container) {
        const isNearBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 50;
        if (isNearBottom) {
          streamingPreviewRef.current.scrollIntoView({ behavior: "auto", block: "nearest" });
        }
      }
    }
  };

  useEffect(() => {
    // Only scroll on new messages, not every render
    const timeoutId = setTimeout(scrollToBottom, 100);
    return () => clearTimeout(timeoutId);
  }, [messages.length]); // Changed dependency to only scroll on new messages

  useEffect(() => {
    // Debounced scrolling for streaming to reduce jank
    const timeoutId = setTimeout(() => {
      if (isStreaming && streamingPreview) {
        scrollStreamingToBottom();
      }
    }, 300); // 300ms debounce
    return () => clearTimeout(timeoutId);
  }, [isStreaming]); // Only trigger on streaming state change, not content

  // Enhanced Validation - AWS Foundation Error Pattern
  const validateInput = (value) => {
    const trimmedValue = value.trim();
    
    if (!trimmedValue) {
      setInputError('Message is required and cannot be empty');
      return false;
    }
    if (value.length > 4000) {
      setInputError(`Message exceeds maximum length (${value.length}/4000 characters)`);
      return false;
    }
    if (trimmedValue.length < 2) {
      setInputError('Message must be at least 2 characters long');
      return false;
    }
    
    setInputError('');
    return true;
  };

  // Enhanced Submit Handler - AWS Foundation Pattern
  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (!validateInput(inputMessage)) {
      return;
    }
    
    if (inputMessage.trim() && !isLoading && !isStreaming) {
      const messageContent = inputMessage.trim();
      onSendMessage(messageContent);
      setInputMessage('');
      setInputError('');
      
      // Add success notification with better messaging
      addNotification({
        type: 'success',
        header: 'Message Sent',
        content: 'Message sent to AI Assistant',
        dismissible: true,
        dismissLabel: 'Dismiss notification',
        id: `message-sent-${Date.now()}`
      });
    }
  };

  // Enhanced Notification System - AWS Foundation Pattern
  const addNotification = (notification) => {
    setNotifications(prev => [...prev, notification]);
    
    // Auto-dismiss based on type - Success: 3s, Error: 5s, Info: 4s
    const dismissTimeout = notification.type === 'error' ? 5000 : 
                          notification.type === 'info' ? 4000 : 3000;
    
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== notification.id));
    }, dismissTimeout);
  };

  // Enhanced Keyboard Navigation - AWS Foundation Accessibility
  const handleKeyPress = (detail) => {
    if (detail.key === 'Enter' && !detail.shiftKey) {
      if (!isLoading && !isStreaming) {
        handleSubmit(new Event('submit'));
      }
    }
  };

  // Character count helper with visual feedback
  const getCharacterCountColor = () => {
    const length = inputMessage.length;
    if (length > 3800) return 'text-status-error';
    if (length > 3200) return 'text-status-warning';
    return 'text-body-secondary';
  };

  const getCharacterCountStatus = () => {
    const length = inputMessage.length;
    if (length > 4000) return 'error';
    if (length > 3800) return 'warning';
    return 'success';
  };

  // Build conversation cards for GenAI pattern
  const conversationItems = messages.map((message, index) => ({
    id: `message-${index}`,
    type: message.role,
    content: message.content,
    timestamp: message.timestamp,
    isUser: message.role === 'user'
  }));

  // Agent status indicator
  const getAgentStatus = () => {
    if (!currentAgent) return { type: 'pending', text: 'No agent selected' };
    if (isStreaming) return { type: 'in-progress', text: 'Agent responding...' };
    if (isLoading) return { type: 'loading', text: 'Processing...' };
    return { type: 'success', text: `Connected to ${currentAgent}` };
  };

  const agentStatus = getAgentStatus();

  return (
    <SpaceBetween size="l">
      {/* Enhanced Notifications - AWS Foundation Pattern */}
      {notifications.length > 0 && (
        <Flashbar 
          items={notifications.map(notification => ({
            ...notification,
            onDismiss: () => setNotifications(prev => 
              prev.filter(n => n.id !== notification.id)
            )
          }))}
          stackItems={true}
          i18nStrings={{
            ariaLabel: "Chat notifications",
            errorIconAriaLabel: "Error",
            warningIconAriaLabel: "Warning",
            successIconAriaLabel: "Success",
            infoIconAriaLabel: "Information"
          }}
        />
      )}

      {/* AWS Foundation GenAI Affordance - Chat Interface Header */}
      <Container
        header={
          <Header 
            variant="h1"
            description="AI-powered conversational assistant"
            actions={
              <SpaceBetween direction="horizontal" size="s" alignItems="center">
                <StatusIndicator 
                  type={isStreaming ? "loading" : "success"}
                  iconAriaLabel={isStreaming ? "Processing" : "Ready"}
                >
                  {isStreaming ? "Generating response..." : "Ready for conversation"}
                </StatusIndicator>
                {messages.length > 0 && (
                  <Badge color="blue" variant="subtle">
                    {messages.length} messages
                  </Badge>
                )}
              </SpaceBetween>
            }
          >
            AI Assistant
          </Header>
        }
        variant="default"
      >
        <SpaceBetween size="m">
          
          {/* AWS Foundation GenAI Affordance - Real-time Streaming Indicator */}
          {isStreaming && streamingPreview && (
            <Alert
              type="info"
              header="AI Response Generation in Progress"
              dismissible={false}
              statusIconAriaLabel="Information"
            >
              <SpaceBetween size="m">
                {/* AWS Foundation Typography - Streaming Context */}
                <Box variant="p" color="text-body-secondary">
                  Response generating in real-time...
                </Box>
                
                {/* AWS Foundation Visual Style - Code Display */}
                <Container 
                  variant="stacked"
                  header={
                    <Header variant="h4" description="Live AI response stream">
                      Generated Content
                    </Header>
                  }
                >
                  <Box 
                    variant="code"
                    fontFamily="monospace"
                    fontSize="body-s"
                    padding="s"
                    color="text-body-default"
                  >
                    {streamingPreview || "Initializing AI response generation..."}
                  </Box>
                </Container>
                
                {/* AWS Foundation Visual Context - Progress Indicator */}
                <SpaceBetween direction="horizontal" size="s" alignItems="center">
                  <StatusIndicator type="in-progress" iconAriaLabel="In progress">
                    Streaming in progress...
                  </StatusIndicator>
                  <Box variant="small" color="text-body-secondary">
                    Response will complete automatically
                  </Box>
                </SpaceBetween>
              </SpaceBetween>
              <div ref={streamingPreviewRef} />
            </Alert>
          )}
        </SpaceBetween>
      </Container>

      {/* AWS Foundation GenAI Affordance - Conversation Display */}
      <Container
        header={
          <Header 
            variant="h2"
            counter={messages.length > 0 ? `(${messages.length})` : undefined}
            description={messages.length > 0 ? "Conversation history" : "Start your conversation"}
          >
            Conversation History
          </Header>
        }
        variant="default"
      >
        {messages.length === 0 ? (
          /* AWS Foundation GenAI Affordance - Welcome State */
          <Box textAlign="center" padding={{ vertical: 'xxl', horizontal: 'xl' }}>
            <SpaceBetween size="xl" alignItems="center">
              {/* AWS Foundation Iconography - AI Context */}
              <SpaceBetween size="m" alignItems="center">
                <Icon name="contact" size="large" />
                <Box variant="h2" color="text-body-secondary">
                  Start Your AI Conversation
                </Box>
              </SpaceBetween>
              
              {/* AWS Foundation Typography - Welcome Content */}
              <SpaceBetween size="m" alignItems="center">
                <Box variant="p" color="text-body-secondary" textAlign="center">
                  Ask questions, request analysis, or get help with complex tasks.
                </Box>
              </SpaceBetween>
            </SpaceBetween>
          </Box>
        ) : (
          <SpaceBetween size="l">
            {/* AWS Foundation GenAI Affordance - Enhanced Message Cards */}
            {conversationItems.map(item => (
              <Container
                key={item.id}
                variant={item.isUser ? "default" : "stacked"}
                header={
                  /* AWS Foundation Visual Context - Message Header */
                  <SpaceBetween direction="horizontal" size="s" alignItems="center">
                    <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                      <Icon name={item.isUser ? "user-profile" : "contact"} />
                      <Badge 
                        color={item.isUser ? 'blue' : 'green'}
                        variant="normal"
                      >
                        {item.isUser ? 'You' : 'AI Assistant'}
                      </Badge>
                    </SpaceBetween>
                    
                    <Box variant="small" color="text-body-secondary">
                      {item.timestamp}
                    </Box>
                    
                    <Box flex="1" />
                    
                  </SpaceBetween>
                }
              >
                {/* AWS Foundation Typography - Message Content */}
                <Box 
                  padding={{ top: 's', left: 'm' }}
                  color="text-body-default"
                >
                  <Box 
                    style={{ 
                      lineHeight: '1.6',
                      wordBreak: 'break-word',
                      fontSize: '14px', // AWS Foundation Typography - Body text
                      whiteSpace: 'pre-wrap'
                    }}
                  >
                    {/* SECURITY: Using formatMessage which escapes HTML before applying markdown formatting */}
                    {item.isUser ? (
                      // User messages: render as plain text
                      <Box variant="code">{item.content}</Box>
                    ) : (
                      // AI messages: render formatted markdown with Cloudscape TextContent component
                      <TextContent>
                        <div dangerouslySetInnerHTML={{ __html: formatMessage(item.content) }} />
                      </TextContent>
                    )}
                  </Box>
                </Box>
              </Container>
            ))}
            
            {/* AWS Foundation GenAI Affordance - AI Processing Indicator */}
            {isLoading && !isStreaming && (
              <Container 
                variant="stacked"
                header={
                  <Header variant="h4" description="AI model processing your request">
                    Generating Response
                  </Header>
                }
              >
                <Box textAlign="center" padding="l">
                  <SpaceBetween size="l" alignItems="center">
                    {/* AWS Foundation Visual Style - Processing Animation */}
                    <SpaceBetween size="s" alignItems="center">
                      <Spinner size="large" />
                      <Icon name="contact" />
                    </SpaceBetween>
                    
                    {/* AWS Foundation Typography - Processing Context */}
                    <SpaceBetween size="s" alignItems="center">
                      <StatusIndicator type="loading" iconAriaLabel="AI processing">
                        Processing your request...
                      </StatusIndicator>
                    </SpaceBetween>
                  </SpaceBetween>
                </Box>
              </Container>
            )}
            
            <div ref={messagesEndRef} />
          </SpaceBetween>
        )}
      </Container>

      {/* AWS Foundation GenAI Affordance - Message Input Interface */}
      <Container
        header={
          <Header 
            variant="h3"
            description="Send messages to your AI assistant"
          >
            Message Composer
          </Header>
        }
        variant="default"
      >
        <form onSubmit={handleSubmit} role="form" aria-label="Send message to AI assistant">
          <SpaceBetween size="m">
            <FormField
              label="Your message"
              description="Ask questions, request analysis, or provide instructions"
              errorText={inputError}
              stretch={true}
            >
              <Input
                value={inputMessage}
                onChange={({ detail }) => {
                  setInputMessage(detail.value);
                  if (inputError) validateInput(detail.value);
                }}
                onKeyDown={({ detail }) => handleKeyPress(detail)}
                onFocus={() => setIsInputFocused(true)}
                onBlur={() => setIsInputFocused(false)}
                placeholder={
                  isStreaming 
                    ? "Please wait - response in progress..." 
                    : "Type your message for the AI Assistant..."
                }
                disabled={isLoading || isStreaming}
                invalid={!!inputError}
                type="text"
                inputMode="text"
                autoComplete="off"
                ariaLabel="Message input field"
                ariaDescribedBy="message-input-description"
              />
            </FormField>
            
            {/* Enhanced Character Count and Action Bar - AWS Foundation Pattern */}
            <SpaceBetween direction="horizontal" size="m" alignItems="center">
              <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                <Box 
                  variant="small" 
                  color={getCharacterCountColor()}
                >
                  {inputMessage.length}/4000 characters
                </Box>
                {inputMessage.length > 3200 && (
                  <StatusIndicator 
                    type={getCharacterCountStatus()}
                    iconAriaLabel={`Character count ${getCharacterCountStatus()}`}
                    variant="subtle"
                  />
                )}
              </SpaceBetween>
              
              <Box flex="1" />
              
              <SpaceBetween direction="horizontal" size="s">
                {inputMessage.length > 0 && (
                  <Button
                    variant="normal"
                    onClick={() => {
                      setInputMessage('');
                      setInputError('');
                    }}
                    disabled={isLoading || isStreaming}
                    iconName="close"
                    ariaLabel="Clear message"
                  >
                    Clear
                  </Button>
                )}
                
                <Button
                  variant="primary"
                  onClick={handleSubmit}
                  disabled={isLoading || !inputMessage.trim() || !!inputError || isStreaming}
                  loading={isLoading && !isStreaming}
                  iconName="send"
                  size="large"
                  ariaLabel="Send message to AI assistant"
                >
                  {isStreaming ? 'AI responding...' : 
                   isLoading ? 'Processing...' : 
                   'Send to AI'}
                </Button>
              </SpaceBetween>
            </SpaceBetween>
            
            {/* AWS Foundation Typography - Input Helper Text */}
            <Box variant="small" color="text-body-secondary" id="message-input-description">
              <SpaceBetween direction="horizontal" size="xs" alignItems="center">
                <Icon name="status-info" />
                <Box>Press Enter to send message to AI</Box>
                {isInputFocused && (
                  <>
                    <Box>•</Box>
                    <Box>Shift+Enter for new line</Box>
                  </>
                )}
              </SpaceBetween>
            </Box>
          </SpaceBetween>
        </form>
      </Container>
    </SpaceBetween>
  );
};

export default ChatInterface;
