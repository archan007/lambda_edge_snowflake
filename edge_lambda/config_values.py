"""
Per-Environment Config Values
=============================
These values are SUBSTITUTED at build time by the CI/CD pipeline.

The values committed here are the DEV defaults. The deploy-edge workflow
copies the appropriate per-env file (config_values_dev.py, _uat.py, _prod.py)
over this file before zipping, so the deployed artifact always has the
right values for its target environment.

For local testing (pytest), the committed dev values are used as-is.

Why a separate file instead of templating config.py directly:
  - Keeps the logic in config.py stable and testable
  - File substitution is harder to get wrong than sed/string replacement
  - Diffs in PRs cleanly show env-specific changes
"""

# Full ARN of the core Lambda function in us-east-1.
# DEV value here; overridden at build time for UAT/PROD.
CORE_LAMBDA_ARN = "arn:aws:lambda:us-east-1:123456789012:function:snowflake-api-core-dev"

# Region of the core Lambda. Must match the region in CORE_LAMBDA_ARN.
CORE_LAMBDA_REGION = "us-east-1"

# CORS-allowed origins, env-specific.
# DEV: includes localhost for developer testing.
# UAT/PROD: localhost is dropped — see config_values_uat.py / config_values_prod.py.
ALLOWED_ORIGINS = [
    "https://your-dev-distribution.cloudfront.net",
    "https://your-dev-domain.example.com",
    "http://localhost:3000",
]
