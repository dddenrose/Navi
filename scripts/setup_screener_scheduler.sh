#!/usr/bin/env bash
# Cloud Scheduler — Navi Screener 排程設定
#
# 建立 4 個排程 job 觸發 POST /api/screener/run：
#   - daily-momentum   平日 06:00 (Asia/Taipei)
#   - daily-value      平日 06:05
#   - weekly-momentum  週日 20:00
#   - weekly-value     週日 20:05
#
# Auth：MVP 階段使用 shared-secret（X-Scheduler-Token header）。
#       Token 存在 Secret Manager（screener-runner-token），Cloud Run 服務
#       透過環境變數讀取；本腳本會在建立 job 時把 token 內嵌到 header value。
#       未來可升級為 OIDC + Cloud Run invoker SA。
#
# Prereq:
#   1. gcloud auth login & gcloud config set project navi-stock-analyzer
#   2. Cloud Run service "navi-backend" 已部署
#   3. Secret "screener-runner-token" 已建立並注入到 Cloud Run（見步驟 0）
#
# Usage:
#   ./scripts/setup_screener_scheduler.sh                   # 建立全部 4 個 job
#   ./scripts/setup_screener_scheduler.sh --create-secret   # 同時建立 Secret
#   ./scripts/setup_screener_scheduler.sh --pause           # 暫停全部 job
#   ./scripts/setup_screener_scheduler.sh --resume          # 恢復全部 job
#   ./scripts/setup_screener_scheduler.sh --delete          # 刪除全部 job

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-navi-stock-analyzer}"
REGION="${SCHEDULER_REGION:-asia-east1}"
SERVICE_NAME="${SERVICE_NAME:-navi-backend}"
SECRET_NAME="screener-runner-token"
TIMEZONE="Asia/Taipei"
JOB_PREFIX="screener"

# Cloud Run service URL
get_service_url() {
  gcloud run services describe "${SERVICE_NAME}" \
    --region="${REGION}" --project="${PROJECT_ID}" \
    --format='value(status.url)' 2>/dev/null
}

# ── 0. （選用）建立 Secret + 注入 Cloud Run ─────────────────────────────────
if [[ "${1:-}" == "--create-secret" ]]; then
  echo "▶ 建立 Secret: ${SECRET_NAME}"
  if gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    echo "   Secret 已存在，略過建立"
  else
    TOKEN_VALUE="$(openssl rand -hex 32)"
    echo -n "${TOKEN_VALUE}" | gcloud secrets create "${SECRET_NAME}" \
      --data-file=- \
      --replication-policy=automatic \
      --project="${PROJECT_ID}"
    echo "   ✅ Secret 已建立（隨機 token, 64 hex chars）"
  fi

  # 授予 Cloud Run runtime SA 讀取 secret 權限
  RUN_SA="navi-backend@${PROJECT_ID}.iam.gserviceaccount.com"
  echo "▶ 授予 ${RUN_SA} 讀取 Secret 權限"
  gcloud secrets add-iam-policy-binding "${SECRET_NAME}" \
    --member="serviceAccount:${RUN_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="${PROJECT_ID}" \
    --quiet >/dev/null

  echo ""
  echo "✅ Secret 設定完成。請手動把 secret 注入到 Cloud Run："
  echo ""
  echo "  gcloud run services update ${SERVICE_NAME} \\"
  echo "    --region=${REGION} --project=${PROJECT_ID} \\"
  echo "    --update-secrets=SCREENER_RUNNER_TOKEN=${SECRET_NAME}:latest"
  echo ""
  exit 0
fi

# ── 取得 token + service URL ────────────────────────────────────────────────
SERVICE_URL="$(get_service_url || true)"
if [[ -z "${SERVICE_URL}" ]]; then
  echo "❌ 找不到 Cloud Run service '${SERVICE_NAME}' (region=${REGION})"
  echo "   請先部署：./scripts/deploy.sh"
  exit 1
