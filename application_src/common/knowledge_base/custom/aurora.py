"""
Aurora PostgreSQL knowledge base provider for GenAI-In-A-Box agent.
This module provides a knowledge base provider using Aurora PostgreSQL with Data API and LLM-powered SQL generation.
"""

import traceback
import json
import time
import boto3
from typing import List, Dict, Any, Optional
from strands import tool
from ..base import BaseKnowledgeBaseProvider
import logging
from ...secure_logging_utils import SecureLogger


logger = logging.getLogger(__name__)

class AuroraKnowledgeBaseProvider(BaseKnowledgeBaseProvider):
    """Knowledge base provider for Aurora PostgreSQL using Data API with schema-aware SQL generation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Aurora knowledge base provider."""
        super().__init__(config)
        self.provider_name = "aurora"
        self.rds_data_client = None
        self.bedrock_client = None
        self.is_initialized = False
        self.aurora_config = {}
        self.schema_cache = None
        self.schema_cache_time = None
        self.cache_duration = 300  # 5 minutes cache
        
    def initialize(self) -> List:
        """Initialize the Aurora knowledge base provider and get the tools."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses # is_initialized is a boolean attribute, not a function
            return self.tools
            
        try:
            provider_config = self.get_provider_config()
            start_time = time.time()
            
            # Extract Aurora configuration from SSM (keys match YAML configuration)
            self.aurora_config = {
                "cluster_arn": provider_config.get("aurora_cluster_arn"),
                "secret_arn": provider_config.get("aurora_secret_arn"), 
                "database_name": provider_config.get("aurora_database_name", "db_finserve_intel"),
                "region": provider_config.get("aurora_region", "us-east-1")
            }
            
            # Get main model ID from config instead of separate aurora model
            from config import Config
            config_instance = Config(self.config.get("agent_name", "qa_agent"))
            model_config = config_instance.get_model_config()
            self.aurora_config["model_id"] = model_config.get("model_id", "anthropic.claude-3-sonnet-20240229-v1:0")
            
            # Validate required configuration
            if not self.aurora_config["cluster_arn"]:
                print("❌ Error: Missing 'cluster_arn' in Aurora provider config")
                return []
            if not self.aurora_config["secret_arn"]:
                print("❌ Error: Missing 'secret_arn' in Aurora provider config")
                return []
            
            print(f"✅ Aurora config initialized:")
            print(f"   Cluster ARN: {'✅ Configured' if self.aurora_config['cluster_arn'] else '❌ Missing'}")
            print(f"   Secret ARN: {'✅ Configured' if self.aurora_config['secret_arn'] else '❌ Missing'}")
            # Use secure logging to prevent clear text exposure of sensitive configuration
            secure_logger = SecureLogger()
            print(f"   Database: {secure_logger.hash_sensitive_value(self.aurora_config['database_name'])}")
            print(f"   Region: {secure_logger.hash_sensitive_value(self.aurora_config['region'])}")
            print(f"   Model ID: {secure_logger.hash_sensitive_value(self.aurora_config['model_id'])}")
            
            # Initialize AWS clients
            self._initialize_clients()
            
            # Test connection by getting schema
            print("🔍 Testing Aurora connection and caching schema...")
            schema_info = self._get_database_schema()
            if schema_info:
                print(f"✅ Successfully connected to Aurora and cached schema ({len(schema_info.split('Table:'))-1} tables)")
            else:
                print("❌ Failed to connect to Aurora or retrieve schema")
                return []
            
            # Create tools
            self._create_tools()
            self.is_initialized = True
            
            # Log initialization time
            print(f"✅ Aurora PostgreSQL provider initialized in {time.time() - start_time:.2f}s with {len(self.tools)} tools")
            
            for tool_func in self.tools:
                print(f"  - {tool_func.__name__ if hasattr(tool_func, '__name__') else str(tool_func)}")
            
            return self.tools
            
        except Exception as e:
            print(f"❌ Error initializing Aurora knowledge base provider: {str(e)}")
            traceback.print_exc()
            self.close()
            return []
    
    def _initialize_clients(self):
        """Initialize AWS clients for RDS Data API and Bedrock."""
        try:
            # Initialize RDS Data API client
            self.rds_data_client = boto3.client(
                'rds-data', 
                region_name=self.aurora_config["region"]
            )
            
            # Initialize Bedrock client for LLM
            self.bedrock_client = boto3.client(
                'bedrock-runtime',
                region_name=self.aurora_config["region"]
            )
            
            print("✅ AWS clients initialized successfully")
            
        except Exception as e:
            print(f"❌ Error initializing AWS clients: {str(e)}")
            raise
    
    def _execute_sql(self, sql_statement: str, include_result_metadata: bool = True) -> Dict:
        """Execute SQL statement using RDS Data API and return response."""
        try:
            print(f"🔍 Executing SQL: {sql_statement[:100]}...")
            
            response = self.rds_data_client.execute_statement(
                resourceArn=self.aurora_config["cluster_arn"],
                secretArn=self.aurora_config["secret_arn"],
                database=self.aurora_config["database_name"],
                sql=sql_statement,
                includeResultMetadata=include_result_metadata
            )
            
            print("✅ SQL executed successfully")
            return response
            
        except Exception as e:
            print(f"❌ Error executing SQL: {str(e)}")
            raise
    
    def _get_database_schema(self, force_refresh: bool = False) -> str:
        """Get comprehensive database schema information with caching."""
        try:
            # Check cache first
            current_time = time.time()
            if (not force_refresh and 
                self.schema_cache and 
                self.schema_cache_time and 
                (current_time - self.schema_cache_time) < self.cache_duration):
                print("📋 Using cached schema information")
                return self.schema_cache
            
            print("🔍 Retrieving fresh database schema information...")
            
            # Get all schemas, tables, and columns with constraints and indexes
            schema_query = """
            WITH table_info AS (
                SELECT 
                    t.table_schema,
                    t.table_name,
                    t.table_type,
                    obj_description(c.oid) as table_comment
                FROM information_schema.tables t
                LEFT JOIN pg_class c ON c.relname = t.table_name
                WHERE t.table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ORDER BY t.table_schema, t.table_name
            ),
            column_info AS (
                SELECT 
                    c.table_schema,
                    c.table_name,
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    c.ordinal_position,
                    col_description(pgc.oid, c.ordinal_position) as column_comment
                FROM information_schema.columns c
                LEFT JOIN pg_class pgc ON pgc.relname = c.table_name
                WHERE c.table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
                ORDER BY c.table_schema, c.table_name, c.ordinal_position
            ),
            constraint_info AS (
                SELECT 
                    tc.table_schema,
                    tc.table_name,
                    tc.constraint_name,
                    tc.constraint_type,
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints tc
                LEFT JOIN information_schema.key_column_usage kcu 
                    ON tc.constraint_name = kcu.constraint_name
                LEFT JOIN information_schema.constraint_column_usage ccu 
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.table_schema NOT IN ('information_schema', 'pg_catalog', 'pg_toast')
            )
            SELECT 
                'SCHEMA' as info_type,
                ti.table_schema,
                ti.table_name,
                ti.table_type,
                ti.table_comment,
                NULL as column_name,
                NULL as data_type,
                NULL as is_nullable,
                NULL as column_default,
                NULL as column_comment,
                NULL as constraint_type,
                NULL as foreign_table_name,
                NULL as foreign_column_name,
                NULL as ordinal_position
            FROM table_info ti
            UNION ALL
            SELECT 
                'COLUMN' as info_type,
                ci.table_schema,
                ci.table_name,
                NULL as table_type,
                NULL as table_comment,
                ci.column_name,
                ci.data_type,
                ci.is_nullable,
                ci.column_default,
                ci.column_comment,
                NULL as constraint_type,
                NULL as foreign_table_name,
                NULL as foreign_column_name,
                ci.ordinal_position
            FROM column_info ci
            UNION ALL
            SELECT 
                'CONSTRAINT' as info_type,
                co.table_schema,
                co.table_name,
                NULL as table_type,
                NULL as table_comment,
                co.column_name,
                NULL as data_type,
                NULL as is_nullable,
                NULL as column_default,
                NULL as column_comment,
                co.constraint_type,
                co.foreign_table_name,
                co.foreign_column_name,
                NULL as ordinal_position
            FROM constraint_info co
            ORDER BY table_schema, table_name, info_type, ordinal_position, column_name;
            """
            
            response = self._execute_sql(schema_query)
            
            if not response.get('records'):
                return "No schema information available."
            
            # Format schema information
            schema_text = "=== DATABASE SCHEMA INFORMATION ===\n\n"
            current_schema = None
            current_table = None
            
            for record in response['records']:
                info_type = self._extract_value(record[0])
                table_schema = self._extract_value(record[1])
                table_name = self._extract_value(record[2])
                
                # New schema section
                if current_schema != table_schema:
                    current_schema = table_schema
                    schema_text += f"📁 SCHEMA: {table_schema}\n"
                    schema_text += "=" * 50 + "\n\n"
                
                # New table section  
                if current_table != f"{table_schema}.{table_name}":
                    current_table = f"{table_schema}.{table_name}"
                    
                    if info_type == 'SCHEMA':
                        table_type = self._extract_value(record[3])
                        table_comment = self._extract_value(record[4])
                        
                        schema_text += f"📋 TABLE: {table_name} ({table_type})\n"
                        if table_comment:
                            schema_text += f"   Comment: {table_comment}\n"
                        schema_text += "   Columns:\n"
                
                # Column information
                elif info_type == 'COLUMN':
                    column_name = self._extract_value(record[5])
                    data_type = self._extract_value(record[6])
                    is_nullable = self._extract_value(record[7])
                    column_default = self._extract_value(record[8])
                    column_comment = self._extract_value(record[9])
                    
                    nullable_text = "NULL" if is_nullable == "YES" else "NOT NULL"
                    default_text = f", DEFAULT: {column_default}" if column_default else ""
                    comment_text = f" -- {column_comment}" if column_comment else ""
                    
                    schema_text += f"     • {column_name}: {data_type} {nullable_text}{default_text}{comment_text}\n"
                
                # Constraint information
                elif info_type == 'CONSTRAINT':
                    column_name = self._extract_value(record[5])
                    constraint_type = self._extract_value(record[10])
                    foreign_table = self._extract_value(record[11])
                    foreign_column = self._extract_value(record[12])
                    
                    if constraint_type == 'PRIMARY KEY':
                        schema_text += f"     🗝️  PRIMARY KEY: {column_name}\n"
                    elif constraint_type == 'FOREIGN KEY':
                        schema_text += f"     🔗 FOREIGN KEY: {column_name} → {foreign_table}.{foreign_column}\n"
                    elif constraint_type == 'UNIQUE':
                        schema_text += f"     ⭐ UNIQUE: {column_name}\n"
            
            # Add sample data query suggestions
            schema_text += "\n=== QUERY SUGGESTIONS ===\n"
            schema_text += "• Use fully qualified table names: schema_name.table_name\n"
            schema_text += "• Always include LIMIT clause for SELECT statements\n"
            schema_text += "• Use proper JOIN syntax for related tables\n"
            schema_text += "• Consider using aggregate functions for summaries\n\n"
            
            # Cache the result
            self.schema_cache = schema_text
            self.schema_cache_time = current_time
            
            print(f"✅ Schema information retrieved and cached ({len(schema_text)} characters)")
            return schema_text
            
        except Exception as e:
            print(f"❌ Error retrieving database schema: {str(e)}")
            return f"Error retrieving schema: {str(e)}"
    
    def _extract_value(self, field) -> str:
        """Extract value from Data API field format."""
        if isinstance(field, dict):
            if 'stringValue' in field:
                return field['stringValue']
            elif 'longValue' in field:
                return str(field['longValue'])
            elif 'isNull' in field and field['isNull']:
                return 'NULL'
            else:
                return str(field)
        return str(field) if field is not None else 'NULL'
    
    def _generate_sql_with_llm(self, natural_query: str, schema_info: str) -> str:
        """Use LLM to generate SQL query from natural language."""
        try:
            print(f"🤖 Generating SQL with LLM for: {natural_query}")
            
            prompt = f"""You are an expert PostgreSQL SQL developer. Generate a safe, efficient SQL query based on the user's natural language request.

