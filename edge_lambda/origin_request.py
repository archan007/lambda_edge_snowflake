"""
Lambda@Edge — Origin Request (core Lambda invoker)
==================================================
Runs on the CloudFront `origin-request` event for the /api/* behavior.

By the time this runs, the viewer-request function has already:
  - Rejected OPTIONS preflight (returned 200 directly, never got here)
  - Rejected unauthenticated requests (returned 401 directly, never got here)

So every request that reaches this function is authenticated and non-preflight.

Responsibilities:
  1. Translate the CloudFront request into an ALB-style event
     (the shape core Lambda's router.py / utils/auth.py expect)
  2. Invoke the core Lambda synchronously via boto3
  3. Translate the core Lambda's ALB-style response back into CloudFront's
     response shape
  4. Return the response — short-circuits CloudFront's actual origin
     (the dummy S3 bucket configured on the distribution is never called)

Limits to remember:
  - Memory: configurable up to 10 GB (we'll start at 256 MB)
  - Timeout: up to 30 seconds
  - No environment variables (use config.py)
  - No VPC access
  - Response body up to 1 MB (matters here — large Snowflake result sets)
  - Must be deployed to us-east-1 and associated as a numbered version

Cold-start cost: a few hundred ms. boto3 is bundled in the Python runtime
so no layer is needed.

The boto3 Lambda client is created at module load and reused across warm
invocations — same pattern as the core Lambda's Snowflake client.
"""

import base64
import json
import logging

import boto3
from botocore.config import Config

from cf_events import (
    cf_headers_to_alb_multivalue,
    cf_headers_to_alb_singlevalue,
    get_cf_request,
    get_origin,
    parse_querystring,
)
from config import (
    ALLOWED_ORIGINS,
    CORE_LAMBDA_ARN,
    CORE_LAMBDA_REGION,
    DEFAULT_ORIGIN,
)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Module-level boto3 client — reused across warm invocations.
# Tight timeouts: this whole edge function must finish in 30s.
_LAMBDA_CLIENT = boto3.client(
    "lambda",
    region_name=CORE_LAMBDA_REGION,
    config=Config(
        connect_timeout=3,
        read_timeout=25,
        retries={"max_attempts": 1},   # Edge timeout is 30s — no room for retries
    ),
)


# ---------------------------------------------------------------------------
# CloudFront response builders
# ---------------------------------------------------------------------------
def _resolve_cors_origin(request_origin):
    if request_origin and request_origin in ALLOWED_ORIGINS:
        return request_origin
    return DEFAULT_ORIGIN


def _error_response(status_code, message, request_origin):
    """Build a CloudFront response for edge-layer errors (502, 504, etc)."""
    cors_origin = _resolve_cors_origin(request_origin)
    return {
        "status": str(status_code),
        "statusDescription": _status_description(status_code),
        "headers": {
            "content-type":                [{"key": "Content-Type", "value": "application/json"}],
            "access-control-allow-origin": [{"key": "Access-Control-Allow-Origin", "value": cors_origin}],
        },
        "body": json.dumps({"message": message}),
    }


def _status_description(status_code):
    return {
        200: "OK",
        400: "Bad Request",
        401: "Unauthorized",
        402: "Payment Required",
        403: "Forbidden",
        404: "Not Found",
        500: "Internal Server Error",
        502: "Bad Gateway",
        504: "Gateway Timeout",
    }.get(status_code, str(status_code))


# ---------------------------------------------------------------------------
# CloudFront → ALB event translation
# ---------------------------------------------------------------------------
def _build_alb_event(cf_request):
    """
    Build the ALB-with-multi-value-headers event shape that the core
    Lambda's router.py expects.

    Match the actual shape ALB sends so the core Lambda code path is
    IDENTICAL to before — no behavioural diff between old (ALB) and new
    (edge) front-ends.
    """
    method = cf_request.get("method", "GET").upper()
    uri = cf_request.get("uri", "/")
    querystring = cf_request.get("querystring", "")

    qs_single, qs_multi = parse_querystring(querystring)

    headers_single = cf_headers_to_alb_singlevalue(cf_request.get("headers", {}))
    headers_multi  = cf_headers_to_alb_multivalue(cf_request.get("headers", {}))

    # Body handling — CloudFront delivers body base64-encoded when present.
    # Forward it through in the same encoding it arrived with.
    body = None
    is_base64 = False
    cf_body = cf_request.get("body") or {}
    if cf_body.get("data"):
        body = cf_body["data"]
        is_base64 = cf_body.get("encoding") == "base64"

    return {
        "httpMethod": method,
        "path": uri,                                          # core Lambda strips /api itself
        "queryStringParameters": qs_single or None,
        "multiValueQueryStringParameters": qs_multi or None,
        "headers": headers_single,
        "multiValueHeaders": {k: v for k, v in headers_multi.items()},
        "body": body,
        "isBase64Encoded": is_base64,
        # requestContext: ALB normally provides ARN here. Core Lambda doesn't
        # read it today, so an empty stub is enough.
        "requestContext": {
            "elb": {"targetGroupArn": "edge-lambda-synthetic"},
        },
    }


