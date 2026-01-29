# Custom direct client knowledge base providers

from .aurora import AuroraKnowledgeBaseProvider
from .bedrock_kb import BedrockKnowledgeBaseProvider
from .elastic import ElasticKnowledgeBaseProvider
from .snowflake import SnowflakeKnowledgeBaseProvider

# Import MongoDB provider with error handling
try:
    from .mongodb import MongoDBKnowledgeBaseProvider
    _mongodb_available = True
except ImportError as e:
    print(f"Warning: MongoDB provider import failed: {e}")
    MongoDBKnowledgeBaseProvider = None
    _mongodb_available = False

__all__ = [
    'AuroraKnowledgeBaseProvider',
    'BedrockKnowledgeBaseProvider', 
    'ElasticKnowledgeBaseProvider',
    'MongoDBKnowledgeBaseProvider',
    'SnowflakeKnowledgeBaseProvider'
]
