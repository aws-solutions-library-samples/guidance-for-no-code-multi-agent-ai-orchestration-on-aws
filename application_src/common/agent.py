"""
Agent module for GenAI-In-A-Box.
This module provides functions for creating and running agents.
"""

import os
import traceback
import uuid
from typing import Iterator, Dict, Any, Optional

# Import logging configuration
from logging_config import get_logger, log_debug, log_info, log_error_without_exception, log_exception, log_warning

# Initialize logger for this module
logger = get_logger(__name__)

# CRITICAL: Initialize observability BEFORE importing Strands Agent
# This ensures environment variables are set before Strands Agent initialization
log_info(logger, "🔧 Initializing observability before Strands Agent import")
from config import Config
from observability import ObservabilityFactory

# Note: Observability will be initialized per-agent, not at module level
log_warning(logger, "⚠️ Observability will be initialized per-agent - Strands Agent will run without global tracing")

# NOW import Strands Agent and tracer (after environment variables are set)
from strands import Agent, tool
from strands.models import BedrockModel
from strands.telemetry.tracer import get_tracer
from strands_tools import http_request

# Import system prompt
from system_prompt import get_system_prompt

# Import providers
from memory import get_memory_tools
from knowledge_base import KnowledgeBaseFactory, reset_knowledge_base_provider
from observability import get_trace_attributes
from tools import get_default_tools, get_mcp_connection_info
from tools.custom import get_custom_tools

def create_tool_wrapper(name: str, description: str, input_schema: Dict[str, Any], conn_id: str):
    """
    Create a tool wrapper function for MCP tools with runtime execution fix.
    
    This function handles both function and module cases for mcp_client execution
    to fix "'module' object is not callable" errors discovered in production.
    """
    try:
        from strands_tools import mcp_client
    except ImportError as e:
        print(f"🚨 Failed to import mcp_client from strands_tools: {e}")
        return None
    
    def mcp_tool_func(tool_input: dict) -> dict:
        """Execute MCP tool with proper error handling for both function and module cases."""
        try:
            # Prepare arguments
            final_args = tool_input if isinstance(tool_input, dict) else {}
            
            print(f"🛠️ Calling MCP tool '{name}' with connection_id '{conn_id}'")
            
            # Call the MCP server tool - handle both function and module cases
            try:
                # Try calling it as a function first
                result = mcp_client(
                    action="call_tool",
                    connection_id=conn_id,
                    tool_name=name,
                    arguments=final_args
                )
            except TypeError as e:
                # If it's a module, we need to find the actual function
                print(f"🔧 mcp_client is a module, looking for the function...")
                if hasattr(mcp_client, 'mcp_client'):
                    # Try calling the function inside the module
                    result = mcp_client.mcp_client(
                        action="call_tool",
                        connection_id=conn_id,
                        tool_name=name,
                        arguments=final_args
                    )
                else:
                    print(f"🚨 Cannot find mcp_client function in module: {e}")
                    return {"error": f"MCP client module error: {e}", "success": False}
            
            print(f"✅ MCP tool '{name}' executed successfully")
            return result
            
        except Exception as e:
            print(f"🚨 Error executing MCP tool '{name}': {e}")
            return {
                "error": f"Failed to execute MCP tool '{name}': {str(e)}",
                "success": False
            }
    
    # Set function metadata for Strands Agent recognition
    mcp_tool_func.__name__ = f"mcp_{name.replace('-', '_')}"
    mcp_tool_func.__doc__ = description
    mcp_tool_func.input_schema = input_schema
    
    # Apply Strands @tool decorator - this is critical for recognition
    return tool(mcp_tool_func)

# Import retrieve tool for Bedrock Knowledge Base
try:
    from strands_tools import retrieve
    log_debug(logger, "Successfully imported retrieve tool", tool=str(retrieve))
except ImportError as e:
    log_warning(logger, "Failed to import retrieve tool", error=str(e))
    retrieve = None

# Initialize mem0_module to None - will be imported only if memory is enabled
mem0_module = None

# Knowledge base provider will be initialized per-agent, not at module level
# This ensures each agent gets its own properly configured KB provider
kb_provider = None  # Will be initialized per-agent

# Default user ID for memory operations when none is provided
DEFAULT_USER_ID = "default_user"

