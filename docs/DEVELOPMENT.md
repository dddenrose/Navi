# Development Guide

Detailed setup, configuration, and project layout. For a 3-command quickstart see
the [README](../README.md#getting-started).

## Prerequisites

- **Python 3.12+** with the [uv](https://docs.astral.sh/uv/) package manager
- **Node.js 20+** with npm
- **Google Cloud project** with Firestore and Vertex AI enabled
- **Firebase project** with Authentication enabled
- **Service Account JSON** with Firestore and Vertex AI permissions

## Backend

```bash
cd backend

uv sync                          # install dependencies (incl. dev)

cp .env.example .env             # then fill in GOOGLE_CLOUD_PROJECT etc.

mkdir -p .secrets                # place your service account key
cp /path/to/service-account.json .secrets/service-account.json

uv run python cli.py ingest      # ingest knowledge base docs into Firestore

uv run uvicorn main:app --reload --port 8000
```

Swagger UI is served at `http://localhost:8000/docs` when `DEBUG=true`.

## Frontend

```bash
cd frontend
npm install
# fill in your Firebase config in src/lib/firebase.ts
npm run dev
```

## Docker

```bash
docker compose up --build        # backend only
```

## Tests

```bash
cd backend
uv run pytest tests/                            # all tests
uv run pytest tests/test_stock_service.py -v    # a single file
```

CI runs the same suite on every push and pull request against `main`
([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)).

## Environment Variables

| Variable                         | Description                                                 | Default                               |
| -------------------------------- | ----------------------------------------------------------- | ------------------------------------- |
| `GOOGLE_CLOUD_PROJECT`           | Google Cloud project ID                                     | —                                     |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to Service Account JSON                                | —                                     |
| `GEMINI_MODEL_NAME`              | LLM model for paid tiers (pro/unlimited/admin)              | `gemini-2.5-flash`                    |
| `GEMINI_MODEL_NAME_FREE`         | LLM model for the free tier                                 | `gemini-2.5-flash-lite`               |
| `EMBEDDING_MODEL_NAME`           | Embedding model                                             | `text-embedding-004`                  |
| `AUTH_REQUIRED`                  | Enable JWT authentication                                   | `true`                                |
| `CORS_ORIGINS`                   | Allowed CORS origins (comma-separated)                      | —                                     |
| `DEBUG`                          | Debug mode (enables Swagger UI)                             | `false`                               |
| `TW_QUOTE_PROVIDER`              | TW price source: `mis` (realtime) or `openapi` (T-1 close)  | `mis`                                 |
| `SCREENER_LLM_MODEL`             | Screener Stage-3 interpretation model                       | `gemini-2.5-flash-lite`               |
| `SCREENER_RUNNER_TOKEN`          | Shared secret for Scheduler-triggered screener endpoints    | —                                     |
| `SCREENER_UNSUBSCRIBE_SECRET`    | HMAC secret for one-click unsubscribe links                 | —                                     |
| `SCREENER_PUBLIC_BASE_URL`       | Public base URL used in email links                         | `https://navi-stock-analyzer.web.app` |
| `SENDGRID_API_KEY`               | SendGrid key for screener email digests (optional)          | —                                     |
| `EMAIL_FROM_ADDRESS`             | Sender address for digest emails                            | `notify@navi-stock.app`               |
| `EMAIL_FROM_NAME`                | Sender display name for digest emails                       | `Navi 智能選股`                       |

## Project Structure

```
navi/
├── backend/
│   ├── main.py                  # FastAPI entry point
│   ├── config.py                # Environment config + per-tier model selection (pydantic-settings)
│   ├── cli.py                   # CLI tools (knowledge ingestion, etc.)
│   ├── api/routes/              # API routes
│   │   ├── chat.py              #   AI chat (SSE Streaming) + quota
│   │   ├── stock.py             #   Stock data & analysis (search, technical, fundamental, chips)
│   │   ├── portfolio.py         #   Portfolio + transactions (fees/tax, realized P/L)
│   │   ├── screener.py          #   AI screener: run / reports / tracking / subscriptions
│   │   ├── features.py          #   Feature-access discovery
│   │   ├── admin.py             #   Admin console API (users, quota, flags, logs)
│   │   └── knowledge.py         #   Knowledge base management
│   ├── services/                # Business logic layer
│   │   ├── agent_service.py     #   LangGraph ReAct + Hybrid Intent Classifier + Prefetch
│   │   ├── conversation_service.py # Multi-turn conversation history (Firestore)
│   │   ├── stock_service.py     #   Stock data (yfinance) + ticker resolution
│   │   ├── embedding_service.py #   Embedding processing
│   │   ├── backtest_service.py  #   Backtesting engine (agent tool only, no REST route)
│   │   ├── institutional_service.py # TWSE/OTC institutional data
│   │   ├── margin_service.py    #   Margin trading data
│   │   ├── macro_service.py     #   Market-wide index / flows / futures positioning
│   │   ├── news_service.py      #   Google News RSS
│   │   ├── portfolio_service.py #   Portfolio management
│   │   ├── quota_service.py     #   Per-user daily quota counters
│   │   ├── feature_access_service.py # Tier-based feature gating
│   │   ├── twse_parsers.py      #   Shared TWSE field-parsing layer (T86 / MI_MARGN)
│   │   ├── screener/            #   Screener pipeline (rules, scoring, valuation, AI, email, tracking)
│   │   └── firestore_client.py  #   Firestore client singleton
│   ├── tools/                   # LangChain / LangGraph Agent Tools (12 tools)
│   ├── models/                  # Pydantic Schemas (schemas.py)
│   ├── knowledge_base/          # Curated knowledge docs (24 Markdown files, 8 categories)
│   │   ├── technical_analysis/  #   RSI, MACD, KD, MA, BB, volume, candlesticks, S/R
│   │   ├── fundamental_analysis/#   Financial ratios, earnings, valuation, industry
│   │   ├── investment_theory/   #   Risk management, portfolio theory, behavioral, ETF
│   │   ├── taiwan_market/       #   Taiwan-specific trading mechanics & data sources
│   │   ├── macro/               #   Macro indicators (rates, FX, cycles)
│   │   ├── agent_persona/       #   Investment philosophy & response style
│   │   ├── compliance/          #   Disclaimers & risk warnings
│   │   └── tool_interpretation/ #   How to read backtest / analysis outputs
│   ├── data_pipeline/           # Knowledge ingestion pipeline
│   ├── scripts/                 # Ops scripts (seed configs, set admin/tier, local screener run)
│   └── tests/                   # Pytest tests (services, screener, parsers, RAG, quota …)
├── frontend/
│   ├── src/
│   │   ├── pages/               # Dashboard, Chat, Stock (tabs), Portfolio, Screener, Login, admin/
│   │   ├── components/          # Layout, PriceChart, RsiChart, StatCard, QuotaBadge, FeatureGuard, etc.
│   │   ├── lib/                 # API client (+ api/screener.ts) & Firebase config
│   │   └── store/               # Zustand (auth + theme + quota)
│   └── firebase.json            # Firebase Hosting config (rewrites, headers, cache)
├── docker-compose.yml           # Local dev container
├── cloudbuild.yaml              # Cloud Build → Cloud Run deployment
├── cloudbuild-ingest.yaml       # Cloud Build → Knowledge ingestion
└── scripts/
    ├── deploy.sh                # Manual deploy script (Artifact Registry → Cloud Run)
    ├── setup_screener_scheduler.sh # Cloud Scheduler jobs (run / track / notify)
    └── setup_trigger.sh         # Cloud Build trigger setup
```

## Deployment

- **Backend** — pushing to `main` triggers Cloud Build → Cloud Run (`asia-east1`).
- **Frontend** — `npm run build` then `firebase deploy --only hosting`.
- **Screener schedule** — `scripts/setup_screener_scheduler.sh` creates the
  Cloud Scheduler jobs for `run` / `track` / `notify`.
