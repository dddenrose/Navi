#!/usr/bin/env bash
# LINE Bot — Navi LINE 問答的 GCP 設定
#
# 做四件事（都可重複執行）：
#   1. 啟用 Cloud Tasks API，建立 queue（webhook 先回 200，再由 task 另起 request 跑 agent）
#   2. 授予 Cloud Run runtime SA 在該 queue 建立 task 的權限
#   3. 把 LINE 的 Channel secret / Channel access token 存進 Secret Manager
#   4. 為去重用的 line_events collection 設定 Firestore TTL
#
# Prereq:
#   1. gcloud auth login & gcloud config set project navi-stock-analyzer
#   2. 已在 LINE Developers Console 取得 Channel secret 與 Channel access token (long-lived)
#
# Usage:
#   ./scripts/setup_line_bot.sh              # 建立 queue + IAM + TTL
#   ./scripts/setup_line_bot.sh --secrets    # 另外互動輸入兩個 LINE 金鑰並存入 Secret Manager

set -euo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-navi-stock-analyzer}"
REGION="${TASKS_REGION:-asia-east1}"
SERVICE_NAME="${SERVICE_NAME:-navi-backend}"
QUEUE_NAME="${LINE_TASKS_QUEUE:-line-events}"
RUN_SA="navi-backend@${PROJECT_ID}.iam.gserviceaccount.com"
SECRET_CHANNEL_SECRET="line-channel-secret"
SECRET_ACCESS_TOKEN="line-channel-access-token"

echo "💬 Navi LINE Bot — GCP 設定"
echo "   Project : ${PROJECT_ID}"
echo "   Region  : ${REGION}"
echo "   Queue   : ${QUEUE_NAME}"
echo ""

# ── 1. Cloud Tasks API + queue ──────────────────────────────────────────────
echo "▶ 啟用 Cloud Tasks API"
gcloud services enable cloudtasks.googleapis.com --project="${PROJECT_ID}" --quiet

# max-concurrent-dispatches=3：不同人的問題可以同時處理。同一人連發兩題時，
#   handler 以 line_links.inflight_until 佔位擋下第二題，對話記錄不會互蓋。
#   一題約 20 秒、多半在等 LLM 與外部 API，3 題同時跑一個實例就吃得下。
# max-attempts=3：只救「request 還沒進到 handler 就失敗」的情況；
#   已開始處理的事件有 webhookEventId 去重，不會重跑。
QUEUE_FLAGS=(
  --location="${REGION}"
  --project="${PROJECT_ID}"
  --max-concurrent-dispatches=3
  --max-attempts=3
  --min-backoff=2s
  --max-backoff=10s
)
if gcloud tasks queues describe "${QUEUE_NAME}" \
    --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
  echo "▶ 更新 queue: ${QUEUE_NAME}"
  gcloud tasks queues update "${QUEUE_NAME}" "${QUEUE_FLAGS[@]}" --quiet >/dev/null
else
  echo "▶ 建立 queue: ${QUEUE_NAME}"
  gcloud tasks queues create "${QUEUE_NAME}" "${QUEUE_FLAGS[@]}" --quiet >/dev/null
fi

# ── 2. IAM：runtime SA 可在此 queue 建立 task ───────────────────────────────
echo "▶ 授予 ${RUN_SA} 建立 task 的權限"
gcloud tasks queues add-iam-policy-binding "${QUEUE_NAME}" \
  --location="${REGION}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${RUN_SA}" \
  --role="roles/cloudtasks.enqueuer" \
  --quiet >/dev/null

# ── 3. Firestore TTL：line_events 文件到期自動清除 ──────────────────────────
echo "▶ 設定 Firestore TTL: line_events.expires_at"
gcloud firestore fields ttls update expires_at \
  --collection-group=line_events \
  --enable-ttl \
  --project="${PROJECT_ID}" \
  --async \
  --quiet >/dev/null

# ── 4. （選用）LINE 金鑰存入 Secret Manager ─────────────────────────────────
store_secret() {
  local name="$1" prompt="$2" value
  read -rs -p "${prompt}: " value
  echo ""
  if [[ -z "${value}" ]]; then
    echo "   ⚠️  未輸入，略過 ${name}"
    return 0
  fi
  if gcloud secrets describe "${name}" --project="${PROJECT_ID}" &>/dev/null; then
    echo -n "${value}" | gcloud secrets versions add "${name}" \
      --data-file=- --project="${PROJECT_ID}" >/dev/null
    echo "   ↻ ${name} 已新增版本"
  else
    echo -n "${value}" | gcloud secrets create "${name}" \
      --data-file=- --replication-policy=automatic --project="${PROJECT_ID}" >/dev/null
    echo "   ✚ ${name} 已建立"
  fi
  gcloud secrets add-iam-policy-binding "${name}" \
    --member="serviceAccount:${RUN_SA}" \
    --role="roles/secretmanager.secretAccessor" \
    --project="${PROJECT_ID}" \
    --quiet >/dev/null
}

if [[ "${1:-}" == "--secrets" ]]; then
  echo "▶ 存入 LINE 金鑰（輸入不會顯示在畫面上）"
  store_secret "${SECRET_CHANNEL_SECRET}" "Channel secret"
  store_secret "${SECRET_ACCESS_TOKEN}" "Channel access token (long-lived)"

  echo ""
  echo "✅ Secret 設定完成。請手動把 secret 注入到 Cloud Run："
  echo ""
  echo "  gcloud run services update ${SERVICE_NAME} \\"
  echo "    --region=${REGION} --project=${PROJECT_ID} \\"
  echo "    --update-secrets=LINE_CHANNEL_SECRET=${SECRET_CHANNEL_SECRET}:latest,LINE_CHANNEL_ACCESS_TOKEN=${SECRET_ACCESS_TOKEN}:latest"
  echo ""
fi

SERVICE_URL="$(gcloud run services describe "${SERVICE_NAME}" \
  --region="${REGION}" --project="${PROJECT_ID}" \
  --format='value(status.url)' 2>/dev/null || true)"

echo ""
echo "✅ 完成。接下來："
echo ""
echo "  1. 部署後端（cloudbuild.yaml 已帶 LINE_TASKS_QUEUE=${QUEUE_NAME}）"
echo "  2. 若尚未存入金鑰：$0 --secrets，並執行它印出的 --update-secrets 指令"
echo "  3. LINE Developers Console → Messaging API → Webhook URL 填："
echo "       ${SERVICE_URL:-<Cloud Run URL>}/api/line/webhook"
echo "     並開啟 Use webhook 與 Webhook redelivery；"
echo "     LINE Official Account Manager 關閉「自動回應訊息」"
echo "  4. 加好友就能用：第一次互動時自動建立 LINE 專用帳號（free 層），停用與額度在管理後台調整"
echo "     要讓 LINE 改用你的網頁帳號：cd backend && uv run python scripts/link_line.py <email> <LINE user ID>"