def get_mcp_tools_for_agent(agent_name):
    """Get MCP tools for a specific agent using in-memory connection info."""
    try:
        print(f"📁 Loading MCP tools from in-memory storage for {agent_name}")
        
        # Get MCP connection info from in-memory storage
        mcp_info = get_mcp_connection_info(agent_name)
        if not mcp_info:
            print(f"No MCP connection info found for {agent_name}")
            return []
            
        print(f"🔗 Found MCP connection info: {len(mcp_info.get('available_tools', []))} tools from {mcp_info.get('server_url', 'unknown server')}")
        
        # Import mcp_client for tool execution
        try:
            from strands_tools import mcp_client
        except ImportError as e:
            print(f"Failed to import mcp_client: {e}")
            return []
        
        # Create direct tool wrappers for each MCP tool
        mcp_tools = []
        connection_id = mcp_info.get("connection_id")
        available_tools = mcp_info.get("available_tools", [])
        
        for tool_info in available_tools:
            tool_name = tool_info.get("name", "")
            tool_description = tool_info.get("description", "")
            input_schema = tool_info.get("inputSchema", {})
            
            # Create a direct MCP tool wrapper with mcp_ prefix
            def create_direct_mcp_tool(name, description, schema, conn_id):
                @tool
                def mcp_tool_direct(tool_input: dict) -> dict:
                    """Dynamically created MCP tool wrapper."""
                    try:
                        # Handle both function and module cases for mcp_client
                        try:
                            result = mcp_client(
                                action="call_tool",
                                connection_id=conn_id,
                                tool_name=name,
                                arguments=tool_input
                            )
                        except TypeError:
                            # If it's a module, try calling the function inside
                            if hasattr(mcp_client, 'mcp_client'):
                                result = mcp_client.mcp_client(
                                    action="call_tool",
                                    connection_id=conn_id,
                                    tool_name=name,
                                    arguments=tool_input
                                )
                            else:
                                raise
                        
                        return result
                    except Exception as e:
                        return {"error": f"MCP tool execution failed: {str(e)}"}
                
                # Set function metadata for Strands Agent recognition
                mcp_tool_direct.__name__ = f"mcp_{name}"
                mcp_tool_direct.__doc__ = description
                
                return mcp_tool_direct
            
            mcp_tool = create_direct_mcp_tool(tool_name, tool_description, input_schema, connection_id)
            mcp_tools.append(mcp_tool)
            
        print(f"✅ Created {len(mcp_tools)} MCP tool wrappers for agent creation")
        return mcp_tools
        
    except Exception as e:
        print(f"❌ Error loading MCP tools: {e}")
        import traceback
        traceback.print_exc()
        return []

def load_mcp_tools_into_agent(agent_name):
    """Load MCP tools into agent using in-memory storage (backwards compatibility)."""
    print(f"🔄 Checking for MCP tools for agent: {agent_name}")
    
    # Check if MCP connection info exists in memory
    mcp_info = get_mcp_connection_info(agent_name)
    if not mcp_info:
        print(f"No MCP connection info found in memory for {agent_name}")
        return False
        
    print(f"✅ MCP connection info found in memory: {len(mcp_info.get('available_tools', []))} tools available")
    return True

def check_memory_config(agent_name="qa_agent"):
    """Check if memory configuration is properly set up."""
    log_debug(logger, "=== Memory Configuration Check ===")
    log_debug(logger, "Memory API key status", 
              mem0_api_key_set='MEM0_API_KEY' in os.environ)
    if 'MEM0_API_KEY' in os.environ:
        key = os.environ['MEM0_API_KEY']
        log_debug(logger, "API key details", 
                  key_length=len(key), 
                  valid_format=key.startswith('m0-'))
    
    # Create a config instance with the specified agent_name
    from config import Config
    agent_config = Config(agent_name)
    
    memory_config = agent_config.get_memory_config()
    log_debug(logger, "Memory configuration details",
              enabled=memory_config.get('enabled', False),
              provider=memory_config.get('provider', 'unknown'),
              agent_name=agent_name)
    log_debug(logger, "================================")
    
    return memory_config

