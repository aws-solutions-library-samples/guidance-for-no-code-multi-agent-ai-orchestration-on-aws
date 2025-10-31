"""
Snowflake Cortex Analyst knowledge base provider for GenAI-In-A-Box agent.
This module provides a simple knowledge base provider using Snowflake Cortex Analyst REST API.
"""

import traceback
import json
import time
import requests
import snowflake.connector
import base64
from typing import List, Dict, Any, Optional
from strands import tool
from ..base import BaseKnowledgeBaseProvider
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)

class SnowflakeKnowledgeBaseProvider(BaseKnowledgeBaseProvider):
    """Knowledge base provider for Snowflake using Cortex Analyst REST API."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the Snowflake knowledge base provider."""
        super().__init__(config)
        self.provider_name = "snowflake"
        self.snowflake_conn = None
        self.session_token = None
        self.is_initialized = False
        self.snowflake_config = {}
        self.semantic_model_path = ""
        self.tools = []
        self._private_key = None
    
    def initialize(self) -> List:
        """Initialize the Snowflake knowledge base provider and get the tools."""
        if self.is_initialized:  # nosemgrep: is-function-without-parentheses # is_initialized is a boolean attribute, not a function
            return self.tools
            
        try:
            provider_config = self.get_provider_config()
            start_time = time.time()
            
            # Extract Snowflake configuration
            self.snowflake_config = {
                "account": provider_config.get("snowflake_account"),
                "user": provider_config.get("snowflake_username"),
                "role": provider_config.get("snowflake_role", "ACCOUNTADMIN"),
                "warehouse": provider_config.get("snowflake_warehouse", "LARGE_WH"),
                "database": provider_config.get("snowflake_database", "SALES_INTELLIGENCE"),
                "schema": provider_config.get("snowflake_schema", "DATA")
            }
            
            # Validate required configuration
            if not self.snowflake_config["account"]:
                print("❌ Error: Missing 'snowflake_account' in provider config")
                return []
            if not self.snowflake_config["user"]:
                print("❌ Error: Missing 'snowflake_username' in provider config")
                return []
            
            # Set semantic model path from SSM config
            self.semantic_model_path = provider_config.get("semantic_model_path")
            
            if not self.semantic_model_path:
                print("❌ Error: Missing 'semantic_model_path' in provider config")
                return []
            
            print(f"✅ Snowflake config initialized:")
            print(f"   Account: {self.snowflake_config['account']}")
            print(f"   User: {self.snowflake_config['user']}")
            print(f"   Role: {self.snowflake_config['role']}")
            print(f"   Database: {self.snowflake_config['database']}")
            print(f"   Schema: {self.snowflake_config['schema']}")
            print(f"   Semantic Model: {self.semantic_model_path}")
            
            # Initialize connection
            self._initialize_connection()
            
            # Create tools
            self._create_tools()
            self.is_initialized = True
            
            # Log initialization time
            print(f"✅ Snowflake Cortex Analyst provider initialized in {time.time() - start_time:.2f}s with {len(self.tools)} tools")
            
            for tool_func in self.tools:
                print(f"  - {tool_func.__name__ if hasattr(tool_func, '__name__') else str(tool_func)}")
            
            return self.tools
            
        except Exception as e:
            print(f"❌ Error initializing Snowflake knowledge base provider: {str(e)}")
            traceback.print_exc()
            self.close()
            return []
    
    def _initialize_connection(self):
        """Initialize Snowflake connection."""
        start_time = time.time()
        try:
            # Get private key configuration from SSM
            provider_config = self.get_provider_config()
            
            # Load private key content from SSM parameter (secure approach)
            private_key_content = provider_config.get("snowflake_private_key_content")
            private_key_passphrase = provider_config.get("snowflake_private_key_passphrase")
            
            if not private_key_content:
                raise ValueError("Missing 'snowflake_private_key_content' in SSM parameters. Please store the Snowflake private key content in SSM.")
            
            if not private_key_passphrase:
                raise ValueError("Missing 'snowflake_private_key_passphrase' in SSM parameters")
            
            print("🔐 Loading Snowflake private key from SSM parameters")
            
            try:
                # Handle base64 encoded content if needed
                normalized_content = private_key_content.replace('\\n', '\n').replace('\\r', '\r').replace('\\t', '\t').strip()
                
                if '-----BEGIN' in normalized_content:
                    key_bytes = normalized_content.encode('utf-8')
                else:
                    key_bytes = base64.b64decode(private_key_content)
                
                self._private_key = serialization.load_pem_private_key(
                    key_bytes,
                    password=private_key_passphrase.encode(),
                    backend=default_backend()
                )
                
                print(f"✅ Snowflake private key loaded successfully")
                
            except Exception as e:
                print(f"❌ Error loading Snowflake private key from SSM: {str(e)}")
                raise
            
            self._create_connection()
            
            print(f"✅ Snowflake connection established in {time.time() - start_time:.2f}s")
            print(f"🎫 Session token extracted successfully")
            
        except Exception as e:
            print(f"❌ Error initializing Snowflake connection: {str(e)}")
            traceback.print_exc()
            raise
    
    def _create_connection(self):
        """Create or recreate Snowflake connection."""
        try:
            # Close existing connection if any
            if self.snowflake_conn:
                try:
                    self.snowflake_conn.close()
                except:
                    pass
                self.snowflake_conn = None
                self.session_token = None
            
            # Connect using JWT authentication
            self.snowflake_conn = snowflake.connector.connect(
                user=self.snowflake_config["user"],
                account=self.snowflake_config["account"],
                private_key=self._private_key,
                authenticator='snowflake_jwt',
                role=self.snowflake_config["role"],
                warehouse=self.snowflake_config["warehouse"],
                database=self.snowflake_config["database"],
                schema=self.snowflake_config["schema"]
            )
            
            # Test the connection
            cursor = self.snowflake_conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            
            # Extract session token
            self.session_token = self.snowflake_conn._rest._token
            
            print(f"🔄 Snowflake connection refreshed successfully")
            
        except Exception as e:
            print(f"❌ Error creating Snowflake connection: {str(e)}")
            raise
    
    def _ensure_connection(self):
        """Ensure we have a valid Snowflake connection, reconnect if needed."""
        try:
            if not self.snowflake_conn or not self.session_token:
                print("🔄 No connection or token, reconnecting...")
                self._create_connection()
                return
            
            # Test connection with a simple query
            cursor = self.snowflake_conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            cursor.close()
            
        except Exception as e:
            print(f"🔄 Connection test failed ({str(e)}), reconnecting...")
            self._create_connection()
    
    def _create_tools(self):
        """Create Snowflake Cortex Analyst tools using the REST API."""
        
        @tool
        def retriever_snowflake_cortex_analyst(query: str) -> str:
            """
            Ask natural language business questions using Snowflake Cortex Analyst.
            Returns AI-generated insights and can execute SQL queries on sales data.
            """
            try:
                print(f"🚀 Calling Snowflake Cortex Analyst for: {query}")
                
                # Ensure we have a valid connection before making the API call
                self._ensure_connection()
                
                # Cortex Analyst REST API endpoint
                url = f"https://{self.snowflake_config['account']}.snowflakecomputing.com/api/v2/cortex/analyst/message"
                
                # Use the working authorization format
                headers = {
                    "Authorization": f'Snowflake Token="{self.session_token}"',
                    "Content-Type": "application/json"
                }
                
                # Request payload
                payload = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": query
                                }
                            ]
                        }
                    ],
                    "semantic_model_file": self.semantic_model_path
                }
                
                print(f"📤 Making API request to Snowflake Cortex Analyst")
                
                # Make the API call
                response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
                
                print(f"📥 Response status: {response.status_code}")
                
                if response.status_code != 200:
                    error_msg = f"Cortex Analyst API error {response.status_code}: {response.text}"
                    print(f"❌ {error_msg}")
                    return error_msg
                
                response_data = response.json()
                print(f"✅ Cortex Analyst responded successfully")
                
                # Extract response content
                result_text = ""
                
                # Process the response content
                # Handle both string and dictionary response formats
                if isinstance(response_data.get("message"), dict):
                    message_content = response_data["message"].get("content", [])
                elif isinstance(response_data.get("message"), str):
                    # If message is a string, create a text content item
                    message_content = [{"type": "text", "text": response_data["message"]}]
                else:
                    message_content = []

                for item in message_content:
                    if item.get("type") == "text":
                        result_text += item.get("text", "") + "\n\n"
                    elif item.get("type") == "sql":
                        # Execute the SQL and include results
                        sql_statement = item.get("statement", "")
                        if sql_statement:
                            result_text += "📊 **Generated SQL Query:**\n"
                            result_text += f"```sql\n{sql_statement}\n```\n\n"
                            
                            # Execute the SQL
                            sql_results = self._execute_sql(sql_statement)
                            if sql_results:
                                result_text += "📈 **Query Results:**\n"
                                result_text += sql_results + "\n\n"
                
                # Add metadata if available
                metadata = response_data.get("response_metadata", {})
                if metadata:
                    model_names = metadata.get("model_names", [])
                    if model_names:
                        result_text += f"🤖 *Powered by: {', '.join(model_names)}*\n"
                
                if not result_text.strip():
                    result_text = "No response content received from Cortex Analyst."
                
                return result_text.strip()
                
            except Exception as e:
                error_msg = f"Error calling Snowflake Cortex Analyst: {str(e)}"
                print(f"❌ {error_msg}")
                traceback.print_exc()
                return error_msg
        
        print("✅ Creating Snowflake Cortex Analyst tools:")
        print(f"  1. retriever_snowflake_cortex_analyst: {retriever_snowflake_cortex_analyst}")
        
        self.tools = [retriever_snowflake_cortex_analyst]
    
    def _execute_sql(self, sql_statement: str) -> str:
        """Execute SQL statement and return formatted results."""
        start_time = time.time()
        cursor = None
        
        try:
            print(f"🔍 Executing SQL: {sql_statement[:100]}...")
            
            # Ensure we have a valid connection before executing SQL
            self._ensure_connection()
            
            if not self.snowflake_conn:
                print("❌ No Snowflake connection available")
                return "Error: No Snowflake connection available"
            
            cursor = self.snowflake_conn.cursor()
            execute_start = time.time()
            cursor.execute(sql_statement)
            execute_time = time.time() - execute_start
            
            fetch_start = time.time()
            results = cursor.fetchall()
            fetch_time = time.time() - fetch_start
            
            columns = [desc[0] for desc in cursor.description]
            
            if not results:
                if cursor:
                    cursor.close()
                return "No results returned from query."
            
            # Format results as a table
            format_start = time.time()
            result_text = ""
            
            # Add column headers
            header = " | ".join(f"{col:15}" for col in columns)
            result_text += header + "\n"
            result_text += "-" * len(header) + "\n"
            
            # Add data rows (limit to first 10 for readability)
            for i, row in enumerate(results[:10]):
                row_str = " | ".join(f"{str(val):15}" for val in row)
                result_text += row_str + "\n"
            
            if len(results) > 10:
                result_text += f"\n... and {len(results) - 10} more rows\n"
            
            result_text += f"\nTotal rows: {len(results)}"
            format_time = time.time() - format_start
            
            # Close the cursor
            if cursor:
                cursor.close()
            
            total_time = time.time() - start_time
            print(f"✅ SQL execution timing:")
            print(f"   - Total time: {total_time:.3f}s")
            print(f"   - Execute time: {execute_time:.3f}s")
            print(f"   - Fetch time: {fetch_time:.3f}s")
            print(f"   - Format time: {format_time:.3f}s")
            print(f"   - Rows returned: {len(results)}")
            
            return result_text
            
        except Exception as e:
            error_msg = f"Error executing SQL: {str(e)}"
            print(f"❌ {error_msg}")
            
            # Clean up resources
            if cursor:
                try:
                    cursor.close()
                except:
                    pass
                
            return error_msg
    
    def close(self):
        """Close Snowflake connection and clean up resources."""
        if self.is_initialized:
            try:
                if self.snowflake_conn:
                    self.snowflake_conn.close()
                    self.snowflake_conn = None
                
                self.is_initialized = False
                self.tools = []
                self.session_token = None
                print("✅ Snowflake provider resources released")
            except Exception as e:
                print(f"❌ Error closing Snowflake resources: {str(e)}")
                traceback.print_exc()
