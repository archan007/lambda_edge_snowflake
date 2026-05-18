"""
Custom Exceptions
=================
Domain-specific exceptions that map to HTTP status codes.

Why custom exceptions?
- Decouples handlers from HTTP concerns (handlers raise meaningful errors)
- Centralized error-to-status-code mapping in lambda_function.py
- Easier to test (assert specific exception types)
"""


class APIError(Exception):
    """Base class for all API errors."""
    pass


class UnauthorizedError(APIError):
    """Raised when authentication fails. Maps to HTTP 401."""
    pass


class ValidationError(APIError):
    """Raised when input validation fails. Maps to HTTP 402."""
    pass


class NotFoundError(APIError):
    """Raised when a resource or route is not found. Maps to HTTP 404."""
    pass


class SnowflakeError(APIError):
    """Raised when Snowflake operations fail. Maps to HTTP 500."""
    pass