def test_memory_with_user_id(user_id=None):
    """Test memory operations with a specific user ID."""
    try:
        # Set user_id to default if not provided
        if user_id is None:
            user_id = DEFAULT_USER_ID
            
        log_debug(logger, "Testing memory with user_id", user_id=user_id)
        
        # Check if memory is enabled
        agent_config = Config(agent_name)
        memory_config = agent_config.get_memory_config()
        memory_enabled = memory_config.get("enabled", False)
        
        if not memory_enabled:
            log_info(logger, "Memory is disabled, skipping test")
            return False
        
        # Check if mem0_memory function is available
        if not mem0_module or not hasattr(mem0_module, 'mem0_memory'):
            log_warning(logger, "Skipping memory test - mem0_memory function not available")
            return False
        
        # Generate a test ID
        test_id = str(uuid.uuid4())
        log_debug(logger, "Testing memory with ID", test_id=test_id)
        
        # Test store operation
        log_debug(logger, "Testing store operation")
        store_result = mem0_module.mem0_memory({
            "name": "mem0_memory",
            "toolUseId": f"test_store_{test_id}",
            "input": {
                "action": "store",
                "content": f"Test memory {test_id}",
                "user_id": user_id
            }
        })
        log_debug(logger, "Store result", result=store_result)
        
        # Test retrieve operation
        log_debug(logger, "Testing retrieve operation")
        retrieve_result = mem0_module.mem0_memory({
            "name": "mem0_memory",
            "toolUseId": f"test_retrieve_{test_id}",
            "input": {
                "action": "retrieve",
                "query": f"Test memory {test_id}",
                "user_id": user_id
            }
        })
        log_debug(logger, "Retrieve result", result=retrieve_result)
        
        # Test list operation
        log_debug(logger, "Testing list operation")
        list_result = mem0_module.mem0_memory({
            "name": "mem0_memory",
            "toolUseId": f"test_list_{test_id}",
            "input": {
                "action": "list",
                "user_id": user_id
            }
        })
        log_debug(logger, "List result", result=list_result)
        
        return True
    except Exception as e:
        log_exception(logger, f"Memory test failed: {str(e)}")
        return False

