# Snowflake Lambda Project

Customer intelligence data platform on AWS, fronting Snowflake through Lambda.

## Architecture

```
Browser
   │
   ▼
CloudFront  ───── /api/* behavior
   │
   ├── viewer-request   ──► Lambda@Edge: auth check, OPTIONS preflight
   │                         (edge_lambda/viewer_request.py)
   │
   ├── origin-request   ──► Lambda@Edge: invoke core Lambda via SDK
   │                         (edge_lambda/origin_request.py)
   │
   └── (dummy S3 origin — never actually called)

                                   │
                                   ▼
                        Core Lambda  ──► Snowflake
                        (core_lambda/)
```

The ALB used in the previous architecture has been removed. All edge logic
runs in Lambda@Edge; the core Lambda is unchanged from the ALB era and
still receives ALB-shape events (built by the origin-request edge function).

## Repository layout

```
.
├── core_lambda/                # Core API Lambda — unchanged from ALB era
│   ├── lambda_function.py      # Entry point
│   ├── router.py               # URL → handler routing, /api prefix strip
│   ├── handlers/               # Per-domain business logic
│   ├── services/               # Snowflake client, Secrets Manager
│   ├── utils/                  # auth, response builder, validators, etc.
│   ├── config/                 # Data product enums, etc.
│   └── tests/
│
├── edge_lambda/                # Lambda@Edge functions (us-east-1)
│   ├── viewer_request.py       # Auth gate + OPTIONS preflight
│   ├── origin_request.py       # Translates CF event ↔ ALB event, invokes core
│   ├── cf_events.py            # Shared CloudFront event helpers
│   ├── config.py               # Stable config (shared across envs)
│   ├── config_values.py        # DEV values (substituted per env at build)
│   ├── config_values_uat.py    # UAT values
│   └── config_values_prod.py   # PROD values
│
├── .github/workflows/          # CI/CD
│   ├── deploy-core.yml         # Core lambda dev→uat→prod pipeline
│   ├── deploy-edge.yml         # Edge lambdas dev→uat→prod pipeline
│   └── pr-validation.yml       # Tests on every PR, no deploy
│
├── docs/
│   └── GITHUB_SETUP.md         # Secrets, environments, workflow guide
│
└── deployment/                 # Infrastructure-as-policy + scripts
    ├── README.md               # From-scratch deployment guide
    ├── deploy_edge.sh          # Manual per-env deploy script
    └── iam/                    # Per-env IAM policies
        ├── edge_lambda_trust_policy.json     # Shared trust policy
        ├── edge_execution_policy_dev.json    # Per-env execution policies
        ├── edge_execution_policy_uat.json
        ├── edge_execution_policy_prod.json
        ├── github_actions_policy_dev.json    # Per-env deploy creds policies
        ├── github_actions_policy_uat.json
        └── github_actions_policy_prod.json
```

## Why two edge functions

| Function | Trigger | Why |
|----------|---------|-----|
| `viewer_request.py` | viewer-request | Reject unauth/OPTIONS at the **earliest** point in the CloudFront pipeline. Responses are tiny — well under the 40 KB viewer-event body cap. |
| `origin_request.py` | origin-request | Invokes core Lambda and translates the response. The 1 MB body cap applies here, which is what we want for Snowflake result sets. |

If response sizes ever push past 1 MB, we'd need to revisit (pagination,
streaming via a different transport, etc).

## Why no Function URL

The security review board mandated zero internet-reachable Lambda surface,
even with `AWS_IAM` auth + Origin Access Control. The trade-off: the
origin-request function pays SDK invocation latency on every request
(~tens of ms warm, a few hundred ms cold). For an internal data platform,
this is acceptable.

## Why no environment variables

Lambda@Edge does not support them. Config lives in `edge_lambda/config.py`
and is baked into the deploy artifact. Update the file, redeploy, publish
a new version, re-associate with CloudFront. ~10 minutes end to end.

## Why the core Lambda is unchanged

The origin-request edge function builds an ALB-shape event before invoking
the core Lambda. From the core Lambda's point of view, nothing has changed
since the ALB days — same `multiValueHeaders`, same `multiValueQueryStringParameters`,
same `/api`-prefixed path, same response shape expected back. This isolates
the migration risk to the edge layer alone.

## Getting started

For deployment from a clean slate, see [`deployment/README.md`](deployment/README.md).

For the core Lambda's internals (Snowflake setup, handlers, etc),
see [`core_lambda/README.md`](core_lambda/README.md) (original README,
unchanged content, just relocated).
