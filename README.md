# 🧚 Navi — AI-Powered Stock Analyzer

[繁體中文](README.zh-TW.md)

> _"Hey! Listen!"_ — Your personal investment analysis fairy.
>
> Inspired by Navi, the fairy guide from _The Legend of Zelda: Ocarina of Time_,
> this AI assistant navigates you through the stock market.

⚠️ **Disclaimer: This project is for learning and research purposes only. All analysis results do not constitute investment advice. Invest at your own risk.**

---

## ✨ Features

- **AI Chat Analysis** — Ask questions in natural language; an intent classifier auto-routes to the optimal response mode (Prefetch parallel tools or Agent autonomous decision), combining RAG knowledge base with real-time data via SSE Streaming
- **Smart Intent Classification** — LLM-based classifier with 10 intent categories and confidence scoring; low-confidence queries auto-fallback to full Agent mode
- **Chinese Stock Name Resolution** — Dynamically resolves Chinese company names to ticker codes via TWSE + TPEx APIs (~2,400 stocks, 24h cache)
- **Technical Analysis** — RSI, MACD, KD, moving averages, Bollinger Bands, Fibonacci retracement, 5-source support/resistance levels (MA, Bollinger, swing points, Fibonacci, psychological levels), and auto-calculated stop-loss with risk/reward ratio
- **Fundamental Analysis** — PE, PB, ROE, EPS, revenue growth, and 3-tier fair value estimation (cheap / fair / expensive based on PE percentile × EPS)
- **Institutional Tracking** — Integrates with TWSE/OTC APIs to fetch institutional investor (foreign, investment trust, dealer) buy/sell data and margin trading info (balance, utilization rate, margin offset)
- **Financial News** — Real-time financial news search via Google News RSS
- **Portfolio Tracking** — Record holdings, compute real-time market value, P/L & allocation percentage; the AI agent can query your positions directly
- **Strategy Backtesting** — Supports MA crossover, RSI, MACD, and custom condition strategies; simulates historical performance with full metrics (return, Sharpe ratio, max drawdown, win rate)
- **Conversation History** — Multi-turn conversations persisted per-user in Firestore with full history retrieval API

---

## 🏗️ Architecture

```
┌──────────────────┐         ┌─────────────────────────────────────────┐
│  React + Vite    │  REST   │              Cloud Run                   │
│  (TypeScript)    │────────▶│           FastAPI Backend                │
│                  │◀────────│                                          │
│ Firebase Hosting │   SSE   │  ┌────────────┐                         │
│                  │         │  │  Intent     │ ── confidence < 0.7 ──┐│
│                  │         │  │  Classifier │                       ││
│                  │         │  └──────┬─────┘                        ││
│                  │         │    Prefetch │ intents          Agent    ││
│                  │         │         ▼                     mode     ││
│                  │         │  ┌────────────┐        ┌────────────┐  ││
│                  │         │  │  Parallel   │        │ LangChain  │◀─┘│
│                  │         │  │  Tool Exec  │        │ AgentExec  │   │
│                  │         │  └──────┬─────┘        └──────┬─────┘   │
│                  │         │         └──────────┬───────────┘         │
│                  │         │                    ▼                     │
│                  │         │            ┌──────────────┐              │
│                  │         │            │  9 Agent     │              │
│                  │         │            │  Tools       │              │
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
            │  + History   │                              │News RSS  │
            └──────────────┘                              └──────────┘
```

### Dual-Mode Dispatch

The **Intent Classifier** analyzes each user question (10 categories, with confidence scoring) and routes to one of two modes:

- **Prefetch Mode** — For well-defined intents (e.g. entry analysis, comprehensive analysis): runs all required tools in parallel, then synthesizes results with a structured Chain-of-Thought prompt. Lower latency.
- **Agent Mode** — For open-ended or low-confidence queries: LangChain `AgentExecutor` autonomously decides which tools to call. More flexible.

### 9 Agent Tools