def create_agent(prompt, user_id=None, agent_name="qa_agent"):
    """Create an agent with the latest configuration from SSM"""
    
    # Set user_id to default if not provided
    if user_id is None:
        user_id = DEFAULT_USER_ID
    
    log_debug(logger, "Creating agent", user_id=user_id, agent_name=agent_name)
    
    try:
        # Create a config instance with the specified agent_name
        from config import Config
        agent_config = Config(agent_name)
        
        # Get model configuration
        model_config = agent_config.get_model_config()
        
        # Get guardrail configuration
        guardrail_config = agent_config.get_guardrail_config()
        
        # Reset knowledge base provider to ensure we get the latest configuration
        log_debug(logger, "Resetting knowledge base provider to get latest configuration")
        reset_knowledge_base_provider()
        
        # Create a new knowledge base provider with the latest configuration
        global kb_provider
        kb_provider = KnowledgeBaseFactory.create(agent_name)
        log_debug(logger, "Created KB provider", agent_name=agent_name)
        
        # Create a Bedrock model instance with the configuration parameters
        bedrock_model_params = {
            "model_id": model_config["model_id"],
            "temperature": model_config["temperature"],
            "top_p": model_config["top_p"],
            "streaming": model_config["streaming"]  # Take streaming from SSM model_config
        }
        
        # Add guardrail configuration if enabled
        if guardrail_config["enabled"]:
            for provider in guardrail_config["provider_details"]:
                if provider["name"] == "bedrock_guardrails":
                    guardrail_id = provider["config"].get("guardrail_id", "")
                    if guardrail_id:
                        bedrock_model_params["guardrail_id"] = guardrail_id
                        bedrock_model_params["guardrail_trace"] = "enabled"
        
        # Create the Bedrock model
        bedrock_model = BedrockModel(**bedrock_model_params)
        
        # Get the system prompt with user_id context
        system_prompt = get_system_prompt(user_id=user_id)
        
        # Initialize tools list with default tools
        tools = get_default_tools()
        
        # Add custom tools
        custom_tools = get_custom_tools()
        if custom_tools:
            tools.extend(custom_tools)
        
        # Add memory tools if enabled
        agent_config = Config(agent_name)
        memory_config = agent_config.get_memory_config()
        memory_enabled = memory_config.get("enabled", False)
        
        log_debug(logger, "Memory configuration", memory_enabled=memory_enabled)
        
        if memory_enabled:
            # Import mem0_memory module only if memory is enabled
            global mem0_module
            if mem0_module is None:
                try:
                    import strands_tools.mem0_memory as mem0_module
                    log_debug(logger, "Successfully imported mem0_memory module", module=str(mem0_module))
                except ImportError as e:
                    log_warning(logger, "Failed to import mem0_memory module", error=str(e))
                    mem0_module = None
            
            memory_tools = get_memory_tools(agent_name)
            if memory_tools:
                tools.extend(memory_tools)
        else:
            log_debug(logger, "Memory is disabled, skipping memory tools")
        
        # Add knowledge base tools if available
        if kb_provider and hasattr(kb_provider, 'tools'):
            # Ensure tools are initialized
            kb_tools = kb_provider.get_tools()
            if kb_tools:
                print(f"DEBUG AGENT: Adding {len(kb_tools)} knowledge base tools from provider: {getattr(kb_provider, 'provider_name', 'unknown')}")
                for i, tool in enumerate(kb_tools):
                    tool_name = tool.__name__ if hasattr(tool, '__name__') else str(tool)
                    print(f"  KB Tool {i+1}: {tool_name}")
                tools.extend(kb_tools)
            else:
                print("No knowledge base tools available")
        
        # Configure Strands SDK observability (get_tracer + logging)
        try:
            observability_provider = ObservabilityFactory.get_current_provider()
            if observability_provider:
                service_name = observability_provider.trace_attributes.get("service.name", agent_name)
                environment = observability_provider.trace_attributes.get("deployment.environment", "production")
                
                print(f"🔍 Configuring Strands SDK observability for {observability_provider.provider_name}...")
                
                # Configure Strands tracer with provider-specific settings
                if hasattr(observability_provider, 'get_strands_tracer_config'):
                    tracer_config = observability_provider.get_strands_tracer_config(service_name, environment)
                    if tracer_config:
                        print(f"📡 Configuring Strands get_tracer with {observability_provider.provider_name} settings...")
                        tracer = get_tracer(**tracer_config)
                        print(f"✅ Strands tracer configured for {observability_provider.provider_name}")
                
                # Configure Strands logging with provider-specific settings  
                if hasattr(observability_provider, 'configure_strands_logging'):
                    observability_provider.configure_strands_logging(service_name, environment)
                
        except Exception as obs_error:
            print(f"⚠️ Error configuring Strands SDK observability: {obs_error}")
        
        # Get trace attributes for observability
        trace_attributes = get_trace_attributes(agent_name)
        
        # Store the user query in memory if memory is enabled
        if memory_enabled and mem0_module and hasattr(mem0_module, 'mem0_memory'):
            try:
                # Use the mem0_memory function from the module
                store_result = mem0_module.mem0_memory({
                    "name": "mem0_memory",
                    "toolUseId": f"store_query_{uuid.uuid4()}",
                    "input": {
                        "action": "store",
                        "content": f"User query: {prompt}",
                        "user_id": user_id
                    }
                })
                print(f"Stored user query in memory for user_id={user_id}: {store_result}")
            except Exception as e:
                print(f"Failed to store query in memory: {str(e)}")
        
        # Create the agent with the configured model, tools, and system prompt
        print(f"🤖 Creating Strands Agent with trace attributes: {trace_attributes}")
        agent = Agent(
            model=bedrock_model,
            tools=tools,
            system_prompt=system_prompt,
            trace_attributes=trace_attributes
        )
        
        print(f"✅ Strands Agent created successfully with observability")
        # Return the agent
        return agent
    except Exception as e:
        print(f"Error creating agent: {str(e)}")
        traceback.print_exc()
        return None

