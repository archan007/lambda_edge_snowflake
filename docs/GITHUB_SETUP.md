# GitHub Secrets & Workflows Configuration Guide

CI/CD configuration for the Lambda@Edge architecture with **separate edge function names and IAM roles per environment (dev/uat/prod)**.

## Workflows in this repo

| Workflow | Purpose | Triggers |
|---|---|---|
| `.github/workflows/deploy-core.yml` | Build and deploy the **core Lambda** | Push to main with `core_lambda/**` changes, `v*.*.*` tags, or manual dispatch |
| `.github/workflows/deploy-edge.yml` | Build per-env packages and **publish new versions** of the edge Lambda@Edge functions | Push to main with `edge_lambda/**` changes, `edge-v*.*.*` tags, or manual dispatch |
| `.github/workflows/pr-validation.yml` | Run tests on every PR — no deployment | Pull requests to main |

The two deploy workflows are **independent**. Changes to `core_lambda/**` only redeploy the core lambda; changes to `edge_lambda/**` only republish the edge lambdas.

## Tagging conventions

| Tag pattern | Triggers |
|---|---|
| `v1.2.3` | Core lambda UAT + PROD release |
| `edge-v1.2.3` | Edge lambda UAT + PROD release |

Separate prefixes let you release core and edge changes independently.

## Per-environment naming

| Env | Edge function names | Core lambda | Edge IAM role |
|---|---|---|---|
| dev | `snowflake-api-edge-viewer-request-dev`<br>`snowflake-api-edge-origin-request-dev` | `snowflake-api-core-dev` | `snowflake-api-edge-role-dev` |
| uat | `snowflake-api-edge-viewer-request-uat`<br>`snowflake-api-edge-origin-request-uat` | `snowflake-api-core-uat` | `snowflake-api-edge-role-uat` |
| prod | `snowflake-api-edge-viewer-request-prod`<br>`snowflake-api-edge-origin-request-prod` | `snowflake-api-core-prod` | `snowflake-api-edge-role-prod` |

Each environment's edge IAM role can invoke **only** its own environment's core lambda. No cross-env blast radius.

## AWS OIDC Setup (one-time, per account)

Workflows authenticate via **OIDC federation** — GitHub Actions exchanges a short-lived token for temporary AWS credentials by assuming a per-env IAM role. No long-lived access keys are stored anywhere.

### Step 1 — Create the GitHub OIDC identity provider in IAM (once per account)

In the AWS Console → IAM → Identity providers → Add provider:

