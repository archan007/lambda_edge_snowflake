# Edge Lambda Deployment Guide (Multi-Environment)

End-to-end setup for the **CloudFront → Lambda@Edge (viewer) → Lambda@Edge (origin) → Core Lambda → Snowflake** architecture, with **separate function names and IAM roles per environment (dev/uat/prod)**.

Naming convention used throughout:
- Edge functions: `snowflake-api-edge-{viewer,origin}-request-{env}`
- Edge IAM roles: `snowflake-api-edge-role-{env}`
- Core lambdas (assumed already deployed): `snowflake-api-core-{env}`

This guide walks through setting up **one environment** end to end, then notes what to repeat for the others.

---

## Architecture recap

```
        ┌──────────────┐
        │   Browser    │
        └──────┬───────┘
               │
               ▼
   ┌───────────────────────┐
   │  CloudFront           │  one distribution per environment
   │  (per env)            │
   └──────┬────────────────┘
          │ /api/* behavior
          ▼
   ┌───────────────────────┐
   │  viewer-request       │  per-env function, per-env IAM role
   │  snowflake-api-       │   - auth gate
   │  edge-viewer-         │   - OPTIONS preflight
   │  request-<env>        │
   └──────┬────────────────┘
          │ (auth ok)
          ▼
   ┌───────────────────────┐
   │  origin-request       │  per-env function, per-env IAM role
   │  snowflake-api-       │  Can only invoke its env's core lambda
   │  edge-origin-         │
   │  request-<env>        │
   └──────┬────────────────┘
          │ boto3 SDK
          ▼
   ┌───────────────────────┐
   │  Core Lambda          │  snowflake-api-core-<env>
   │  (per env)            │
   └──────┬────────────────┘
          ▼
       Snowflake
```

Each environment is fully isolated: the dev edge functions cannot invoke the prod core lambda even if compromised, because the dev edge role only has permission on `snowflake-api-core-dev`.

---

## Step 1 — Update placeholders

Edit these files before doing anything in AWS. Search the repo for `123456789012` and the `your-*.example.com` strings.

| File | What to change |
|---|---|
| `edge_lambda/config_values.py` | DEV core lambda ARN, DEV CORS origins |
| `edge_lambda/config_values_uat.py` | UAT core lambda ARN, UAT CORS origins |
| `edge_lambda/config_values_prod.py` | PROD core lambda ARN, PROD CORS origins |
| `deployment/iam/edge_execution_policy_dev.json` | DEV core lambda ARN, account ID |
| `deployment/iam/edge_execution_policy_uat.json` | UAT core lambda ARN, account ID |
| `deployment/iam/edge_execution_policy_prod.json` | PROD core lambda ARN, account ID |
| `deployment/iam/github_actions_policy_*.json` | Account ID in resource ARNs |

The `_comment` keys in the JSON files are non-standard — IAM ignores them when you apply via `aws iam put-role-policy`. They're there to document intent.

---

## Step 2 — Create the IAM execution role for ONE environment

Repeat this section once per environment, changing `<ENV>` to `dev`, `uat`, or `prod`.

```bash
ENV=dev   # change for each env

aws iam create-role \
  --role-name snowflake-api-edge-role-${ENV} \
  --assume-role-policy-document file://deployment/iam/edge_lambda_trust_policy.json

aws iam put-role-policy \
  --role-name snowflake-api-edge-role-${ENV} \
  --policy-name snowflake-api-edge-policy-${ENV} \
  --policy-document file://deployment/iam/edge_execution_policy_${ENV}.json

# Capture the role ARN — needed in step 4
ROLE_ARN=$(aws iam get-role --role-name snowflake-api-edge-role-${ENV} --query 'Role.Arn' --output text)
echo "$ROLE_ARN"
```

The trust policy is the **same across environments** — it grants `edgelambda.amazonaws.com` and `lambda.amazonaws.com` permission to assume the role. The execution policy is **different per environment** — it pins the role to only its env's core lambda ARN.

---

## Step 3 — Add resource policy on the core lambda

Allow the edge role to invoke its env's core lambda:

```bash
aws lambda add-permission \
  --function-name snowflake-api-core-${ENV} \
  --statement-id AllowEdgeLambdaInvoke \
  --action lambda:InvokeFunction \
  --principal "$ROLE_ARN"
```

This is the matching half of the IAM policy from step 2 — the execution policy says "edge role *can* invoke core lambda"; the resource policy says "core lambda *allows* invocation from edge role." Both must be in place.

---

## Step 4 — Create the two edge functions

Both edge functions live in `us-east-1`. **Lambda@Edge functions must be authored in us-east-1**; CloudFront replicates them globally itself.

