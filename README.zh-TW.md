# 🧚 Navi — AI 智能股票分析助手

[English](README.md)

> _"Hey! Listen!"_ — 你的個人投資分析精靈
>
> 靈感來自《薩爾達傳說：時之笛》中的精靈嚮導 Navi，用 AI 為你導航股海。

⚠️ **免責聲明：本專案僅供學習與研究用途，所有分析結果不構成投資建議。投資有風險，決策請自行判斷。**

---

## ✨ 功能特色

- **AI 對話分析** — 自然語言提問，結合 RAG 知識庫與即時數據，給出附有數據佐證的投資分析（SSE Streaming）
- **技術面分析** — 自動計算 RSI、MACD、KD、均線、布林通道等指標並綜合判斷
- **基本面分析** — PE、PB、ROE、EPS、營收成長等財務比率一覽
- **籌碼面分析** — 串接台灣證交所 API，取得三大法人買賣超與融資融券數據
- **財經新聞** — Google News RSS 即時財經新聞搜尋
- **投資組合追蹤** — 記錄持股、即時計算市值損益，AI 可直接查詢你的持倉狀態
- **策略回測** — 支援均線交叉、RSI、MACD 策略，以歷史數據模擬績效並產出回測報告

---

## 🏗️ 系統架構

```
┌──────────────────┐         ┌───────────────────────────────┐
│  React + Vite    │  REST   │         Cloud Run              │
│  (TypeScript)    │────────▶│       FastAPI Backend          │
│                  │◀────────│                                │
│ Firebase Hosting │   SSE   │  ┌───────────┐ ┌───────────┐  │
│                  │         │  │ LangChain  │ │ 9 Agent   │  │
│                  │         │  │ Agent      │ │ Tools     │  │
└──────────────────┘         │  └─────┬──┬──┘ └─────┬─────┘  │
                             └────────┼──┼──────────┼─────────┘
                                      │  │          │
                        ┌─────────────┘  │          │
                        ▼                ▼          ▼
                ┌──────────────┐  ┌──────────┐  ┌────────────┐
                │  Firestore   │  │ Gemini   │  │ yfinance   │
                │  Vector      │  │ 2.5 Pro  │  │ TWSE API   │
                │  Search      │  │          │  │ Google News│
                │  + Auth      │  └──────────┘  └────────────┘
                └──────────────┘
```

LangChain Agent 可自主選擇以下 9 種工具來回答問題：

| 工具                    | 說明                              |
| ----------------------- | --------------------------------- |
| `get_stock_price`       | 即時股價查詢                      |
| `analyze_technicals`    | 技術指標計算（RSI, MACD, KD, MA） |
| `analyze_fundamentals`  | 基本面財務比率                    |
| `search_knowledge`      | RAG 知識庫向量搜尋                |
| `get_institutional`     | 三大法人買賣超（TWSE API）        |
| `get_margin_trading`    | 融資融券數據                      |
| `search_financial_news` | 財經新聞搜尋                      |
| `get_portfolio`         | 查詢使用者投資組合                |
| `run_strategy_backtest` | 執行策略回測                      |

---

## 🛠️ 技術棧

### 後端

| 類別      | 技術                                      |
| --------- | ----------------------------------------- |
| 語言      | Python 3.12                               |
| Web 框架  | FastAPI                                   |
| AI 框架   | LangChain（Tool-calling Agent）           |
| LLM       | Gemini 2.5 Pro                            |
| Embedding | text-embedding-004                        |
| Vector DB | Firestore Vector Search                   |
| 資料來源  | yfinance · TWSE/OTC API · Google News RSS |

### 前端

| 類別     | 技術                    |
| -------- | ----------------------- |
| 框架     | React 19 + TypeScript   |
| 建構工具 | Vite                    |
| 樣式     | Tailwind CSS            |
| 圖表     | Recharts                |
| 狀態管理 | Zustand                 |
| 認證     | Firebase Authentication |

### 基礎設施

| 類別     | 技術               |
| -------- | ------------------ |
| 後端部署 | Google Cloud Run   |
| 前端部署 | Firebase Hosting   |
| CI/CD    | Google Cloud Build |
| 資料庫   | Firestore          |
| 容器化   | Docker             |

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
│   ├── config.py                # 環境變數管理
│   ├── cli.py                   # CLI 工具（知識庫匯入等）
│   ├── api/routes/              # API 路由
│   │   ├── chat.py              #   AI 對話（SSE Streaming）
│   │   ├── stock.py             #   股票數據
│   │   ├── portfolio.py         #   投資組合 CRUD
│   │   ├── backtest.py          #   策略回測
│   │   └── knowledge.py         #   知識庫管理
│   ├── services/                # 業務邏輯層
│   │   ├── agent_service.py     #   LangChain Agent 核心
│   │   ├── rag_service.py       #   RAG Pipeline
│   │   ├── stock_service.py     #   股票數據（yfinance）
│   │   ├── embedding_service.py #   Embedding 處理
│   │   └── ...                  #   其他服務
│   ├── tools/                   # LangChain Agent Tools（9 種）
│   ├── models/                  # Pydantic Schemas & Prompts
│   ├── knowledge_base/          # 靜態知識文件（Markdown）
│   └── tests/                   # 測試
├── frontend/
│   ├── src/
│   │   ├── pages/               # 頁面（Dashboard, Chat, Stock, Portfolio, Backtest）
│   │   ├── components/          # UI 元件（圖表、Layout 等）
│   │   ├── lib/                 # API Client & Firebase 設定
│   │   └── store/               # Zustand 狀態管理
│   └── firebase.json            # Firebase Hosting 設定
├── docker-compose.yml           # 本地開發容器
├── cloudbuild.yaml              # Cloud Build 部署管線
└── PROPOSAL.md                  # 詳細專案企劃書
```

---

## 📄 License

This project is for personal learning and portfolio demonstration purposes.