DATABASE SCHEMA:
{schema_info}

USER REQUEST: {natural_query}

IMPORTANT RULES:
1. Only generate SELECT statements - no INSERT, UPDATE, DELETE, DROP, ALTER, or CREATE statements
2. Always include a LIMIT clause (default LIMIT 20 unless user specifies otherwise)
3. Use proper PostgreSQL syntax and functions
4. Use fully qualified table names (schema.table)
5. Add appropriate WHERE clauses for filtering
6. Use proper JOIN syntax when combining tables
7. Handle date/time comparisons appropriately
8. Use aggregate functions (COUNT, SUM, AVG, etc.) when appropriate
9. Return only the SQL query without any explanation or markdown formatting
10. Ensure the query is syntactically correct and runnable

Generate the SQL query:"""

            response = self.bedrock_client.invoke_model(
                modelId=self.aurora_config["model_id"],
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.1
                })
            )
            
            response_body = json.loads(response['body'].read())
            sql_query = response_body['content'][0]['text'].strip()
            
            # Clean up the SQL query (remove any markdown formatting)
            sql_query = sql_query.replace('```sql', '').replace('```', '').strip()
            
            print(f"✅ Generated SQL: {sql_query}")
            return sql_query
            
        except Exception as e:
            print(f"❌ Error generating SQL with LLM: {str(e)}")
            raise
    
    def _format_query_results(self, response: Dict) -> str:
        """Format SQL query results into readable text."""
        try:
            if not response.get('records'):
                return "No results returned from query."
            
            records = response['records']
            columns = []
            
            # Extract column names from metadata
            if response.get('columnMetadata'):
                columns = [col['name'] for col in response['columnMetadata']]
            else:
                # Fallback: use generic column names
                columns = [f"column_{i+1}" for i in range(len(records[0]) if records else 0)]
            
            if not records:
                return "No results returned from query."
            
            # Format as table
            result_text = ""
            
            # Add column headers
            header = " | ".join(f"{col:20}" for col in columns)
            result_text += header + "\n"
            result_text += "-" * len(header) + "\n"
            
            # Add data rows (limit to first 50 for readability)
            for i, record in enumerate(records[:50]):
                row_values = [self._extract_value(field) for field in record]
                row_str = " | ".join(f"{str(val):20}" for val in row_values)
                result_text += row_str + "\n"
            
            if len(records) > 50:
                result_text += f"\n... and {len(records) - 50} more rows\n"
            
            result_text += f"\nTotal rows: {len(records)}"
            
            return result_text
            
        except Exception as e:
            return f"Error formatting results: {str(e)}"
    
    def _summarize_results_with_llm(self, query: str, sql_query: str, results: str) -> str:
        """Use LLM to create a summary of the query results."""
        try:
            print("🤖 Creating summary with LLM...")
            
            prompt = f"""You are a data analyst. Provide a clear, concise summary of the SQL query results.

