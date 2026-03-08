# 🧚 Navi — AI 智能股票分析助手

[English](README.md)

> _"Hey! Listen!"_ — 你的個人投資分析精靈
>
> 靈感來自《薩爾達傳說：時之笛》中的精靈嚮導 Navi，用 AI 為你導航股海。

⚠️ **免責聲明：本專案僅供學習與研究用途，所有分析結果不構成投資建議。投資有風險，決策請自行判斷。**

---

## ✨ 功能特色

- **AI 對話分析** — 自然語言提問，意圖分類器自動路由至最佳回應模式（Prefetch 平行工具 或 Agent 自主決策），結合 RAG 知識庫與即時數據，透過 SSE Streaming 產出分析
- **智慧意圖分類** — LLM 分類器支援 10 種意圖類別與信心度評分；低信心度自動 fallback 至完整 Agent 模式
- **中文股票名稱解析** — 動態串接 TWSE + TPEx API，支援中文名稱 → 代碼查詢（~2,400 檔股票，24 小時快取）
- **技術面分析** — RSI、MACD、KD、均線、布林通道、費波那契回撤、5 源支撐壓力位（均線、布林、波段高低點、Fibonacci、心理關卡），以及自動計算停損與風險報酬比
- **基本面分析** — PE、PB、ROE、EPS、營收成長，以及 3 層級公平價位估算（便宜價/合理價/昂貴價，基於 PE 百分位 × EPS）
- **籌碼面分析** — 三大法人（外資、投信、自營商）買賣超追蹤，以及融資融券數據（餘額、使用率、資券互抵）
- **財經新聞** — Google News RSS 即時財經新聞搜尋
- **投資組合追蹤** — 記錄持股、即時計算市值損益與持股佔比，AI 可直接查詢你的持倉狀態
- **策略回測** — 支援均線交叉、RSI、MACD 及自訂條件策略；完整績效報告（報酬率、夏普比率、最大回撤、勝率）
- **對話歷史** — 多輪對話以使用者為單位持久化至 Firestore，支援歷史訊息載入

---

## 🏗️ 系統架構

```
┌──────────────────┐         ┌─────────────────────────────────────────┐
│  React + Vite    │  REST   │              Cloud Run                   │
│  (TypeScript)    │────────▶│           FastAPI Backend                │
│                  │◀────────│                                          │
│ Firebase Hosting │   SSE   │  ┌────────────┐                         │
│                  │         │  │  意圖分類器  │ ── 信心度 < 0.7 ──────┐│
│                  │         │  │  Classifier │                       ││
│                  │         │  └──────┬─────┘                        ││
│                  │         │   Prefetch │ 意圖             Agent    ││
│                  │         │         ▼                     模式     ││
│                  │         │  ┌────────────┐        ┌────────────┐  ││
│                  │         │  │  平行工具   │        │ LangChain  │◀─┘│
│                  │         │  │  執行       │        │ AgentExec  │   │
│                  │         │  └──────┬─────┘        └──────┬─────┘   │
│                  │         │         └──────────┬───────────┘         │
│                  │         │                    ▼                     │
│                  │         │            ┌──────────────┐              │
│                  │         │            │  9 種 Agent  │              │
│                  │         │            │  工具         │              │
└──────────────────┘         │            └──────┬───────┘              │
                             └───────────────────┼─────────────────────┘
                                                 │
                    ┌────────────────┬────────────┼────────────┐
                    ▼                ▼            ▼            ▼
            ┌──────────────┐ ┌──────────┐ ┌────────────┐ ┌──────────┐
            │  Firestore   │ │ Gemini   │ │ yfinance   │ │ TWSE/TPEx│
            │  Vector      │ │ 2.5 Pro  │ │            │ │ Open API │
            │  Search      │ └──────────┘ └────────────┘ ├──────────┤
            │  + Auth      │                              │Google    │
            │  + 對話歷史   │                              │News RSS  │
            └──────────────┘                              └──────────┘
```

### 雙模式分派

**意圖分類器**分析每個使用者問題（10 種類別，附信心度評分），路由至兩種模式之一：

- **Prefetch 模式** — 針對明確意圖（例如：進場分析、全面分析）：平行呼叫所有所需工具，再以結構化 Chain-of-Thought 提示彙整結果，延遲更低
- **Agent 模式** — 針對開放式或低信心度的問題：由 LangChain `AgentExecutor` 自主決定呼叫哪些工具，彈性更高

### 9 種 Agent 工具

