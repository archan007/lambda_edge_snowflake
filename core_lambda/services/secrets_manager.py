"""
AWS Secrets Manager Service
===========================
Retrieves secrets from AWS Secrets Manager with in-memory caching.

Caching strategy:
- First call: fetches from Secrets Manager (~100-200ms)
- Subsequent calls: returns from memory (~1ms)
- Cache persists across warm Lambda invocations
"""

import json
import logging
import os
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from utils.exceptions import SnowflakeError

logger = logging.getLogger(__name__)

# Module-level cache: persists across warm Lambda invocations
_secrets_cache: Dict[str, Dict[str, Any]] = {}

# Reusable boto3 client (faster than creating per-call)
_secrets_client = None


def _get_client():
    """Get or create the Secrets Manager boto3 client."""
    global _secrets_client
    if _secrets_client is None:
        region = os.environ.get("AWS_REGION", "us-east-1")
        _secrets_client = boto3.client("secretsmanager", region_name=region)
    return _secrets_client


def get_secret(secret_name: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Retrieve a secret from AWS Secrets Manager with caching.
    
    Args:
        secret_name: Name/ARN of the secret
        force_refresh: If True, bypass cache and fetch fresh secret
        
    Returns:
        Dictionary of secret key-value pairs
        
    Raises:
        SnowflakeError: If secret retrieval fails
    """
    # Return cached value if available
    if not force_refresh and secret_name in _secrets_cache:
        logger.debug(f"Cache hit for secret: {secret_name}")
        return _secrets_cache[secret_name]
    
    logger.info(f"Fetching secret from AWS Secrets Manager: {secret_name}")
    
    try:
        client = _get_client()
        response = client.get_secret_value(SecretId=secret_name)
        secret_value = json.loads(response["SecretString"])
        
        # Cache for future calls
        _secrets_cache[secret_name] = secret_value
        return secret_value
        
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "ResourceNotFoundException":
            raise SnowflakeError(f"Secret not found: {secret_name}")
        elif error_code == "AccessDeniedException":
            raise SnowflakeError(f"Access denied to secret: {secret_name}")
        else:
            raise SnowflakeError(f"Failed to retrieve secret: {str(e)}")
    except json.JSONDecodeError:
        raise SnowflakeError(f"Secret {secret_name} is not valid JSON")


def clear_cache():
    """Clear the secrets cache (useful for testing)."""
    global _secrets_cache
    _secrets_cache = {}
