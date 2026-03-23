"""
Bedrock Model Service - Dynamic model discovery using AWS APIs.

This service eliminates model ID duplication by fetching available models
directly from AWS Bedrock, with configurable defaults loaded from configuration files.
"""

import logging
import boto3
import os
from typing import Dict, List, Optional, Any
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


# Regex to detect context-window variant model IDs such as:
#   amazon.nova-lite-v1:0:24k   amazon.nova-pro-v1:0:300k   amazon.nova-2-lite-v1:0:256k
# These IDs exist in the list response but are NOT valid invocation targets —
# calling Converse on them returns ResourceNotFoundException("Model not found").
# Only the base ID (e.g. amazon.nova-lite-v1:0) is a valid invocation target.
import re as _re
_CONTEXT_VARIANT_RE = _re.compile(
    r':\d+k$'          # ends in :<number>k  (e.g. :24k, :256k, :300k, :1000k)
    r'|:mm$'           # ends in :mm (multimodal context variant)
)

# Minimal list of model ID prefixes that must be hardcoded because the AWS
# list_foundation_models API provides no distinguishing programmatic signal:
#
#   twelvelabs.  — video-understanding models; VIDEO in inputModalities is too
#                  broad a signal (50+ valid multimodal models also have IMAGE input).
#   amazon.titan-tg1-large — EOL at runtime ("This model version has reached the
#                  end of life") but the list API shows no endOfLifeTime and
#                  responseStreamingSupported=True, so no API signal is available.
#
# NOTE: cohere.rerank-* was previously here but is now caught by the
# responseStreamingSupported=False programmatic check below.
_HARDCODED_EXCLUDED_MODEL_PREFIXES = (
    'twelvelabs.',              # video-only models, no Converse support
    'amazon.titan-tg1-large',   # EOL at runtime, no API signal available
)


def _is_context_variant(model_id: str) -> bool:
    """Return True for context-window variant IDs that cannot be invoked directly."""
    return bool(_CONTEXT_VARIANT_RE.search(model_id))


def _should_exclude_model(model_id: str, response_streaming_supported: bool) -> bool:
    """
    Return True for models that should be excluded from the UI dropdown.

    Uses programmatic API signals where possible:
      - responseStreamingSupported=False  → reranking or other non-conversational
        model (e.g. cohere.rerank-*).  All models used via converse_stream require
        streaming support.

    Falls back to a minimal hardcoded prefix list only for models where the AWS
    list_foundation_models API provides no useful distinguishing signal.
    """
    # Programmatic signal: streaming is required for converse_stream.
    if not response_streaming_supported:
        return True
    # Minimal hardcoded exclusions where no API signal is available.
    if model_id.startswith(_HARDCODED_EXCLUDED_MODEL_PREFIXES):
        return True
    return False


def _is_legacy_model_error(error: Exception) -> bool:
    """
    Detect errors indicating a model is marked Legacy by the provider AND has not
    been actively used in the last 15 days.

    AWS raises ResourceNotFoundException with a specific message at inference time
    for such models.  The same pattern can surface during get_foundation_model
    calls.  When detected we skip the model entirely so it never appears in the
    UI dropdown or model cache.

    Example message:
        "Access denied. This Model is marked by provider as Legacy and you have
         not been actively using the model in the last 15 days. Please upgrade to
         an active model on Amazon Bedrock"
    """
    if isinstance(error, ClientError):
        error_code = error.response.get('Error', {}).get('Code', '')
        error_message = str(error).lower()

        if error_code == 'ResourceNotFoundException':
            legacy_indicators = [
                'marked by provider as legacy',
                'legacy',
                'not been actively using the model',
                'upgrade to an active model',
            ]
            for indicator in legacy_indicators:
                if indicator in error_message:
                    return True

    return False


# Global model cache - populated at application startup
_global_model_cache = None
_cache_lock = None