# ---------------------------------------------------------------------------
# ALB response → CloudFront response translation
# ---------------------------------------------------------------------------
def _build_cf_response(alb_response, request_origin):
    """
    Convert the core Lambda's ALB-shaped response into CloudFront's shape.

    Core Lambda always returns both `headers` and `multiValueHeaders`.
    We prefer `multiValueHeaders` (more general) and fall back to `headers`.
    """
    status_code = int(alb_response.get("statusCode", 502))

    # Body: pass through as-is. Core Lambda always returns a string.
    body = alb_response.get("body", "")
    is_base64 = alb_response.get("isBase64Encoded", False)

    # Headers: build CloudFront's shape {lower-name: [{key, value}, ...]}
    cf_headers = {}

    mv = alb_response.get("multiValueHeaders") or {}
    sv = alb_response.get("headers") or {}

    if mv:
        for k, values in mv.items():
            cf_headers[k.lower()] = [{"key": k, "value": v} for v in (values or [])]
    else:
        for k, v in sv.items():
            cf_headers[k.lower()] = [{"key": k, "value": v}]

    # Defensive: ensure Access-Control-Allow-Origin is present and correct
    # even if the core Lambda failed to set it (e.g. unexpected exception path).
    if "access-control-allow-origin" not in cf_headers:
        cf_headers["access-control-allow-origin"] = [{
            "key": "Access-Control-Allow-Origin",
            "value": _resolve_cors_origin(request_origin),
        }]

    return {
        "status": str(status_code),
        "statusDescription": _status_description(status_code),
        "headers": cf_headers,
        "body": body,
        "bodyEncoding": "base64" if is_base64 else "text",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def lambda_handler(event, context):
    cf_request = get_cf_request(event)
    request_origin = get_origin(cf_request)

    request_id = event["Records"][0]["cf"]["config"].get("requestId", "unknown")
    logger.info(
        f"[{request_id}] origin-request: {cf_request.get('method')} {cf_request.get('uri')}"
    )

    # 1. Translate CloudFront → ALB event
    try:
        alb_event = _build_alb_event(cf_request)
    except Exception as e:
        logger.error(f"[{request_id}] failed to build ALB event: {e}", exc_info=True)
        return _error_response(500, "Edge request translation failed", request_origin)

    # 2. Invoke core Lambda synchronously
    try:
        invoke_resp = _LAMBDA_CLIENT.invoke(
            FunctionName=CORE_LAMBDA_ARN,
            InvocationType="RequestResponse",
            Payload=json.dumps(alb_event).encode("utf-8"),
        )
    except Exception as e:
        logger.error(f"[{request_id}] lambda.invoke failed: {e}", exc_info=True)
        return _error_response(502, "Upstream service unavailable", request_origin)

    # 3. Read core Lambda's response payload
    status_code = invoke_resp.get("StatusCode", 500)
    function_error = invoke_resp.get("FunctionError")

    payload_bytes = invoke_resp["Payload"].read()
    try:
        alb_response = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        logger.error(f"[{request_id}] failed to decode core lambda payload: {e}", exc_info=True)
        return _error_response(502, "Invalid upstream response", request_origin)

    # FunctionError set => core lambda raised an unhandled exception.
    # Payload contains {"errorType", "errorMessage", "stackTrace"} — log and
    # return 500, but do NOT leak the upstream stack trace to the client.
    if function_error:
        logger.error(
            f"[{request_id}] core lambda FunctionError={function_error} "
            f"payload={alb_response}"
        )
        return _error_response(500, "Internal server error", request_origin)

    if status_code >= 300:
        logger.error(
            f"[{request_id}] unexpected invoke StatusCode={status_code} payload={alb_response}"
        )
        return _error_response(502, "Upstream invocation error", request_origin)

    # 4. Translate ALB response → CloudFront response
    cf_response = _build_cf_response(alb_response, request_origin)
    logger.info(f"[{request_id}] origin-request returning status={cf_response['status']}")
    return cf_response
