# Snowflake Secrets Configuration

## AWS Secrets Manager Structure

This document describes the Snowflake credentials structure for multi-data-product access.

## Architecture Note

The Lambda connects to a Snowflake **database** but does NOT specify a default schema, because it needs to query multiple data products (schemas) like `GOLD_C360`, `GOLD_CI`, etc.

Each handler explicitly declares which schema it queries via `config/data_products.py`.

## Secret Naming Convention

- **DEV**: `snowflake/dev/credentials`
- **UAT**: `snowflake/uat/credentials`
- **PROD**: `snowflake/prod/credentials`

## Secret Structure (JSON)

```json
{
  "account": "SNOWFLAKE_ACCOUNT_IDENTIFIER",
  "user": "SERVICE_USER_NAME",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE...\n-----END PRIVATE KEY-----",
  "private_key_passphrase": "OPTIONAL_PASSPHRASE",
  "database": "DATABASE_NAME",
  "warehouse": "WAREHOUSE_NAME",
  "role": "ROLE_NAME"
}
```

### Field Descriptions

| Field | Required | Description | Example |
|-------|----------|-------------|---------|
| `account` | Yes | Snowflake account identifier | `myorg-dev` or `xy12345.us-east-1` |
| `user` | Yes | Snowflake service user | `SVC_LAMBDA_USER` |
| `private_key` | Yes | PEM-formatted RSA private key | (see below) |
| `private_key_passphrase` | No | Passphrase if key is encrypted | `secure_pass_123` |
| `database` | Yes | Database containing all data product schemas | `ANALYTICS_DB_DEV` |
| `warehouse` | Yes | Compute warehouse | `LAMBDA_WH` |
| `role` | Yes | Role with access to all required schemas | `API_ROLE` |

### ❌ What's NOT in Secrets Anymore

- `schema` — REMOVED. The Lambda queries multiple schemas, so we don't set a default. Schemas are explicit per handler.

## Example Configurations

### DEV Environment (`snowflake/dev/credentials`)

```json
{
  "account": "mycompany-dev",
  "user": "SVC_LAMBDA_DEV",
  "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7...\n-----END PRIVATE KEY-----",
  "database": "ANALYTICS_DB_DEV",
  "warehouse": "LAMBDA_WH_DEV",
  "role": "API_ROLE_DEV"
}
```

### UAT Environment (`snowflake/uat/credentials`)

```json
{
  "account": "mycompany-uat",
  "user": "SVC_LAMBDA_UAT",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
  "database": "ANALYTICS_DB_UAT",
  "warehouse": "LAMBDA_WH_UAT",
  "role": "API_ROLE_UAT"
}
```

### PROD Environment (`snowflake/prod/credentials`)

```json
{
  "account": "mycompany-prod",
  "user": "SVC_LAMBDA_PROD",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----",
  "database": "ANALYTICS_DB_PROD",
  "warehouse": "LAMBDA_WH_PROD",
  "role": "API_ROLE_PROD"
}
```

## Snowflake Permissions Required

The role specified in secrets needs:

```sql
-- Database access
GRANT USAGE ON DATABASE ANALYTICS_DB_DEV TO ROLE API_ROLE_DEV;

-- Schema access (one GRANT per data product)
GRANT USAGE ON SCHEMA ANALYTICS_DB_DEV.GOLD_C360 TO ROLE API_ROLE_DEV;
GRANT USAGE ON SCHEMA ANALYTICS_DB_DEV.GOLD_CI TO ROLE API_ROLE_DEV;
-- ... add for each data product

-- Warehouse access
GRANT USAGE ON WAREHOUSE LAMBDA_WH_DEV TO ROLE API_ROLE_DEV;

-- Procedure execution (one GRANT per stored procedure)
GRANT USAGE ON PROCEDURE ANALYTICS_DB_DEV.GOLD_C360.sp_account_summary(...) TO ROLE API_ROLE_DEV;
GRANT USAGE ON PROCEDURE ANALYTICS_DB_DEV.GOLD_C360.sp_account_detail(...) TO ROLE API_ROLE_DEV;
GRANT USAGE ON PROCEDURE ANALYTICS_DB_DEV.GOLD_CI.sp_endpoint_d(...) TO ROLE API_ROLE_DEV;
-- ... etc.

-- Or grant ALL procedures in a schema (less granular but easier):
GRANT USAGE ON ALL PROCEDURES IN SCHEMA ANALYTICS_DB_DEV.GOLD_C360 TO ROLE API_ROLE_DEV;
GRANT USAGE ON FUTURE PROCEDURES IN SCHEMA ANALYTICS_DB_DEV.GOLD_C360 TO ROLE API_ROLE_DEV;
```

## Generating Key Pair

### 1. Generate Private Key

```bash
# Encrypted (recommended for PROD)
openssl genrsa 2048 | openssl pkcs8 -topk8 -v2 des3 -out rsa_key.p8

# Unencrypted (only for DEV testing)
openssl genrsa 2048 | openssl pkcs8 -topk8 -nocrypt -out rsa_key.p8
```

### 2. Generate Public Key

```bash
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
```

### 3. Assign Public Key to Snowflake User

```sql
ALTER USER SVC_LAMBDA_DEV SET RSA_PUBLIC_KEY='MIIBIjANBgkqhki...';
DESC USER SVC_LAMBDA_DEV;
```

## Creating Secrets via AWS CLI

```bash
aws secretsmanager create-secret \
  --name snowflake/dev/credentials \
  --description "Snowflake credentials for DEV" \
  --secret-string file://dev-secret.json \
  --region us-east-1
```

## Lambda Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `ENVIRONMENT` | Target environment | `DEV` / `UAT` / `PROD` |
| `SNOWFLAKE_SECRET_NAME` | Secret name in Secrets Manager | `snowflake/dev/credentials` |
| `AWS_REGION` | AWS region | `us-east-1` |

## IAM Permissions for Lambda

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": [
        "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:snowflake/dev/*",
        "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:snowflake/uat/*",
        "arn:aws:secretsmanager:us-east-1:ACCOUNT_ID:secret:snowflake/prod/*"
      ]
    }
  ]
}
```

## Adding a New Data Product

When you add a new schema (e.g., `GOLD_RDR`):

### 1. Add to `config/data_products.py`

```python
class DataProduct:
    GOLD_C360 = "GOLD_C360"
    GOLD_CI = "GOLD_CI"
    GOLD_RDR = "GOLD_RDR"  # ← New
```

### 2. Grant Snowflake permissions

```sql
GRANT USAGE ON SCHEMA ANALYTICS_DB_DEV.GOLD_RDR TO ROLE API_ROLE_DEV;
GRANT USAGE ON ALL PROCEDURES IN SCHEMA ANALYTICS_DB_DEV.GOLD_RDR TO ROLE API_ROLE_DEV;
```

### 3. Use in handlers

```python
from config.data_products import DataProduct

SCHEMA = DataProduct.GOLD_RDR

def my_new_handler(event, context):
    rows, _ = snowflake_client.call_procedure(
        schema=SCHEMA,
        procedure_name="sp_my_new_proc",
        params=(...)
    )
```

**No changes needed to:**
- AWS Secrets Manager (same secret, no schema there)
- Lambda environment variables
- CI/CD pipeline
