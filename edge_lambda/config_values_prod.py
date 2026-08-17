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

# Azure Entra ID (Azure AD) app registration backing the PROD SSO login.
AZURE_TENANT_ID = "00000000-0000-0000-0000-000000000000"
AZURE_CLIENT_ID = "00000000-0000-0000-0000-000000000000"