| Tool                    | Description                                                                              |
| ----------------------- | ---------------------------------------------------------------------------------------- |
| `get_stock_price`       | Real-time stock price, change %, volume, market cap                                      |
| `analyze_technicals`    | MA, RSI, MACD, KD, Bollinger Bands, Fibonacci retracement, support/resistance, stop-loss |
| `analyze_fundamentals`  | PE, PB, ROE, EPS, growth rates, 3-tier fair value (cheap/fair/expensive)                 |
| `search_knowledge`      | RAG vector search across 13 investment knowledge documents (top-5 results)               |
| `get_institutional`     | Foreign, investment trust, dealer buy/sell data (TWSE/OTC API)                           |
| `get_margin_trading`    | Margin balance, utilization rate, short selling, margin offset                           |
| `search_financial_news` | Financial news via Google News RSS                                                       |
| `get_portfolio`         | User portfolio with real-time P/L and allocation breakdown                               |
| `run_strategy_backtest` | Backtest with MA crossover / RSI / MACD / custom strategies                              |

---

## 🛠️ Tech Stack

### Backend

| Category      | Technology                                |
| ------------- | ----------------------------------------- |
| Language      | Python 3.12                               |
| Web Framework | FastAPI 0.115+                            |
| AI Framework  | LangChain 0.3+ (Tool-calling Agent)       |
| LLM           | Gemini 2.5 Pro (via Vertex AI)            |
| Embedding     | text-embedding-004 (768 dimensions)       |
| Vector DB     | Firestore Vector Search                   |
| Data Sources  | yfinance · TWSE/OTC API · Google News RSS |

### Frontend

| Category         | Technology              |
| ---------------- | ----------------------- |
| Framework        | React 19 + TypeScript   |
| Build Tool       | Vite 7                  |
| Styling          | Tailwind CSS 4          |
| Charts           | Recharts                |
| Routing          | React Router DOM 7      |
| State Management | Zustand                 |
| Auth             | Firebase Authentication |

### Infrastructure

| Category         | Technology                       |
| ---------------- | -------------------------------- |
| Backend Hosting  | Google Cloud Run (asia-east1)    |
| Frontend Hosting | Firebase Hosting (CDN + headers) |
| CI/CD            | Google Cloud Build               |
| Database         | Firestore                        |
| Containerization | Docker                           |

---

## 📡 API Endpoints

