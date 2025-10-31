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
            
            for model in response.get('modelSummaries', []):
                model_id = model['modelId']
                model_name = model['modelName']
                provider_name = model['providerName']
                
                # Get detailed model information for foundation models
                try:
                    model_detail_response = self.bedrock_client.get_foundation_model(modelIdentifier=model_id)
                    model_details_info = model_detail_response['modelDetails']
                    
                    # Extract capabilities
                    input_modalities = model_details_info.get('inputModalities', [])
                    output_modalities = model_details_info.get('outputModalities', [])
                    
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
                        'response_streaming_supported': model_details_info.get('responseStreamingSupported', False)
                    }
                    
                except Exception as detail_error:
                    logger.warning(f"Could not get details for model {model_id}: {detail_error}")
                    # Add basic info even if details fail
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
                        'response_streaming_supported': True
                    }
                
                # Add to all models list
                models_by_capability['all_models'].append(model_details[model_id])
            
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
        
        Args:
            force_refresh: Whether to bypass cache and fetch fresh data
            
        Returns:
            Dictionary containing available models with metadata
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
                
                # Get detailed model information
                try:
                    model_detail_response = self.bedrock_client.get_foundation_model(modelIdentifier=model_id)
                    model_details_info = model_detail_response['modelDetails']
                    
                    # Extract capabilities
                    input_modalities = model_details_info.get('inputModalities', [])
                    output_modalities = model_details_info.get('outputModalities', [])
                    
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
                        'response_streaming_supported': model_details_info.get('responseStreamingSupported', False)
                    }
                    
                except Exception as detail_error:
                    logger.warning(f"Could not get details for model {model_id}: {detail_error}")
                    # Add basic info even if details fail
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
                        'response_streaming_supported': True
                    }
                
                # Add to all models list
                models_by_capability['all_models'].append(model_details[model_id])
            
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
