"""
CloudFront Event Helpers
========================
Shared utilities for parsing CloudFront Lambda@Edge events.

CloudFront event structure (viewer-request and origin-request):

    {
      "Records": [{
        "cf": {
          "config": {
            "distributionId": "...",
            "eventType": "viewer-request" | "origin-request",
            "requestId": "..."
          },
          "request": {
            "method": "GET",
            "uri": "/api/account-summary",
            "querystring": "page=1&limit=20",
            "headers": {
              "host": [{"key": "Host", "value": "..."}],
              "authorization": [{"key": "Authorization", "value": "Bearer ..."}]
            },
            "body": {
              "action": "read-only",
              "data": "<base64 if present>",
              "encoding": "base64" | "text",
              "inputTruncated": false
            },
            "origin": { ... }   # origin-request only
          }
        }
      }]
    }

Headers in this structure are lower-cased keys mapping to a list of
{key, value} dicts. This is intentional — CloudFront preserves the original
header casing in `key` while letting you look up by the normalised lower-case
name.
"""

from typing import Any, Dict, List, Optional, Tuple


def get_cf_request(event: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the request object from a CloudFront event."""
    return event["Records"][0]["cf"]["request"]


def get_header(cf_request: Dict[str, Any], name: str) -> Optional[str]:
    """
    Read the first value of a header from a CloudFront request, case-insensitively.

    Returns None if the header is absent.
    """
    headers = cf_request.get("headers") or {}
    entries = headers.get(name.lower())
    if not entries:
        return None
    return entries[0].get("value")


def get_origin(cf_request: Dict[str, Any]) -> Optional[str]:
    """Convenience: read the Origin header (set by browsers on CORS requests)."""
    return get_header(cf_request, "origin")


def parse_querystring(querystring: str) -> Tuple[Dict[str, str], Dict[str, List[str]]]:
    """
    Parse CloudFront's raw querystring (a single string, NOT a dict).

    Returns:
        (single_value_dict, multi_value_dict)
        - single_value_dict matches API Gateway/ALB queryStringParameters shape
        - multi_value_dict matches ALB multiValueQueryStringParameters shape

    Both are produced so the constructed event matches the shape the core
    Lambda's router.py expects (it falls back from queryStringParameters
    to multiValueQueryStringParameters).

    We avoid urllib.parse.parse_qs because it drops empty values by default
    and re-encodes oddly. A manual split keeps behaviour predictable.
    """
    single: Dict[str, str] = {}
    multi: Dict[str, List[str]] = {}

    if not querystring:
        return single, multi

    # urllib's unquote_plus handles + as space and %XX decoding
    from urllib.parse import unquote_plus

    for pair in querystring.split("&"):
        if not pair:
            continue
        if "=" in pair:
            k, v = pair.split("=", 1)
        else:
            k, v = pair, ""
        key = unquote_plus(k)
        val = unquote_plus(v)
        # Single-value: last write wins (matches API Gateway behaviour)
        single[key] = val
        multi.setdefault(key, []).append(val)

    return single, multi


def cf_headers_to_alb_multivalue(cf_headers: Dict[str, List[Dict[str, str]]]) -> Dict[str, List[str]]:
    """
    Convert CloudFront's header shape to ALB's multiValueHeaders shape.

    CloudFront:   {"authorization": [{"key": "Authorization", "value": "Bearer x"}]}
    ALB output:   {"Authorization": ["Bearer x"]}

    We preserve the original-case key from CloudFront's `key` field so
    downstream code that checks "Authorization" vs "authorization" sees
    what the client actually sent.
    """
    result: Dict[str, List[str]] = {}
    for _lower, entries in (cf_headers or {}).items():
        if not entries:
            continue
        original_key = entries[0].get("key") or _lower
        result[original_key] = [e.get("value", "") for e in entries]
    return result


def cf_headers_to_alb_singlevalue(cf_headers: Dict[str, List[Dict[str, str]]]) -> Dict[str, str]:
    """
    Convert CloudFront's header shape to ALB's single-value headers shape.

    Takes the first value for each header.
    """
    result: Dict[str, str] = {}
    for _lower, entries in (cf_headers or {}).items():
        if not entries:
            continue
        original_key = entries[0].get("key") or _lower
        result[original_key] = entries[0].get("value", "")
    return result
