"""
Custom Bedrock Model Provider for Strands SDK.
Implements immediate throttling detection and model switching following official Strands SDK patterns.
Shared across all agents for consistent model switching behavior.
"""
import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, AsyncIterable, Callable, Optional, Type, TypeVar, Union
from typing_extensions import TypedDict, Unpack, override

import boto3
from botocore.config import Config as BotocoreConfig
from botocore.exceptions import ClientError
from pydantic import BaseModel

from strands.models import Model
from strands.event_loop import streaming
from strands.tools import convert_pydantic_to_tool_spec
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec
from strands.types.exceptions import ContextWindowOverflowException, ModelThrottledException

# Import shared model configuration
from model_config import ANTHROPIC_MODELS, MODEL_COOLDOWN_SECONDS

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class CustomBedrockModel(Model):
    """
    Custom Bedrock model provider with immediate throttling detection and model switching.
    Follows official Strands SDK patterns for custom model providers.
    """
    
    class ModelConfig(TypedDict):
        """
        Configuration for Bedrock model.
        
        Attributes:
            model_id: ID of Bedrock model.
            region: AWS region for Bedrock client.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature.
            top_p: Top-p sampling parameter.
        """
        model_id: str
        region: Optional[str]
        max_tokens: Optional[int]
        temperature: Optional[float]
        top_p: Optional[float]
    
    def __init__(
        self,
        model_id: str,
        **model_config: Unpack[ModelConfig]
    ) -> None:
        """Initialize custom Bedrock provider.
        
        Args:
            model_id: The Bedrock model ID to use.
            **model_config: Configuration options for Bedrock model.
        """
        # Get region from environment variable with fallback
        import os
        region = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
        
        # Set defaults for any missing configuration
        defaults = {
            'model_id': model_id,
            'region': region,
            'max_tokens': 4000,
            'temperature': 0.7,
            'top_p': 0.9
        }
        
        # Override defaults with provided config
        final_config = {**defaults, **model_config}
        
        self.config = CustomBedrockModel.ModelConfig(**final_config)
        
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize boto3 Bedrock client with improved connection stability."""
        try:
            self.client = boto3.client(
                'bedrock-runtime',
                region_name=self.config['region'],
                config=BotocoreConfig(
                    retries={
                        'max_attempts': 1,  # Allow one retry for connection issues
                        'mode': 'standard'
                    },
                    read_timeout=180,   # Extended timeout for large responses
                    connect_timeout=30, # Longer connection timeout for stability
                    max_pool_connections=50,
                    tcp_keepalive=True  # Enable TCP keepalive for long connections
                )
            )
            logger.info(f"Custom Bedrock client initialized for {self.config['model_id']} in region {self.config['region']}")
        except Exception as e:
            logger.error(f"Failed to initialize custom Bedrock client: {e}")
            raise
    
    def _is_throttling_error(self, error: Exception) -> bool:
        """
        Enhanced throttling detection for Bedrock errors.
        Only detects actual throttling, not generic timeouts.
        """
        if isinstance(error, ClientError):
            error_code = error.response.get('Error', {}).get('Code', '')
            error_message = str(error).lower()
            
            # Bedrock-specific throttling error codes
            throttling_codes = [
                'ThrottlingException',
                'ServiceQuotaExceededException', 
                'TooManyRequestsException',
                'LimitExceededException'
            ]
            
            # Check error code first (most reliable)
            for code in throttling_codes:
                if code in error_code:
                    logger.warning(f"Bedrock throttling detected - error code: {error_code}")
                    return True
            
            # Check error message for throttling indicators
            throttling_messages = [
                'throttled', 'rate exceeded', 'too many requests',
                'quota exceeded', 'limit exceeded', 'slow down',
                'service unavailable', 'temporarily unavailable'
            ]
            
            for msg in throttling_messages:
                if msg in error_message:
                    logger.warning(f"Bedrock throttling detected - message: {error_message}")
                    return True
        
        return False
    
    def _is_connection_error(self, error: Exception) -> bool:
        """
        Detect connection-related errors that might benefit from retrying.
        """
        error_message = str(error).lower()
        
        # Connection-related error patterns
        connection_errors = [
            'connection was closed',
            'connection timeout',
            'connection reset',
            'connection refused',
            'connection aborted',
            'endpoint url',
            'network is unreachable',
            'temporary failure in name resolution',
            'ssl',
            'tls'
        ]
        
        for pattern in connection_errors:
            if pattern in error_message:
                logger.warning(f"Connection error detected: {error_message}")
                return True
        
        return False
    
    def _format_messages_for_bedrock(self, messages: Messages) -> list[dict[str, Any]]:
        """Convert Strands Messages to Bedrock converse_stream format with validation."""
        bedrock_messages = []
        tool_use_ids = set()  # Track tool use IDs to validate results
        
        for msg_idx, message in enumerate(messages):
            role = message.get('role', 'user')
            content_blocks = message.get('content', [])
            
            # Format content blocks for Bedrock converse_stream API
            bedrock_content = []
            for block in content_blocks:
                if isinstance(block, dict) and 'text' in block:
                    bedrock_content.append({"text": block['text']})
                elif isinstance(block, str):
                    bedrock_content.append({"text": block})
                elif isinstance(block, dict) and 'toolUse' in block:
                    # Handle tool use blocks
                    tool_use = block['toolUse']
                    tool_use_id = tool_use.get('toolUseId')
                    if tool_use_id:
                        tool_use_ids.add(tool_use_id)
                        logger.debug(f"Registered tool use ID: {tool_use_id}")
                    bedrock_content.append({
                        "toolUse": {
                            "toolUseId": tool_use_id,
                            "name": tool_use.get('name'),
                            "input": tool_use.get('input', {})
                        }
                    })
                elif isinstance(block, dict) and 'toolResult' in block:
                    # Handle tool result blocks
                    tool_result = block['toolResult']
                    tool_use_id = tool_result.get('toolUseId')
                    
                    # Validate that this tool result matches a previous tool use
                    if tool_use_id not in tool_use_ids:
                        logger.warning(f"Tool result ID {tool_use_id} at message {msg_idx} doesn't match any previous tool use. Available IDs: {tool_use_ids}")
                        # Skip this invalid tool result to prevent ValidationException
                        continue
                    
                    bedrock_content.append({
                        "toolResult": {
                            "toolUseId": tool_use_id,
                            "content": tool_result.get('content', [])
                        }
                    })
                    logger.debug(f"Validated tool result ID: {tool_use_id}")
            
            # Only add messages with actual content
            if bedrock_content:
                bedrock_messages.append({
                    "role": role,
                    "content": bedrock_content
                })
            else:
                logger.warning(f"Skipping empty message with role: {role}")
        
        # Ensure we have at least one message
        if not bedrock_messages:
            logger.warning("No valid messages found, adding default message")
            bedrock_messages.append({
                "role": "user",
                "content": [{"text": "Hello"}]
            })
        
        logger.debug(f"Formatted {len(bedrock_messages)} messages with {len(tool_use_ids)} tool use IDs")
        return bedrock_messages
    
    def _format_request_body(
        self, 
        messages: Messages, 
        system_prompt: Optional[str] = None,
        tool_specs: Optional[list[ToolSpec]] = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """Format request body for Bedrock converse_stream API (following official SDK pattern)."""
        bedrock_messages = self._format_messages_for_bedrock(messages)
        
        # Follow the exact pattern from official Strands SDK
        request = {
            "modelId": self.config.get('model_id'),
            "messages": bedrock_messages,
            "system": [
                *([{"text": system_prompt}] if system_prompt else []),
            ],
            **(
                {
                    "toolConfig": {
                        "tools": [
                            *[{"toolSpec": tool_spec} for tool_spec in tool_specs],
                        ],
                        "toolChoice": {"auto": {}},
                    }
                }
                if tool_specs else {}
            ),
            "inferenceConfig": {
                key: value
                for key, value in [
                    ("maxTokens", self.config.get("max_tokens")),
                    ("temperature", self.config.get("temperature")),
                    ("topP", self.config.get("top_p")),
                ]
                if value is not None
            },
        }
        
        return request
    
    @override
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream responses from Bedrock with immediate throttling detection and tool support.
        
        Args:
            messages: List of conversation messages
            tool_specs: Optional list of available tools
            system_prompt: Optional system prompt
            **kwargs: Additional keyword arguments
        
        Returns:
            Iterator of StreamEvent objects
        """
        if not self.client:
            raise Exception("Custom Bedrock client not initialized")
        
        
        try:
            # Format request using converse_stream API (following official SDK pattern)
            request = self._format_request_body(messages, system_prompt, tool_specs, **kwargs)
            
            if tool_specs:
                logger.debug(f"Custom Bedrock request includes {len(tool_specs)} tools")
            
            logger.info(f"Custom Bedrock streaming with {self.config['model_id']}")
            
            # Use converse_stream API like official SDK
            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.client.converse_stream(**request)
            )
            
            # Process the streaming response following official SDK pattern
            stream = response.get('stream')
            
            if stream:
                for chunk in stream:
                    # Yield the chunk directly as it comes from Bedrock
                    # This follows the same pattern as the official SDK
                    yield chunk
            
            logger.info(f"Custom Bedrock streaming completed for {self.config['model_id']}")
            
        except Exception as e:
            logger.exception("Custom Bedrock streaming error")
            
            # Check if this is throttling and convert to Strands exception
            if self._is_throttling_error(e):
                # Raise Strands-compatible throttling exception
                raise ModelThrottledException(f"Custom Bedrock throttling detected: {e}") from e
            elif self._is_connection_error(e):
                # Connection errors - treat as throttling to trigger model switching
                logger.warning(f"Connection error treated as throttling: {e}")
                raise ModelThrottledException(f"Custom Bedrock connection error: {e}") from e
            else:
                # Re-raise non-throttling errors as-is
                raise e
    
    def update_config(self, **model_config: Unpack[ModelConfig]) -> None:
        """Update Bedrock model configuration.
        
        Args:
            **model_config: Configuration overrides.
        """
        self.config.update(model_config)
    
    def get_config(self) -> ModelConfig:
        """Get Bedrock model configuration.
        
        Returns:
            The Bedrock model configuration.
        """
        return self.config
    
    @override
    async def structured_output(
        self,
        output_model: Type[T],
        prompt: Messages,
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncGenerator[dict[str, Union[T, Any]], None]:
        """Get structured output from the model.
        
        Args:
            output_model: The output model to use for the agent.
            prompt: The prompt messages to use for the agent.
            system_prompt: System prompt to provide context to the model.
            **kwargs: Additional keyword arguments for future extensibility.
        
        Yields:
            Model events with the last being the structured output.
        """
        tool_spec = convert_pydantic_to_tool_spec(output_model)
        response = self.stream(messages=prompt, tool_specs=[tool_spec], system_prompt=system_prompt, **kwargs)
        
        async for event in streaming.process_stream(response):
            yield event
        
        stop_reason, messages, _, _ = event["stop"]
        
        if stop_reason != "tool_use":
            raise ValueError(f'Model returned stop_reason: {stop_reason} instead of "tool_use".')
        
        content = messages["content"]
        output_response: dict[str, Any] | None = None
        
        for block in content:
            # if the tool use name doesn't match the tool spec name, skip, and if the block is not a tool use, skip.
            # if the tool use name never matches, raise an error.
            if block.get("toolUse") and block["toolUse"]["name"] == tool_spec["name"]:
                output_response = block["toolUse"]["input"]
            else:
                continue
        
        if output_response is None:
            raise ValueError("No valid tool use or tool use input was found in the Bedrock response.")
        
        yield {"output": output_model(**output_response)}


class ModelSwitchingBedrockProvider:
    """
    Enhanced provider that manages multiple Bedrock models for automatic switching.
    This class coordinates model switching when throttling occurs.
    """
    
    def __init__(self, available_models: Optional[list[str]] = None, model_manager=None):
        """
        Initialize the model switching provider.
        
        Args:
            available_models: List of available Bedrock model IDs (defaults to ANTHROPIC_MODELS from shared config)
            model_manager: Optional model switching manager for coordination
        """
        # Use shared configuration from model_config.py
        self.available_models = available_models or ANTHROPIC_MODELS
        self.model_manager = model_manager
        self.current_model_index = 0
        self.model_cooldowns = {}  # model_id -> cooldown_until_timestamp
        
        logger.info(f"Model Switching Bedrock Provider initialized with {len(self.available_models)} models from shared config")
    
    def get_next_available_model(self) -> Optional[str]:
        """
        Get the next available model that's not in cooldown.
        
        Returns:
            Next available model ID or None if all models are in cooldown
        """
        current_time = time.time()
        
        # Remove expired cooldowns
        expired_models = [
            model_id for model_id, cooldown_until in self.model_cooldowns.items()
            if current_time >= cooldown_until
        ]
        for model_id in expired_models:
            del self.model_cooldowns[model_id]
            logger.info(f"Model {model_id} cooldown expired")
        
        # Find next available model
        for i in range(len(self.available_models)):
            next_index = (self.current_model_index + i + 1) % len(self.available_models)
            next_model = self.available_models[next_index]
            
            if next_model not in self.model_cooldowns:
                self.current_model_index = next_index
                logger.info(f"Next available model: {next_model}")
                return next_model
        
        logger.warning("No models available - all in cooldown")
        return None
    
    def put_model_in_cooldown(self, model_id: str, cooldown_seconds: Optional[int] = None):
        """Put a model in cooldown for the specified duration."""
        if cooldown_seconds is None:
            cooldown_seconds = MODEL_COOLDOWN_SECONDS
        
        cooldown_until = time.time() + cooldown_seconds
        self.model_cooldowns[model_id] = cooldown_until
        logger.warning(f"Model {model_id} in cooldown for {cooldown_seconds}s (using shared config)")
    
    def create_switching_model(self, initial_model_id: Optional[str] = None, **kwargs) -> 'SwitchingBedrockModel':
        """
        Create a model that automatically switches on throttling.
        
        Args:
            initial_model_id: Initial model to try (defaults to first available)
            **kwargs: Additional configuration
        
        Returns:
            SwitchingBedrockModel instance
        """
        if not initial_model_id:
            initial_model_id = self.available_models[0]
        
        return SwitchingBedrockModel(
            provider=self,
            initial_model_id=initial_model_id,
            **kwargs
        )


class SwitchingBedrockModel(Model):
    """
    A wrapper model that automatically switches between different Bedrock models on throttling.
    Maintains the Strands SDK interface while providing seamless model switching.
    """
    
    def __init__(
        self, 
        provider: ModelSwitchingBedrockProvider, 
        initial_model_id: str,
        max_switches: int = 2,
        **kwargs
    ):
        """
        Initialize the switching model.
        
        Args:
            provider: The switching provider instance
            initial_model_id: Initial model to use
            max_switches: Maximum switches allowed per request
            **kwargs: Additional configuration
        """
        self.provider = provider
        self.max_switches = max_switches
        self.switches_attempted = 0
        self.kwargs = kwargs
        
        # Initialize with the first model
        self.current_model = CustomBedrockModel(model_id=initial_model_id, **kwargs)
        logger.info(f"Switching model initialized with {initial_model_id}")
    
    def _switch_to_model(self, model_id: str):
        """Switch to a specific model."""
        try:
            self.current_model = CustomBedrockModel(model_id=model_id, **self.kwargs)
            logger.info(f"Switched to model: {model_id}")
        except Exception as e:
            logger.error(f"Error in stream: {e}")
            raise
    
    async def stream(
        self,
        messages: Messages,
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> AsyncIterable[StreamEvent]:
        """
        Stream with automatic model switching on throttling.
        """
        self.switches_attempted = 0
        
        while self.switches_attempted <= self.max_switches:
            try:
                logger.info(f"Attempting stream with model: {self.current_model.get_config()['model_id']} (switch attempt {self.switches_attempted})")
                
                async for event in self.current_model.stream(messages, tool_specs, system_prompt, **kwargs):
                    yield event
                
                # Success - stream completed
                logger.info(f"Stream completed successfully with model: {self.current_model.get_config()['model_id']}")
                return
                
            except ModelThrottledException as e:
                self.switches_attempted += 1
                current_model_id = self.current_model.get_config()['model_id']
                logger.warning(f"Model {current_model_id} throttled (attempt {self.switches_attempted})")
                
                if self.switches_attempted > self.max_switches:
                    logger.error(f"Exceeded max model switches ({self.max_switches})")
                    raise Exception(f"All model switching attempts failed. Last error: {e}")
                
                # Put current model in cooldown
                self.provider.put_model_in_cooldown(current_model_id, cooldown_seconds=60)
                
                # Try to get next available model
                next_model = self.provider.get_next_available_model()
                if next_model:
                    # Switch to next model
                    self._switch_to_model(next_model)
                    logger.warning(f"Immediate model switch: {current_model_id} -> {next_model}")
                    continue
                
                # No more models available
                logger.error("No alternative models available")
                raise Exception(f"No alternative models available. Last error: {e}")
            
            except Exception as e:
                logger.exception(f"Non-throttling error with model {self.current_model.get_config()['model_id']}")
                raise e
        
        raise Exception(f"Stream failed after {self.switches_attempted} model switches")
    
    def update_config(self, **model_config) -> None:
        """Update configuration of current model."""
        self.current_model.update_config(**model_config)
    
    def get_config(self):
        """Get configuration of current model."""
        return self.current_model.get_config()
    
    async def structured_output(
        self,
        messages: Messages,
        schema: dict[str, Any],
        tool_specs: Optional[list[ToolSpec]] = None,
        system_prompt: Optional[str] = None,
        **kwargs: Any
    ) -> Any:
        """
        Generate structured output with automatic model switching on throttling.
        
        Args:
            messages: List of conversation messages
            schema: JSON schema for structured output
            tool_specs: Optional list of available tools
            system_prompt: Optional system prompt
            **kwargs: Additional keyword arguments
        
        Returns:
            Structured output matching the provided schema
        """
        self.switches_attempted = 0
        
        while self.switches_attempted <= self.max_switches:
            try:
                logger.info(f"Attempting structured output with model: {self.current_model.get_config()['model_id']} (switch attempt {self.switches_attempted})")
                
                result = await self.current_model.structured_output(messages, schema, tool_specs, system_prompt, **kwargs)
                
                # Success - structured output completed
                logger.info(f"Structured output completed successfully with model: {self.current_model.get_config()['model_id']}")
                return result
                
            except ModelThrottledException as e:
                self.switches_attempted += 1
                current_model_id = self.current_model.get_config()['model_id']
                logger.warning(f"Model {current_model_id} throttled during structured output (attempt {self.switches_attempted})")
                
                if self.switches_attempted > self.max_switches:
                    logger.error(f"Exceeded max model switches ({self.max_switches}) for structured output")
                    raise Exception(f"All model switching attempts failed for structured output. Last error: {e}")
                
                # Put current model in cooldown
                self.provider.put_model_in_cooldown(current_model_id, cooldown_seconds=60)
                
                # Try to get next available model
                next_model = self.provider.get_next_available_model()
                if next_model:
                    # Switch to next model
                    self._switch_to_model(next_model)
                    logger.warning(f"Immediate model switch for structured output: {current_model_id} -> {next_model}")
                    continue
                
                # No more models available
                logger.error("No alternative models available for structured output")
                raise Exception(f"No alternative models available for structured output. Last error: {e}")
            
            except Exception as e:
                logger.exception(f"Non-throttling error during structured output with model {self.current_model.get_config()['model_id']}")
                raise e
        
        raise Exception(f"Structured output failed after {self.switches_attempted} model switches")
