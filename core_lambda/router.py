"""
Router Module
=============
Maps incoming requests (HTTP method + path) to handler functions.

Supports all HTTP methods (GET, POST, PUT, DELETE, PATCH).
Handles both Lambda Function URL and ALB/API Gateway event structures.

Adding a new endpoint:
1. Create handler function in handlers/{product}.py
2. Register route below
3. Done!
"""

import re
from typing import Any, Dict

from utils.exceptions import NotFoundError
from utils.auth import validate_authorization

from handlers import accounts, product_1, product_2, health


class Router:

    def __init__(self):
        self.routes = [

            # Health check — must be first, no auth
            ("GET", "/health", health.health_check),

            # ===========================================================
            # GOLD_C360 - Customer 360 Data Product
            # ===========================================================
            ("GET", "/account-summary",           accounts.get_account_summary),
            ("GET", "/account-managers",           accounts.get_account_managers),
            ("GET", "/account-team-region",        accounts.get_account_team_regions),
            ("GET", "/portfolio",                  accounts.get_portfolio),
            ("GET", "/accounts/{id}",              accounts.get_account_detail),
            ("GET", "/account-conversation/{id}", accounts.get_account_conversation),
            ("GET", "/customer-lineage/{id}",     accounts.get_customer_lineage),
            ("GET", "/accounts/{id}/overview",     accounts.get_customer_overview),
            ("GET", "/accounts/{id}/activities",   accounts.get_account_activities),
            ("GET", "/revenue-history/{id}",       accounts.get_revenue_history),

            # ===========================================================
            # GOLD_C360 - Generic Product 1 endpoints
            # ===========================================================
            ("GET", "/endpoint-a",                 product_1.list_endpoint_a),
            ("GET", "/endpoint-b/{id}",            product_1.get_endpoint_b_detail),
            ("GET", "/endpoint-c/summary",         product_1.get_endpoint_c_summary),

            # ===========================================================
            # GOLD_CI - Generic Product 2 endpoints
            # ===========================================================
            ("GET", "/endpoint-d",                 product_2.list_endpoint_d),
            ("GET", "/endpoint-e/{id}",            product_2.get_endpoint_e_detail),
            ("GET", "/endpoint-f/metrics",         product_2.get_endpoint_f_metrics),
            ("GET", "/endpoint-g",                 product_2.get_endpoint_g),
        ]

        self._compiled_routes = [
            (method.upper(), self._compile_pattern(pattern), handler)
            for method, pattern, handler in self.routes
        ]

    @staticmethod
    def _compile_pattern(pattern: str) -> re.Pattern:
        regex_pattern = re.sub(
            r'\{(\w+)\}',
            r'(?P<\1>[^/]+)',
            pattern
        )
        return re.compile(f"^{regex_pattern}$")

    def route(self, event: Dict[str, Any], context: Any) -> Any:
        """
        Route the incoming request to the correct handler.

        Handles:
          - ALB events:              event["httpMethod"] / event["path"]
          - API Gateway events:      event["httpMethod"] / event["path"]
          - Lambda Function URL:     event["requestContext"]["http"]["method/path"]
        """
        http_context = event.get("requestContext", {}).get("http", {})

        method = (
            event.get("httpMethod")           # ALB + API Gateway
            or http_context.get("method")     # Lambda Function URL
            or "GET"
        ).upper()

        path = (
            event.get("path")                 # ALB + API Gateway
            or http_context.get("path")       # Lambda Function URL
            or "/"
        )

        # Strip /api prefix forwarded by CloudFront /api/* behavior
        # so routes can be registered without it (e.g. /health not /api/health)
        if path.startswith("/api"):
            path = path[4:] or "/"

        # ----------------------------------------------------------------
        # Normalise query string parameters
        # ALB with multi-value headers enabled populates multiValueQueryStringParameters
        # (dict of str -> list[str]) instead of queryStringParameters.
        # Flatten it to single values so all handlers can use queryStringParameters
        # consistently regardless of whether the request came via ALB or Function URL.
        # ----------------------------------------------------------------
        if not event.get("queryStringParameters") and event.get("multiValueQueryStringParameters"):
            event["queryStringParameters"] = {
                k: v[0] if v else None
                for k, v in event["multiValueQueryStringParameters"].items()
            }

        # ----------------------------------------------------------------
        # Health check — bypass auth entirely
        # ALB calls this every 30 seconds without Authorization header
        # ----------------------------------------------------------------
        if path == "/health":
            return health.health_check(event, context)

        # ----------------------------------------------------------------
        # OPTIONS preflight — bypass auth entirely
        # Browsers send this before every cross-origin request (CORS).
        # Must return 200 with CORS headers immediately — no auth needed.
        # ----------------------------------------------------------------
        if method == "OPTIONS":
            return {}

        # ----------------------------------------------------------------
        # Auth check — applies to ALL other endpoints
        # ----------------------------------------------------------------
        validate_authorization(event)

        # ----------------------------------------------------------------
        # Route matching
        # ----------------------------------------------------------------
        for route_method, route_regex, handler in self._compiled_routes:
            if route_method != method:
                continue

            match = route_regex.match(path)
            if match:
                path_params = match.groupdict()
                event["pathParameters"] = {
                    **(event.get("pathParameters") or {}),
                    **path_params,
                }
                return handler(event, context)

        raise NotFoundError(f"Route not found: {method} {path}")

    def list_routes(self) -> list:
        return [(method, pattern) for method, pattern, _ in self.routes]