- Provider type: **OpenID Connect**
- Provider URL: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`

> Skip this step if the provider already exists (common if other repos already use OIDC in the same account).

### Step 2 — Create one IAM role per environment

Repeat for `dev`, `uat`, `prod`. Suggested role names:

- `snowflake-api-github-actions-dev`
- `snowflake-api-github-actions-uat`
- `snowflake-api-github-actions-prod`

**Trust policy** — use the file in `deployment/iam/github_actions_oidc_trust_policy_<env>.json` (replace `123456789012` with your account ID). The `sub` condition locks the role to that specific GitHub Environment — the UAT role cannot be assumed by the DEV job.

**Permissions policy** — attach `deployment/iam/github_actions_policy_<env>.json` (edge Lambda permissions). For the core workflow, also attach an inline policy granting `s3:PutObject` on the env's deployment bucket.

### Step 3 — Note the role ARNs

After creating each role, copy its ARN:
```
arn:aws:iam::<account-id>:role/snowflake-api-github-actions-dev
```

## Repository Secrets

The same three secrets serve both the core and edge workflows.

| Secret Name | Used by | Value |
|---|---|---|
| `AWS_ROLE_ARN_DEV` | both | IAM role ARN for the `dev` environment (from Step 3 above) |
| `AWS_ROLE_ARN_UAT` | both | IAM role ARN for the `uat` environment |
| `AWS_ROLE_ARN_PROD` | both | IAM role ARN for the `prod` environment |
| `S3_BUCKET_DEV` | core only | S3 bucket name for core lambda zip artifacts |
| `S3_BUCKET_UAT` | core only | UAT artifact bucket name |
| `S3_BUCKET_PROD` | core only | PROD artifact bucket name |

Add at: Settings → Secrets and variables → Actions → Repository secrets.

The edge workflow does NOT use S3 — `aws lambda update-function-code --zip-file` uploads directly.

## IAM permissions for the deploy roles

Each role's permissions are scoped to that environment's resources only.

The exact policy is in `deployment/iam/github_actions_policy_<env>.json`. The key permissions:

```json
{
  "Action": [
    "lambda:UpdateFunctionCode",
    "lambda:PublishVersion",
    "lambda:GetFunction"
  ],
  "Resource": [
    "arn:aws:lambda:us-east-1:<account-id>:function:snowflake-api-edge-viewer-request-<env>",
    "arn:aws:lambda:us-east-1:<account-id>:function:snowflake-api-edge-origin-request-<env>"
  ]
}
```

**Critical**: the resource ARNs are scoped to just that env's function names. The DEV role cannot accidentally update PROD edge functions. The OIDC trust policy's `sub` condition adds a second layer — the PROD role can only be assumed by a GitHub Actions job running in the `prod` GitHub Environment.

## GitHub Environments Setup

1. Settings → Environments → create three: `dev`, `uat`, `prod`
2. These environments are shared between the core and edge workflows.

### Environment: dev
- No protection rules — auto-deploy on push to main

### Environment: uat
- Required reviewer: 1 (QA team)
- Deployment branches: `main` only

### Environment: prod
- Required reviewers: 2 (release managers)
- Optional wait timer (e.g. 5 min)
- Deployment branches: `main` only

The protection rules gate **the GitHub Actions job from running** — when a job targets an environment with required reviewers, the workflow pauses and waits for approval in the GitHub UI before proceeding.

## How per-env config baking works in the workflow

Lambda@Edge has no env vars. The workflow handles this by building **three pairs of zips per run** (one pair per env), each with the right `config_values.py` baked in:

```
edge_lambda/
├── config.py                  # logic — imports from config_values
├── config_values.py           # DEV values (committed)
├── config_values_uat.py       # UAT values (committed)
└── config_values_prod.py      # PROD values (committed)
```

At build time, the workflow:
1. Stages each handler with `cf_events.py` and `config.py`
2. Copies `config_values_<env>.py` over `config_values.py` for that env's zip
3. Zips it

The deployed artifact in each env has its own `config_values.py` content baked in. Test mocks and local runs use the committed DEV values.

## Release flows

### Edge lambda — DEV deploy (automatic)

```bash
git checkout main && git pull
git merge feature/some-edge-change
git push
```
→ DEV publishes a new version automatically.

### Edge lambda — UAT + PROD via tag

```bash
git tag -a edge-v1.0.1 -m "Edge v1.0.1: fix CORS handling"
git push origin edge-v1.0.1
```
→ UAT publishes (waits for QA approval) → PROD publishes (waits for release manager approval).

### Coordinated core + edge release

```bash
git tag -a v1.3.0 -m "Release v1.3.0: new endpoint"
git tag -a edge-v1.1.0 -m "Edge v1.1.0: route /api/new-endpoint"
git push origin v1.3.0 edge-v1.1.0
```
→ Both workflows run in parallel.

## After-deploy: CloudFront association

Every successful edge publish stops with version ARNs in the workflow summary. To activate the new version:

1. Copy the ARN from the workflow summary
2. AWS Console → CloudFront → that env's distribution
3. Edit the `/api/*` behavior
4. Replace the existing viewer-request / origin-request association with the new version ARN
5. Save — CloudFront deploy takes 5-10 min

**Per environment**. Each env has its own CloudFront distribution; you update each one separately when promoting changes through dev → uat → prod.

## Why CloudFront association is manual

1. **Propagation delay.** Each CloudFront update is a 5-10 min global distribution deploy. Doing this in the workflow makes every edge deploy a 10+ min event.
2. **Human review.** Eyeballing the ARN before paste catches mistakes (wrong env, wrong function).
3. **Change windows.** Some teams require a CAB for prod CloudFront edits.

If you later want to automate it, the workflow needs CloudFront permissions added per env and an extra job that runs after publish. See comments in `deploy-edge.yml`.

## Rollback strategy

### Edge rollback

Lambda@Edge keeps all published versions. To roll back:

1. Find the previous good version ARN (in earlier workflow run summaries, or in the AWS Console under each function's Versions tab)
2. In CloudFront, edit `/api/*` to associate the **previous** version ARN
3. Save — distribution deploys the rollback in 5-10 min

**No workflow re-run needed.** Old versions stay deployable as long as the function exists.

### Core rollback

Push a fix, or revert the commit. Tag if it's a UAT/PROD release.

## Versioning

```
v{MAJOR}.{MINOR}.{PATCH}        # core
edge-v{MAJOR}.{MINOR}.{PATCH}   # edge
```

| Change | Bump | Example |
|---|---|---|
| Bug fix | PATCH | `v1.0.0` → `v1.0.1` |
| New feature (backward compat) | MINOR | `v1.0.1` → `v1.1.0` |
| Breaking change | MAJOR | `v1.1.0` → `v2.0.0` |

## Troubleshooting

### Workflow fails: "function does not exist"
The edge function hasn't been created yet for that env. The workflow only updates existing functions. First-time creation is manual (see `deployment/README.md` step 4).

### Workflow fails: "is not authorized to perform: lambda:UpdateFunctionCode"
The role lacks permissions. Apply `deployment/iam/github_actions_policy_<env>.json` to the IAM role for that env.

### Workflow fails: "Could not assume role" / "Not authorized to perform sts:AssumeRoleWithWebIdentity"
Two possible causes:
1. The GitHub OIDC identity provider hasn't been created in IAM yet (see Step 1 above).
2. The trust policy `sub` condition doesn't match — check that the GitHub Environment name in the trust policy exactly matches the `environment: name:` in the workflow job.

### Tag triggers wrong workflow
- `v*.*.*` → core only
- `edge-v*.*.*` → edge only

Match the prefix to what you intend to deploy.

### Edge workflow runs but core doesn't (or vice versa)
The `paths:` filter at the top of each workflow restricts which file changes trigger them. Shared files (top-level README, etc) trigger neither. Intentional.

### Wrong env's function got updated
Each job uses scoped credentials AND scoped function names. If the wrong function was updated, check:
1. The function name in the workflow's `env:` block for that job
2. The IAM policy on the deploy credentials — they should only allow the env's functions
