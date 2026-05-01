# 📊 Navi Screener — 智能定時選股系統 Proposal

> **狀態**：Draft v1 · 待 review 後進入實作
> **作者**：Navi 規劃會議產出
> **日期**：2026-04-30
> **範圍**：M1 + M2 + Email 推送（不含 LINE / Web Push / 訂閱管理 UI）

---

## 0. TL;DR

讓 Navi 從「被動回答」進化為「主動推薦」。新增一個**三階段漏斗式選股管線**，
每日 / 每週由 Cloud Scheduler 觸發，產出**兩份策略報告**（Value Hunter + Momentum Rider），
依**約 10 個產業類別**分組呈現，並把報告摘要透過 **Email 寄送**給訂閱者；
前端新增 `/screener` 頁面可切換策略 / 產業 / 歷史日期瀏覽。

每一檔推薦都附 **RAG 引用的理論依據** + **數據佐證** + **目標價區間** + **停損建議** + **信心評分**，
讓使用者看得懂「為什麼推薦」，而非黑箱選股。

---

## 1. 背景與動機

### 1.1 現況痛點

- Navi 目前只能「被動回答」：使用者要先想到要問哪檔股票，AI 才會分析。
- 知識庫（24 篇 / 8 類）+ 9 個分析工具已經很完整，但「使用觸發點」全押在使用者手上。
- 缺少「市場掃描」能力 — 沒辦法主動告訴使用者「今天有哪些值得看的標的」。

### 1.2 新功能價值

| 對使用者                                       | 對專案                                                  |
| ---------------------------------------------- | ------------------------------------------------------- |
| 每天打開 Dashboard 就有當日 / 當週推薦清單     | 從「Chatbot」升級為「投資助理」，差異化明顯             |
| 看到推薦不用自己再去問 — 點進去就有完整 thesis | 既有 9 tools + KB 的 ROI 翻倍（被定時呼叫，而非僅按需） |
| 可訂閱 Email，不用主動打開網頁也能收到報告     | 加入「定時 batch + 推送」場景，技術深度增加             |
| 儀表板可切換策略、依產業瀏覽                   | 為未來「個人化訂閱」「事件驅動推播」鋪路                |

### 1.3 與既有功能的關係

**100% 復用、零重寫**：

- Stage 3 的 LLM 評估直接呼叫 `tools/` 下的 9 個 tool（fundamental / technical / institutional / margin / news / knowledge_search …）
- RAG 直接用 `services/embedding_service.py` + 既有 24 篇 KB 文件
- LLM 用既有的 Vertex AI Gemini 2.5 Pro 配置
- Firestore client 沿用 `services/firestore_client.py`
- 新增的只有 **「呼叫者（orchestrator）+ 排程入口 + 報告儲存模型 + 前端頁面 + Email sender」**

---

## 2. 篩選策略設計

### 2.1 三階段漏斗（避免 LLM 成本爆炸）

```
全市場 ~2,400 檔台股 (TWSE + TPEx)
    │
    ▼  Stage 1 — 量化粗篩（純規則，零 LLM 成本，~10 秒）
    │   ├─ 流動性：20 日均成交額 > 5,000 萬
    │   ├─ 市值：> 50 億（過濾妖股）
    │   └─ 排除：全額交割、處置股、停資停券
    │
    ▼  ~300-500 檔
    │
    ▼  Stage 2 — 多因子打分（規則化，分產業排名，~30 秒）
    │   ├─ 價值面 (Value)：PE 產業百分位、PB、殖利率、PEG
    │   ├─ 動能面 (Momentum)：3M/6M 漲幅、相對大盤強度、量能擴增
    │   ├─ 籌碼面 (Chips)：法人連續買超、融資減融券增、券資比
    │   └─ 品質面 (Quality)：ROE、營收 YoY、毛利率趨勢
    │   → 依 Profile 套用權重 → 各產業取 Top 10
    │
    ▼  ~80-100 檔候選
    │
    ▼  Stage 3 — AI 深度評估（LLM + RAG，並行 8 檔/批，~3-5 分鐘）
    │   ├─ 對每檔呼叫既有 5-6 個 tools 取得完整面向
    │   ├─ search_knowledge 搜尋對應策略理論
    │   ├─ Gemini 2.5 Pro 產出結構化 JSON：
    │   │    thesis / target_price / stop_loss / risks / confidence
    │   └─ 信心評分 ≥ 70 進入最終報告
    │
    ▼  最終報告：每產業 3-5 檔，總計 ~25-35 檔
```