ORIGINAL USER QUESTION: {query}

SQL QUERY EXECUTED:
{sql_query}

QUERY RESULTS:
{results}

Please provide:
1. A brief summary of what the data shows
2. Key insights or patterns (if any)
3. Notable numbers or trends
4. Direct answer to the user's original question

Keep the summary concise but informative. Focus on business insights rather than technical details."""

            response = self.bedrock_client.invoke_model(
                modelId=self.aurora_config["model_id"],
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "messages": [
                        {
                            "role": "user", 
                            "content": prompt
                        }
                    ],
                    "max_tokens": 800,
                    "temperature": 0.3
                })
            )
            
            response_body = json.loads(response['body'].read())
            summary = response_body['content'][0]['text'].strip()
            
            print("✅ Summary generated successfully")
            return summary
            
        except Exception as e:
            error_msg = f"Error generating summary: {str(e)}"
            print(f"❌ {error_msg}")
            return error_msg
    
    def _create_tools(self):
        """Create Aurora PostgreSQL query tools."""
        
        @tool
        def retriever_aurora_sql_query(query: str) -> str:
            """
            Execute natural language queries against Aurora PostgreSQL database using AI-generated SQL.
            This tool can answer questions about data by generating and executing appropriate SQL queries.
            """
            try:
                print(f"🚀 Processing Aurora query: {query}")
                start_time = time.time()
                
                # Get database schema
                schema_info = self._get_database_schema()
                if not schema_info:
                    return "Error: Could not retrieve database schema information."
                
                # Generate SQL using LLM
                sql_query = self._generate_sql_with_llm(query, schema_info)
                if not sql_query:
                    return "Error: Could not generate SQL query from natural language."
                
                # Execute the SQL query
                try:
                    response = self._execute_sql(sql_query)
                except Exception as e:
                    return f"Error executing generated SQL query: {str(e)}\n\nGenerated SQL was:\n{sql_query}"
                
                # Format results
                formatted_results = self._format_query_results(response)
                
                # Generate summary with LLM
                summary = self._summarize_results_with_llm(query, sql_query, formatted_results)
                
                # Compile final response
                final_response = f"""🔍 **Query Analysis Complete**