class BedrockModelService:
    """Service for dynamic Bedrock model discovery and management with global caching."""
    
    def __init__(self, region_name: str = None):
        """
        Initialize Bedrock model service.
        
        Args:
            region_name: AWS region for Bedrock operations
        """
        # Get region from environment variable if not provided
        if region_name is None:
            import os
            region_name = os.environ.get('AWS_REGION', os.environ.get('AWS_DEFAULT_REGION', 'us-east-1'))
            
        self.region_name = region_name
        self.bedrock_client = boto3.client('bedrock', region_name=region_name)
        
        # Load default model selections from configuration instead of hardcoding
        self.default_models = self._load_default_models_from_config()
        
        logger.info(f"BedrockModelService initialized for region: {region_name}")
    
    def _load_default_models_from_config(self) -> Dict[str, Any]:
        """
        Load default model configurations from config files and environment variables.
        
        Returns:
            Dictionary of default model configurations
        """
        try:
            # Try to load from helper.config first (CDK configuration)
            try:
                from helper.config import Config
                config = Config('development')  # Use development config
                
                return {
                    "primary_model": config.get_optional_config('SupervisorModelId', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0'),
                    "judge_model": config.get_optional_config('SupervisorJudgeModelId', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0'),
                    "embedding_model": config.get_optional_config('SupervisorEmbeddingModelId', 'amazon.titan-embed-text-v2:0'),
                    "fallback_models": [
                        config.get_optional_config('SupervisorModelId', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0'),
                        config.get_optional_config('GenericAgentModelId', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0'),
                    ]
                }
            except ImportError:
                # If helper.config not available, use environment variables or minimal defaults
                return {
                    "primary_model": os.environ.get('BEDROCK_DEFAULT_MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0'),
                    "judge_model": os.environ.get('BEDROCK_DEFAULT_JUDGE_MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0'),
                    "embedding_model": os.environ.get('BEDROCK_DEFAULT_EMBEDDING_MODEL_ID', 'amazon.titan-embed-text-v2:0'),
                    "fallback_models": [
                        os.environ.get('BEDROCK_DEFAULT_MODEL_ID', 'us.anthropic.claude-3-5-sonnet-20241022-v2:0')
                    ]
                }
        except Exception as e:
            logger.warning(f"Could not load default models from config, using minimal defaults: {e}")
            # Ultra-minimal defaults - just one model to prevent failures
            return {
                "primary_model": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
                "judge_model": "us.anthropic.claude-3-5-sonnet-20241022-v2:0", 
                "embedding_model": "amazon.titan-embed-text-v2:0",
                "fallback_models": ["us.anthropic.claude-3-5-sonnet-20241022-v2:0"]
            }
    
    @classmethod
    async def initialize_global_model_cache(cls, region_name: str = "us-east-1") -> None:
        """
        Initialize the global model cache at application startup.
        This runs once and populates the cache for all subsequent requests.
        
        Args:
            region_name: AWS region for Bedrock operations
        """
        global _global_model_cache, _cache_lock
        
        if _cache_lock is None:
            import asyncio
            _cache_lock = asyncio.Lock()
        
        async with _cache_lock:
            if _global_model_cache is not None:
                logger.info("Global model cache already initialized")
                return
            
            logger.info("🚀 Initializing global Bedrock model cache at startup...")
            
            try:
                # Create temporary service instance for initialization
                temp_service = cls(region_name)
                
                # Fetch models and cache globally
                models_data = await temp_service._fetch_models_from_aws()
                _global_model_cache = models_data
                
                total_models = models_data.get('total_models', 0)
                logger.info(f"✅ Global model cache initialized with {total_models} models from AWS Bedrock")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize global model cache: {e}")
                # Set empty cache to prevent repeated failures
                _global_model_cache = {
                    'models_by_capability': {'text_generation': [], 'text_embedding': [], 'multimodal': [], 'all_models': []},
                    'model_details': {},
                    'total_models': 0,
                    'error': str(e),
                    'region': region_name
                }
    
    @classmethod
    def get_cached_models(cls) -> Optional[Dict[str, Any]]:
        """Get models from global cache without making AWS API calls."""
        global _global_model_cache
        return _global_model_cache
    
    async def _fetch_models_from_aws(self) -> Dict[str, Any]:
        """
        Fetch models from AWS Bedrock asynchronously for startup caching.
        Includes both foundation models and cross-region inference profiles.
        
        Returns:
            Dictionary containing available models with metadata
        """
        try:
            import time
            logger.info("Fetching available foundation models and inference profiles from AWS Bedrock...")
            
            # Process and categorize models
            models_by_capability = {
                "text_generation": [],
                "text_embedding": [],
                "multimodal": [],
                "all_models": []
            }
            
            model_details = {}
            
            # Step 1: Fetch foundation models
            logger.info("Fetching foundation models...")
            response = self.bedrock_client.list_foundation_models()
            
            total_foundation_models = len(response.get('modelSummaries', []))
            active_foundation_models = 0
            skipped_foundation_models = 0
            
            for model in response.get('modelSummaries', []):
                model_id = model['modelId']
                model_name = model['modelName']
                provider_name = model['providerName']
                # AWS returns modelLifecycle.status ('ACTIVE' | 'LEGACY'), not a flat
                # 'modelLifecycleStatus' key.  Read it correctly from the nested dict.
                model_lifecycle_status = model.get('modelLifecycle', {}).get('status', 'ACTIVE')

                # Only show ACTIVE models in the UI.  LEGACY models may still be
                # callable for existing users but should not appear as new options.
                if model_lifecycle_status == 'LEGACY':
                    logger.debug(f"Skipping LEGACY model {model_id}")
                    skipped_foundation_models += 1
                    continue

                # Skip context-window variants (e.g. amazon.nova-lite-v1:0:24k) —
                # these IDs are not valid invocation targets; only the base ID is.
                if _is_context_variant(model_id):
                    logger.debug(f"Skipping context-window variant {model_id}")
                    skipped_foundation_models += 1
                    continue

                # Skip non-conversational models using programmatic signals where
                # possible (responseStreamingSupported=False) and a minimal
                # hardcoded list for models with no distinguishing API signal.
                response_streaming = model.get('responseStreamingSupported', True)
                if _should_exclude_model(model_id, response_streaming):
                    logger.debug(f"Skipping non-conversational/EOL model {model_id}")
                    skipped_foundation_models += 1
                    continue

                active_foundation_models += 1

                # Get detailed model information for foundation models
                try:
                    model_detail_response = self.bedrock_client.get_foundation_model(modelIdentifier=model_id)
                    model_details_info = model_detail_response['modelDetails']
                    
                    # Extract capabilities — prefer detail response; fall back to
                    # list-level modalities which AWS always populates correctly
                    input_modalities = model_details_info.get('inputModalities') or model.get('inputModalities', [])
                    output_modalities = model_details_info.get('outputModalities') or model.get('outputModalities', [])
                    
                    # Categorize by capability
                    capabilities = []
                    if 'TEXT' in input_modalities and 'TEXT' in output_modalities:
                        capabilities.append('text_generation')
                        models_by_capability['text_generation'].append({
                            'model_id': model_id,
                            'display_name': f"{provider_name} {model_name}",
                            'provider': provider_name.lower()
                        })
                    
                    if 'TEXT' in input_modalities and 'EMBEDDING' in output_modalities:
                        capabilities.append('text_embedding')
                        models_by_capability['text_embedding'].append({
                            'model_id': model_id,
                            'display_name': f"{provider_name} {model_name} (Embedding)",
                            'provider': provider_name.lower()
                        })
                    
                    if len(input_modalities) > 1 or len(output_modalities) > 1:
                        capabilities.append('multimodal')
                        models_by_capability['multimodal'].append({
                            'model_id': model_id,
                            'display_name': f"{provider_name} {model_name} (Multimodal)",
                            'provider': provider_name.lower()
                        })
                    
                    # Store detailed information
                    model_details[model_id] = {
                        'model_id': model_id,
                        'model_name': model_name,
                        'provider_name': provider_name,
                        'display_name': f"{provider_name} {model_name}",
                        'capabilities': capabilities,
                        'input_modalities': input_modalities,
                        'output_modalities': output_modalities,
                        'customizations_supported': model_details_info.get('customizationsSupported', []),
                        'inference_types_supported': model_details_info.get('inferenceTypesSupported', []),
                        'response_streaming_supported': model_details_info.get('responseStreamingSupported', False),
                        'model_lifecycle_status': model_lifecycle_status
                    }

                except Exception as detail_error:
                    # If the provider marked this model as Legacy and it hasn't been
                    # used in the last 15 days, AWS returns ResourceNotFoundException
                    # at detail-fetch time even though list_foundation_models still
                    # returns it as ACTIVE.  Skip it completely so it never shows up
                    # in UI dropdowns or the model cache.
                    if _is_legacy_model_error(detail_error):
                        logger.warning(
                            f"Skipping legacy/inactive model {model_id} "
                            f"(ResourceNotFoundException during detail fetch): {detail_error}"
                        )
                        skipped_foundation_models += 1
                        active_foundation_models -= 1  # correct the earlier increment
                        continue  # do NOT add to model_details or all_models
                    logger.warning(f"Could not get details for model {model_id}: {detail_error}")
                    # Add basic info for non-legacy detail failures so the model
                    # still appears in the cache with sensible defaults.
                    model_details[model_id] = {
                        'model_id': model_id,
                        'model_name': model_name,
                        'provider_name': provider_name,
                        'display_name': f"{provider_name} {model_name}",
                        'capabilities': ['text_generation'],  # Assume basic capability
                        'input_modalities': ['TEXT'],
                        'output_modalities': ['TEXT'],
                        'customizations_supported': [],
                        'inference_types_supported': [],
                        'response_streaming_supported': True,
                        'model_lifecycle_status': model_lifecycle_status
                    }

                # Add to all models list
                models_by_capability['all_models'].append(model_details[model_id])
            
            # Log filtering summary for foundation models
            logger.info(
                f"Foundation model filtering summary: {active_foundation_models} ACTIVE models cached, "
                f"{skipped_foundation_models} non-ACTIVE/legacy models skipped "
                f"(out of {total_foundation_models} total)"
            )

            # Step 2: Fetch cross-region inference profiles
            logger.info("Fetching cross-region inference profiles...")
            try:
                inference_profiles_response = self.bedrock_client.list_inference_profiles()
                
                for profile in inference_profiles_response.get('inferenceProfileSummaries', []):
                    profile_id = profile['inferenceProfileId']
                    profile_name = profile.get('inferenceProfileName', profile_id)
                    profile_type = profile.get('type', 'SYSTEM_DEFINED')
                    
                    # Extract provider and model info from profile_id for display name
                    parts = profile_id.split('.')
                    if len(parts) >= 2:
                        geography = parts[0].upper()  # us -> US
                        provider = parts[1].title()   # anthropic -> Anthropic
                        model_part = '.'.join(parts[2:]).replace('-', ' ').title().replace('V1 0', 'v1.0')
                        display_name = f"{geography} {provider} {model_part}"
                    else:
                        display_name = f"{profile_name}"
                    
                    # Get detailed profile information (optional - proceed even if this fails)
                    models_in_profile = []
                    try:
                        profile_detail = self.bedrock_client.get_inference_profile(inferenceProfileIdentifier=profile_id)
                        models_in_profile = profile_detail.get('models', [])
                    except Exception as profile_detail_error:
                        pass  # Continue with basic profile info if details fail
                    
                    # Always add inference profile to available models (even if details failed)
                    models_by_capability['text_generation'].append({
                        'model_id': profile_id,
                        'display_name': display_name,
                        'provider': parts[1] if len(parts) >= 2 else 'cross-region',
                        'type': 'inference_profile',
                        'geography': parts[0] if len(parts) >= 2 else 'global'
                    })
                    
                    # Store detailed information for inference profile
                    model_details[profile_id] = {
                        'model_id': profile_id,
                        'model_name': profile_name,
                        'provider_name': parts[1].title() if len(parts) >= 2 else 'Cross-Region',
                        'display_name': display_name,
                        'capabilities': ['text_generation'],
                        'input_modalities': ['TEXT'],
                        'output_modalities': ['TEXT'],
                        'type': 'inference_profile',
                        'profile_type': profile_type,
                        'geography': parts[0] if len(parts) >= 2 else 'global',
                        'models': models_in_profile,
                        'response_streaming_supported': True
                    }
                    
                    # Add to all models list
                    models_by_capability['all_models'].append(model_details[profile_id])
                    
                    logger.info(f"✅ Added inference profile: {profile_id} -> {display_name}")
                        
            except Exception as profiles_error:
                logger.warning(f"Could not fetch inference profiles (may not be supported in region): {profiles_error}")
            
            # Foundation models were already processed in Step 1 - avoid duplicate processing
            
            # Cache results
            cache_result = {
                'models_by_capability': models_by_capability,
                'model_details': model_details,
                'total_models': len(model_details),
                'last_updated': time.time(),
                'region': self.region_name
            }
            
            logger.info(f"Successfully fetched {len(model_details)} models from AWS Bedrock")
            return cache_result
            
        except ClientError as e:
            logger.error(f"AWS Bedrock API error: {e}")
            # Return empty structure on failure
            return {
                'models_by_capability': {'text_generation': [], 'text_embedding': [], 'multimodal': [], 'all_models': []},
                'model_details': {},
                'total_models': 0,
                'error': str(e),
                'region': self.region_name
            }
        except Exception as e:
            logger.error(f"Error fetching Bedrock models: {e}")
            # Return empty structure on failure
            return {
                'models_by_capability': {'text_generation': [], 'text_embedding': [], 'multimodal': [], 'all_models': []},
                'model_details': {},
                'total_models': 0,
                'error': str(e),
                'region': self.region_name
            }
    
    def get_text_generation_models(self) -> List[Dict[str, str]]:
        """Get all available text generation models for form dropdowns using global cache."""
        try:
            # Try to use global cache first for better performance
            cached_models = self.get_cached_models()
            if cached_models:
                return cached_models['models_by_capability']['text_generation']
            
            # Fallback to live API call if cache not available
            models_data = self.get_available_foundation_models()
            return models_data['models_by_capability']['text_generation']
        except Exception as e:
            logger.error(f"Error getting text generation models: {e}")
            return []
    
    def get_embedding_models(self) -> List[Dict[str, str]]:
        """Get all available embedding models for form dropdowns using global cache."""
        try:
            # Try to use global cache first for better performance
            cached_models = self.get_cached_models()
            if cached_models:
                return cached_models['models_by_capability']['text_embedding']
            
            # Fallback to live API call if cache not available
            models_data = self.get_available_foundation_models()
            return models_data['models_by_capability']['text_embedding']
        except Exception as e:
            logger.error(f"Error getting embedding models: {e}")
            return []
    
    def validate_model_id(self, model_id: str) -> bool:
        """
        Check if a model ID is available in the current region.
        
        Args:
            model_id: Model identifier to validate
            
        Returns:
            True if model is available, False otherwise
        """
        try:
            # Try global cache first
            cached_models = self.get_cached_models()
            if cached_models:
                return model_id in cached_models['model_details']
            
            # Fallback to live API call
            models_data = self.get_available_foundation_models()
            return model_id in models_data['model_details']
        except Exception as e:
            logger.warning(f"Could not validate model ID {model_id}: {e}")
            return False
    
    def get_model_display_name(self, model_id: str) -> str:
        """
        Get human-readable display name for a model.
        
        Args:
            model_id: Model identifier
            
        Returns:
            Display name if found, model_id if not found
        """
        try:
            # Try global cache first
            cached_models = self.get_cached_models()
            if cached_models:
                model_info = cached_models['model_details'].get(model_id)
                if model_info:
                    return model_info['display_name']
            
            # Fallback to live API call
            models_data = self.get_available_foundation_models()
            model_info = models_data['model_details'].get(model_id)
            return model_info['display_name'] if model_info else model_id
        except Exception as e:
            logger.warning(f"Could not get display name for model {model_id}: {e}")
            return model_id
    
    def get_recommended_models_for_agent_type(self, agent_type: str = "default") -> Dict[str, str]:
        """
        Get recommended model selections for different agent types from configuration.
        No hardcoded models - all values loaded from configuration files.
        
        Args:
            agent_type: Type of agent (default, supervisor, qa, etc.)
            
        Returns:
            Dictionary with recommended model IDs for different purposes
        """
        try:
            # Load recommendations from configuration file
            from helper.config import Config
            config = Config('development')
            
            # Map agent types to configuration keys
            config_mapping = {
                "supervisor": {
                    "model_id": config.get_optional_config('SupervisorModelId', self.default_models["primary_model"]),
                    "judge_model_id": config.get_optional_config('SupervisorJudgeModelId', self.default_models["judge_model"]),
                    "embedding_model_id": config.get_optional_config('SupervisorEmbeddingModelId', self.default_models["embedding_model"])
                },
                "qa": {
                    "model_id": config.get_optional_config('GenericAgentModelId', self.default_models["primary_model"]),
                    "judge_model_id": config.get_optional_config('GenericAgentJudgeModelId', self.default_models["judge_model"]),
                    "embedding_model_id": config.get_optional_config('GenericAgentEmbeddingModelId', self.default_models["embedding_model"])
                },
                "default": {
                    "model_id": config.get_optional_config('GenericAgentModelId', self.default_models["primary_model"]),
                    "judge_model_id": config.get_optional_config('GenericAgentJudgeModelId', self.default_models["judge_model"]),
                    "embedding_model_id": config.get_optional_config('GenericAgentEmbeddingModelId', self.default_models["embedding_model"])
                }
            }
            
            return config_mapping.get(agent_type, config_mapping["default"])
            
        except Exception as e:
            logger.warning(f"Could not load agent recommendations from config: {e}")
            # Return minimal defaults from our loaded configuration
            return {
                "model_id": self.default_models["primary_model"],
                "judge_model_id": self.default_models["judge_model"],
                "embedding_model_id": self.default_models["embedding_model"]
            }
    
    def generate_form_schema_options(self, capability: str = "text_generation") -> List[Dict[str, Any]]:
        """
        Generate form schema options for UI dropdowns from live AWS data.
        
        Args:
            capability: Model capability to filter by
            
        Returns:
            List of form options with value and label
        """
        try:
            if capability == "text_generation":
                models = self.get_text_generation_models()
            elif capability == "text_embedding":
                models = self.get_embedding_models()
            else:
                models_data = self.get_available_foundation_models()
                models = models_data['models_by_capability']['all_models']
            
            # Convert to form schema format
            form_options = []
            for model in models:
                form_options.append({
                    "value": model['model_id'],
                    "label": model['display_name'],
                    "disabled": False
                })
            
            # Sort by provider and model name for better UX
            form_options.sort(key=lambda x: (x['label']))
            
            logger.info(f"Generated {len(form_options)} form options for {capability}")
            return form_options
            
        except Exception as e:
            logger.error(f"Error generating form schema options: {e}")
            return []
    
    def get_available_foundation_models(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get all available foundation models from global cache or AWS Bedrock.
        Only includes models with ACTIVE lifecycle status.
        
        Args:
            force_refresh: Whether to bypass cache and fetch fresh data
            
        Returns:
            Dictionary containing available ACTIVE models with metadata
        """
        try:
            # Try global cache first for better performance
            if not force_refresh:
                cached_models = self.get_cached_models()
                if cached_models:
                    return cached_models
            
            # Fallback to live API call
            import time
            logger.info("Fetching available foundation models from AWS Bedrock...")
            
            # Fetch models from AWS Bedrock
            response = self.bedrock_client.list_foundation_models()
            
            total_foundation_models = len(response.get('modelSummaries', []))
            active_foundation_models = 0
            skipped_foundation_models = 0
            
            # Process and categorize models
            models_by_capability = {
                "text_generation": [],
                "text_embedding": [],
                "multimodal": [],
                "all_models": []
            }
            
            model_details = {}
            
            for model in response.get('modelSummaries', []):
                model_id = model['modelId']
                model_name = model['modelName']
                provider_name = model['providerName']
                # AWS returns modelLifecycle.status ('ACTIVE' | 'LEGACY'), not a flat
                # 'modelLifecycleStatus' key.  Read it correctly from the nested dict.
                model_lifecycle_status = model.get('modelLifecycle', {}).get('status', 'ACTIVE')

                # Only show ACTIVE models in the UI.  LEGACY models may still be
                # callable for existing users but should not appear as new options.
                if model_lifecycle_status == 'LEGACY':
                    logger.debug(f"Skipping LEGACY model {model_id}")
                    skipped_foundation_models += 1
                    continue

                # Skip context-window variants (e.g. amazon.nova-lite-v1:0:24k) —
                # these IDs are not valid invocation targets; only the base ID is.
                if _is_context_variant(model_id):
                    logger.debug(f"Skipping context-window variant {model_id}")
                    skipped_foundation_models += 1
                    continue

                # Skip non-conversational models using programmatic signals where
                # possible (responseStreamingSupported=False) and a minimal
                # hardcoded list for models with no distinguishing API signal.
                response_streaming = model.get('responseStreamingSupported', True)
                if _should_exclude_model(model_id, response_streaming):
                    logger.debug(f"Skipping non-conversational/EOL model {model_id}")
                    skipped_foundation_models += 1
                    continue

                active_foundation_models += 1

                # Get detailed model information
                try:
                    model_detail_response = self.bedrock_client.get_foundation_model(modelIdentifier=model_id)
                    model_details_info = model_detail_response['modelDetails']

                    # Extract capabilities — prefer detail response; fall back to
                    # list-level modalities which AWS always populates correctly
                    input_modalities = model_details_info.get('inputModalities') or model.get('inputModalities', [])
                    output_modalities = model_details_info.get('outputModalities') or model.get('outputModalities', [])

                    # Categorize by capability
                    capabilities = []
                    if 'TEXT' in input_modalities and 'TEXT' in output_modalities:
                        capabilities.append('text_generation')
                        models_by_capability['text_generation'].append({
                            'model_id': model_id,
                            'display_name': f"{provider_name} {model_name}",
                            'provider': provider_name.lower()
                        })

                    if 'TEXT' in input_modalities and 'EMBEDDING' in output_modalities:
                        capabilities.append('text_embedding')
                        models_by_capability['text_embedding'].append({
                            'model_id': model_id,
                            'display_name': f"{provider_name} {model_name} (Embedding)",
                            'provider': provider_name.lower()
                        })

                    if len(input_modalities) > 1 or len(output_modalities) > 1:
                        capabilities.append('multimodal')
                        models_by_capability['multimodal'].append({
                            'model_id': model_id,
                            'display_name': f"{provider_name} {model_name} (Multimodal)",
                            'provider': provider_name.lower()
                        })

                    # Store detailed information
                    model_details[model_id] = {
                        'model_id': model_id,
                        'model_name': model_name,
                        'provider_name': provider_name,
                        'display_name': f"{provider_name} {model_name}",
                        'capabilities': capabilities,
                        'input_modalities': input_modalities,
                        'output_modalities': output_modalities,
                        'customizations_supported': model_details_info.get('customizationsSupported', []),
                        'inference_types_supported': model_details_info.get('inferenceTypesSupported', []),
                        'response_streaming_supported': model_details_info.get('responseStreamingSupported', False),
                        'model_lifecycle_status': model_lifecycle_status
                    }

                except Exception as detail_error:
                    # Legacy/inactive models surface a ResourceNotFoundException here
                    # even though list_foundation_models still returns them as ACTIVE.
                    # Skip completely so they never appear in the UI or model cache.
                    if _is_legacy_model_error(detail_error):
                        logger.warning(
                            f"Skipping legacy/inactive model {model_id} "
                            f"(ResourceNotFoundException during detail fetch): {detail_error}"
                        )
                        skipped_foundation_models += 1
                        active_foundation_models -= 1  # correct the earlier increment
                        continue  # do NOT add to model_details or all_models
                    logger.warning(f"Could not get details for model {model_id}: {detail_error}")
                    # Add basic info for non-legacy detail failures so the model
                    # still appears in the cache with sensible defaults.
                    model_details[model_id] = {
                        'model_id': model_id,
                        'model_name': model_name,
                        'provider_name': provider_name,
                        'display_name': f"{provider_name} {model_name}",
                        'capabilities': ['text_generation'],  # Assume basic capability
                        'input_modalities': ['TEXT'],
                        'output_modalities': ['TEXT'],
                        'customizations_supported': [],
                        'inference_types_supported': [],
                        'response_streaming_supported': True,
                        'model_lifecycle_status': model_lifecycle_status
                    }

                # Add to all models list
                models_by_capability['all_models'].append(model_details[model_id])

            # Log filtering summary for foundation models
            logger.info(
                f"Foundation model filtering summary: {active_foundation_models} ACTIVE models cached, "
                f"{skipped_foundation_models} non-ACTIVE/legacy models skipped "
                f"(out of {total_foundation_models} total)"
            )

            # Cache results
            cache_result = {
                'models_by_capability': models_by_capability,
                'model_details': model_details,
                'total_models': len(model_details),
                'last_updated': time.time(),
                'region': self.region_name
            }
            
            logger.info(f"Successfully fetched {len(model_details)} models from AWS Bedrock")
            return cache_result
            
        except ClientError as e:
            logger.error(f"AWS Bedrock API error: {e}")
            # Return empty structure on failure
            return {
                'models_by_capability': {'text_generation': [], 'text_embedding': [], 'multimodal': [], 'all_models': []},
                'model_details': {},
                'total_models': 0,
                'error': str(e),
                'region': self.region_name
            }
        except Exception as e:
            logger.error(f"Error fetching Bedrock models: {e}")
            # Return empty structure on failure
            return {
                'models_by_capability': {'text_generation': [], 'text_embedding': [], 'multimodal': [], 'all_models': []},
                'model_details': {},
                'total_models': 0,
                'error': str(e),
                'region': self.region_name
            }
    
    def update_default_models(self, new_defaults: Dict[str, str]) -> bool:
        """
        Update default model selections (could be stored in SSM for persistence).
        
        Args:
            new_defaults: Dictionary of new default model selections
            
        Returns:
            True if successful
        """
        try:
            # Validate all model IDs are available
            for model_purpose, model_id in new_defaults.items():
                if not self.validate_model_id(model_id):
                    logger.error(f"Invalid model ID for {model_purpose}: {model_id}")
                    return False
            
            # Update defaults
            self.default_models.update(new_defaults)
            
            # TODO: Store in SSM parameter for persistence across restarts
            # self.ssm_service.store_json_parameter("/system/default_models", self.default_models)
            
            logger.info(f"Updated default models: {new_defaults}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating default models: {e}")
            return False
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Test Bedrock connectivity and return service status.
        
        Returns:
            Dictionary containing connection status and region info
        """
        try:
            # Test connectivity by listing a small number of models
            response = self.bedrock_client.list_foundation_models(maxResults=1)
            return {
                "status": "connected",
                "region": self.region_name,
                "service": "bedrock",
                "models_available": len(response.get('modelSummaries', []))
            }
        except Exception as e:
            logger.error(f"Bedrock connectivity test failed: {e}")
            return {
                "status": "error",
                "region": self.region_name,
                "service": "bedrock", 
                "error": str(e)
            }