fi

# 取 secret 最新版本當 header value（內嵌到 Scheduler job HTTP header）
if ! gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "❌ Secret '${SECRET_NAME}' 不存在。請先執行：$0 --create-secret"
  exit 1
fi
TOKEN="$(gcloud secrets versions access latest --secret="${SECRET_NAME}" --project="${PROJECT_ID}")"

echo "🗓️  Navi Screener — Cloud Scheduler 設定"
echo "   Project    : ${PROJECT_ID}"
echo "   Region     : ${REGION}"
echo "   Endpoint   : ${SERVICE_URL}/api/screener/run"
echo "   Timezone   : ${TIMEZONE}"
echo ""

# Job 定義表：name | schedule | profile | frequency
# 目前只啟用 weekly（週日晚上跑）。需要 daily 時把下方兩行取消註解。
JOBS=(
  # "${JOB_PREFIX}-daily-momentum|0 6 * * 1-5|momentum|daily"
  # "${JOB_PREFIX}-daily-value|5 6 * * 1-5|value|daily"
  "${JOB_PREFIX}-weekly-momentum|0 20 * * 0|momentum|weekly"
  "${JOB_PREFIX}-weekly-value|5 20 * * 0|value|weekly"
)

# ── --pause / --resume / --delete ───────────────────────────────────────────
if [[ "${1:-}" == "--pause" || "${1:-}" == "--resume" || "${1:-}" == "--delete" ]]; then
  ACTION="${1#--}"
  for entry in "${JOBS[@]}"; do
    IFS='|' read -r name _ _ _ <<< "${entry}"
    echo "▶ ${ACTION} ${name}"
    gcloud scheduler jobs "${ACTION}" "${name}" \
      --location="${REGION}" --project="${PROJECT_ID}" --quiet || true
  done
  echo "✅ 完成"
  exit 0
fi

# ── 建立 / 更新 jobs ────────────────────────────────────────────────────────
for entry in "${JOBS[@]}"; do
  IFS='|' read -r name schedule profile frequency <<< "${entry}"
  body="{\"profile\":\"${profile}\",\"frequency\":\"${frequency}\"}"

  echo "▶ ${name}  cron='${schedule}'  body=${body}"

  if gcloud scheduler jobs describe "${name}" \
      --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud scheduler jobs update http "${name}" \
      --location="${REGION}" \
      --project="${PROJECT_ID}" \
      --schedule="${schedule}" \
      --time-zone="${TIMEZONE}" \
      --uri="${SERVICE_URL}/api/screener/run" \
      --http-method=POST \
      --headers="Content-Type=application/json,X-Scheduler-Token=${TOKEN}" \
      --message-body="${body}" \
      --attempt-deadline=900s \
      --quiet >/dev/null
    echo "   ↻ updated"
  else
    gcloud scheduler jobs create http "${name}" \
      --location="${REGION}" \
      --project="${PROJECT_ID}" \
      --schedule="${schedule}" \
      --time-zone="${TIMEZONE}" \
      --uri="${SERVICE_URL}/api/screener/run" \
      --http-method=POST \
      --headers="Content-Type=application/json,X-Scheduler-Token=${TOKEN}" \
      --message-body="${body}" \
      --attempt-deadline=900s \
      --description="Navi Screener: ${profile} / ${frequency}" \
      --quiet >/dev/null
    echo "   ✚ created"
  fi
done

echo ""
echo "✅ 完成。可用以下指令驗證："
echo ""
echo "  gcloud scheduler jobs list --location=${REGION} --project=${PROJECT_ID}"
echo ""
echo "立即手動觸發（測試）："
echo "  gcloud scheduler jobs run ${JOB_PREFIX}-daily-momentum --location=${REGION}"
echo ""
echo "📌 注意：Email notify job (/api/screener/notify) 尚未實作，待 M2.3 完成再加。"
