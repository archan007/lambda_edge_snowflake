"""
Response Builder
================
Creates properly formatted responses compatible with:
- ALB (Application Load Balancer) with multi-value headers enabled
- API Gateway
- Lambda Function URL

ALB is the strictest — requires statusCode, body as string,
isBase64Encoded, and multiValueHeaders when multi-value mode is on.
"""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional


class APIEncoder(json.JSONEncoder):
    """
    Custom JSON encoder that handles Snowflake-specific types.

    Snowflake returns:
    - NUMBER columns as Decimal
    - DATE/TIMESTAMP as datetime objects
    """
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, bytes):
            return obj.decode("utf-8")
        return super().default(obj)


# Allowed CORS origins — both your CloudFront distribution domain
# and your custom DNS domain.
# TODO: replace these with your actual domains before deploying
ALLOWED_ORIGINS = [
    "https://your-distribution.cloudfront.net",
    "https://your-custom-domain.com",
]

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}

# Maps status codes to descriptions for ALB
STATUS_DESCRIPTIONS = {
    200: "200 OK",
    201: "201 Created",
    400: "400 Bad Request",
    401: "401 Unauthorized",
    402: "402 Payment Required",
    403: "403 Forbidden",
    404: "404 Not Found",
    500: "500 Internal Server Error",
}


def get_cors_origin(event: Dict[str, Any]) -> str:
    """
    Reflect the request Origin back if it is in ALLOWED_ORIGINS.

    Access-Control-Allow-Origin only accepts a single value, so we
    dynamically match the incoming Origin against the allowed list
    instead of hardcoding '*' or one domain.

    Falls back to the first allowed origin for non-browser callers
    (e.g. Postman) that don't send an Origin header.
    """
    multi_headers = event.get("multiValueHeaders") or {}
    single_headers = event.get("headers") or {}

    request_origin = (
        (multi_headers.get("Origin") or multi_headers.get("origin") or [None])[0]
        or single_headers.get("Origin")
        or single_headers.get("origin")
    )

    if request_origin and request_origin in ALLOWED_ORIGINS:
        return request_origin

    return ALLOWED_ORIGINS[0]


def create_response(
    status_code: int,
    body: Any,
    event: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Build a response compatible with ALB (multi-value headers enabled),
    API Gateway and Lambda Function URL.

    Both 'headers' and 'multiValueHeaders' are returned:
    - ALB (multi-value headers ON) reads multiValueHeaders
    - Lambda Function URL / API Gateway reads headers
    Neither complains about the presence of the other.

    Args:
        status_code: HTTP status code
        body: Response body (will be JSON-serialized to string)
        event: Original Lambda event — used to reflect correct CORS origin
        headers: Optional extra headers to merge with defaults

    Returns:
        Response dictionary
    """
    cors_origin = get_cors_origin(event) if event else ALLOWED_ORIGINS[0]

    response_headers = {
        **DEFAULT_HEADERS,
        "Access-Control-Allow-Origin": cors_origin,
        **(headers or {}),
    }

    return {
        "statusCode": status_code,
        "statusDescription": STATUS_DESCRIPTIONS.get(status_code, str(status_code)),
        "headers": response_headers,                                          # Lambda Function URL + API Gateway
        "multiValueHeaders": {k: [v] for k, v in response_headers.items()}, # ALB multi-value headers
        "body": json.dumps(body, cls=APIEncoder),
        "isBase64Encoded": False,
    }