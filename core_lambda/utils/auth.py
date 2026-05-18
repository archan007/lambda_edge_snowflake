"""
Authorization Utility
=====================
Validates incoming Authorization headers.

Note: Actual token validation logic depends on your auth provider.
This is a placeholder structure - replace with your JWT validation,
OAuth introspection, or API Gateway authorizer logic.
"""

import logging
from typing import Any, Dict

from utils.exceptions import UnauthorizedError

logger = logging.getLogger(__name__)


def validate_authorization(event: Dict[str, Any]) -> None:
    """
    Validate the Authorization header from the incoming request.
    
    Args:
        event: API Gateway event
        
    Raises:
        UnauthorizedError: If auth header is missing or invalid
    """
    # With ALB multi-value headers enabled, headers arrive under multiValueHeaders
    # (dict of str -> list[str]). Fall back to single-value headers for direct
    # Lambda URL / API Gateway invocations.
    multi_headers = event.get("multiValueHeaders") or {}
    single_headers = event.get("headers") or {}

    # Headers can be case-insensitive depending on ALB / API Gateway config
    auth_header = (
        # Multi-value headers: take first value from list
        (multi_headers.get("Authorization") or multi_headers.get("authorization") or [None])[0]
        # Single-value headers fallback
        or single_headers.get("Authorization")
        or single_headers.get("authorization")
    )
    
    if not auth_header:
        raise UnauthorizedError("Missing authorization token")
    
    # Basic Bearer token check
    if not auth_header.startswith("Bearer "):
        raise UnauthorizedError("Invalid authorization format. Expected: Bearer <token>")
    
    token = auth_header[7:].strip()
    
    if not token:
        raise UnauthorizedError("Empty authorization token")
    
    # TODO: Replace with actual token validation
    # Examples:
    #   - Validate JWT signature and claims
    #   - Call OAuth introspection endpoint
    #   - Verify against API Gateway authorizer context
    
    logger.debug("Authorization validated successfully")