| Path                                    | Method     | Description                     | Auth |
| --------------------------------------- | ---------- | ------------------------------- | ---- |
| `/api/chat`                             | POST       | SSE streaming chat              | ✓    |
| `/api/chat/conversations`               | GET        | List user conversations         | ✓    |
| `/api/chat/conversations/{id}/messages` | GET        | Get conversation history        | ✓    |
| `/api/chat/conversations/{id}`          | DELETE     | Delete a conversation           | ✓    |
| `/api/stock/{ticker}`                   | GET        | Stock overview (price, change)  | ✓    |
| `/api/stock/{ticker}/technical`         | GET        | Technical indicators            | ✓    |
| `/api/stock/{ticker}/fundamental`       | GET        | Fundamental ratios + fair value | ✓    |
| `/api/portfolio`                        | GET        | Portfolio with real-time P/L    | ✓    |
| `/api/portfolio/holdings`               | GET/POST   | List / add holdings             | ✓    |
| `/api/portfolio/holdings/{id}`          | PUT/DELETE | Update / delete a holding       | ✓    |
| `/api/backtest`                         | POST       | Run strategy backtest           | ✓    |
| `/api/backtest/strategies`              | GET        | List available strategies       | ✓    |
| `/api/knowledge/stats`                  | GET        | Knowledge base statistics       | ✓    |
| `/health`                               | GET        | Health check                    | ✗    |

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.12+** with [uv](https://docs.astral.sh/uv/) package manager
- **Node.js 20+** with npm
- **Google Cloud project** (Firestore & Vertex AI enabled)
- **Firebase project** (Authentication enabled)
- **Service Account JSON** (with Firestore & Vertex AI permissions)

### Backend

```bash
cd backend

# Install dependencies
uv sync

# Set up environment variables
cp .env.example .env
# Edit .env with your Google Cloud Project ID and other settings

# Place your Service Account key
mkdir -p .secrets
cp /path/to/your/service-account.json .secrets/service-account.json

# Ingest knowledge base documents into Firestore
uv run python cli.py ingest

# Start the dev server
uv run uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure Firebase (fill in your Firebase config in src/lib/firebase.ts)

# Start the dev server
npm run dev
```

### Docker (one-command backend)

```bash
docker compose up --build
```

### Running Tests

```bash
cd backend
uv sync                    # Install dependencies (including dev)
uv run pytest tests/       # Run all tests
uv run pytest tests/test_stock_service.py -v  # Run a specific test file
```

### Environment Variables

| Variable                         | Description                            | Default              |
| -------------------------------- | -------------------------------------- | -------------------- |
| `GOOGLE_CLOUD_PROJECT`           | Google Cloud project ID                | —                    |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Service Account JSON           | —                    |
| `GEMINI_MODEL_NAME`              | LLM model name                         | `gemini-2.5-pro`     |
| `EMBEDDING_MODEL_NAME`           | Embedding model                        | `text-embedding-004` |
| `AUTH_REQUIRED`                  | Enable JWT authentication              | `true`               |
| `CORS_ORIGINS`                   | Allowed CORS origins (comma-separated) | —                    |
| `DEBUG`                          | Debug mode (enables Swagger UI)        | `false`              |

---

## 📁 Project Structure

```
navi/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── config.py                # Environment config (pydantic-settings)
│   ├── cli.py                   # CLI tools (knowledge ingestion, etc.)
│   ├── api/routes/              # API routes
│   │   ├── chat.py              #   AI chat (SSE Streaming)
│   │   ├── stock.py             #   Stock data & analysis
│   │   ├── portfolio.py         #   Portfolio CRUD
│   │   ├── backtest.py          #   Strategy backtesting
│   │   └── knowledge.py         #   Knowledge base management
│   ├── services/                # Business logic layer
│   │   ├── agent_service.py     #   LangChain Agent + Intent Classifier + Prefetch
│   │   ├── conversation_service.py # Multi-turn conversation history (Firestore)
│   │   ├── rag_service.py       #   RAG Pipeline
│   │   ├── stock_service.py     #   Stock data (yfinance) + ticker resolution
│   │   ├── embedding_service.py #   Embedding processing
│   │   ├── backtest_service.py  #   Backtesting engine
│   │   ├── institutional_service.py # TWSE/OTC institutional data
│   │   ├── margin_service.py    #   Margin trading data
│   │   ├── news_service.py      #   Google News RSS
│   │   ├── portfolio_service.py #   Portfolio management
│   │   └── firestore_client.py  #   Firestore client singleton
│   ├── tools/                   # LangChain Agent Tools (9 tools)
│   ├── models/                  # Pydantic Schemas & Prompt Templates
│   ├── knowledge_base/          # Static knowledge docs (13 Markdown files)
│   │   ├── technical_analysis/  #   RSI, MACD, KD, MA, BB, candlesticks, etc.
│   │   ├── fundamental_analysis/#   Financial ratios, earnings, valuation, etc.
│   │   └── investment_theory/   #   Risk management
│   ├── data_pipeline/           # Knowledge ingestion pipeline
│   └── tests/                   # Pytest tests
├── frontend/
│   ├── src/
│   │   ├── pages/               # Dashboard, Chat, Stock, Portfolio, Backtest, Login
│   │   ├── components/          # Layout, PriceChart, RsiChart, StatCard, etc.
│   │   ├── lib/                 # API client & Firebase config
│   │   └── store/               # Zustand (auth + theme)
│   └── firebase.json            # Firebase Hosting config (rewrites, headers, cache)
├── docker-compose.yml           # Local dev container
├── cloudbuild.yaml              # Cloud Build → Cloud Run deployment
├── cloudbuild-ingest.yaml       # Cloud Build → Knowledge ingestion
├── cloudbuild-test.yaml         # Cloud Build → Test pipeline
├── scripts/
│   ├── deploy.sh                # Manual deploy script (Artifact Registry → Cloud Run)
│   └── setup_trigger.sh         # Cloud Build trigger setup
├── PROPOSAL.md                  # Detailed project proposal
└── CHANGELOG.md                 # Version history
```

---

## 📄 License

This project is for personal learning and portfolio demonstration purposes.
