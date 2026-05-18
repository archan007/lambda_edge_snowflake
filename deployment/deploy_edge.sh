#!/usr/bin/env bash
# ============================================================================
# Edge Lambda Deployment Script (local/manual)
# ============================================================================
# Builds and uploads the two edge functions for a SPECIFIC environment.
# Use this for emergency manual deploys or local testing — the normal flow
# is via GitHub Actions (.github/workflows/deploy-edge.yml).
#
# Prereqs:
#   - aws CLI configured with credentials for the target environment's account
#   - Functions already CREATED for that env (see deployment/README.md step 4)
#
# Usage:
#   ./deployment/deploy_edge.sh <env> [viewer|origin|both]
#
#   Examples:
#     ./deployment/deploy_edge.sh dev
#     ./deployment/deploy_edge.sh uat origin
#     ./deployment/deploy_edge.sh prod both
#
# After running, copy the printed version ARN into the matching CloudFront
# distribution's /api/* behavior to activate the new version.
# ============================================================================

set -euo pipefail

ENV="${1:-}"
TARGET="${2:-both}"

if [[ -z "$ENV" ]] || [[ ! "$ENV" =~ ^(dev|uat|prod)$ ]]; then
  echo "Usage: $0 <dev|uat|prod> [viewer|origin|both]"
  exit 1
fi

REGION="us-east-1"
VIEWER_FN_NAME="snowflake-api-edge-viewer-request-${ENV}"
ORIGIN_FN_NAME="snowflake-api-edge-origin-request-${ENV}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EDGE_DIR="${REPO_ROOT}/edge_lambda"
BUILD_DIR="${REPO_ROOT}/.build/${ENV}"

mkdir -p "${BUILD_DIR}"

# ---------------------------------------------------------------------------
# Package one function for the target env. Substitutes config_values_<env>.py
# in for config_values.py before zipping.
# ---------------------------------------------------------------------------
package() {
  local handler_file="$1"   # e.g. viewer_request.py
  local zip_name="$2"       # e.g. viewer.zip

  local stage="${BUILD_DIR}/stage_${handler_file%.py}"
  rm -rf "${stage}"
  mkdir -p "${stage}"

  cp "${EDGE_DIR}/cf_events.py"            "${stage}/"
  cp "${EDGE_DIR}/config.py"               "${stage}/"
  cp "${EDGE_DIR}/config_values_${ENV}.py" "${stage}/config_values.py"
  cp "${EDGE_DIR}/${handler_file}"         "${stage}/"

  ( cd "${stage}" && zip -qr "${BUILD_DIR}/${zip_name}" . )
  echo "Built ${BUILD_DIR}/${zip_name}"
}

upload_and_publish() {
  local fn_name="$1"
  local zip_path="$2"

  echo "Uploading code for ${fn_name}..."
  aws lambda update-function-code \
    --region "${REGION}" \
    --function-name "${fn_name}" \
    --zip-file "fileb://${zip_path}" \
    --publish \
    --output text \
    --query 'FunctionArn'
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
echo "Deploying edge lambdas to ENV=${ENV} (target=${TARGET})"
echo ""

if [[ "${TARGET}" == "viewer" || "${TARGET}" == "both" ]]; then
  package "viewer_request.py" "viewer.zip"
  VIEWER_ARN=$(upload_and_publish "${VIEWER_FN_NAME}" "${BUILD_DIR}/viewer.zip")
  echo "Published viewer-request version: ${VIEWER_ARN}"
fi

if [[ "${TARGET}" == "origin" || "${TARGET}" == "both" ]]; then
  package "origin_request.py" "origin.zip"
  ORIGIN_ARN=$(upload_and_publish "${ORIGIN_FN_NAME}" "${BUILD_DIR}/origin.zip")
  echo "Published origin-request version: ${ORIGIN_ARN}"
fi

echo ""
echo "============================================================"
echo "Next step: associate these version ARNs with the ${ENV}"
echo "CloudFront distribution's /api/* behavior."
echo "Distribution deploy takes ~5-10 minutes to propagate."
echo "============================================================"
