"""
Field Name Converters
=====================
Snowflake returns column names as UPPER_SNAKE_CASE.
APIs typically use camelCase.

This module handles the conversion.
"""

from typing import Any, Dict, List


def snake_to_camel(snake_str: str) -> str:
    """
    Convert SNAKE_CASE or snake_case to camelCase.
    
    Examples:
        ACCOUNT_NAME -> accountName
        annual_contract_value -> annualContractValue
    """
    parts = snake_str.lower().split("_")
    return parts[0] + "".join(word.capitalize() for word in parts[1:])


def convert_row_keys_to_camel(row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert all keys in a dictionary from snake_case to camelCase.
    
    Args:
        row: Dictionary with snake_case keys
        
    Returns:
        New dictionary with camelCase keys
    """
    return {snake_to_camel(key): value for key, value in row.items()}


def convert_rows_to_camel(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert all rows' keys from snake_case to camelCase."""
    return [convert_row_keys_to_camel(row) for row in rows]
