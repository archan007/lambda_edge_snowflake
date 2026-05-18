"""
Snowflake Client Service
========================
Manages Snowflake connections with reuse across warm Lambda invocations.

Key design decisions:
- Connection is database-scoped, NOT schema-scoped
- Each procedure call is fully qualified: SCHEMA.procedure_name(...)
- This allows ONE Lambda to query multiple data products (schemas)
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import snowflake.connector
from snowflake.connector import DictCursor

from services.secrets_manager import get_secret
from utils.exceptions import SnowflakeError
from utils.crypto import load_private_key

logger = logging.getLogger(__name__)


class SnowflakeClient:
    """
    Singleton Snowflake client supporting multi-schema queries.
    
    Connection is established once per Lambda container and reused
    across warm invocations and across data products (schemas).
    """
    
    _instance: Optional["SnowflakeClient"] = None
    _connection: Optional[snowflake.connector.SnowflakeConnection] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def _is_connection_alive(self) -> bool:
        """Check if existing connection is still valid."""
        if self._connection is None:
            return False
        try:
            self._connection.cursor().execute("SELECT 1").fetchone()
            return True
        except Exception:
            logger.info("Existing Snowflake connection is stale")
            return False
    
    def _create_connection(self) -> snowflake.connector.SnowflakeConnection:
        """
        Create a new Snowflake connection.
        
        Note: We do NOT specify a default schema here because this Lambda
        queries multiple schemas (data products). Each query uses
        fully-qualified names: SCHEMA.procedure_name(...)
        """
        environment = os.environ.get("ENVIRONMENT", "DEV")
        secret_name = os.environ.get(
            "SNOWFLAKE_SECRET_NAME",
            f"snowflake/{environment.lower()}/credentials"
        )
        
        logger.info(f"Establishing new Snowflake connection for {environment}")
        
        try:
            secrets = get_secret(secret_name)
            
            private_key_bytes = load_private_key(
                secrets["private_key"],
                secrets.get("private_key_passphrase")
            )
            
            # Note: NO 'schema' parameter - we use fully-qualified names per call
            connection = snowflake.connector.connect(
                account=secrets["account"],
                user=secrets["user"],
                private_key=private_key_bytes,
                database=secrets["database"],
                warehouse=secrets["warehouse"],
                role=secrets.get("role"),
                client_session_keep_alive=True,
                client_session_keep_alive_heartbeat_frequency=900,
            )
            
            logger.info(f"Connected to Snowflake database: {secrets['database']}")
            return connection
            
        except KeyError as e:
            raise SnowflakeError(f"Missing required secret field: {str(e)}")
        except Exception as e:
            raise SnowflakeError(f"Failed to connect to Snowflake: {str(e)}")
    
    def get_connection(self) -> snowflake.connector.SnowflakeConnection:
        """Get an active Snowflake connection (reuse or create)."""
        if not self._is_connection_alive():
            self._connection = self._create_connection()
        return self._connection
    
    def call_procedure(
        self,
        schema: str,
        procedure_name: str,
        params: Tuple = (),
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Call a Snowflake stored procedure with fully-qualified naming.
        
        Args:
            schema: Schema/data product name (e.g., 'GOLD_C360', 'GOLD_CI')
            procedure_name: Procedure name (e.g., 'sp_account_summary')
            params: Tuple of parameters in the order expected by the SP
            
        Returns:
            Tuple of (rows as list of dicts, column names)
            
        Example:
            rows, cols = snowflake_client.call_procedure(
                schema="GOLD_C360",
                procedure_name="sp_account_summary",
                params=(1, 25, None, ...)
            )
        """
        connection = self.get_connection()
        
        placeholders = ", ".join(["?" for _ in params]) if params else ""
        qualified_name = f"{schema}.{procedure_name}"
        call_statement = f"CALL {qualified_name}({placeholders})"
        
        logger.info(f"Executing: {qualified_name} with {len(params)} parameters")
        
        cursor = None
        try:
            cursor = connection.cursor(DictCursor)
            cursor.execute(call_statement, params)
            
            rows = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]
            
            logger.info(f"{qualified_name} returned {len(rows)} rows")
            return rows, column_names
            
        except snowflake.connector.errors.ProgrammingError as e:
            logger.error(f"SP error in {qualified_name}: {str(e)}")
            raise SnowflakeError(f"Stored procedure error: {str(e)}")
        except Exception as e:
            logger.error(f"DB error in {qualified_name}: {str(e)}")
            raise SnowflakeError(f"Database error: {str(e)}")
        finally:
            if cursor:
                cursor.close()
    
    def execute_query(
        self,
        schema: str,
        query: str,
        params: Optional[Tuple] = None,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Execute a raw SQL query against a specific schema.
        
        Used for POST/PUT operations where direct SQL is needed
        (e.g., INSERT/UPDATE statements that don't warrant a stored procedure).
        
        Args:
            schema: Schema/data product name
            query: SQL query (use {schema} placeholder for injection)
            params: Optional parameters for parameterized queries
            
        Example:
            rows, cols = snowflake_client.execute_query(
                schema="GOLD_C360",
                query="UPDATE {schema}.accounts SET status=? WHERE id=?",
                params=("active", 123)
            )
        """
        connection = self.get_connection()
        formatted_query = query.format(schema=schema)
        
        logger.info(f"Executing query on schema {schema}")
        
        cursor = None
        try:
            cursor = connection.cursor(DictCursor)
            
            if params:
                cursor.execute(formatted_query, params)
            else:
                cursor.execute(formatted_query)
            
            try:
                rows = cursor.fetchall()
                column_names = [desc[0] for desc in cursor.description] if cursor.description else []
            except Exception:
                rows = []
                column_names = []
            
            return rows, column_names
            
        except snowflake.connector.errors.ProgrammingError as e:
            logger.error(f"Query error: {str(e)}")
            raise SnowflakeError(f"Query error: {str(e)}")
        finally:
            if cursor:
                cursor.close()
    
    def close(self):
        """Close the connection (rarely needed)."""
        if self._connection:
            try:
                self._connection.close()
                logger.info("Snowflake connection closed")
            except Exception as e:
                logger.warning(f"Error closing connection: {str(e)}")
            finally:
                self._connection = None


# Module-level singleton (created once per Lambda container)
snowflake_client = SnowflakeClient()
