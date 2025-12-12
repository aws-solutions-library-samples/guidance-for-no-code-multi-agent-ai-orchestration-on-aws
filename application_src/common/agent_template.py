"""
Agent template module for GenAI-In-A-Box multi-agent servers.
This module provides a concise function for creating agents with specific configurations.
"""

import os
import traceback
import uuid

# CRITICAL: Initialize observability BEFORE importing Strands Agent
print("🔧 Initializing observability before Strands Agent import...")
from config import Config
from observability import ObservabilityFactory

# Observability will be initialized per-agent in create_agent function
print("⚠️ No observability provider - Strands Agent will run without tracing")

# NOW import Strands Agent (after environment variables are set)
from strands import Agent
from strands.models import BedrockModel

# Import custom Bedrock provider for model switching
from custom_bedrock_provider import ModelSwitchingBedrockProvider

# Import system prompt
from system_prompt import get_system_prompt

# Import providers
from memory import get_memory_tools
from knowledge_base import KnowledgeBaseFactory, reset_knowledge_base_provider
from observability import get_trace_attributes
from tools import get_default_tools
from tools.custom import get_custom_tools

# Initialize mem0_module to None - will be imported only if memory is enabled
mem0_module = None

# Default user ID for memory operations when none is provided
DEFAULT_USER_ID = "default_user"

def create_agent(agent_name="qa_agent", agent_description="A QA agent that can answer questions from Knowledge Base", user_id=None, prompt="You are a knowledge assistant"):
    """Create an agent with the specified configuration from SSM"""
    
    # Set user_id to default if not provided
    if user_id is None:
        user_id = DEFAULT_USER_ID
    
    print(f"DEBUG CREATE_AGENT: Creating agent for user_id: {user_id}, agent_name: {agent_name}")
    
    try:
        # Initialize observability provider with the correct agent name
        print(f"🏭 ObservabilityFactory.create() called for agent: {agent_name}")
        obs_provider = ObservabilityFactory.create(agent_name)
        if obs_provider:
            print("✅ Observability provider initialized")
            obs_provider.initialize()
        else:
            print("❌ No observability provider available")
        
        # Create a config instance with the specified agent_name
        agent_config = Config(agent_name)
        
        # Get model configuration
        model_config = agent_config.get_model_config()
        
        # Get guardrail configuration
        guardrail_config = agent_config.get_guardrail_config()
        
        # Reset knowledge base provider to ensure we get the latest configuration
        print(f"DEBUG AGENT: Resetting knowledge base provider for agent_name: {agent_name}")
        reset_knowledge_base_provider()
        
        # Create a new knowledge base provider with the latest configuration
        kb_provider = KnowledgeBaseFactory.create(agent_name)
        provider_name = getattr(kb_provider, 'provider_name', 'unknown') if kb_provider else 'None'
        print(f"DEBUG AGENT: Created KB provider for agent_name: {agent_name}, provider: {provider_name}")
        
        # Create a Bedrock model instance with the configuration parameters
        bedrock_model_params = {
            "model_id": model_config["model_id"],
            "temperature": model_config["temperature"],
            "top_p": model_config["top_p"],
            "streaming": model_config["streaming"]
        }
        
        # Add guardrail configuration if enabled
        if guardrail_config["enabled"]:
            for provider in guardrail_config["provider_details"]:
                if provider["name"] == "bedrock_guardrails":
                    guardrail_id = provider["config"].get("guardrail_id", "")
                    if guardrail_id:
                        bedrock_model_params["guardrail_id"] = guardrail_id
                        bedrock_model_params["guardrail_trace"] = "enabled"
        
        # Create enhanced custom Bedrock provider with model switching capabilities
        custom_bedrock_provider = ModelSwitchingBedrockProvider()
        bedrock_model = custom_bedrock_provider.create_switching_model(
            initial_model_id=model_config["model_id"],
            region='us-east-1',  # Use default region, can be made configurable later
            max_tokens=4000,     # Can be made configurable later
            temperature=model_config["temperature"],
            top_p=model_config["top_p"]
        )
        
        print(f"✅ Agent '{agent_name}' using ENHANCED custom Bedrock provider with model switching: {model_config['model_id']}")
        
        # Get the system prompt with user_id context and correct agent_name
        system_prompt = get_system_prompt(user_id=user_id, agent_name=agent_name)
        
        # Initialize tools list with default tools
        tools = get_default_tools(agent_name)
        
        # Add custom tools
        custom_tools = get_custom_tools()
        if custom_tools:
            tools.extend(custom_tools)
        
        # Add memory tools if enabled
        memory_config = agent_config.get_memory_config()
        memory_enabled = memory_config.get("enabled", False)
        
        print(f"Memory enabled: {memory_enabled}")
        
        memory_provider = None
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
            
            # Get memory tools and provider
            memory_tools = get_memory_tools(agent_name)
            if memory_tools:
                tools.extend(memory_tools)
                
                # Get the memory provider for hook registration
                from memory import MemoryFactory
                memory_provider = MemoryFactory.create(agent_name)
                print(f"Memory provider created: {getattr(memory_provider, 'provider_name', 'unknown') if memory_provider else 'None'}")
        else:
            print("Memory is disabled, skipping memory tools")
        
        # Add knowledge base tools if available
        if kb_provider and hasattr(kb_provider, 'tools'):
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
        print(f"🤖 Creating Strands Agent with trace attributes: {trace_attributes}")
        agent = Agent(
            name=agent_name,
            description=agent_description,
            model=bedrock_model,
            tools=tools,
            system_prompt=system_prompt,
            trace_attributes=trace_attributes
        )
        
        # Register Bedrock AgentCore Memory hooks if enabled and provider is available
        if memory_enabled and memory_provider and hasattr(memory_provider, 'provider_name') and memory_provider.provider_name == "bedrock_agentcore":
            try:
                print("🪝 Registering Bedrock AgentCore Memory hooks with Strands Agent...")
                
                # Create memory hooks for this agent session
                memory_hooks = memory_provider.create_memory_hooks(
                    actor_id=user_id,
                    session_id=f"agent_session_{uuid.uuid4().hex[:8]}"
                )
                
                if memory_hooks and hasattr(agent, 'hook_registry'):
                    # Register hooks with the agent's hook registry
                    memory_hooks.register_hooks(agent.hook_registry)
                    print("✅ Bedrock AgentCore Memory hooks registered successfully")
                    print("   - MessageAddedEvent: retrieve_user_context (loads relevant memories before processing)")
                    print("   - AfterInvocationEvent: save_interaction (stores conversation after response)")
                elif memory_hooks:
                    print("⚠️ Memory hooks created but agent doesn't have hook_registry - manual registration needed")
                else:
                    print("⚠️ Could not create memory hooks - Strands framework may not be available")
                    
            except Exception as e:
                print(f"⚠️ Failed to register Bedrock AgentCore Memory hooks: {str(e)}")
                # Don't fail agent creation if hooks fail
        
        # CRITICAL: Enable auto-instrumentation for complete observability
        if obs_provider:
            try:
                print("🤖 Enabling auto-instrumentation for complete observability...")
                service_name, _ = obs_provider._get_service_info()
                environment = os.environ.get('ENVIRONMENT', 'production')
                obs_provider.enable_auto_instrumentation(service_name, environment)
            except Exception as e:
                print(f"⚠️ Failed to enable auto-instrumentation: {e}")
        
        print(f"✅ Strands Agent '{agent_name}' created with AUTOMATIC observability")
        print("🎯 All metrics, logs, traces will be sent automatically to configured provider!")
        return agent
        
    except Exception as e:
        print(f"Error creating agent: {str(e)}")
        traceback.print_exc()
        return None


