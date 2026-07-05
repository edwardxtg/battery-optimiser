#!/usr/bin/env bash
# Deploy the battery-optimiser backend to Google Cloud Run.
#
# Prerequisites (one-off):
#   1. A Google Cloud project with billing enabled.
#   2. gcloud CLI installed and authenticated:  gcloud auth login
#   3. Select your project:                     gcloud config set project YOUR_PROJECT_ID
#
# Run from the backend/ directory:  bash deploy/cloudrun.sh
# Cloud Run scales to zero, so an idle demo costs ~£0.
set -euo pipefail

PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
REGION="${REGION:-europe-west2}"        # London
SERVICE="${SERVICE:-battery-optimiser}"
# Optional: restrict CORS to your deployed frontend, e.g.
#   ALLOWED_ORIGINS="https://your-site.com" bash deploy/cloudrun.sh
ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-*}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "No project set. Run: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi

echo "Enabling required APIs (safe to re-run)…"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

echo "Building from the Dockerfile and deploying to Cloud Run (${REGION})…"
gcloud run deploy "${SERVICE}" \
  --source . \
  --region "${REGION}" \
  --allow-unauthenticated \
  --memory 1Gi \
  --cpu 1 \
  --timeout 120 \
  --max-instances 3 \
  --set-env-vars "ALLOWED_ORIGINS=${ALLOWED_ORIGINS}"

echo
echo "Service URL:"
gcloud run services describe "${SERVICE}" --region "${REGION}" --format='value(status.url)'
