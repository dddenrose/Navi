# Navi 額度權限控管 — 實作 Proposal

> 目的：將「每個帳號可無上限詢問」改為「依使用者等級限制每日訊息數，並提供後台管理」。

## 0. 已決策設計參數

| 項目          | 決定                                                     |
| ------------- | -------------------------------------------------------- |
| Tier 預設額度 | `free` 10/日、`pro` 100/日、`unlimited` ∞、`admin` ∞     |
| 計量單位      | 訊息數（一次成功的 `/api/chat` 呼叫 = 1）                |
| 重置週期      | 自然日，**Asia/Taipei 00:00** 重置                       |
| 首位 admin    | 跑一次 `scripts/set_admin.py` 設置 Firebase custom claim |
| 付費流程      | 不接金流，內部管理                                       |
| Audit log     | 啟用，保留 90 天（用 Firestore TTL policy）              |

---

## 1. 資料模型（Firestore）

### 1.1 `users/{uid}`

使用者主檔。第一次呼叫任意需要驗證的 API 時自動 upsert。

```jsonc
{
  "uid": "string",
  "email": "string",
  "display_name": "string",
  "tier": "free | pro | unlimited | admin",
  "status": "active | suspended",
  "custom_daily_limit": null, // null = 用 tier 預設；數字 = 個別 override；-1 = 無限
  "created_at": "timestamp",
  "updated_at": "timestamp",
  "last_active_at": "timestamp",
  "notes": "string", // 後台管理員備註
}
```

### 1.2 `quota_configs/{tier}`

Tier 額度設定，後台可動態調整。

```jsonc
{
  "tier": "free",
  "daily_limit": 10, // -1 = unlimited
  "per_minute_limit": 5, // 防爆衝（記憶體）
  "description": "免費方案",
  "updated_at": "timestamp",
  "updated_by": "uid",
}
```

種子資料：

| tier      | daily_limit | per_minute_limit |
| --------- | ----------- | ---------------- |
| free      | 10          | 5                |
| pro       | 100         | 10               |
| unlimited | -1          | 30               |
| admin     | -1          | 60               |

### 1.3 `usage_counters/{uid}_{YYYY-MM-DD}`

每日用量。原子 increment。

```jsonc
{
  "uid": "string",
  "date": "2026-04-29", // Asia/Taipei
  "chat_count": 7,
  "last_request_at": "timestamp",
  "expires_at": "timestamp", // 90 天後刪除（Firestore TTL）
}
```

### 1.4 `usage_logs/{auto_id}`

Audit log。

```jsonc
{
  "uid": "string",
  "email": "string",
  "tier": "string",
  "endpoint": "/api/chat",
  "conversation_id": "string | null",
  "question_preview": "string (前 100 字)",
  "blocked": false,
  "block_reason": "string | null",
  "timestamp": "timestamp",
  "expires_at": "timestamp", // 90 天後刪除
}
```

> **TTL policy**：在 GCP console 為 `usage_counters` 與 `usage_logs` 的 `expires_at` 欄位開啟 TTL（單次設定，本 proposal 不寫程式自動化）。

---

## 2. 後端架構

### 2.1 新檔

- `backend/services/quota_service.py` — 核心 quota 邏輯
- `backend/api/routes/admin.py` — 管理員 REST API
- `backend/scripts/set_admin.py` — 初始化首位 admin
- `backend/scripts/seed_quota_configs.py` — 寫入 4 個 tier 預設設定
- `backend/tests/test_quota_service.py`

### 2.2 修改

- `backend/api/dependencies.py`
  - 新增 `require_admin` dependency（檢查 token 內 `admin: true` claim）
  - 新增 `get_current_user_with_tier`（回傳 uid + tier，順便 upsert `users/{uid}`）
- `backend/api/rate_limit.py`
  - 保留記憶體 limiter 做 per-minute 防爆衝
  - 新增 `quota_check` middleware-style helper
- `backend/api/routes/chat.py`
  - `/api/chat` POST：在 SSE 開始前 → `quota_service.check_and_consume()` → 若失敗回 429 結構化錯誤
  - 寫 `usage_logs`（成功/失敗都記）
- `backend/main.py`
  - 註冊 `admin.router`

