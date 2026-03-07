#!/usr/bin/env bash
# Set up Cloud Build triggers for Navi (gcloud CLI)
#
# Prerequisites:
#   1. gcloud auth login
#   2. gcloud config set project navi-stock-analyzer
#   3. GitHub repo already connected to Cloud Build
#      (first time: run with --setup-connection flag)
#
# Usage:
#   ./scripts/setup_trigger.sh [--setup-connection]

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-navi-stock-analyzer}"
REPO_OWNER="${GITHUB_OWNER:-}"        # export GITHUB_OWNER=<你的帳號>
REPO_NAME="Navi"
TRIGGER_REGION="asia-east1"           # connection 與 trigger 須同一 region
BUILD_REGION="asia-east1"

# ── Resolve GitHub owner ──────────────────────────────────────────────────────
if [[ -z "${REPO_OWNER}" ]]; then
  echo "❌ 請先 export GITHUB_OWNER=<你的 GitHub 帳號或 Org 名稱>"
  exit 1
fi

echo "🔧 Navi — Cloud Build Trigger 設定"
echo "   Project    : ${PROJECT_ID}"
echo "   GitHub     : ${REPO_OWNER}/${REPO_NAME}"
echo "   Trigger 區域: ${TRIGGER_REGION}"
echo ""

# ── 0. 啟用必要 APIs ──────────────────────────────────────────────────────────
echo "▶ 啟用必要 APIs（cloudbuild / secretmanager）..."
gcloud services enable \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  --project="${PROJECT_ID}"

# Cloud Build P4SA 需要 Secret Manager 權限才能建立 GitHub connection
echo "▶ 授予 Cloud Build P4SA Secret Manager 權限..."
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"
P4SA="service-${PROJECT_NUMBER}@gcp-sa-cloudbuild.iam.gserviceaccount.com"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${P4SA}" \
  --role="roles/secretmanager.admin" \
  --condition=None \
  --quiet

# ── 1. 連結 GitHub（僅首次需要）──────────────────────────────────────────────
if [[ "${1:-}" == "--setup-connection" ]]; then
  echo "▶ 建立 GitHub 連線（會開啟瀏覽器授權）..."
  if gcloud builds connections describe "navi-github-connection" \
      --region="${TRIGGER_REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "   連線已存在，略過建立步驟"
  else
    gcloud builds connections create github "navi-github-connection" \
      --region="${TRIGGER_REGION}" \
      --project="${PROJECT_ID}"
  fi

  # 確認 OAuth 授權狀態
  CONN_STATE="$(gcloud builds connections describe "navi-github-connection" \
    --region="${TRIGGER_REGION}" --project="${PROJECT_ID}" \
    --format='value(installationState.stage)')"
  if [[ "${CONN_STATE}" != "COMPLETE" ]]; then
    echo ""
    echo "⚠️  GitHub 連線尚未完成授權（目前狀態：${CONN_STATE}）"
    echo "   請先開啟瀏覽器完成授權："
    gcloud builds connections describe "navi-github-connection" \
      --region="${TRIGGER_REGION}" --project="${PROJECT_ID}" \
      --format='value(installationState.actionUri)'
    echo ""
    echo "   授權完成後再重新執行：./scripts/setup_trigger.sh --setup-connection"
    exit 1
  fi

  echo "▶ 連結 GitHub repo..."
  gcloud builds repositories describe "${REPO_NAME}" \
    --connection="navi-github-connection" \
    --region="${TRIGGER_REGION}" \
    --project="${PROJECT_ID}" 2>/dev/null || \
  gcloud builds repositories create "${REPO_NAME}" \
    --connection="navi-github-connection" \
    --remote-uri="https://github.com/${REPO_OWNER}/${REPO_NAME}.git" \
    --region="${TRIGGER_REGION}" \
    --project="${PROJECT_ID}"

  echo "✅ GitHub 連線完成"
  echo ""
fi

# ── 2. 建立 / 設定 Cloud Build 專用 Service Account ──────────────────────────
echo "▶ 設定 Cloud Build Service Account..."
CB_SA="navi-cloudbuild@${PROJECT_ID}.iam.gserviceaccount.com"

# 建立 SA（idempotent）
gcloud iam service-accounts describe "${CB_SA}" --project="${PROJECT_ID}" &>/dev/null || \
gcloud iam service-accounts create "navi-cloudbuild" \
  --display-name="Navi Cloud Build" \
  --description="User-managed SA for Cloud Build triggers (2nd gen)" \
  --project="${PROJECT_ID}"

# 授予所需的 IAM 角色
for ROLE in roles/run.admin roles/iam.serviceAccountUser roles/artifactregistry.writer roles/cloudbuild.builds.builder roles/logging.logWriter roles/datastore.user roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${CB_SA}" \
    --role="${ROLE}" \
    --condition=None \
    --quiet >/dev/null
done

echo "   Cloud Build SA: ${CB_SA}"