def create_agent_with_evaluation_hooks(agent_name="qa_agent", agent_description="A QA agent that can answer questions from Knowledge Base", user_id=None, prompt="You are a knowledge assistant"):
    """
    Create an agent with built-in evaluation and observability hooks.
    
    Args:
        agent_name: Name of the agent configuration
        agent_description: Description of the agent
        user_id: User ID for memory operations
        prompt: System prompt for the agent
        
    Returns:
        Agent: Enhanced Strands Agent with evaluation capabilities
    """
    try:
        print(f"🎯 Creating agent with evaluation hooks: {agent_name}")
        
        # Create base agent using standard method
        agent = create_agent(agent_name, agent_description, user_id, prompt)
        if not agent:
            return None
        
        # Add evaluation metrics to observability
        obs_provider = ObservabilityFactory.create(agent_name)
        if obs_provider:
            print("📈 Adding evaluation metrics hooks...")
            
            # Add custom evaluation metrics
            try:
                from opentelemetry import metrics as otel_metrics
                meter_provider = otel_metrics.get_meter_provider() 
                if meter_provider:
                    eval_meter = meter_provider.get_meter("strands_evaluation", version="1.0.0")
                    
                    # Create evaluation counters
                    agent.evaluation_success_counter = eval_meter.create_counter(
                        name="strands.evaluation.success",
                        description="Successful agent evaluations", 
                        unit="1"
                    )
                    
                    agent.evaluation_failure_counter = eval_meter.create_counter(
                        name="strands.evaluation.failures",
                        description="Failed agent evaluations",
                        unit="1"
                    )
                    
                    agent.evaluation_score_histogram = eval_meter.create_histogram(
                        name="strands.evaluation.score",
                        description="Agent evaluation scores",
                        unit="1"
                    )
                    
                    print("✅ Evaluation metrics hooks added to agent")
                    
            except Exception as eval_error:
                print(f"⚠️ Failed to add evaluation metrics: {eval_error}")
        
        return agent
        
    except Exception as e:
        print(f"❌ Error creating agent with evaluation hooks: {e}")
        import traceback
        traceback.print_exc()
        return None


def execute_agent_with_observability(agent, user_input: str, agent_name: str = "qa_agent"):
    """
    Execute a Strands Agent with AUTOMATIC observability.
    ADOT + Strands[otel] handles all metrics, logs, traces automatically.
    
    Args:
        agent: The Strands Agent instance
        user_input: User input message to send to the agent
        agent_name: Agent name for identification
        
    Returns:
        AgentResult: The result from the agent execution
    """
    try:
        print(f"🚀 Executing agent '{agent_name}' with AUTOMATIC observability...")
        print("📊 ADOT will automatically capture and forward all metrics, logs, traces!")
        
        # Execute the agent - ADOT auto-instrumentation handles everything automatically
        agent_result = agent.invoke(user_input)
        
        print(f"✅ Agent executed successfully - all telemetry sent automatically!")
        return agent_result
        
    except Exception as e:
        print(f"❌ Error executing agent: {e}")
        import traceback
        traceback.print_exc()
        return None