def run_agent(prompt: str, user_id=None, agent_name="qa_agent"):
    """Create and run an agent with the given prompt."""
    # Set user_id to default if not provided
    if user_id is None:
        user_id = DEFAULT_USER_ID
    
    print(f"DEBUG AGENT: Running agent for user_id: {user_id}, agent_name: {agent_name}")
    
    try:
        # Create the agent with the specified agent_name
        agent = create_agent(prompt, user_id, agent_name)
        if not agent:
            return "Error: Failed to create agent"
        
        # Run the agent
        agent_result = agent(prompt)  # Call the agent directly and get AgentResult
        
        # Extract response from AgentResult
        response = str(agent_result)  # AgentResult can be converted to string for response
        
        # Send Strands metrics to observability provider if configured
        try:
            observability_provider = ObservabilityFactory.get_current_provider()
            if observability_provider and hasattr(observability_provider, 'process_strands_metrics'):
                service_name = observability_provider.trace_attributes.get("service.name", agent_name)
                environment = observability_provider.trace_attributes.get("deployment.environment", "production")
                
                print(f"📊 Forwarding Strands metrics to {observability_provider.provider_name}...")
                observability_provider.process_strands_metrics(
                    agent_result, service_name, environment
                )
            else:
                print("ℹ️ No observability provider configured for metrics")
        except Exception as metrics_error:
            print(f"⚠️ Failed to process Strands metrics: {metrics_error}")
        
        # Get memory configuration from the specified agent
        from config import Config
        agent_config = Config(agent_name)
        memory_config = agent_config.get_memory_config()
        memory_enabled = memory_config.get("enabled", False)
        
        # Store the response in memory if memory is enabled
        if memory_enabled and mem0_module and hasattr(mem0_module, 'mem0_memory'):
            try:
                # Use the mem0_memory function from the module
                store_result = mem0_module.mem0_memory({
                    "name": "mem0_memory",
                    "toolUseId": f"store_response_{uuid.uuid4()}",
                    "input": {
                        "action": "store",
                        "content": f"Assistant response: {response}",
                        "user_id": user_id
                    }
                })
                print(f"Stored response in memory for user_id={user_id}: {store_result}")
            except Exception as e:
                print(f"Failed to store response in memory: {str(e)}")
        
        return response
    except Exception as e:
        print(f"Error creating agent: {str(e)}")
        traceback.print_exc()
        return f"Error: {str(e)}"