# 2nd gen connection 的 repo resource path
REPO_RESOURCE="projects/${PROJECT_ID}/locations/${TRIGGER_REGION}/connections/navi-github-connection/repositories/${REPO_NAME}"
SERVICE_ACCOUNT="projects/${PROJECT_ID}/serviceAccounts/${CB_SA}"
ACCESS_TOKEN="$(gcloud auth print-access-token)"
API_BASE="https://cloudbuild.googleapis.com/v1/projects/${PROJECT_ID}/locations/${TRIGGER_REGION}/triggers"

# ── 3. 建立 / 更新 Trigger：push to main → 部署 production ──────────────────
echo ""
echo "▶ 建立 Trigger [1/3]：push to main → deploy production..."

# 先刪除已有的同類 trigger（idempotent，API 會在 name 加後綴所以用 description 匹配）
EXISTING_ID="$(gcloud builds triggers list \
  --region="${TRIGGER_REGION}" --project="${PROJECT_ID}" \
  --format='value(id)' --filter='description~"Push to main"' 2>/dev/null || true)"
for TID in ${EXISTING_ID}; do
  gcloud builds triggers delete "${TID}" \
    --region="${TRIGGER_REGION}" --project="${PROJECT_ID}" --quiet
done

RESPONSE="$(curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "${API_BASE}" \
  -d "{
    \"description\": \"Push to main: build & deploy backend to Cloud Run\",
    \"serviceAccount\": \"${SERVICE_ACCOUNT}\",
    \"filename\": \"cloudbuild.yaml\",
    \"includedFiles\": [\"backend/**\"],
    \"ignoredFiles\": [\"**/*.md\", \"frontend/**\"],
    \"repositoryEventConfig\": {
      \"repository\": \"${REPO_RESOURCE}\",
      \"push\": { \"branch\": \"^main$\" }
    }
  }")"
echo "${RESPONSE}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
if 'error' in d: print('   ❌ 失敗:', d['error'].get('message',d)); sys.exit(1)
else: print('   ✅ 建立成功:', d.get('name'))
"

# ── 4. 建立 Trigger：PR to main → 只跑測試（防禦性 CI）──────────────────────
echo "▶ 建立 Trigger [2/3]：PR to main → run tests..."

EXISTING_ID="$(gcloud builds triggers list \
  --region="${TRIGGER_REGION}" --project="${PROJECT_ID}" \
  --format='value(id)' --filter='description~"PR to main"' 2>/dev/null || true)"
for TID in ${EXISTING_ID}; do
  gcloud builds triggers delete "${TID}" \
    --region="${TRIGGER_REGION}" --project="${PROJECT_ID}" --quiet
done

RESPONSE="$(curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "${API_BASE}" \
  -d "{
    \"description\": \"PR to main: run backend tests\",
    \"serviceAccount\": \"${SERVICE_ACCOUNT}\",
    \"filename\": \"cloudbuild-test.yaml\",
    \"includedFiles\": [\"backend/**\"],
    \"repositoryEventConfig\": {
      \"repository\": \"${REPO_RESOURCE}\",
      \"pullRequest\": {
        \"branch\": \"^main$\",
        \"commentControl\": \"COMMENTS_ENABLED_FOR_EXTERNAL_CONTRIBUTORS_ONLY\"
      }
    }
  }")"
echo "${RESPONSE}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
if 'error' in d: print('   ❌ 失敗:', d['error'].get('message',d)); sys.exit(1)
else: print('   ✅ 建立成功:', d.get('name'))
"

# ── 5. 建立 Trigger：tag knowledge-v* → ingest knowledge base ────────────────
echo "▶ 建立 Trigger [3/3]：tag knowledge-v* → ingest knowledge base..."

EXISTING_ID="$(gcloud builds triggers list \
  --region="${TRIGGER_REGION}" --project="${PROJECT_ID}" \
  --format='value(id)' --filter='description~"Tag knowledge"' 2>/dev/null || true)"
for TID in ${EXISTING_ID}; do
  gcloud builds triggers delete "${TID}" \
    --region="${TRIGGER_REGION}" --project="${PROJECT_ID}" --quiet
done

RESPONSE="$(curl -s -X POST \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" \
  "${API_BASE}" \
  -d "{
    \"description\": \"Tag knowledge-v*: ingest knowledge base into RAG\",
    \"serviceAccount\": \"${SERVICE_ACCOUNT}\",
    \"filename\": \"cloudbuild-ingest.yaml\",
    \"repositoryEventConfig\": {
      \"repository\": \"${REPO_RESOURCE}\",
      \"push\": { \"tag\": \"^knowledge-v.*$\" }
    }
  }")"
echo "${RESPONSE}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
if 'error' in d: print('   ❌ 失敗:', d['error'].get('message',d)); sys.exit(1)
else: print('   ✅ 建立成功:', d.get('name'))
"

# ── 6. 列出已建立的 triggers ─────────────────────────────────────────────────
echo ""
echo "✅ 所有 Trigger 設定完成！"
echo ""
gcloud builds triggers list \
  --region="${TRIGGER_REGION}" \
  --project="${PROJECT_ID}" \
  --format="table(name, github.push.branch, github.pullRequest.branch, filename)"