| 工具                    | 說明                                                            |
| ----------------------- | --------------------------------------------------------------- |
| `get_stock_price`       | 即時股價、漲跌幅、成交量、市值                                  |
| `analyze_technicals`    | MA、RSI、MACD、KD、布林通道、Fibonacci 回撤、支撐壓力、停損建議 |
| `analyze_fundamentals`  | PE、PB、ROE、EPS、成長率、3 層級公平價位（便宜/合理/昂貴）      |
| `search_knowledge`      | 對 13 份投資知識文件進行 RAG 向量搜尋（取 top-5）               |
| `get_institutional`     | 外資、投信、自營商買賣超數據（TWSE/OTC API）                    |
| `get_margin_trading`    | 融資融券餘額、使用率、資券互抵                                  |
| `search_financial_news` | Google News RSS 財經新聞搜尋                                    |
| `get_portfolio`         | 使用者投資組合（含即時損益與持股佔比分析）                      |
| `run_strategy_backtest` | 均線交叉 / RSI / MACD / 自訂條件策略回測                        |

---

## 🛠️ 技術棧

### 後端

| 類別      | 技術                                      |
| --------- | ----------------------------------------- |
| 語言      | Python 3.12                               |
| Web 框架  | FastAPI 0.115+                            |
| AI 框架   | LangChain 0.3+（Tool-calling Agent）      |
| LLM       | Gemini 2.5 Pro（透過 Vertex AI）          |
| Embedding | text-embedding-004（768 維向量）          |
| Vector DB | Firestore Vector Search                   |
| 資料來源  | yfinance · TWSE/OTC API · Google News RSS |

### 前端

| 類別     | 技術                    |
| -------- | ----------------------- |
| 框架     | React 19 + TypeScript   |
| 建構工具 | Vite 7                  |
| 樣式     | Tailwind CSS 4          |
| 圖表     | Recharts                |
| 路由     | React Router DOM 7      |
| 狀態管理 | Zustand                 |
| 認證     | Firebase Authentication |

### 基礎設施

| 類別     | 技術                              |
| -------- | --------------------------------- |
| 後端部署 | Google Cloud Run（asia-east1）    |
| 前端部署 | Firebase Hosting（CDN + headers） |
| CI/CD    | Google Cloud Build                |
| 資料庫   | Firestore                         |
| 容器化   | Docker                            |

---

## 📡 API 端點

| 路徑                                    | 方法       | 說明                   | 認證 |
| --------------------------------------- | ---------- | ---------------------- | ---- |
| `/api/chat`                             | POST       | SSE 串流對話           | ✓    |
| `/api/chat/conversations`               | GET        | 列出使用者對話         | ✓    |
| `/api/chat/conversations/{id}/messages` | GET        | 取得對話歷史訊息       | ✓    |
| `/api/chat/conversations/{id}`          | DELETE     | 刪除對話               | ✓    |
| `/api/stock/{ticker}`                   | GET        | 股票概覽（價格、漲跌） | ✓    |
| `/api/stock/{ticker}/technical`         | GET        | 技術指標分析           | ✓    |
| `/api/stock/{ticker}/fundamental`       | GET        | 基本面分析 + 公平價    | ✓    |
| `/api/portfolio`                        | GET        | 投資組合（含即時損益） | ✓    |
| `/api/portfolio/holdings`               | GET/POST   | 查看 / 新增持股        | ✓    |
| `/api/portfolio/holdings/{id}`          | PUT/DELETE | 修改 / 刪除持股        | ✓    |
| `/api/backtest`                         | POST       | 執行策略回測           | ✓    |
| `/api/backtest/strategies`              | GET        | 列出可用策略           | ✓    |
| `/api/knowledge/stats`                  | GET        | 知識庫統計             | ✓    |
| `/health`                               | GET        | 健康檢查               | ✗    |

---

## 🚀 快速開始

### 前置需求

