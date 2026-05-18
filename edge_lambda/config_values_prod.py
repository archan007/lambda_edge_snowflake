"""
PROD environment values for edge_lambda/config_values.py.

The deploy-edge workflow copies this file over config_values.py
before zipping for PROD deploys.
"""

# Full ARN of the PROD core Lambda function.
CORE_LAMBDA_ARN = "arn:aws:lambda:us-east-1:123456789012:function:snowflake-api-core-prod"

CORE_LAMBDA_REGION = "us-east-1"

# PROD-allowed origins. NO localhost. NO non-prod domains.
ALLOWED_ORIGINS = [
    "https://your-prod-distribution.cloudfront.net",
    "https://your-prod-domain.example.com",
]
