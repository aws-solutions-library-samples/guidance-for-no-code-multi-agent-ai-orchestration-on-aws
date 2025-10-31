"""
System prompt handler for GenAI-In-A-Box agent.
This module loads system prompts from SSM parameter store.
"""

from ssm_client import ssm
from common.config import Config

# Default system prompt as fallback
DEFAULT_SYSTEM_PROMPT = """You are a helpful assistant with memory capabilities. You can:

1. Remember information about the user and their preferences
2. Retrieve relevant memories to personalize your responses
3. Store new information for future reference

When retrieving information:
1. FIRST check your memory for relevant information using mem0_memory with action="retrieve"
2. If memory doesn't have the answer, then use other tools or knowledge
3. Always store important new information about the user in memory using mem0_memory with action="store"

When displaying responses:
- Use remembered information to personalize your answers
- Don't explicitly mention the memory system to the user
- Handle memory errors gracefully
- Provide helpful responses even if memory access fails

IMPORTANT: When provided with information from memory, you MUST incorporate this information in your responses. 
Always acknowledge and use any memory information provided at the beginning of the prompt.

Always explain information clearly and provide context for your answers.
When you don't know something, admit it rather than making up information.
Always provide factual, well-reasoned responses based on reliable information."""

def get_system_prompt(streaming=False, user_id=None, agent_name="qa_agent"):
    """Get the appropriate system prompt from SSM parameter store"""
    try:
        # Create config instance with the correct agent name
        agent_config = Config(agent_name)
        
        # Get the system prompt name from config
        system_prompt_name = agent_config.get_system_prompt_name()
        
        # Get the system prompts index with force refresh
        system_prompts_index = ssm.get_json_parameter(f'/agent/{agent_name}/system-prompts/index', {}, force_refresh=True)
        
        # Get the path to the specific system prompt
        system_prompt_path = system_prompts_index.get(system_prompt_name)
        
        if system_prompt_path:
            # Get the actual system prompt with force refresh
            system_prompt = ssm.get_parameter(system_prompt_path, DEFAULT_SYSTEM_PROMPT, force_refresh=True)
            
            # Enhance the system prompt with memory instructions if not already included
            if "memory" not in system_prompt.lower():
                # Include user_id in memory instructions
                effective_user_id = user_id if user_id else "default_user"
                memory_instructions = f"""

ENHANCED MEMORY USAGE INSTRUCTIONS:
IMPORTANT: Your current user_id is "{effective_user_id}". ALWAYS use this user_id in all memory operations.

1. FIRST, ALWAYS use mem0_memory with action="retrieve" and user_id="{effective_user_id}" to check if relevant information exists in memory.
2. For different types of questions, use appropriate queries:
   - For recent conversation: "recent conversation" or "last question asked"
   - For user profile info: "user information" or "about user"
   - For specific topics: use the topic keywords directly
3. If memory has relevant info, use it in your response naturally.
4. If memory is empty, proceed with other tools or knowledge.
5. ALWAYS store important information using mem0_memory with action="store" and user_id="{effective_user_id}" after providing your response.

MEMORY QUERY EXAMPLES:
- "What did I just ask?" → mem0_memory(action="retrieve", query="recent conversation", user_id="{effective_user_id}")
- "What do you know about me?" → mem0_memory(action="retrieve", query="user information", user_id="{effective_user_id}")
- Store new info → mem0_memory(action="store", content="User's favorite color is blue", user_id="{effective_user_id}")

CRITICAL: NEVER forget to include user_id="{effective_user_id}" in ALL memory operations.
"""
                system_prompt += memory_instructions
            
            # Add streaming instructions if this is for streaming
            if streaming:
                streaming_instructions = """

STREAMING RESPONSE INSTRUCTIONS:
IMPORTANT: When you are ready to provide your final response to the user, you MUST call the ready_to_summarize() tool first.
This tool signals that you are about to provide your final answer. Only call this tool once you have:
1. Completed all necessary research and tool usage
2. Retrieved any needed information from memory or knowledge bases
3. Are ready to provide a complete, final response to the user

After calling ready_to_summarize(), provide your complete response in a clear, well-formatted manner.
"""
                system_prompt += streaming_instructions
            
            return system_prompt
        else:
            print(f"System prompt name '{system_prompt_name}' not found in index")
            return DEFAULT_SYSTEM_PROMPT
    except Exception as e:
        print(f"Error retrieving system prompt from SSM: {str(e)}")
        return DEFAULT_SYSTEM_PROMPT
