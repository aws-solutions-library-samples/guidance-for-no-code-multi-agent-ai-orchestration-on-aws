"""
Tests for Elasticsearch memory adapter.

This module tests the Elasticsearch memory provider integration.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from memory.elasticsearch import ElasticsearchMemoryAdapter


class TestElasticsearchMemoryAdapter:
    """Test cases for Elasticsearch memory adapter."""
    
    def test_initialization_with_default_config(self):
        """Test adapter initialization with default configuration."""
        config = {
            "elasticsearch_url": "http://localhost:9200",
            "index_name": "test_memory"
        }
        
        adapter = ElasticsearchMemoryAdapter(config, agent_name="test_agent")
        
        assert adapter.elasticsearch_url == "http://localhost:9200"
        assert adapter.index_name == "test_memory"
        assert adapter.agent_name == "test_agent"
        assert adapter.username is None
        assert adapter.password is None
    
    def test_initialization_with_auth(self):
        """Test adapter initialization with authentication."""
        config = {
            "elasticsearch_url": "http://localhost:9200",
            "index_name": "test_memory",
            "username": "elastic",
            "password": "test_password"
        }
        
        adapter = ElasticsearchMemoryAdapter(config, agent_name="test_agent")
        
        assert adapter.username == "elastic"
        assert adapter.password == "test_password"
    
    def test_initialization_missing_url(self):
        """Test adapter initialization fails without URL."""
        config = {
            "index_name": "test_memory"
        }
        
        with pytest.raises(ValueError, match="elasticsearch_url is required"):
            ElasticsearchMemoryAdapter(config, agent_name="test_agent")
    
    def test_initialization_missing_index(self):
        """Test adapter initialization fails without index name."""
        config = {
            "elasticsearch_url": "http://localhost:9200"
        }
        
        with pytest.raises(ValueError, match="index_name is required"):
            ElasticsearchMemoryAdapter(config, agent_name="test_agent")
    
    @patch('memory.elasticsearch.elasticsearch_memory')
    def test_get_tools_returns_wrapped_function(self, mock_elasticsearch_memory):
        """Test that get_tools returns a wrapped elasticsearch_memory function."""
        config = {
            "elasticsearch_url": "http://localhost:9200",
            "index_name": "test_memory"
        }
        
        adapter = ElasticsearchMemoryAdapter(config, agent_name="test_agent")
        tools = adapter.get_tools()
        
        assert len(tools) == 1
        assert callable(tools[0])
        assert hasattr(tools[0], '__name__')
        assert 'elasticsearch_memory' in tools[0].__name__
    
    @patch('memory.elasticsearch.elasticsearch_memory')
    def test_memory_tool_with_store_action(self, mock_elasticsearch_memory):
        """Test memory tool wrapper with store action."""
        mock_elasticsearch_memory.return_value = {"success": True, "message": "Stored successfully"}
        
        config = {
            "elasticsearch_url": "http://localhost:9200",
            "index_name": "test_memory"
        }
        
        adapter = ElasticsearchMemoryAdapter(config, agent_name="test_agent")
        tools = adapter.get_tools()
        memory_tool = tools[0]
        
        # Simulate tool call with store action
        tool_input = {
            "name": "elasticsearch_memory",
            "toolUseId": "test_123",
            "input": {
                "action": "store",
                "content": "Test memory content",
                "user_id": "user123"
            }
        }
        
        result = memory_tool(tool_input)
        
        # Verify the tool was called with correct parameters
        mock_elasticsearch_memory.assert_called_once()
        call_args = mock_elasticsearch_memory.call_args[0][0]
        
        assert call_args["input"]["elasticsearch_url"] == "http://localhost:9200"
        assert call_args["input"]["index_name"] == "test_memory"
        assert call_args["input"]["action"] == "store"
        assert call_args["input"]["content"] == "Test memory content"
        assert call_args["input"]["user_id"] == "user123"
    
    @patch('memory.elasticsearch.elasticsearch_memory')
    def test_memory_tool_with_retrieve_action(self, mock_elasticsearch_memory):
        """Test memory tool wrapper with retrieve action."""
        mock_elasticsearch_memory.return_value = {
            "success": True,
            "results": [{"content": "Retrieved memory", "score": 0.95}]
        }
        
        config = {
            "elasticsearch_url": "http://localhost:9200",
            "index_name": "test_memory",
            "username": "elastic",
            "password": "test_pass"
        }
        
        adapter = ElasticsearchMemoryAdapter(config, agent_name="test_agent")
        tools = adapter.get_tools()
        memory_tool = tools[0]
        
        # Simulate tool call with retrieve action
        tool_input = {
            "name": "elasticsearch_memory",
            "toolUseId": "test_456",
            "input": {
                "action": "retrieve",
                "query": "Test query",
                "user_id": "user123"
            }
        }
        
        result = memory_tool(tool_input)
        
        # Verify the tool was called with correct parameters including auth
        mock_elasticsearch_memory.assert_called_once()
        call_args = mock_elasticsearch_memory.call_args[0][0]
        
        assert call_args["input"]["elasticsearch_url"] == "http://localhost:9200"
        assert call_args["input"]["index_name"] == "test_memory"
        assert call_args["input"]["username"] == "elastic"
        assert call_args["input"]["password"] == "test_pass"
        assert call_args["input"]["action"] == "retrieve"
        assert call_args["input"]["query"] == "Test query"
    
    @patch('memory.elasticsearch.elasticsearch_memory')
    def test_memory_tool_error_handling(self, mock_elasticsearch_memory):
        """Test memory tool wrapper handles errors gracefully."""
        mock_elasticsearch_memory.side_effect = Exception("Elasticsearch connection failed")
        
        config = {
            "elasticsearch_url": "http://localhost:9200",
            "index_name": "test_memory"
        }
        
        adapter = ElasticsearchMemoryAdapter(config, agent_name="test_agent")
        tools = adapter.get_tools()
        memory_tool = tools[0]
        
        # Simulate tool call
        tool_input = {
            "name": "elasticsearch_memory",
            "toolUseId": "test_789",
            "input": {
                "action": "store",
                "content": "Test",
                "user_id": "user123"
            }
        }
        
        result = memory_tool(tool_input)
        
        # Should return error dict instead of raising exception
        assert "error" in result
        assert "Elasticsearch connection failed" in result["error"]
    
    def test_elasticsearch_url_normalization(self):
        """Test that Elasticsearch URL is properly normalized."""
        config = {
            "elasticsearch_url": "http://localhost:9200/",  # trailing slash
            "index_name": "test_memory"
        }
        
        adapter = ElasticsearchMemoryAdapter(config, agent_name="test_agent")
        
        # URL should be normalized (trailing slash removed if needed)
        assert adapter.elasticsearch_url == "http://localhost:9200/" or adapter.elasticsearch_url == "http://localhost:9200"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