**Original Question:** {query}

**Generated SQL:**
```sql
{sql_query}
```

**Summary:**
{summary}

**Raw Results:**
{formatted_results}

*Query completed in {time.time() - start_time:.2f} seconds*"""
                
                return final_response
                
            except Exception as e:
                error_msg = f"Error processing Aurora query: {str(e)}"
                print(f"❌ {error_msg}")
                traceback.print_exc()
                return error_msg
        
        @tool  
        def retriever_aurora_schema_info(schema_name: str = "") -> str:
            """
            Get database schema information for Aurora PostgreSQL.
            Optionally filter by schema name. Useful for understanding database structure.
            """
            try:
                print(f"🔍 Retrieving schema information for: {schema_name or 'all schemas'}")
                
                schema_info = self._get_database_schema(force_refresh=True)
                
                if schema_name:
                    # Filter schema info for specific schema
                    lines = schema_info.split('\n')
                    filtered_lines = []
                    include_section = False
                    
                    for line in lines:
                        if line.startswith(f"📁 SCHEMA: {schema_name}"):
                            include_section = True
                        elif line.startswith("📁 SCHEMA: ") and not line.startswith(f"📁 SCHEMA: {schema_name}"):
                            include_section = False
                        
                        if include_section or line.startswith("==="):
                            filtered_lines.append(line)
                    
                    if filtered_lines:
                        return '\n'.join(filtered_lines)
                    else:
                        return f"Schema '{schema_name}' not found. Available schemas can be seen in the full schema listing."
                
                return schema_info
                
            except Exception as e:
                error_msg = f"Error retrieving schema information: {str(e)}"
                print(f"❌ {error_msg}")
                return error_msg
        
        print("✅ Creating Aurora PostgreSQL tools:")
        print(f"  1. retriever_aurora_sql_query: {retriever_aurora_sql_query}")
        print(f"  2. retriever_aurora_schema_info: {retriever_aurora_schema_info}")
        
        self.tools = [retriever_aurora_sql_query, retriever_aurora_schema_info]
    
    def close(self):
        """Close Aurora connections and clean up resources."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses # is_initialized is a boolean attribute, not a function
            try:
                self.is_initialized = False
                self.tools = []
                self.rds_data_client = None
                self.bedrock_client = None
                self.schema_cache = None
                self.schema_cache_time = None
                print("✅ Aurora provider resources released")
            except Exception as e:
                print(f"❌ Error closing Aurora resources: {str(e)}")
                traceback.print_exc()