async def run_agent_and_stream_response(prompt: str, user_id=None, agent_name="qa_agent"):
    """
    A helper function to yield summary text chunks one by one as they come in,
    allowing the web server to emit them to caller live
    """
    # Set user_id to default if not provided
    if user_id is None:
        user_id = DEFAULT_USER_ID
    
    print(f"DEBUG AGENT STREAMING: Streaming response for user_id: {user_id}, agent_name: {agent_name}")
    
    try:
        # Create a config instance with the specified agent_name
        from config import Config
        agent_config = Config(agent_name)
        
        # Get model configuration
        model_config = agent_config.get_model_config()
        
        # Get guardrail configuration
        guardrail_config = agent_config.get_guardrail_config()
        
        # Reset knowledge base provider to ensure we get the latest configuration
        print("Resetting knowledge base provider to get latest configuration")
        reset_knowledge_base_provider()
        
        # Create a new knowledge base provider with the latest configuration
        global kb_provider
        kb_provider = KnowledgeBaseFactory.create(agent_name)
        print(f"DEBUG AGENT: Created KB provider for agent_name: {agent_name}")
        
        # Create a Bedrock model instance with the configuration parameters
        bedrock_model_params = {
            "model_id": model_config["model_id"],
            "temperature": model_config["temperature"],
            "top_p": model_config["top_p"],
            "streaming": True  # Force streaming for this function
        }
        
        # Add guardrail configuration if enabled
        if guardrail_config["enabled"]:
            for provider in guardrail_config["provider_details"]:
                if provider["name"] == "bedrock_guardrails":
                    guardrail_id = provider["config"].get("guardrail_id", "")
                    if guardrail_id:
                        bedrock_model_params["guardrail_id"] = guardrail_id
                        bedrock_model_params["guardrail_trace"] = "enabled"
        
        # Create the Bedrock model
        bedrock_model = BedrockModel(**bedrock_model_params)
        
        # Get the system prompt with user_id context (no special streaming instructions needed)
        system_prompt = get_system_prompt(user_id=user_id)
        
        # Initialize tools list with default tools
        tools = get_default_tools()
        
        # Add custom tools
        custom_tools = get_custom_tools()
        if custom_tools:
            tools.extend(custom_tools)
        
        # Add memory tools if enabled
        agent_config = Config(agent_name)
        memory_config = agent_config.get_memory_config()
        memory_enabled = memory_config.get("enabled", False)
        
        print(f"Memory enabled: {memory_enabled}")
        
        if memory_enabled:
            # Import mem0_memory module only if memory is enabled
            global mem0_module
            if mem0_module is None:
                try:
                    import strands_tools.mem0_memory as mem0_module
                    print(f"Successfully imported mem0_memory module: {mem0_module}")
                except ImportError as e:
                    print(f"Failed to import mem0_memory module: {e}")
                    mem0_module = None
            
            memory_tools = get_memory_tools(agent_name)
            if memory_tools:
                tools.extend(memory_tools)
        else:
            print("Memory is disabled, skipping memory tools")
        
        # Add knowledge base tools if available
        if kb_provider and hasattr(kb_provider, 'tools'):
            # Ensure tools are initialized
            kb_tools = kb_provider.get_tools()
            if kb_tools:
                print(f"DEBUG AGENT: Adding {len(kb_tools)} knowledge base tools from provider: {getattr(kb_provider, 'provider_name', 'unknown')}")
                for i, tool in enumerate(kb_tools):
                    tool_name = tool.__name__ if hasattr(tool, '__name__') else str(tool)
                    print(f"  KB Tool {i+1}: {tool_name}")
                tools.extend(kb_tools)
            else:
                print("No knowledge base tools available")
        
        # Get trace attributes for observability
        trace_attributes = get_trace_attributes(agent_name)
        
        # Store the user query in memory if memory is enabled
        if memory_enabled and mem0_module and hasattr(mem0_module, 'mem0_memory'):
            try:
                # Use the mem0_memory function from the module
                store_result = mem0_module.mem0_memory({
                    "name": "mem0_memory",
                    "toolUseId": f"store_query_{uuid.uuid4()}",
                    "input": {
                        "action": "store",
                        "content": f"User query: {prompt}",
                        "user_id": user_id
                    }
                })
                print(f"Stored user query in memory for user_id={user_id}: {store_result}")
            except Exception as e:
                print(f"Failed to store query in memory: {str(e)}")
        
        # Create the agent with the configured model, tools, and system prompt
        print(f"🤖 Creating Strands Streaming Agent with trace attributes: {trace_attributes}")
        agent = Agent(
            model=bedrock_model,
            tools=tools,
            system_prompt=system_prompt,
            trace_attributes=trace_attributes
        )
        
        print(f"✅ Strands Streaming Agent created successfully with observability")
        
        # Stream all response content (not just after ready_to_summarize)
        response = ""
        tool_usage_phase = True
        response_phase = False
        
        async for item in agent.stream_async(prompt):
            print(f"Stream item: {item}")  # Debug logging
            
            if "data" in item:
                chunk_text = item['data']
                
                # Check if we're transitioning from tool usage to response
                if tool_usage_phase and chunk_text.strip() and not chunk_text.startswith("Tool #"):
                    # We've moved past tool usage, start streaming response
                    tool_usage_phase = False
                    response_phase = True
                    print("🚀 Starting response streaming phase")
                
                # Stream content during response phase
                if response_phase:
                    response += chunk_text
                    yield chunk_text
                    print(f"Streamed chunk: {repr(chunk_text)}")
        
        print(f"✅ Streaming completed. Total response length: {len(response)}")
        
        # Send Strands metrics to observability provider if configured (after streaming completes)
        try:
            observability_provider = ObservabilityFactory.get_current_provider()
            if observability_provider and hasattr(observability_provider, 'process_strands_metrics'):
                # Get the final AgentResult from the completed streaming
                final_result = agent.last_result if hasattr(agent, 'last_result') else None
                if final_result:
                    service_name = observability_provider.trace_attributes.get("service.name", agent_name)
                    environment = observability_provider.trace_attributes.get("deployment.environment", "production")
                    
                    print(f"📊 Forwarding Strands streaming metrics to {observability_provider.provider_name}...")
                    observability_provider.process_strands_metrics(
                        final_result, service_name, environment
                    )
                else:
                    print("ℹ️ No AgentResult available for metrics processing")
            else:
                print("ℹ️ No observability provider configured for metrics")
        except Exception as metrics_error:
            print(f"⚠️ Failed to process Strands streaming metrics: {metrics_error}")
        
        # Store the response in memory if memory is enabled
        if memory_enabled and mem0_module and hasattr(mem0_module, 'mem0_memory'):
            try:
                # Use the mem0_memory function from the module
                store_result = mem0_module.mem0_memory({
                    "name": "mem0_memory",
                    "toolUseId": f"store_response_{uuid.uuid4()}",
                    "input": {
                        "action": "store",
                        "content": f"Assistant response: {response}",
                        "user_id": user_id
                    }
                })
                print(f"Stored streaming response in memory for user_id={user_id}: {store_result}")
            except Exception as e:
                print(f"Failed to store response in memory: {str(e)}")
                
    except Exception as e:
        print(f"Error streaming response: {str(e)}")
        traceback.print_exc()
        yield f"Error: {str(e)}"
