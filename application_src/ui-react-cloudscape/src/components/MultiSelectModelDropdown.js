import React, { useState, useEffect } from 'react';
import Multiselect from '@cloudscape-design/components/multiselect';
import FormField from '@cloudscape-design/components/form-field';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Badge from '@cloudscape-design/components/badge';
import configService from '../services/configuration';

// AWS Foundation Multi-Select Model Dropdown
const MultiSelectModelDropdown = ({ 
  selectedModels = [], 
  onChange, 
  maxSelections = 5, 
  placeholder = "Select models...", 
  disabled = false,
  label = "Model Selection",
  description = "Select multiple models for dynamic switching capabilities"
}) => {
  const [availableModels, setAvailableModels] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch available models using configService properly
  useEffect(() => {
    const fetchModels = async () => {
      setLoading(true);
      setError(null);
      try {
        // Use configService to get form schema for models
        const formSchema = await configService.getFormSchema('models');
        
        // Extract model options from the bedrock provider
        const bedrockProvider = formSchema.providers?.bedrock;
        if (bedrockProvider && bedrockProvider.fields) {
          const modelField = bedrockProvider.fields.find(field => field.name === 'model_id');
          if (modelField && modelField.options) {
            const modelOptions = modelField.options.map(option => ({
              label: formatModelName(option.value),
              value: option.value,
              description: getModelDescription(option.value),
              group: getModelProvider(option.value)
            }));
            setAvailableModels(modelOptions);
          } else {
            setAvailableModels([]);
            setError('No model options found in configuration');
          }
        } else {
          setAvailableModels([]);
          setError('No bedrock provider configuration found');
        }
      } catch (error) {setError(`Failed to load models: ${error.message}`);
        setAvailableModels([]);
      } finally {
        setLoading(false);
      }
    };

    fetchModels();
  }, []);

  const formatModelName = (modelId) => {
    // Extract readable name from model ID
    const modelMap = {
      'us.amazon.nova-lite-v1:0': 'Nova Lite (Cost-effective)',
      'us.amazon.nova-pro-v1:0': 'Nova Pro (Balanced)',
      'us.amazon.nova-premier-v1:0': 'Nova Premier (Advanced)',
      'us.anthropic.claude-3-5-sonnet-20241022-v2:0': 'Claude 3.5 Sonnet (Recommended)',
      'us.anthropic.claude-3-5-haiku-20241022-v1:0': 'Claude 3.5 Haiku (Fast)',
      'anthropic.claude-3-5-sonnet-20241022-v2:0': 'Claude 3.5 Sonnet',
      'anthropic.claude-3-5-haiku-20241022-v1:0': 'Claude 3.5 Haiku'
    };
    
    return modelMap[modelId] || modelId;
  };

  const getModelDescription = (modelId) => {
    const descMap = {
      'us.amazon.nova-lite-v1:0': 'Amazon\'s cost-effective model for general tasks',
      'us.amazon.nova-pro-v1:0': 'Amazon\'s balanced model for complex workflows',
      'us.amazon.nova-premier-v1:0': 'Amazon\'s most advanced model for complex reasoning',
      'us.anthropic.claude-3-5-sonnet-20241022-v2:0': 'Best overall performance for complex reasoning and analysis',
      'us.anthropic.claude-3-5-haiku-20241022-v1:0': 'Optimized for speed and efficiency with good reasoning',
      'anthropic.claude-3-5-sonnet-20241022-v2:0': 'Excellent for complex reasoning tasks',
      'anthropic.claude-3-5-haiku-20241022-v1:0': 'Fast and efficient for quick responses'
    };
    
    return descMap[modelId] || 'AI language model';
  };

  const getModelProvider = (modelId) => {
    if (modelId.includes('amazon.nova') || modelId.includes('us.amazon.nova')) {
      return 'Amazon Nova';
    }
    if (modelId.includes('anthropic.claude') || modelId.includes('us.anthropic.claude')) {
      return 'Anthropic Claude';
    }
    if (modelId.includes('meta.llama')) {
      return 'Meta Llama';
    }
    return 'Other';
  };

  const handleSelectionChange = ({ detail }) => {
    const newSelectedOptions = detail.selectedOptions;
    const newSelectedValues = newSelectedOptions.map(option => option.value);
    onChange(newSelectedValues);
  };

  const getSelectedOptions = () => {
    return selectedModels.map(modelId => {
      const model = availableModels.find(m => m.value === modelId);
      return model || {
        label: formatModelName(modelId),
        value: modelId,
        description: getModelDescription(modelId),
        group: getModelProvider(modelId)
      };
    });
  };

  const getSelectionStatus = () => {
    if (selectedModels.length === 0) return { type: 'warning', text: 'No models selected' };
    if (selectedModels.length === maxSelections) return { type: 'success', text: `Maximum ${maxSelections} models selected` };
    return { type: 'success', text: `${selectedModels.length} of ${maxSelections} models selected` };
  };

  const selectionStatus = getSelectionStatus();

  if (error) {
    return (
      <FormField
        label={label}
        description={description}
        errorText={error}
      >
        <Box variant="p" color="text-status-error">
          Failed to load available models. Please try again.
        </Box>
      </FormField>
    );
  }

  return (
    <FormField
      label={label}
      description={
        <SpaceBetween size="xs">
          <Box variant="small">{description}</Box>
          <SpaceBetween direction="horizontal" size="xs" alignItems="center">
            <StatusIndicator 
              type={selectionStatus.type} 
              iconAriaLabel={selectionStatus.type}
              variant="subtle"
            >
              {selectionStatus.text}
            </StatusIndicator>
            {selectedModels.length > 0 && (
              <Badge color="blue" variant="subtle">
                Multi-model switching enabled
              </Badge>
            )}
          </SpaceBetween>
        </SpaceBetween>
      }
      constraintText={`Maximum ${maxSelections} selections • Enables dynamic model switching`}
    >
      <Multiselect
        selectedOptions={getSelectedOptions()}
        onChange={handleSelectionChange}
        options={availableModels}
        placeholder={loading ? "Loading available models..." : placeholder}
        disabled={disabled || loading}
        loadingText="Loading models..."
        errorText={error}
        empty="No models available"
        finishedText={selectedModels.length >= maxSelections ? "Maximum selections reached" : undefined}
        statusType={loading ? "loading" : error ? "error" : "finished"}
        tokenLimit={maxSelections}
        hideTokens={false}
        expandToViewport={true}
        keepOpen={false}
        ariaLabel="Select AI models for dynamic switching"
        i18nStrings={{
          tokenLimitShowMore: showMoreCount => `Show ${showMoreCount} more`,
          tokenLimitShowFewer: "Show fewer"
        }}
      />
      
      {/* Selection Summary */}
      {selectedModels.length > 0 && (
        <Box margin={{ top: 's' }}>
          <SpaceBetween size="xs">
            <Box variant="small" color="text-body-secondary">
              Selected models will be available for dynamic switching during conversations
            </Box>
            <SpaceBetween direction="horizontal" size="xs" wrap={true}>
              {selectedModels.map(modelId => (
                <Badge key={modelId} color="green" variant="subtle">
                  {formatModelName(modelId)}
                </Badge>
              ))}
            </SpaceBetween>
          </SpaceBetween>
        </Box>
      )}
    </FormField>
  );
};

export default MultiSelectModelDropdown;
