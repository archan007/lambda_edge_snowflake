"""
Input Validators
================
Reusable validation functions for query parameters.

Each validator raises ValidationError with a clear message on failure.
"""

from typing import Any, List, Optional

from utils.exceptions import ValidationError


def validate_enum(
    value: Optional[str],
    field_name: str,
    allowed_values: List[str],
    required: bool = False,
) -> Optional[str]:
    """
    Validate that a value is in a list of allowed enum values.
    
    Args:
        value: The value to check (can be None if not required)
        field_name: Field name for error messages
        allowed_values: List of allowed values
        required: If True, raises error when value is None
        
    Returns:
        The validated value (or None if not provided and not required)
        
    Raises:
        ValidationError: If value is invalid
    """
    if value is None or value == "":
        if required:
            raise ValidationError(f"{field_name} is required")
        return None
    
    if value not in allowed_values:
        raise ValidationError(
            f"Invalid value for {field_name}. "
            f"Allowed values: {', '.join(allowed_values)}"
        )
    
    return value


def validate_int(
    value: Any,
    field_name: str,
    min_value: Optional[int] = None,
    max_value: Optional[int] = None,
    default: Optional[int] = None,
) -> Optional[int]:
    """
    Validate and convert a value to integer with optional bounds.
    
    Args:
        value: The value to validate (string, int, or None)
        field_name: Field name for error messages
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
        default: Default value if input is None/empty
        
    Returns:
        Validated integer value
        
    Raises:
        ValidationError: If value is invalid
    """
    if value is None or value == "":
        return default
    
    try:
        int_value = int(value)
    except (ValueError, TypeError):
        raise ValidationError(f"{field_name} must be a valid integer")
    
    if min_value is not None and int_value < min_value:
        raise ValidationError(f"{field_name} must be >= {min_value}")
    
    if max_value is not None and int_value > max_value:
        raise ValidationError(f"{field_name} must be <= {max_value}")
    
    return int_value


def validate_string(
    value: Optional[str],
    field_name: str,
    max_length: Optional[int] = None,
    required: bool = False,
) -> Optional[str]:
    """
    Validate a string value.
    
    Args:
        value: The value to validate
        field_name: Field name for error messages
        max_length: Maximum allowed length
        required: If True, raises error when value is empty
        
    Returns:
        Validated string (or None if empty and not required)
    """
    if value is None or value == "":
        if required:
            raise ValidationError(f"{field_name} is required")
        return None
    
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    
    if max_length and len(value) > max_length:
        raise ValidationError(f"{field_name} exceeds max length of {max_length}")
    
    return value