### 4a. Build the initial zip locally

The zip must include the right `config_values.py` for the target env. The CI/CD pipeline does this automatically; for first-time manual creation:

```bash
ENV=dev   # change for each env

mkdir -p .build/initial/${ENV}/viewer .build/initial/${ENV}/origin

# viewer-request package
cp edge_lambda/cf_events.py            .build/initial/${ENV}/viewer/
cp edge_lambda/config.py               .build/initial/${ENV}/viewer/
cp edge_lambda/config_values_${ENV}.py .build/initial/${ENV}/viewer/config_values.py
cp edge_lambda/viewer_request.py       .build/initial/${ENV}/viewer/
( cd .build/initial/${ENV}/viewer && zip -qr ../viewer.zip . )

# origin-request package
cp edge_lambda/cf_events.py            .build/initial/${ENV}/origin/
cp edge_lambda/config.py               .build/initial/${ENV}/origin/
cp edge_lambda/config_values_${ENV}.py .build/initial/${ENV}/origin/config_values.py
cp edge_lambda/origin_request.py       .build/initial/${ENV}/origin/
( cd .build/initial/${ENV}/origin && zip -qr ../origin.zip . )
```

### 4b. Create viewer-request function

```bash
aws lambda create-function \
  --region us-east-1 \
  --function-name snowflake-api-edge-viewer-request-${ENV} \
  --runtime python3.12 \
  --role "$ROLE_ARN" \
  --handler viewer_request.lambda_handler \
  --timeout 5 \
  --memory-size 128 \
  --zip-file fileb://.build/initial/${ENV}/viewer.zip \
  --publish
```

Viewer-request constraints (these are AWS-enforced caps for viewer events):
- **Timeout**: max 5 seconds
- **Memory**: max 128 MB
- **Response body**: max 40 KB

The `--publish` flag creates version 1 immediately. Lambda@Edge cannot use `$LATEST` — you must always associate a numbered version.

Save the published version ARN that's printed.

### 4c. Create origin-request function

```bash
aws lambda create-function \
  --region us-east-1 \
  --function-name snowflake-api-edge-origin-request-${ENV} \
  --runtime python3.12 \
  --role "$ROLE_ARN" \
  --handler origin_request.lambda_handler \
  --timeout 30 \
  --memory-size 256 \
  --zip-file fileb://.build/initial/${ENV}/origin.zip \
  --publish
```

Origin-request limits:
- **Timeout**: max 30 seconds
- **Memory**: max 10 GB (we start at 256 MB)
- **Response body**: max 1 MB

Save the version ARN.

---

## Step 5 — Create a dummy S3 origin per environment

CloudFront requires an origin even though our edge functions never actually let traffic reach it. Cheapest choice: a private S3 bucket per env.

```bash
ENV=dev   # change for each env

BUCKET_NAME="snowflake-api-cf-dummy-origin-${ENV}-$(date +%s)"
aws s3api create-bucket --bucket "$BUCKET_NAME" --region us-east-1

aws s3api put-public-access-block \
  --bucket "$BUCKET_NAME" \
  --public-access-block-configuration \
  "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

echo "Use as CloudFront origin: ${BUCKET_NAME}.s3.us-east-1.amazonaws.com"
```

---

## Step 6 — Create the CloudFront distribution per environment

**Recommendation: do this in the console**, not via CLI. CloudFront distribution JSON is verbose and error-prone.

For each environment:

1. AWS Console → CloudFront → Create distribution
2. **Origin domain**: the dummy S3 bucket for this env
3. **Origin path**: empty
4. **Origin access**: "Public" (the bucket has Block Public Access on, so nothing is reachable anyway)
5. **Default cache behavior**: leave defaults (it's only `/api/*` that matters)
6. **Alternate domain names (CNAMEs)**: your env-specific domain
7. **Custom SSL certificate**: required if CNAME set; must be in `us-east-1` ACM
8. **Price class**: pick a region set that matches your users
9. Create

While the distribution is deploying (5-10 min), proceed to step 7.

---

## Step 7 — Add the `/api/*` behavior

Edit the distribution and add a second cache behavior:

- **Path pattern**: `/api/*`
- **Origin**: the dummy S3 origin (same as default)
- **Viewer protocol policy**: Redirect HTTP to HTTPS
- **Allowed HTTP methods**: GET, HEAD, OPTIONS, PUT, POST, PATCH, DELETE
- **Cache policy**: `CachingDisabled` (AWS managed)
- **Origin request policy**: `AllViewer` (or a custom one that forwards `Authorization`, `Origin`, all query strings)
- **Function associations**:
  - **Viewer request**: Lambda@Edge → version ARN from step 4b
  - **Origin request**: Lambda@Edge → version ARN from step 4c
  - Leave viewer-response and origin-response empty
  - Check "Include body" if any endpoints accept request bodies

Save. CloudFront deploys (5-10 min).

---

## Step 8 — Test end-to-end

```bash
ENV=dev   # change per env
DIST_DOMAIN="<your-${ENV}-distribution>.cloudfront.net"

# Health check (auth bypassed)
curl -i "https://${DIST_DOMAIN}/api/health"

# Should return 401 without Bearer
curl -i "https://${DIST_DOMAIN}/api/account-summary"

# Should return 200 with valid Bearer
curl -i -H "Authorization: Bearer test-token-123" \
  "https://${DIST_DOMAIN}/api/account-summary?page=1&limit=10"

# OPTIONS preflight
curl -i -X OPTIONS \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  "https://${DIST_DOMAIN}/api/account-summary"
```

---

## Step 9 — Repeat for the other environments

Run steps 2 through 7 for `uat` and `prod`. The only differences are:
- The `ENV` variable
- The execution policy JSON file (per env)
- The core lambda ARN it points to
- The dummy S3 bucket name
- The CloudFront distribution and its domain/CNAME

Total time: ~30 min per env if doing console-based CloudFront setup.

---

## Step 10 — Wire up CI/CD

Once all three environments exist, subsequent code changes flow through GitHub Actions:

1. Edit `edge_lambda/*.py` (and the relevant `config_values_*.py` if needed)
2. Push to main → DEV publishes a new version automatically
3. Tag `edge-v1.2.3` → UAT publishes (with QA approval), then PROD (with release manager approval)
4. **Manual step after each publish**: paste the printed version ARN into the matching CloudFront distribution's `/api/*` behavior

See `docs/GITHUB_SETUP.md` for the GitHub Actions secret and environment setup.

---

## Step 11 — Decommission the old ALB-based path

Once the new pipeline is verified end-to-end and DNS is cut over:

```bash
# 1. Remove ALB invoke permission on each core lambda
ENV=dev   # repeat for uat, prod
aws lambda remove-permission \
  --function-name snowflake-api-core-${ENV} \
  --statement-id <the-old-ALB-statement-id>

# 2. Delete the ALB target groups
# 3. Delete the ALBs
# 4. Delete the old CloudFront distribution (or update its origin/behavior)
```

Verify in CloudWatch that no traffic is still flowing via the old path before deleting.

---

## Troubleshooting

### "The function execution role must be assumable by edgelambda.amazonaws.com"
The trust policy doesn't include `edgelambda.amazonaws.com`. Re-apply `iam/edge_lambda_trust_policy.json`.

### "The function must have a valid published version"
You associated `$LATEST` (or the unqualified ARN) with CloudFront. Use a version-suffixed ARN like `...:function-name:7`.

### CloudFront returns 503 `LambdaValidationError`
The edge function returned a malformed response. Common causes:
- Status code not a string
- Header values not strings
- Body too large (40 KB on viewer events, 1 MB on origin events)
- Missing `headers` field

Check CloudWatch logs **in the region nearest your test client**, not us-east-1.

### CloudFront returns 502 from origin-request function
Most likely the `lambda.invoke` call failed. Check:
- `CORE_LAMBDA_ARN` in `config_values_<env>.py` matches reality
- The resource policy on the core lambda (step 3) was applied
- Core lambda hasn't timed out

### Logs not appearing in us-east-1
Correct — Lambda@Edge logs land in **the region where the function actually executed**, which depends on the viewer's geography. Search across regions for log groups named `/aws/lambda/us-east-1.snowflake-api-edge-*-<env>`.

### Wrong environment's edge function being invoked
Each CloudFront distribution has its own `/api/*` behavior pointing at a specific version ARN. Double-check the ARN you pasted matches the target env's function name.

### "Memory size exceeds the maximum allowed for viewer-request"
Viewer-request is capped at 128 MB. Reduce or move logic to origin-request.

---

## Cost notes

- Lambda@Edge billing is per-request and per-GB-second, ~3x regular Lambda
- Three environments × two functions per env = six functions, each replicated to multiple regions on first invocation
- CloudFront cost scales with traffic but is generally cheap for internal APIs
- S3 dummy buckets: effectively free at zero traffic

For dev/uat with low traffic, the cost difference vs the old ALB is negligible. PROD cost depends on traffic; rough rule of thumb is Lambda@Edge becomes meaningfully more expensive than ALB+regular-Lambda above ~10 RPS sustained.