### 2.3 `quota_service` API

```python
@dataclass
class QuotaCheckResult:
    allowed: bool
    tier: str
    daily_limit: int        # -1 = unlimited
    used_today: int
    remaining: int          # -1 = unlimited
    reset_at: datetime      # Asia/Taipei 隔日 00:00 (UTC datetime)
    reason: str | None      # 拒絕原因

async def get_or_create_user(uid: str, email: str, display_name: str) -> dict
async def get_quota_config(tier: str) -> dict
async def check_and_consume(uid: str) -> QuotaCheckResult
async def get_user_usage(uid: str, days: int = 30) -> list[dict]
async def update_user_tier(uid: str, tier: str, actor_uid: str) -> None
async def write_usage_log(...) -> None
```

`check_and_consume` 用 Firestore Transaction 確保多實例下原子性：

1. 讀 `users/{uid}` 拿 tier 與 custom_daily_limit
2. 讀 `quota_configs/{tier}` 拿 daily_limit
3. 讀 `usage_counters/{uid}_{today_taipei}` 拿 chat_count
4. 比對 limit；若超過 → 回 `allowed=False`
5. 否則 increment chat_count、寫 last_request_at、設 expires_at（now + 90d）

> **效能優化**：tier=unlimited 或 limit=-1 時跳過 transaction，僅做最小寫入（last_request_at），減少 Firestore 成本。

### 2.4 Admin API（`/api/admin/*`）

所有路由用 `Depends(require_admin)`。

| Method | Path                              | 描述                                                    |
| ------ | --------------------------------- | ------------------------------------------------------- |
| GET    | `/api/admin/users`                | 列表（query: `q`、`tier`、`status`、`limit`、`cursor`） |
| GET    | `/api/admin/users/{uid}`          | 詳情 + 近 30 天用量                                     |
| PATCH  | `/api/admin/users/{uid}`          | 改 tier / status / custom_daily_limit / notes           |
| GET    | `/api/admin/quota-configs`        | 列出 4 個 tier                                          |
| PUT    | `/api/admin/quota-configs/{tier}` | 更新 tier 額度                                          |
| GET    | `/api/admin/usage/summary`        | 全站近 30 天 KPI（DAU、訊息數、Top 10 用戶）            |
| GET    | `/api/admin/logs`                 | 查 usage_logs（filter: uid、date、blocked）             |
| GET    | `/api/admin/me`                   | 確認自己是 admin（前端 bootstrapping 用）               |

### 2.5 Custom Claims 同步

- `update_user_tier(uid, tier="admin")` 時呼叫 `firebase_admin.auth.set_custom_user_claims(uid, {"admin": True, "tier": tier})`
- 一般 tier 變更也寫 `tier` claim，前端可直接從 ID Token 讀，不用每次打 `/me`
- 使用者下次 refresh token 才會生效（Firebase 預設 1 小時）

### 2.6 拒絕回應格式

```json
HTTP 429
{
  "detail": {
    "code": "QUOTA_EXCEEDED",
    "message": "今日免費額度已用完，明日 00:00 重置",
    "tier": "free",
    "daily_limit": 10,
    "used_today": 10,
    "remaining": 0,
    "reset_at": "2026-04-30T00:00:00+08:00"
  }
}
```

### 2.7 Response Headers

所有 `/api/chat` 成功回應加上：

```
X-Quota-Tier: free
X-Quota-Daily-Limit: 10
X-Quota-Used: 8
X-Quota-Remaining: 2
X-Quota-Reset: 2026-04-30T00:00:00+08:00
```

> 因 `/api/chat` 是 SSE，這些 header 會在 response start 時送出，前端可直接讀。

---

## 3. 前端架構

### 3.1 新檔

- `frontend/src/lib/quotaApi.ts` — 額度查詢、admin API client
- `frontend/src/store/quotaStore.ts` — zustand store（remaining、tier、reset_at）
- `frontend/src/components/QuotaBadge.tsx` — chat 頁右上角顯示
- `frontend/src/components/QuotaExhaustedModal.tsx` — 額度耗盡提示
- `frontend/src/pages/admin/AdminLayout.tsx` — 路由守衛 + 子側欄
- `frontend/src/pages/admin/AdminDashboard.tsx` — KPI
- `frontend/src/pages/admin/AdminUsers.tsx` — 使用者列表
- `frontend/src/pages/admin/AdminUserDetail.tsx` — 使用者詳情 + 編輯
- `frontend/src/pages/admin/AdminQuotaConfigs.tsx` — Tier 設定
- `frontend/src/pages/admin/AdminLogs.tsx` — Audit log