### 2.2 兩份策略 Profile（同時跑、儀表板可切換）

| Profile            | 定位             | Stage 2 因子權重                         | 適合       |
| ------------------ | ---------------- | ---------------------------------------- | ---------- |
| **Value Hunter**   | 找價值低估的標的 | 價值 50% / 品質 30% / 籌碼 15% / 動能 5% | 長線存股   |
| **Momentum Rider** | 找動能突破的標的 | 動能 50% / 籌碼 30% / 品質 15% / 價值 5% | 中短線波段 |

> **設計理由**：兩種策略訊號常常互斥（被低估的多半冷門、有動能的多半已漲一段），
> 同時跑兩份可避免「策略偏食」，使用者也能直觀理解兩種選股哲學的差異。

### 2.3 因子計算細節（Stage 2）

| 因子                        | 計算方式                                   | 資料來源                     |
| --------------------------- | ------------------------------------------ | ---------------------------- |
| **PE 產業百分位**           | 該檔 PE 在所屬產業中的百分位（越低越便宜） | yfinance + 自建產業表        |
| **PB / 殖利率 / PEG**       | 直接從 `stock_service` 取得                | yfinance                     |
| **3M/6M 漲幅**              | 收盤價 vs N 日前                           | yfinance history             |
| **相對大盤強度**            | 個股漲幅 - 加權指數漲幅                    | yfinance                     |
| **量能擴增**                | 5 日均量 / 20 日均量                       | yfinance                     |
| **法人連續買超**            | 近 5/10 日三大法人累積買超天數             | 既有 `institutional_service` |
| **融資減融券增**            | 近 5 日融資減少 + 融券增加                 | 既有 `margin_service`        |
| **ROE / 營收 YoY / 毛利率** | 直接從 `stock_service`                     | yfinance                     |

每個因子先在「**所屬產業內**」做 z-score 標準化，再依 Profile 權重加總 → 0-100 final score。
**「產業內排名」**避免不同產業（如金融 vs 半導體）PE 直接對比的失真問題。

---

## 3. 產業分類設計（約 10 類）

### 3.1 自建分類表（折衷方案）

TWSE 官方分類（28 類）太細，GICS（11 類）對台股不夠貼切。
採用**自建 11 類**（合併 TWSE 細項），與台股投資人習慣一致：

| #   | 自建類別        | 對應 TWSE 細項                             |
| --- | --------------- | ------------------------------------------ |
| 1   | **半導體**      | 半導體業                                   |
| 2   | **電子零組件**  | 電子零組件、光電、其他電子                 |
| 3   | **電腦及週邊**  | 電腦及周邊設備、通信網路                   |
| 4   | **電子製造**    | 電子通路、資訊服務                         |
| 5   | **金融保險**    | 金融保險、證券                             |
| 6   | **傳產製造**    | 鋼鐵、塑膠、化工、橡膠、玻璃陶瓷、紡織纖維 |
| 7   | **航運汽車**    | 航運業、汽車工業                           |
| 8   | **生技醫療**    | 生技醫療業                                 |
| 9   | **民生消費**    | 食品、貿易百貨、觀光餐旅、居家生活         |
| 10  | **建材營造**    | 建材營造、水泥                             |
| 11  | **公用 / 其他** | 油電燃氣、通信業、文化創意、其他           |

