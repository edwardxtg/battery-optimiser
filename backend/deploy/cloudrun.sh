#!/usr/bin/env bash
# Deploy the backend to Cloud Run. Run from backend/: bash deploy/cloudrun.sh
# Needs a billing-enabled GCP project and authenticated gcloud (gcloud auth login).
set -euo pipefail

PROJECT_ID="$(gcloud config get-value project 2>/dev/null)"
REGION="${REGION:-europe-west2}"        # London
SERVICE="${SERVICE:-battery-optimiser}"
# Set ALLOWED_ORIGINS to your frontend URL to lock CORS (defaults to *).
ALLOWED_ORIGINS="${ALLOWED_ORIGINS:-*}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "No project set. Run: gcloud config set project YOUR_PROJECT_ID" >&2
  exit 1
fi

echo "Enabling required APIs (safe to re-run)…"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com

# Let the default compute service account run source builds (idempotent).
echo "Granting Cloud Build role to the default compute service account (safe to re-run)…"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/cloudbuild.builds.builder" \
  --condition=None >/dev/null
sleep 5  # brief pause for the IAM binding to propagate before the build

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
