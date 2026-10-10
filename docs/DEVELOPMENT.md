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
| `LINE_CHANNEL_SECRET`            | LINE channel secret; empty disables the LINE endpoints      | —                                     |
| `LINE_CHANNEL_ACCESS_TOKEN`      | LINE access token; empty = dry-run (log instead of send)    | —                                     |
| `LINE_TASKS_QUEUE`               | Cloud Tasks queue for LINE events; empty = in-process (dev) | —                                     |
| `LINE_TASKS_LOCATION`            | Region of the Cloud Tasks queue                             | `asia-east1`                          |

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
│   │   ├── line.py              #   LINE Messaging API webhook + Cloud Tasks target
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
│   │   ├── line/                #   LINE chat channel (client, event handler, formatting, task enqueue)
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
│   ├── scripts/                 # Ops scripts (seed configs, set admin/tier, link LINE user, local screener run)
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
    ├── setup_line_bot.sh        # Cloud Tasks queue + LINE secrets for the LINE chat channel
    └── setup_trigger.sh         # Cloud Build trigger setup
```

## Deployment

- **Backend** — pushing to `main` triggers Cloud Build → Cloud Run (`asia-east1`).
- **Frontend** — `npm run build` then `firebase deploy --only hosting`.
- **Screener schedule** — `scripts/setup_screener_scheduler.sh` creates the
  Cloud Scheduler jobs for `run` / `track` / `notify`.
- **LINE bot** — see [LINE Bot](#line-bot) below.

## LINE Bot

Users can chat with Navi in a one-on-one LINE chat. LINE is a second front end
over the same agent: quota, tier, portfolio and conversation history are those
of the linked Navi account, and LINE conversations show up in the web UI.

```
LINE ── POST /api/line/webhook ──▶ verify signature → one Cloud Task per event → 200
Cloud Tasks ── POST /api/line/process ──▶ verify signature again → run agent → reply
```

The webhook must answer within about 2 seconds while an answer takes tens of
seconds, and Cloud Run throttles CPU once a response is sent, so the agent runs
in a second request made by Cloud Tasks. Answers are sent with the free reply
API; if the reply token has expired (about a minute) they fall back to push,
which counts against the LINE plan's monthly message quota.

Only LINE users present in the `line_links` Firestore collection are served;
everyone else gets an invite-only notice followed by their LINE user ID as a
separate message, so it can be copied with a long press.

Each user has at most one question in progress. A second question that arrives
while the first is running gets "still working on your last question" instead
of running concurrently, because conversation history is read-then-written
without a transaction. The lock is `inflight_until` on the user's `line_links`
document, taken in a Firestore transaction with a 5-minute lease. Different
users run in parallel, up to the queue's 3 concurrent dispatches.

Every push logs the month's push usage against the plan limit
(`LINE push usage this month`), at WARNING once it reaches 80%.

**One-time setup**

1. Create a LINE Official Account, enable the Messaging API, and copy the
   channel secret and a long-lived channel access token from the LINE Developers
   Console.
2. `./scripts/setup_line_bot.sh --secrets` — enables Cloud Tasks, creates the
   `line-events` queue, stores both secrets in Secret Manager, and prints the
   `gcloud run services update --update-secrets=...` command to run once.
3. Deploy the backend, then set the webhook URL to
   `<Cloud Run URL>/api/line/webhook`. Turn on **Use webhook** and **Webhook
   redelivery**; turn off auto-reply messages in LINE Official Account Manager.
   The service cold-starts in roughly 30 seconds, so hit `/health` first or the
   console's **Verify** button will time out.
4. Message the bot, copy the LINE user ID from its reply, and link it:
   `cd backend && uv run python scripts/link_line.py <email-or-uid> <line-user-id>`.

**Adding friends who only use LINE** — they have no Navi account, so create a
LINE-only one (uid `line_<line-user-id>`, no email, free tier) and link it in
one step. The friend adds the bot, sends any message, and forwards you the ID
it replies with:

```bash
cd backend
LINE_CHANNEL_ACCESS_TOKEN=$(gcloud secrets versions access latest --secret=line-channel-access-token) \
  uv run python scripts/link_line.py --create <line-user-id>   # display name read from LINE
uv run python scripts/link_line.py --create <line-user-id> 阿明  # or give one explicitly
```

Change their tier or daily limit in the admin console, or with
`scripts/set_tier.py line_<line-user-id> <tier>`.

**Local development** — leave `LINE_TASKS_QUEUE` and `LINE_CHANNEL_ACCESS_TOKEN`
empty and set `LINE_CHANNEL_SECRET` to any value. Events are then handled
in-process and outgoing messages are only logged, so a signed request is enough
to exercise the whole flow:

```bash
BODY='{"events":[{"type":"message","webhookEventId":"TEST0001","replyToken":"dummy","source":{"type":"user","userId":"U00000000000000000000000000000001"},"message":{"type":"text","id":"1","text":"台積電現在多少"}}]}'
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$LINE_CHANNEL_SECRET" -binary | base64)
curl -i localhost:8000/api/line/webhook -H "X-Line-Signature: $SIG" --data-binary "$BODY"
```
