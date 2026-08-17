"""
UAT environment values for edge_lambda/config_values.py.

The deploy-edge workflow copies this file over config_values.py
before zipping for UAT deploys.
"""

# Full ARN of the UAT core Lambda function.
CORE_LAMBDA_ARN = "arn:aws:lambda:us-east-1:123456789012:function:snowflake-api-core-uat"

CORE_LAMBDA_REGION = "us-east-1"

# UAT-allowed origins. NO localhost — UAT is not a developer environment.
ALLOWED_ORIGINS = [
    "https://your-uat-distribution.cloudfront.net",
    "https://your-uat-domain.example.com",
]

# Azure Entra ID (Azure AD) app registration backing the UAT SSO login.
AZURE_TENANT_ID = "00000000-0000-0000-0000-000000000000"
AZURE_CLIENT_ID = "00000000-0000-0000-0000-000000000000"
