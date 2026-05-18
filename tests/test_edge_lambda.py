"""
Local Unit Tests for Edge Lambda Functions
==========================================
Run with:
    cd edge_lambda && python -m pytest ../tests/test_edge_lambda.py -v

These tests use mocked CloudFront events and a mocked boto3 lambda client,
so they require no AWS credentials and no network.

Why this matters: every CloudFront re-deploy takes 5-10 minutes. Catching
bugs locally saves hours of wall-clock time.
"""

import json
import sys
import os
from unittest.mock import patch, MagicMock

import pytest

# Make edge_lambda importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "edge_lambda"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def make_cf_event(method="GET", uri="/api/account-summary", headers=None, querystring=""):
    """Build a CloudFront viewer-request / origin-request event."""
    cf_headers = {}
    for k, v in (headers or {}).items():
        cf_headers[k.lower()] = [{"key": k, "value": v}]
    return {
        "Records": [{
            "cf": {
                "config": {
                    "distributionId": "EXAMPLE",
                    "eventType": "viewer-request",
                    "requestId": "test-request-id"
                },
                "request": {
                    "method": method,
                    "uri": uri,
                    "querystring": querystring,
                    "headers": cf_headers,
                }
            }
        }]
    }


# ---------------------------------------------------------------------------
# viewer_request tests
# ---------------------------------------------------------------------------
class TestViewerRequest:

    def test_options_preflight_returns_200(self):
        from viewer_request import lambda_handler
        event = make_cf_event(method="OPTIONS", headers={"Origin": "http://localhost:3000"})
        resp = lambda_handler(event, None)
        assert resp["status"] == "200"
        assert "access-control-allow-origin" in resp["headers"]

    def test_missing_authorization_returns_401(self):
        from viewer_request import lambda_handler
        event = make_cf_event()
        resp = lambda_handler(event, None)
        assert resp["status"] == "401"
        body = json.loads(resp["body"])
        assert "Missing" in body["message"]

    def test_non_bearer_authorization_returns_401(self):
        from viewer_request import lambda_handler
        event = make_cf_event(headers={"Authorization": "Basic abc123"})
        resp = lambda_handler(event, None)
        assert resp["status"] == "401"

    def test_empty_bearer_returns_401(self):
        from viewer_request import lambda_handler
        event = make_cf_event(headers={"Authorization": "Bearer "})
        resp = lambda_handler(event, None)
        assert resp["status"] == "401"

    def test_valid_bearer_passes_through(self):
        from viewer_request import lambda_handler
        event = make_cf_event(headers={"Authorization": "Bearer abc.def.ghi"})
        resp = lambda_handler(event, None)
        # Pass-through: returns the request dict, not a response dict
        assert "method" in resp
        assert resp["method"] == "GET"

    def test_health_check_bypasses_auth(self):
        from viewer_request import lambda_handler
        event = make_cf_event(uri="/api/health")
        resp = lambda_handler(event, None)
        # Should pass through despite no Authorization header
        assert "method" in resp


# ---------------------------------------------------------------------------
# origin_request tests
# ---------------------------------------------------------------------------
class TestOriginRequest:

    def test_alb_event_built_correctly(self):
        """Verify CloudFront → ALB event translation."""
        from origin_request import _build_alb_event
        cf_request = make_cf_event(
            method="GET",
            uri="/api/account-summary",
            headers={"Authorization": "Bearer tok", "Origin": "http://localhost:3000"},
            querystring="page=1&limit=20&search=acme%20corp",
        )["Records"][0]["cf"]["request"]

        alb = _build_alb_event(cf_request)

        assert alb["httpMethod"] == "GET"
        assert alb["path"] == "/api/account-summary"
        assert alb["queryStringParameters"]["page"] == "1"
        assert alb["queryStringParameters"]["search"] == "acme corp"
        assert alb["multiValueQueryStringParameters"]["limit"] == ["20"]
        assert alb["headers"]["Authorization"] == "Bearer tok"
        assert alb["multiValueHeaders"]["Authorization"] == ["Bearer tok"]

    def test_cf_response_built_from_alb_response(self):
        """Verify ALB → CloudFront response translation."""
        from origin_request import _build_cf_response

        alb_resp = {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "multiValueHeaders": {
                "Content-Type": ["application/json"],
                "Access-Control-Allow-Origin": ["http://localhost:3000"],
            },
            "body": json.dumps({"data": [1, 2, 3]}),
            "isBase64Encoded": False,
        }

        cf_resp = _build_cf_response(alb_resp, request_origin="http://localhost:3000")

        assert cf_resp["status"] == "200"
        assert cf_resp["body"] == json.dumps({"data": [1, 2, 3]})
        assert cf_resp["headers"]["content-type"][0]["value"] == "application/json"
        assert cf_resp["headers"]["access-control-allow-origin"][0]["value"] == "http://localhost:3000"

    def test_invoke_success_returns_translated_response(self):
        from origin_request import lambda_handler

        fake_alb_resp = {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "multiValueHeaders": {"Content-Type": ["application/json"]},
            "body": json.dumps({"data": "ok"}),
            "isBase64Encoded": False,
        }

        fake_invoke_resp = {
            "StatusCode": 200,
            "Payload": MagicMock(read=MagicMock(return_value=json.dumps(fake_alb_resp).encode())),
        }

        with patch("origin_request._LAMBDA_CLIENT") as mock_client:
            mock_client.invoke.return_value = fake_invoke_resp

            event = make_cf_event(headers={"Authorization": "Bearer tok"})
            resp = lambda_handler(event, None)

            assert resp["status"] == "200"
            assert json.loads(resp["body"])["data"] == "ok"
            mock_client.invoke.assert_called_once()

    def test_invoke_function_error_returns_500_no_leak(self):
        """Core Lambda raised an exception — we return 500 but don't leak the stack."""
        from origin_request import lambda_handler

        fake_invoke_resp = {
            "StatusCode": 200,
            "FunctionError": "Unhandled",
            "Payload": MagicMock(read=MagicMock(return_value=json.dumps({
                "errorType": "ValueError",
                "errorMessage": "internal detail that should not leak",
                "stackTrace": ["secret stack frame"],
            }).encode())),
        }

        with patch("origin_request._LAMBDA_CLIENT") as mock_client:
            mock_client.invoke.return_value = fake_invoke_resp

            event = make_cf_event(headers={"Authorization": "Bearer tok"})
            resp = lambda_handler(event, None)

            assert resp["status"] == "500"
            assert "secret stack frame" not in resp["body"]
            assert "internal detail" not in resp["body"]

    def test_invoke_throws_returns_502(self):
        from origin_request import lambda_handler

        with patch("origin_request._LAMBDA_CLIENT") as mock_client:
            mock_client.invoke.side_effect = Exception("network blew up")

            event = make_cf_event(headers={"Authorization": "Bearer tok"})
            resp = lambda_handler(event, None)

            assert resp["status"] == "502"