### 3.2 修改

- `App.tsx` — 新增 `/admin/*` 路由（lazy）
- `Layout.tsx` — 若 ID Token claim `admin=true` 顯示「後台」連結
- `lib/api.ts`
  - `streamChat`：讀 response headers 寫入 quotaStore；429 時 onError 帶結構化資訊
  - 新增 `useTokenClaims` hook 讀 `admin` claim
- `pages/Chat.tsx`
  - 顯示 `<QuotaBadge>`
  - 收到 `QUOTA_EXCEEDED` 時 disable 輸入框 + 顯示重置時間

### 3.3 Admin Console UI 樣式

沿用現有 dark theme（`var(--bg-base)`、`var(--card-bg)`、紫色 gradient）。表格與表單用 Tailwind utility class，不引入新 UI library。圖表如需要，最小化用簡單 bar chart（純 CSS）即可，不引入 recharts 以避免 bundle 暴增。

---

## 4. 實作階段

| Phase              | 範圍                                                     | 完成標準                                  |
| ------------------ | -------------------------------------------------------- | ----------------------------------------- |
| **P1 — 資料層**    | quota_service、users upsert、種子資料、單元測試          | `pytest tests/test_quota_service.py` 通過 |
| **P2 — 強制執行**  | chat 整合 quota、429 回應、前端 QuotaBadge、429 處理     | 手動測：free 用戶第 11 次被擋             |
| **P3 — Admin API** | admin routes、custom claims、audit log、set_admin script | curl 測 API、首位 admin 設定成功          |
| **P4 — Admin UI**  | 5 個 admin 頁面、layout 連結                             | UI 可改 tier、看 usage                    |

每個 phase 結束後可獨立部署，不需等下一階段完成。

---

## 5. 風險與決策

- **時區處理**：所有「今日」以 Asia/Taipei 計算，使用 `zoneinfo.ZoneInfo("Asia/Taipei")`，counter doc id 用 `YYYY-MM-DD` 字串。
- **Transaction 衝突**：高頻使用者可能多請求並發，Firestore Transaction 會自動 retry。設定上限 retry 3 次。
- **冷啟成本**：每次 `/api/chat` 多 1–2 次 Firestore 讀寫（~10–30ms p50）。可接受。
- **降級策略**：若 Firestore 暫時不可用，quota_service 的 fail-mode 為 **fail-open**（記 warning log 但放行），避免整站癱瘓。
- **Custom claim 延遲**：tier 變更後使用者需下次 token refresh 才生效。後台改 tier 時提示「最多 1 小時生效」。
- **Audit log 寫入成本**：每次 chat 多 1 次寫入。如未來流量大可改 batch 寫入或抽樣。

---

## 6. 安全性

- Admin API 雙重檢查：① ID token 有 `admin=true` claim ② Firestore `users/{uid}.tier == "admin"`（防止 claim 被誤改後仍能存取）
- 不可用 admin API 修改自己的 tier（避免 lockout）
- `set_admin.py` script 需在本機跑（要 GCP credentials），不開放 production HTTP endpoint
- 速率限制：admin API 也吃 per-minute limiter

---

## 7. 部署與遷移

1. 部署後端（含 admin route 但尚無 admin 使用者，所有 admin API 回 403）
2. 在 GCP console 開啟 `usage_counters` 與 `usage_logs` 的 TTL policy（`expires_at` 欄位）
3. 跑 `uv run python scripts/seed_quota_configs.py` 寫入 4 個 tier 設定
4. 跑 `uv run python scripts/set_admin.py <your-email>` 將自己設為 admin
5. 部署前端
6. 既有使用者首次登入後自動建立 `users/{uid}` 為 `free` tier
   - 如需批次升級老用戶為 `pro`：之後再寫 migration script

---

> 文件版本：2026-04-29 · 撰寫者：Copilot
