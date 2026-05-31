#!/bin/bash
# Deploy Cloud Run ML inference service
set -e

PROJECT_ID="fit-5225-a2"
SERVICE_NAME="aussie-ecolens-ml"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"

echo "==> Building Docker image..."
cd "$(dirname "$0")/../gcp-cloud-run"
gcloud builds submit --tag "$IMAGE_NAME" --project="$PROJECT_ID"

echo "==> Deploying to Cloud Run..."
gcloud run deploy "$SERVICE_NAME" \
  --image="$IMAGE_NAME" \
  --platform=managed \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --memory=2Gi \
  --cpu=2 \
  --min-instances=1 \
  --max-instances=3 \
  --timeout=300 \
  --concurrency=10 \
  --set-env-vars="GCS_BUCKET=aussie-ecolens-g62-models,DEV_MODE=false" \
  --allow-unauthenticated

SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --project="$PROJECT_ID" --format="value(status.url)")
echo "==> Deployed at: $SERVICE_URL"
echo "    Add this URL as GCP_INFER_URL in AWS Lambda env vars."