- **Python 3.12+** 與 [uv](https://docs.astral.sh/uv/) 套件管理工具
- **Node.js 20+** 與 npm
- **Google Cloud 專案**（已啟用 Firestore、Vertex AI）
- **Firebase 專案**（已啟用 Authentication）
- **Service Account JSON**（具備 Firestore 與 Vertex AI 權限）

### 後端

```bash
cd backend

# 安裝依賴
uv sync

# 設定環境變數
cp .env.example .env
# 編輯 .env，填入你的 Google Cloud Project ID 等設定

# 放入 Service Account 金鑰
mkdir -p .secrets
cp /path/to/your/service-account.json .secrets/service-account.json

# 匯入知識庫文件到 Firestore
uv run python cli.py ingest

# 啟動開發伺服器
uv run uvicorn main:app --reload --port 8000
```

### 前端

```bash
cd frontend

# 安裝依賴
npm install

# 設定 Firebase（在 src/lib/firebase.ts 填入你的 Firebase config）

# 啟動開發伺服器
npm run dev
```

### Docker（一鍵啟動後端）

```bash
docker compose up --build
```

### 執行測試

```bash
cd backend
uv sync                    # 安裝依賴（含開發工具）
uv run pytest tests/       # 執行所有測試
uv run pytest tests/test_stock_service.py -v  # 執行特定測試檔案
```

### 環境變數

| 變數                             | 說明                        | 預設值               |
| -------------------------------- | --------------------------- | -------------------- |
| `GOOGLE_CLOUD_PROJECT`           | Google Cloud 專案 ID        | —                    |
| `GOOGLE_APPLICATION_CREDENTIALS` | Service Account JSON 路徑   | —                    |
| `GEMINI_MODEL_NAME`              | LLM 模型名稱                | `gemini-2.5-pro`     |
| `EMBEDDING_MODEL_NAME`           | Embedding 模型              | `text-embedding-004` |
| `AUTH_REQUIRED`                  | 是否啟用 JWT 驗證           | `true`               |
| `CORS_ORIGINS`                   | 允許的跨域來源（逗號分隔）  | —                    |
| `DEBUG`                          | 除錯模式（開啟 Swagger UI） | `false`              |

---

## 📁 專案結構

```
navi/
├── backend/
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                # 環境變數管理（pydantic-settings）
│   ├── cli.py                   # CLI 工具（知識庫匯入等）
│   ├── api/routes/              # API 路由
│   │   ├── chat.py              #   AI 對話（SSE Streaming）
│   │   ├── stock.py             #   股票數據與分析
│   │   ├── portfolio.py         #   投資組合 CRUD
│   │   ├── backtest.py          #   策略回測
│   │   └── knowledge.py         #   知識庫管理
│   ├── services/                # 業務邏輯層
│   │   ├── agent_service.py     #   LangChain Agent + 意圖分類 + Prefetch
│   │   ├── conversation_service.py # 多輪對話歷史（Firestore）
│   │   ├── rag_service.py       #   RAG Pipeline
│   │   ├── stock_service.py     #   股票數據（yfinance）+ 代碼解析
│   │   ├── embedding_service.py #   Embedding 處理
│   │   ├── backtest_service.py  #   回測引擎
│   │   ├── institutional_service.py # TWSE/OTC 法人數據
│   │   ├── margin_service.py    #   融資融券數據
│   │   ├── news_service.py      #   Google News RSS
│   │   ├── portfolio_service.py #   投資組合管理
│   │   └── firestore_client.py  #   Firestore Client 單例
│   ├── tools/                   # LangChain Agent Tools（9 種）
│   ├── models/                  # Pydantic Schemas & Prompt Templates
│   ├── knowledge_base/          # 靜態知識文件（13 份 Markdown）
│   │   ├── technical_analysis/  #   RSI、MACD、KD、MA、BB、K 線型態等
│   │   ├── fundamental_analysis/#   財務比率、財報解讀、估值方法等
│   │   └── investment_theory/   #   風險管理
│   ├── data_pipeline/           # 知識庫匯入管線
│   └── tests/                   # Pytest 測試
├── frontend/
│   ├── src/
│   │   ├── pages/               # Dashboard、Chat、Stock、Portfolio、Backtest、Login
│   │   ├── components/          # Layout、PriceChart、RsiChart、StatCard 等
│   │   ├── lib/                 # API Client & Firebase 設定
│   │   └── store/               # Zustand（auth + theme）
│   └── firebase.json            # Firebase Hosting 設定（rewrites、headers、cache）
├── docker-compose.yml           # 本地開發容器
├── cloudbuild.yaml              # Cloud Build → Cloud Run 部署
├── cloudbuild-ingest.yaml       # Cloud Build → 知識庫匯入
├── cloudbuild-test.yaml         # Cloud Build → 測試管線
├── scripts/
│   ├── deploy.sh                # 手動部署腳本（Artifact Registry → Cloud Run）
│   └── setup_trigger.sh         # Cloud Build 觸發器設定
├── PROPOSAL.md                  # 詳細專案企劃書
└── CHANGELOG.md                 # 版本變更記錄
```

---

## 📄 License

This project is for personal learning and portfolio demonstration purposes.
