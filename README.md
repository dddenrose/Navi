# 🧚 Navi — AI-Powered Stock Analyzer

[繁體中文](README.zh-TW.md)

> _"Hey! Listen!"_ — Your personal investment analysis fairy.
>
> Inspired by Navi, the fairy guide from _The Legend of Zelda: Ocarina of Time_,
> this AI assistant navigates you through the stock market.

⚠️ **Disclaimer: This project is for learning and research purposes only. All analysis results do not constitute investment advice. Invest at your own risk.**

---

## ✨ Features

- **AI Chat Analysis** — Ask questions in natural language; combines RAG knowledge base with real-time data to deliver data-backed investment analysis (SSE Streaming)
- **Technical Analysis** — Auto-computes RSI, MACD, KD, moving averages, Bollinger Bands, and provides a comprehensive signal summary
- **Fundamental Analysis** — PE, PB, ROE, EPS, revenue growth, and other key financial ratios at a glance
- **Institutional Tracking** — Integrates with TWSE/OTC APIs to fetch institutional investor buy/sell data and margin trading info
- **Financial News** — Real-time financial news search via Google News RSS
- **Portfolio Tracking** — Record holdings, compute real-time market value & P/L; the AI agent can query your positions directly
- **Strategy Backtesting** — Supports MA crossover, RSI, and MACD strategies; simulates historical performance and generates backtest reports

---

## 🏗️ Architecture

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

The LangChain Agent autonomously selects from 9 tools to answer questions:

| Tool                    | Description                                     |
| ----------------------- | ----------------------------------------------- |
| `get_stock_price`       | Real-time stock price lookup                    |
| `analyze_technicals`    | Technical indicators (RSI, MACD, KD, MA)        |
| `analyze_fundamentals`  | Fundamental financial ratios                    |
| `search_knowledge`      | RAG knowledge base vector search                |
| `get_institutional`     | Institutional investor buy/sell data (TWSE API) |
| `get_margin_trading`    | Margin trading data                             |
| `search_financial_news` | Financial news search                           |
| `get_portfolio`         | Query user's portfolio                          |
| `run_strategy_backtest` | Run strategy backtests                          |

---

## 🛠️ Tech Stack

### Backend

| Category      | Technology                                |
| ------------- | ----------------------------------------- |
| Language      | Python 3.12                               |
| Web Framework | FastAPI                                   |
| AI Framework  | LangChain (Tool-calling Agent)            |
| LLM           | Gemini 2.5 Pro                            |
| Embedding     | text-embedding-004                        |
| Vector DB     | Firestore Vector Search                   |
| Data Sources  | yfinance · TWSE/OTC API · Google News RSS |

### Frontend

| Category         | Technology              |
| ---------------- | ----------------------- |
| Framework        | React 19 + TypeScript   |
| Build Tool       | Vite                    |
| Styling          | Tailwind CSS            |
| Charts           | Recharts                |
| State Management | Zustand                 |
| Auth             | Firebase Authentication |

### Infrastructure

| Category         | Technology         |
| ---------------- | ------------------ |
| Backend Hosting  | Google Cloud Run   |
| Frontend Hosting | Firebase Hosting   |
| CI/CD            | Google Cloud Build |
| Database         | Firestore          |
| Containerization | Docker             |

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
│   ├── config.py                # Environment config
│   ├── cli.py                   # CLI tools (knowledge ingestion, etc.)
│   ├── api/routes/              # API routes
│   │   ├── chat.py              #   AI chat (SSE Streaming)
│   │   ├── stock.py             #   Stock data
│   │   ├── portfolio.py         #   Portfolio CRUD
│   │   ├── backtest.py          #   Strategy backtesting
│   │   └── knowledge.py         #   Knowledge base management
│   ├── services/                # Business logic layer
│   │   ├── agent_service.py     #   LangChain Agent core
│   │   ├── rag_service.py       #   RAG Pipeline
│   │   ├── stock_service.py     #   Stock data (yfinance)
│   │   ├── embedding_service.py #   Embedding processing
│   │   └── ...                  #   Other services
│   ├── tools/                   # LangChain Agent Tools (9 tools)
│   ├── models/                  # Pydantic Schemas & Prompts
│   ├── knowledge_base/          # Static knowledge docs (Markdown)
│   └── tests/                   # Tests
├── frontend/
│   ├── src/
│   │   ├── pages/               # Pages (Dashboard, Chat, Stock, Portfolio, Backtest)
│   │   ├── components/          # UI components (charts, layout, etc.)
│   │   ├── lib/                 # API client & Firebase config
│   │   └── store/               # Zustand state management
│   └── firebase.json            # Firebase Hosting config
├── docker-compose.yml           # Local dev container
├── cloudbuild.yaml              # Cloud Build deployment pipeline
└── PROPOSAL.md                  # Detailed project proposal
```

---

## 📄 License

This project is for personal learning and portfolio demonstration purposes.
