// AWS Cloudscape Help System Content
// This file contains all help content for the comprehensive help system
// Organized by Bites (tooltips), Snacks (contextual help), and Meals (comprehensive help)

export const helpContent = {
  // BITES: Quick tooltips and info links (1-2 sentences)
  bites: {
    agent_name: "Choose a unique identifier for your AI agent that reflects its purpose.",
    agent_description: "Describe what your agent specializes in and its primary use cases.",
    system_prompt_name: "Select or create a system prompt template that defines your agent's behavior.",
    system_prompt: "The core instructions that guide how your agent responds to user queries.",
    model_id: "The primary AI model that powers your agent's reasoning and responses.",
    model_ids: "Select multiple models to enable dynamic model switching based on query complexity.",
    temperature: "Controls response creativity (0.0 = precise, 1.0 = creative).",
    top_p: "Controls response diversity by limiting word choice probability.",
    tools: "Enable additional capabilities like web browsing, file access, or custom functions.",
    knowledge_base: "Connect your agent to document collections and knowledge repositories.",
    memory: "Allow your agent to remember conversation history across sessions.",
    observability: "Monitor your agent's performance, costs, and usage patterns.",
    guardrail: "Apply content filters and safety controls to agent responses.",
    region_name: "AWS region where your agent will be deployed and run."
  },

  // SNACKS: Contextual help and descriptions (1-3 sentences with context)
  snacks: {
    agent_configuration: {
      title: "Agent Configuration",
      content: "Configure the core settings that define your AI agent's identity and behavior. These settings determine how your agent introduces itself and approaches different types of queries."
    },
    model_configuration: {
      title: "Model Configuration", 
      content: "Select and configure the AI models that power your agent. You can choose a single primary model or enable multi-model switching for different query types. Temperature and Top-P settings control response style and creativity."
    },
    system_prompts: {
      title: "System Prompt Templates",
      content: "System prompts define your agent's personality, expertise, and response style. Choose from existing templates, reuse prompts from other agents, or create custom templates tailored to your specific use case."
    },
    tools_integration: {
      title: "Tools & Capabilities",
      content: "Extend your agent with additional tools and integrations. Choose from built-in tools, MCP (Model Context Protocol) servers, or custom tool implementations to enhance your agent's capabilities."
    },
    knowledge_integration: {
      title: "Knowledge Base Integration",
      content: "Connect your agent to document collections, knowledge repositories, and data sources. This allows your agent to provide informed answers based on your organization's specific information."
    },
    advanced_features: {
      title: "Advanced Features",
      content: "Configure memory systems for conversation persistence, observability for monitoring, and guardrails for content safety. These features enhance security, performance, and user experience."
    }
  },

  // MEALS: Comprehensive help documentation (detailed guides)
  meals: {
    getting_started: {
      title: "Getting Started with Agent Creation",
      sections: [
        {
          heading: "Overview",
          content: "This wizard guides you through creating or configuring AI agents with comprehensive capabilities. Each step focuses on a specific aspect of agent configuration, from basic identity to advanced integrations."
        },
        {
          heading: "Basic Configuration",
          content: [
            "• **Agent Name**: Choose a descriptive, unique identifier",
            "• **Description**: Explain the agent's purpose and specialization", 
            "• **Region**: Select the AWS region for deployment"
          ]
        },
        {
          heading: "System Prompts",
          content: [
            "• **Templates**: Pre-built prompts for common use cases",
            "• **Cross-Agent**: Reuse successful prompts from other agents",
            "• **Custom**: Create tailored prompts for specific requirements",
            "• **Preview**: View template content before selection"
          ]
        }
      ]
    },
    model_selection: {
      title: "Model Selection & Configuration",
      sections: [
        {
          heading: "Primary Model Selection",
          content: "Choose the main AI model that will handle most of your agent's requests. Consider factors like response quality, speed, cost, and specific capabilities when selecting."
        },
        {
          heading: "Multi-Model Configuration", 
          content: [
            "• **Dynamic Switching**: Automatically route queries to optimal models",
            "• **Fallback Models**: Backup options if primary model is unavailable",
            "• **Specialized Models**: Use different models for different query types",
            "• **Cost Optimization**: Balance performance and cost across model selection"
          ]
        },
        {
          heading: "Model Parameters",
          content: [
            "• **Temperature (0.0-1.0)**: Lower values = more focused, higher = more creative",
            "• **Top-P (0.0-1.0)**: Controls diversity by limiting word choice probability",
            "• **Judge Model**: Secondary model for response evaluation and quality control",
            "• **Embedding Model**: For semantic search and knowledge retrieval"
          ]
        }
      ]
    },
    tools_and_capabilities: {
      title: "Tools & Capabilities Integration",
      sections: [
        {
          heading: "Built-in Tools",
          content: [
            "• **HTTP Request**: Make web API calls and fetch external data",
            "• **AWS Integration**: Access AWS services and resources",
            "• **File Operations**: Read, write, and process files",
            "• **MCP Client**: Connect to Model Context Protocol servers"
          ]
        },
        {
          heading: "MCP Server Integration",
          content: "Model Context Protocol (MCP) allows your agent to connect to external services and tools. Configure MCP servers in JSON format with authentication details and service endpoints."
        },
        {
          heading: "Custom Tools",
          content: "Upload and configure custom tool modules specific to your use case. Custom tools extend your agent's capabilities beyond built-in functions."
        }
      ]
    },
    knowledge_base_setup: {
      title: "Knowledge Base Configuration",
      sections: [
        {
          heading: "Knowledge Sources",
          content: [
            "• **Document Collections**: Upload PDFs, Word docs, and text files",
            "• **Web Sources**: Crawl websites and documentation sites", 
            "• **Database Integration**: Connect to structured data sources",
            "• **API Sources**: Fetch data from REST APIs and services"
          ]
        },
        {
          heading: "Retrieval Configuration",
          content: "Configure how your agent searches and retrieves relevant information from knowledge sources. This includes similarity thresholds, chunk sizes, and ranking algorithms."
        }
      ]
    },
    advanced_configuration: {
      title: "Advanced Configuration Options",
      sections: [
        {
          heading: "Memory Systems",
          content: [
            "• **Short-term Memory**: Conversation context within a session",
            "• **Long-term Memory**: Persistent memory across sessions",
            "• **Episodic Memory**: Remember specific interactions and outcomes",
            "• **Semantic Memory**: Store learned concepts and relationships"
          ]
        },
        {
          heading: "Observability & Monitoring",
          content: [
            "• **Performance Metrics**: Track response times and success rates",
            "• **Cost Monitoring**: Monitor API usage and associated costs",
            "• **Error Tracking**: Capture and analyze failure patterns",
            "• **Usage Analytics**: Understand user interaction patterns"
          ]
        },
        {
          heading: "Guardrails & Safety",
          content: [
            "• **Content Filtering**: Block inappropriate or harmful content",
            "• **Input Validation**: Verify and sanitize user inputs",
            "• **Output Monitoring**: Check agent responses for safety",
            "• **Rate Limiting**: Control usage patterns and prevent abuse"
          ]
        }
      ]
    },
    troubleshooting: {
      title: "Troubleshooting Common Issues",
      sections: [
        {
          heading: "Agent Creation Issues",
          content: [
            "• **Validation Errors**: Ensure all required fields are completed",
            "• **Name Conflicts**: Choose unique agent names within your environment",
            "• **Permission Issues**: Verify you have necessary AWS permissions",
            "• **Network Connectivity**: Check VPC and security group settings"
          ]
        },
        {
          heading: "Template Loading Problems", 
          content: [
            "• **Empty Templates**: Check API connectivity and agent permissions",
            "• **Missing Cross-Agent Prompts**: Verify other agents exist and are accessible",
            "• **Template Creation Failures**: Ensure unique names and valid content",
            "• **Content Loading Issues**: Check agent configuration and network access"
          ]
        },
        {
          heading: "Deployment Issues",
          content: [
            "• **ECS Task Failures**: Review ECS logs and resource allocation",
            "• **Load Balancer Issues**: Verify target group health and routing",
            "• **VPC Lattice Problems**: Check service mesh configuration",
            "• **CloudFormation Errors**: Review CDK deployment logs and permissions"
          ]
        }
      ]
    },
    best_practices: {
      title: "Best Practices for Agent Configuration",
      sections: [
        {
          heading: "System Prompt Design",
          content: [
            "• **Clear Identity**: Define who the agent is and its expertise areas",
            "• **Specific Instructions**: Provide concrete guidance on response style",
            "• **Boundary Setting**: Clearly state what the agent can and cannot do",
            "• **Example Interactions**: Include sample conversations when helpful"
          ]
        },
        {
          heading: "Model Selection Strategy",
          content: [
            "• **Use Case Matching**: Choose models that excel at your specific tasks",
            "• **Cost Optimization**: Balance model capability with operational costs",
            "• **Performance Requirements**: Consider latency vs. quality trade-offs",
            "• **Fallback Planning**: Always configure backup model options"
          ]
        },
        {
          heading: "Security Considerations",
          content: [
            "• **Principle of Least Privilege**: Only enable necessary tools and capabilities",
            "• **Content Filtering**: Always enable appropriate guardrails",
            "• **Data Protection**: Ensure sensitive data handling compliance",
            "• **Access Control**: Implement proper authentication and authorization"
          ]
        }
      ]
    }
  }
};

