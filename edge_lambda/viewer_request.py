"""
Lambda@Edge — Viewer Request (auth gate)
========================================
Runs on the CloudFront `viewer-request` event for the /api/* behavior.

Responsibilities:
  1. Short-circuit OPTIONS preflight with a 200 + CORS headers (never hits origin)
  2. Validate the Authorization header — Bearer token must be a real RS256 JWT
     issued by the configured Azure Entra ID tenant (signature, aud, iss,
     exp/nbf). See azure_jwt.py.
  3. On auth failure, return 401 directly — request never reaches origin-request
     or the core Lambda
  4. On success, return the request object unchanged so CloudFront continues
     to the origin-request stage

Why viewer-request and not origin-request:
  - Rejects unauthenticated requests at the EARLIEST point in the CloudFront
    pipeline, before cache lookup or any further processing.
  - Both 401 responses and OPTIONS preflight responses are tiny (well under
    the 40 KB viewer-response limit), so the size cap doesn't bite here.

Limits to remember:
  - Memory: 128 MB (fixed for viewer events)
  - Timeout: 5 seconds
  - No environment variables (use config.py)
  - No VPC access
  - Response body up to 40 KB (only matters for 401 / preflight, both small)
  - Must be deployed to us-east-1 and associated as a numbered version
  - Deployment package capped at 1 MB (AWS hard limit for viewer-request/
    viewer-response, vs 50 MB for origin-request/response) — this is why
    azure_jwt.py is stdlib-only rather than pulling in PyJWT/cryptography
  - First request per warm container pays one JWKS fetch (~cached 24h after)

Logs land in the CloudWatch region nearest the viewer, NOT us-east-1.
Look in regional log groups named /aws/lambda/us-east-1.<function-name>
"""

import json
import logging

from azure_jwt import verify_azure_jwt
from cf_events import (
    get_cf_request,
    get_header,
    get_origin,
)
from config import (
    ALLOWED_ORIGINS,
    AZURE_CLIENT_ID,
    AZURE_TENANT_ID,
    CORS_ALLOW_HEADERS,
    CORS_ALLOW_METHODS,
    DEFAULT_ORIGIN,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def _resolve_cors_origin(request_origin):
    """Reflect request Origin if allow-listed, else fall back to DEFAULT_ORIGIN."""
    if request_origin and request_origin in ALLOWED_ORIGINS:
        return request_origin
    return DEFAULT_ORIGIN


def _cors_headers(request_origin):
    """Build the CORS header set in CloudFront's expected shape."""
    cors_origin = _resolve_cors_origin(request_origin)
    return {
        "access-control-allow-origin":  [{"key": "Access-Control-Allow-Origin",  "value": cors_origin}],
        "access-control-allow-headers": [{"key": "Access-Control-Allow-Headers", "value": CORS_ALLOW_HEADERS}],
        "access-control-allow-methods": [{"key": "Access-Control-Allow-Methods", "value": CORS_ALLOW_METHODS}],
        "access-control-max-age":       [{"key": "Access-Control-Max-Age",       "value": "600"}],
    }


def _preflight_response(request_origin):
    """200 response for OPTIONS preflight. No body needed."""
    return {
        "status": "200",
        "statusDescription": "OK",
        "headers": _cors_headers(request_origin),
        "body": "",
    }


def _unauthorized_response(message, request_origin):
    """401 with CORS headers so the browser can read the error in dev tools."""
    headers = _cors_headers(request_origin)
    headers["content-type"] = [{"key": "Content-Type", "value": "application/json"}]
    return {
        "status": "401",
        "statusDescription": "Unauthorized",
        "headers": headers,
        "body": json.dumps({"message": message}),
    }


def _validate_bearer(authorization_header):
    """
    Validate the Authorization header against Azure Entra ID:
      - Must be present, 'Bearer <token>' shaped, non-empty
      - Token must be a valid RS256 JWT signed by the configured tenant
      - aud must match AZURE_CLIENT_ID, iss must match AZURE_TENANT_ID
      - exp/nbf must be within the current time window

    See azure_jwt.py for why verification is hand-rolled (stdlib only)
    instead of using PyJWT/python-jose.
    """
    if not authorization_header:
        return False, "Missing authorization token"
    if not authorization_header.startswith("Bearer "):
        return False, "Invalid authorization format. Expected: Bearer <token>"
    token = authorization_header[7:].strip()
    if not token:
        return False, "Empty authorization token"

    ok, _claims, error = verify_azure_jwt(token, AZURE_TENANT_ID, AZURE_CLIENT_ID)
    if not ok:
        return False, error
    return True, None


def lambda_handler(event, context):
    """
    Entry point. Returns either:
      - A response dict (short-circuits CloudFront — no origin call)
      - The request dict (CloudFront proceeds to origin-request)
    """
    cf_request = get_cf_request(event)
    method = cf_request.get("method", "GET").upper()
    uri = cf_request.get("uri", "/")
    request_origin = get_origin(cf_request)

    request_id = event["Records"][0]["cf"]["config"].get("requestId", "unknown")
    logger.info(f"[{request_id}] viewer-request: {method} {uri}")

    # ------------------------------------------------------------------
    # 1. OPTIONS preflight — return 200 immediately, do NOT call origin
    # ------------------------------------------------------------------
    if method == "OPTIONS":
        logger.info(f"[{request_id}] OPTIONS preflight short-circuited at edge")
        return _preflight_response(request_origin)

    # ------------------------------------------------------------------
    # 2. Health check — bypass auth (matches core Lambda behaviour)
    #    /api/health and /health both bypass — CloudFront forwards path as-is.
    # ------------------------------------------------------------------
    if uri in ("/api/health", "/health"):
        logger.info(f"[{request_id}] health check — bypassing auth")
        return cf_request

    # ------------------------------------------------------------------
    # 3. Bearer token validation
    # ------------------------------------------------------------------
    auth_header = get_header(cf_request, "authorization")
    ok, error = _validate_bearer(auth_header)
    if not ok:
        logger.warning(f"[{request_id}] auth failed: {error}")
        return _unauthorized_response(error, request_origin)

    logger.info(f"[{request_id}] auth ok — forwarding to origin-request stage")

    # ------------------------------------------------------------------
    # 4. Pass through to origin-request
    # ------------------------------------------------------------------
    return cf_request
