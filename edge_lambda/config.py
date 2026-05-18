"""
Edge Lambda Configuration
=========================
Lambda@Edge does NOT support environment variables. Per-environment values
are baked in at build time via config_values.py — the deploy workflow
copies the appropriate config_values_<env>.py over config_values.py before
zipping, so each environment's deployed artifact carries its own values.

This file (config.py) contains the STABLE config — defaults, derived values,
and constants that are the same across all environments. The per-env values
(core lambda ARN, allowed CORS origins) live in config_values.py.

To change per-env values:
  1. Edit edge_lambda/config_values_<env>.py
  2. Push to main / tag for release
  3. Pipeline rebuilds and re-publishes a new version per env
  4. Update CloudFront association manually (per env)

To change shared values (CORS header names, etc):
  Edit this file. They're the same everywhere.
"""

# Pull per-environment values. At build time, config_values.py has been
# replaced with the env-specific variant by the CI/CD pipeline.
from config_values import (
    CORE_LAMBDA_ARN,
    CORE_LAMBDA_REGION,
    ALLOWED_ORIGINS,
)

# ---------------------------------------------------------------------------
# Shared values — same across all environments
# ---------------------------------------------------------------------------

# Default origin returned when the request has no Origin header (e.g. Postman).
# Must be a member of ALLOWED_ORIGINS.
DEFAULT_ORIGIN = ALLOWED_ORIGINS[0]

# Headers allowed on cross-origin requests (matches core Lambda).
CORS_ALLOW_HEADERS = "Content-Type,Authorization"
CORS_ALLOW_METHODS = "GET,POST,PUT,DELETE,OPTIONS"

# CloudFront forwards /api/* requests here. The core Lambda's router.py
# already strips this prefix internally, so we forward the path AS-IS.
API_PATH_PREFIX = "/api"

# Re-export for downstream imports (so callers don't have to know about
# the config_values.py split).
__all__ = [
    "CORE_LAMBDA_ARN",
    "CORE_LAMBDA_REGION",
    "ALLOWED_ORIGINS",
    "DEFAULT_ORIGIN",
    "CORS_ALLOW_HEADERS",
    "CORS_ALLOW_METHODS",
    "API_PATH_PREFIX",
]