// Helper functions for accessing help content
export const getHelpBite = (key) => helpContent.bites[key] || "";
export const getHelpSnack = (key) => helpContent.snacks[key] || null;
export const getHelpMeal = (key) => helpContent.meals[key] || null;

// Help content modification guide
export const helpModificationGuide = {
  overview: "The help system uses a three-tier approach following AWS Cloudscape patterns",
  tiers: {
    bites: {
      description: "Quick tooltips and info text (1-2 sentences)",
      usage: "Used in FormField info links and tooltips",
      modification: "Edit helpContent.bites[field_name] to update tooltip text"
    },
    snacks: {
      description: "Contextual help sections (1-3 sentences with context)",
      usage: "Used in Alert components and expandable help sections",
      modification: "Edit helpContent.snacks[section_name] to update contextual help"
    },
    meals: {
      description: "Comprehensive documentation with sections and examples",
      usage: "Used in dedicated help panels and modals",
      modification: "Edit helpContent.meals[topic_name] to update comprehensive help"
    }
  },
  howToModify: [
    "1. Open application_src/ui-react-cloudscape/src/components/HelpContent.js",
    "2. Find the appropriate tier (bites, snacks, or meals)",
    "3. Locate the content key you want to modify",
    "4. Update the content following the established pattern",
    "5. Save the file - changes will be reflected immediately"
  ]
};
