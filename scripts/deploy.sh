#!/usr/bin/env bash
# Deploy Navi backend to Cloud Run (manual / local push)
#
# Prerequisites:
#   1. gcloud auth login
#   2. gcloud config set project navi-stock-analyzer
#   3. Artifact Registry repo 'navi' in asia-east1
#
# Usage:
#   ./scripts/deploy.sh [TAG]

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-navi-stock-analyzer}"
REGION="asia-east1"
SERVICE="navi-backend"
REPO="asia-east1-docker.pkg.dev/${PROJECT_ID}/navi"
TAG="${1:-latest}"
IMAGE="${REPO}/backend:${TAG}"

echo "🧚 Navi — Deploying backend to Cloud Run"
echo "   Project : ${PROJECT_ID}"
echo "   Region  : ${REGION}"
echo "   Image   : ${IMAGE}"
echo ""

# 1. Create Artifact Registry repo (idempotent)
gcloud artifacts repositories describe navi \
  --location="${REGION}" --project="${PROJECT_ID}" 2>/dev/null || \
gcloud artifacts repositories create navi \
  --repository-format=docker \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --description="Navi container images"

# 2. Build
echo "📦 Building Docker image..."
docker build -t "${IMAGE}" -f backend/Dockerfile backend/

# 3. Push
echo "⬆️  Pushing to Artifact Registry..."
docker push "${IMAGE}"

# 4. Deploy
echo "🚀 Deploying to Cloud Run..."
gcloud run deploy "${SERVICE}" \
  --image="${IMAGE}" \
  --region="${REGION}" \
  --platform=managed \
  --no-allow-unauthenticated \
  --service-account="navi-backend@${PROJECT_ID}.iam.gserviceaccount.com" \
  --memory=1Gi \
  --cpu=1 \
  --timeout=300 \
  --max-instances=3 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=${PROJECT_ID},AUTH_REQUIRED=true,DEBUG=false,CORS_ORIGINS=https://navi-stock-analyzer.web.app" \
  --project="${PROJECT_ID}"

# 5. Get URL
URL=$(gcloud run services describe "${SERVICE}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format="value(status.url)")

echo ""
echo "✅ Deployed successfully!"
echo "   URL: ${URL}"
echo ""
echo "Test: curl -X POST ${URL}/api/chat -H 'Content-Type: application/json' -d '{\"message\": \"什麼是 RSI？\"}'"