**實作**：在 `backend/services/screener/industry_mapper.py` 維護一份 `ticker → industry` JSON / SQLite。
初版可從 [TWSE 上市公司產業類別](https://isin.twse.com.tw/) 一次性匯出後手動 merge，後續每季更新即可。

---

## 4. 系統架構

```
┌──────────────────────────────────────────────────────────────┐
│  Cloud Scheduler                                             │
│   ├─ 每日 06:00 (週一~五) → POST /api/screener/run           │
│   │      body: { profile: "momentum", frequency: "daily" }  │
│   ├─ 每日 06:05 (週一~五) → POST /api/screener/run           │
│   │      body: { profile: "value",    frequency: "daily" }  │
│   ├─ 每週日 20:00 → 同上 (frequency: "weekly")               │
│   └─ 報告完成後 → POST /api/screener/notify  (寄 Email)      │
└────────────────────────┬─────────────────────────────────────┘
                         │ HTTP + OIDC
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  Cloud Run · FastAPI                                         │
│                                                              │
│  api/routes/screener.py                                      │
│   ├─ POST /run               (Scheduler 觸發, OIDC 保護)     │
│   ├─ POST /notify            (寄送 Email)                    │
│   ├─ GET  /reports           (列表)                          │
│   ├─ GET  /reports/latest    (前端首屏)                      │
│   └─ GET  /reports/{id}      (詳情 + picks)                  │
│                       │                                      │
│                       ▼                                      │
│  services/screener/orchestrator.py                          │
│   ├─► UniverseFilter   (Stage 1)                            │
│   ├─► FactorScorer     (Stage 2, 套 Profile 權重)           │
│   └─► AIEvaluator      (Stage 3, 復用 ALL_TOOLS + RAG)      │
│                       │                                      │
│                       ▼                                      │
│  services/screener/email_sender.py                          │
│   └─ 用 SendGrid / Gmail SMTP 寄送 HTML 摘要                │
│                       │                                      │
│                       ▼                                      │
│  Firestore                                                  │
│   ├─ screener_reports/{report_id}                           │
│   │     └─ picks/{ticker}                                   │
│   └─ screener_email_subscribers/{user_id}                   │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│  Frontend  (新頁面 /screener)                                │
│   ├─ 上方：Profile 切換 Tab (Value / Momentum)               │
│   ├─ 上方：日期選擇 (今日 / 歷史)                            │
│   ├─ 中段：產業 Tabs (11 個 chips)                          │
│   ├─ 主體：個股卡片網格 (score / 上行 % / 縮圖 thesis)      │
│   ├─ 點擊卡片 → Drawer 顯示完整 thesis + KB 引用 + CTA       │
│   │            CTA「丟到 Chat 深入問」→ prefill 既有 chat    │
│   └─ 設定區：Email 訂閱 toggle (寫入 subscribers 集合)       │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. 資料模型（Firestore）

### 5.1 `screener_reports/{report_id}`

`report_id` 格式：`{YYYYMMDD}-{frequency}-{profile}` 例如 `20260501-daily-momentum`

```jsonc
{
  "report_id": "20260501-daily-momentum",
  "generated_at": "2026-05-01T06:15:32+08:00",
  "profile": "momentum",         // value | momentum
  "frequency": "daily",          // daily | weekly
  "universe_size": 2438,
  "stage1_passed": 412,
  "stage2_passed": 87,
  "final_count": 28,
  "industries_covered": ["半導體", "電子零組件", "金融保險", ...],
  "market_summary": "今日加權指數 +0.8% 收 21,450...",  // LLM 一段總覽
  "cost_usd": 0.42,              // Stage 3 LLM 成本（監控用）
  "duration_seconds": 287,
  "status": "completed"          // running | completed | failed
}
```

### 5.2 `screener_reports/{report_id}/picks/{ticker}`

```jsonc
{
  "ticker": "2330.TW",
  "name": "台積電",
  "industry": "半導體",
  "rank_in_industry": 1,
  "factor_scores": {
    "value": 65,
    "momentum": 88,
    "chips": 92,
    "quality": 80,
    "final": 84,
  },
  "snapshot": {
    "price": 1085,
    "change_pct": 1.2,
    "pe": 22.5,
    "pb": 5.8,
    "roe": 0.27,
    "yield": 0.018,
    "rsi": 62,
    "ma_alignment": "多頭排列",
    "foreign_buy_5d_lots": 12500,
    "margin_change_5d_pct": -3.2,
  },
  "thesis": "根據知識庫的『動量策略』理論...（300-500 字 LLM 產出）",
  "kb_citations": [
    "investment_theory/momentum_strategy.md",
    "technical_analysis/moving_averages.md",
  ],
  "target_price": { "low": 1180, "mid": 1250, "high": 1320 },
  "upside_pct": 15.2,
  "stop_loss": 1020,
  "risk_reward_ratio": 2.8,
  "risks": ["匯率波動", "客戶集中度", "AI 需求若放緩"],
  "confidence": 78, // 0-100
}
```

### 5.3 `screener_email_subscribers/{user_id}`

```jsonc
{
  "user_id": "firebase_uid_xxx",
  "email": "user@example.com",
  "enabled": true,
  "profiles": ["value", "momentum"], // 訂閱哪些策略
  "frequency": ["daily", "weekly"], // 訂閱頻率
  "industries_filter": [], // 空陣列 = 全部；後續可加產業過濾
  "created_at": "...",
  "updated_at": "...",
}
```

---

## 6. 程式碼結構（新增 / 修改檔案）

### 6.1 後端

```
backend/
├── services/
│   └── screener/                      ← 新模組
│       ├── __init__.py
│       ├── orchestrator.py            # 主流程串接 Stage 1-3
│       ├── universe.py                # Stage 1: 全清單載入 + 流動性過濾
│       ├── factor_scorer.py           # Stage 2: 多因子計算 + Profile 權重
│       ├── ai_evaluator.py            # Stage 3: 並行呼叫 LLM + tools
│       ├── prompts.py                 # Stage 3 評估 prompt（XML schema）
│       ├── industry_mapper.py         # ticker → 11 類產業
│       ├── industry_data.json         # 自建分類表（一次性匯入）
│       ├── email_sender.py            # SendGrid / SMTP 包裝
│       └── email_template.html        # HTML 報告模板
│
├── api/routes/
│   └── screener.py                    # 新 router
│
├── models/
│   └── schemas.py                     # 新增 Pydantic models
│
└── tests/
    ├── test_screener_universe.py
    ├── test_screener_factor.py
    ├── test_screener_ai_evaluator.py  # mock LLM
    ├── test_screener_email.py         # mock SMTP
    └── test_screener_api.py

scripts/
├── run_screener_local.py              # 本地手動觸發 (debug)
├── seed_industry_mapping.py           # 一次性建 industry_data.json
└── setup_screener_scheduler.sh        # 建立 Cloud Scheduler jobs
```

### 6.2 前端

```
frontend/src/
├── pages/
│   └── Screener.tsx                   # 主頁面
├── components/
│   └── screener/
│       ├── ProfileTabs.tsx
│       ├── IndustryChips.tsx
│       ├── PickCard.tsx
│       ├── PickDetailDrawer.tsx
│       └── EmailSubscribeToggle.tsx
├── lib/
│   └── api/screener.ts                # API client
└── types/
    └── screener.ts                    # TS types (對應後端 schemas)
```

### 6.3 修改既有檔案

| 檔案                                          | 修改                                           |
| --------------------------------------------- | ---------------------------------------------- |
| `backend/main.py`                             | 註冊 `screener.router`                         |
| `backend/config.py`                           | 新增 `SENDGRID_API_KEY` / `EMAIL_FROM_ADDRESS` |
| `backend/pyproject.toml`                      | 新增 `sendgrid` 或 `aiosmtplib`                |
| `frontend/src/App.tsx`                        | 加 `/screener` route                           |
| `frontend/src/components/Sidebar.tsx`（若有） | 新增「📊 選股報告」入口                        |
| `cloudbuild.yaml`                             | （無需改動，部署既有流程）                     |

---

## 7. API 設計

| Method | Path                                               | Auth             | 用途                                           |
| ------ | -------------------------------------------------- | ---------------- | ---------------------------------------------- |
| `POST` | `/api/screener/run`                                | OIDC (Scheduler) | 觸發跑一份報告                                 |
| `POST` | `/api/screener/notify`                             | OIDC (Scheduler) | 報告完成後寄 Email                             |
| `GET`  | `/api/screener/reports`                            | Firebase Auth    | 列表（分頁；可 filter profile/frequency/date） |
| `GET`  | `/api/screener/reports/latest`                     | Firebase Auth    | `?profile=momentum` 取最新                     |
| `GET`  | `/api/screener/reports/{report_id}`                | Firebase Auth    | 詳情 + 所有 picks                              |
| `GET`  | `/api/screener/reports/{report_id}/picks/{ticker}` | Firebase Auth    | 單檔詳情                                       |
| `GET`  | `/api/screener/subscriptions`                      | Firebase Auth    | 取自己的訂閱設定                               |
| `PUT`  | `/api/screener/subscriptions`                      | Firebase Auth    | 更新訂閱設定                                   |

### Request / Response 範例

**`POST /api/screener/run`**

```jsonc
// Request
{ "profile": "momentum", "frequency": "daily" }

// Response (202 Accepted, 因為 Stage 3 需 3-5 分鐘)
{ "report_id": "20260501-daily-momentum", "status": "running" }
```

**`GET /api/screener/reports/latest?profile=momentum`**

```jsonc
{
  "report": { /* screener_reports doc */ },
  "picks_by_industry": {
    "半導體": [ /* StockPick */, ... ],
    "電子零組件": [...],
    ...
  }
}
```

---

## 8. 前端 UX 設計

### 8.1 頁面結構（`/screener`）

```
┌─────────────────────────────────────────────────────────────┐
│  📊 Navi 選股報告                          [📧 Email 訂閱 ▢] │
├─────────────────────────────────────────────────────────────┤
│  策略：[ Value Hunter ] [ Momentum Rider* ]                 │
│  日期：[ 2026-05-01 ▼ ]   頻率：[ 日報 ] [ 週報 ]           │
├─────────────────────────────────────────────────────────────┤
│  📍 今日市場：加權指數 +0.8% 收 21,450，成交 3,820 億...    │
├─────────────────────────────────────────────────────────────┤
│  產業：[ 全部 ] [半導體•5] [電子零組件•4] [金融•3] ...      │
├─────────────────────────────────────────────────────────────┤
│  ┌────────────┐ ┌────────────┐ ┌────────────┐             │
│  │ 2330 台積電 │ │ 2454 聯發科│ │ 3034 聯詠 │             │
│  │ 半導體 #1  │ │ 半導體 #2  │ │ 半導體 #3  │             │
│  │ 1085 +1.2% │ │ 1240 +0.8% │ │ 552 +2.1% │             │
│  │ ⭐ 84      │ │ ⭐ 79      │ │ ⭐ 76      │             │
│  │ 上行 +15%  │ │ 上行 +12%  │ │ 上行 +18%  │             │
│  │ 動能突破...│ │ ...         │ │ ...         │             │
│  └────────────┘ └────────────┘ └────────────┘             │
│  ┌────────────┐ ┌────────────┐ ...                         │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 點擊卡片 → Drawer（右側滑出）

```
┌──────────────────── Drawer ────────────────────┐
│ 2330 台積電  半導體  ⭐ 84                     │
│                                                │
│ 📈 即時數據                                    │
│   價格 1,085 (+1.2%)  PE 22.5  ROE 27%        │
│   RSI 62  MA 多頭排列  外資連 5 日買超         │
│                                                │
│ 💡 推薦理由（thesis）                          │
│   根據知識庫的「動量策略」...                  │
│   [📚 引用：momentum_strategy.md]              │
│   [📚 引用：moving_averages.md]                │
│                                                │
│ 🎯 目標價區間                                  │
│   保守 1,180 / 中估 1,250 / 樂觀 1,320         │
│   上行空間 +15.2%                              │
│                                                │
│ 🛡️ 風險與停損                                  │
│   停損價 1,020 (-6.0%)  風報比 2.8             │
│   ⚠️ 匯率波動、客戶集中度、AI 需求若放緩       │
│                                                │
│ [💬 在 Chat 深入問此檔]  [📊 跑回測]           │
│                                                │
│ ⚠️ 本資訊僅供研究，不構成投資建議              │
└────────────────────────────────────────────────┘
```

### 8.3 Email 訂閱設定（簡版）

首版只要一個 toggle：開啟後預設訂閱「兩個策略 × 兩個頻率」全部寄送。
進階過濾（依產業 / 只訂某策略）放 M3 之後。

---

## 9. Email 設計

### 9.1 寄送時機 / 內容

- Cloud Scheduler 在報告產生後 5 分鐘觸發 `/api/screener/notify`
- 對所有 `enabled=true` 且 `profile`/`frequency` 命中的訂閱者寄送
- HTML 模板包含：
  - Header：Navi logo + 報告類型 + 日期
  - Market Summary（一段）
  - 各產業 Top 3（共 ~15-20 檔）的縮圖卡片（ticker / score / 上行 / 一句 thesis）
  - 「查看完整報告」按鈕 → 連回 `/screener`
  - 退訂連結（一鍵把 `enabled` 設為 `false`）
  - ⚠️ 免責聲明

### 9.2 技術選型

| 選項                        | 優                                   | 缺                          | 決議             |
| --------------------------- | ------------------------------------ | --------------------------- | ---------------- |
| **SendGrid**                | 100 封/日 免費、API 簡單、有 webhook | 需註冊外部服務              | **採用**（首選） |
| Gmail SMTP via App Password | 零成本、Google 生態                  | 500 封/日上限、易被列為垃圾 | 備案             |
| Cloud Tasks + Mailgun       | 可量大                               | 設定複雜                    | 量大時再升級     |

> 個人專案規模 SendGrid 免費額度足夠（每日報告 ≤ 50 訂閱者 × 4 種報告 = 200 封 < 100×4=400）。

### 9.3 防濫用 / 退訂合規

- 每封 Email 帶獨立的 `unsubscribe_token`（HMAC 簽名 user_id）
- 退訂連結為 `GET /api/screener/unsubscribe?token=...`（無需登入）
- 寄送失敗 3 次自動停用該訂閱

---

## 10. 排程配置

### 10.1 Cloud Scheduler Jobs

```yaml
# 早盤前產出，使用者通勤時就能看
- screener-daily-momentum:    "0 6 * * 1-5"   Asia/Taipei
- screener-daily-value:       "5 6 * * 1-5"   Asia/Taipei
- screener-weekly-momentum:   "0 20 * * 0"    Asia/Taipei  # 週日晚
- screener-weekly-value:      "5 20 * * 0"    Asia/Taipei

# 報告完成後 5 分鐘寄 Email
- screener-notify-daily:      "10 6 * * 1-5"  Asia/Taipei
- screener-notify-weekly:     "10 20 * * 0"   Asia/Taipei
```

每個 job 用 OIDC token 認證，invoker SA 限定為 Cloud Run service account。

---

## 11. 成本估算

| 項目                                | 量 / 計算                                                       | 月成本 (USD)     |
| ----------------------------------- | --------------------------------------------------------------- | ---------------- |
| **Stage 3 LLM**                     | 90 檔 × 3K tokens × Gemini 2.5 Pro × 4 報告/日 × 22 日 + 4 週報 | **$50-70**       |
| **Embedding** (KB 已預嵌，僅 query) | 可忽略                                                          | < $1             |
| **Cloud Run**                       | Stage 3 約 5 分鐘 × ~120 次/月，2 vCPU                          | **$3-5**         |
| **Firestore**                       | 報告寫入 ~30 picks × 120 次 + 讀取                              | **$1-2**         |
| **SendGrid**                        | < 100/日 免費額度內                                             | **$0**           |
| **Cloud Scheduler**                 | < 10 jobs (前 3 個免費)                                         | **< $1**         |
| **總計**                            |                                                                 | **~$55-80 / 月** |

> 若想壓低：Stage 3 改用 Gemini 2.5 Flash → 成本 $5-10/月；可作為 fallback。
> 建議：上線首月用 Pro 確認品質，第二個月起做 A/B 比較看是否能降級。

---

## 12. 合規與安全

- **沿用既有規範**：所有 thesis 走既有 prompt 規範（禁止「保證獲利」「必漲」等字眼），底部必加 ⚠️ 免責聲明
- **目標價標註**：一律顯示「估算值非承諾」浮水印
- **Email 必含**：免責聲明 + 退訂連結（CAN-SPAM / GDPR 友善）
- **API 認證**：
  - `/run`、`/notify` → Cloud Scheduler OIDC
  - 其餘 → Firebase Auth ID token（既有 middleware）
- **Rate Limit**：`/run` 加 dedup（同一 `report_id` 已存在則回 409）

---

## 13. 風險與待釐清

| 風險                  | 影響                              | 緩解                                                                                                      |
| --------------------- | --------------------------------- | --------------------------------------------------------------------------------------------------------- |
| yfinance 台股財報延遲 | 中小型股 PE/ROE 可能舊 1-2 季     | 後續可從公開資訊觀測站補；MVP 接受此誤差                                                                  |
| Vertex AI RPM quota   | Stage 3 並行可能撞限制            | `asyncio.Semaphore(8)`；超量自動降級 Flash                                                                |
| LLM 數字幻覺          | thesis 內出現未經 tool 驗證的數字 | Stage 3 用 structured output（Pydantic）強制只輸出 schema 內欄位；數字一律從 snapshot 取，不允許 LLM 自填 |
| 自建產業表維護        | 上市新股需更新                    | `seed_industry_mapping.py` 設成季更，新股在 industry_mapper 找不到時 fallback 到「公用 / 其他」           |
| 報告品質              | 上線初期 thesis 可能空泛          | 首兩週人工 review 50% 樣本，調 prompt                                                                     |
| Email 寄信失敗        | 訂閱者收不到                      | SendGrid webhook 收 bounce 事件 → 標記停用                                                                |

---

## 14. 路線圖（M1 + M2 + Email 範圍 = 本次提案）

| 階段     | 範圍                        | 交付物                   | 驗收標準                                         |
| -------- | --------------------------- | ------------------------ | ------------------------------------------------ |
| **M1.1** | Industry mapper + Stage 1+2 | 規則化排名能跑出 CSV     | 對 100 檔抽樣，產業分類正確率 > 95%              |
| **M1.2** | Stage 3 + Firestore 寫入    | 完整報告寫入 Firestore   | 一份報告可在 Firestore Console 看到 ~30 個 picks |
| **M1.3** | Cloud Scheduler 串接        | 每日自動跑兩份報告       | 連續 3 個工作日成功產報、無異常                  |
| **M2.1** | API + 前端頁面骨架          | `/screener` 可瀏覽報告   | UX 走查通過                                      |
| **M2.2** | Drawer + Chat 整合          | 點卡片可跳到 Chat 深入問 | E2E test 過                                      |
| **M2.3** | Email Sender + 訂閱         | HTML 報告 Email 寄出     | 收到信並可一鍵退訂                               |

> 每個 milestone 結束後做一次 mini retrospective，再決定是否進下一階段。

### 後續迭代（不在本次範圍）

- M3：個人化（依產業偏好過濾、訂閱單一策略）
- M4：把過往 picks 餵 `backtest_tool` 自動回測，量化策略勝率
- M5：事件驅動推播（突發新聞 / 法人異常即時 candidate）

---

## 15. 待你最終確認

1. **Email 服務**：SendGrid 還是 Gmail SMTP？（SendGrid 比較穩，需註冊；Gmail 比較快）
2. **產業分類表**：第 3 章列的 11 類分法 OK 嗎？要加 / 拿掉哪類？
3. **報告排程時間**：建議的早上 6:00（台股開盤前 3 小時）合適嗎？還是想改 7:30？
4. **首批訂閱者**：上線時要先把你自己的 Email 寫死進 seed 還是直接走 UI 訂閱流程？

確認後即可進入 M1.1 實作。
