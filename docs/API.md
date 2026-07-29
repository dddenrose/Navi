# API Reference

REST API for the Navi backend (FastAPI on Cloud Run). Interactive Swagger UI is
available at `/docs` when `DEBUG=true`.

`Auth` column: ✓ = Firebase JWT · **Admin** = admin role · **Token** = Cloud
Scheduler shared secret · ✗ = public.

## Chat

| Path                                    | Method | Description                       | Auth |
| --------------------------------------- | ------ | --------------------------------- | ---- |
| `/api/chat`                             | POST   | SSE streaming chat                | ✓    |
| `/api/chat/quota`                       | GET    | Current user's daily quota status | ✓    |
| `/api/chat/conversations`               | GET    | List user conversations           | ✓    |
| `/api/chat/conversations/{id}/messages` | GET    | Get conversation history          | ✓    |
| `/api/chat/conversations/{id}`          | DELETE | Delete a conversation             | ✓    |

## Stock

| Path                                | Method | Description                     | Auth |
| ----------------------------------- | ------ | ------------------------------- | ---- |
| `/api/stock/search`                 | GET    | Search TW tickers / names       | ✓    |
| `/api/stock/{ticker}`               | GET    | Stock overview (price, change)  | ✓    |
| `/api/stock/{ticker}/technical`     | GET    | Technical indicators            | ✓    |
| `/api/stock/{ticker}/fundamental`   | GET    | Fundamental ratios + fair value | ✓    |
| `/api/stock/{ticker}/institutional` | GET    | Institutional buy/sell (N days) | ✓    |
| `/api/stock/{ticker}/margin`        | GET    | Margin trading (N days)         | ✓    |

## Portfolio

| Path                                   | Method     | Description                                      | Auth |
| -------------------------------------- | ---------- | ------------------------------------------------ | ---- |
| `/api/portfolio`                       | GET        | Portfolio with real-time P/L                     | ✓    |
| `/api/portfolio/holdings`              | GET/POST   | List / add holdings                              | ✓    |
| `/api/portfolio/holdings/{id}`         | PUT/DELETE | Update / delete a holding                        | ✓    |
| `/api/portfolio/transactions`          | GET/POST   | List / record buy-sell transactions (fees + tax) | ✓    |
| `/api/portfolio/transactions/estimate` | GET        | Estimate fees/tax for a transaction              | ✓    |

## Knowledge

| Path                   | Method | Description               | Auth |
| ---------------------- | ------ | ------------------------- | ---- |
| `/api/knowledge/stats` | GET    | Knowledge base statistics | ✓    |

## Screener

| Path                                        | Method  | Description                               | Auth  |
| ------------------------------------------- | ------- | ----------------------------------------- | ----- |
| `/api/screener/run`                         | POST    | Trigger a screener run (Stage 1→2→3)      | Token |
| `/api/screener/reports`                     | GET     | List recent reports                       | ✓     |
| `/api/screener/reports/latest`              | GET     | Latest report for a profile               | ✓     |
| `/api/screener/reports/{id}`                | GET     | Report detail (picks by industry)         | ✓     |
| `/api/screener/reports/{id}/picks/{ticker}` | GET     | Single pick detail                        | ✓     |
| `/api/screener/track`                       | POST    | Update forward-return tracking            | Token |
| `/api/screener/tracking/summary`            | GET     | Pick performance stats (win rate, excess) | ✓     |
| `/api/screener/subscriptions`               | GET/PUT | Get / update email subscription           | ✓     |
| `/api/screener/notify`                      | POST    | Email latest report to subscribers        | Token |
| `/api/screener/unsubscribe`                 | GET     | One-click unsubscribe (HMAC token)        | ✗     |

## Features & Admin

| Path                                      | Method    | Description                       | Auth  |
| ----------------------------------------- | --------- | --------------------------------- | ----- |
| `/api/features/access`                    | GET       | Effective feature access for user | ✓     |
| `/api/admin/me`                           | GET       | Current admin identity            | Admin |
| `/api/admin/users`                        | GET       | List users                        | Admin |
| `/api/admin/users/{uid}`                  | GET/PATCH | Get / update user (tier, status)  | Admin |
| `/api/admin/quota-configs`                | GET       | List quota configs                | Admin |
| `/api/admin/quota-configs/{tier}`         | PUT       | Update a tier's quota             | Admin |
| `/api/admin/feature-access-configs`       | GET       | List feature-access configs       | Admin |
| `/api/admin/feature-access-configs/{key}` | PUT       | Update a feature's access rule    | Admin |
| `/api/admin/usage/summary`                | GET       | Aggregate usage summary           | Admin |
| `/api/admin/logs`                         | GET       | Audit / request logs              | Admin |

## System

| Path      | Method | Description  | Auth |
| --------- | ------ | ------------ | ---- |
| `/health` | GET    | Health check | ✗    |

## Agent Tools

Not HTTP endpoints — these are the LangChain tools the agent can call while
answering a `/api/chat` request.

| Tool                             | Description                                                                              |
| -------------------------------- | ---------------------------------------------------------------------------------------- |
| `get_stock_price`                | Real-time stock price, change %, volume, market cap                                      |
| `analyze_technicals`             | MA, RSI, MACD, KD, Bollinger Bands, Fibonacci retracement, support/resistance, stop-loss |
| `analyze_fundamentals`           | PE, PB, ROE, EPS, growth rates, 3-tier fair value (cheap/fair/expensive)                 |
| `search_knowledge`               | RAG vector search across 24 investment knowledge documents in 8 categories (top-5)       |
| `get_institutional`              | Foreign, investment trust, dealer buy/sell data (TWSE/OTC API)                            |
| `get_margin_trading`             | Margin balance, utilization rate, short selling, margin offset                           |
| `search_financial_news`          | Financial news via Google News RSS                                                       |
| `get_portfolio`                  | User portfolio with real-time P/L and allocation breakdown                               |
| `run_strategy_backtest`          | Backtest with MA crossover / RSI / MACD / custom strategies                               |
| `get_market_overview`            | Whole-market index quote (intraday / latest close)                                       |
| `get_market_institutional_flows` | Aggregate market-wide institutional buy/sell (foreign / trust / dealer)                  |
| `get_market_futures_positions`   | TAIFEX index-futures open-interest positioning (TXF / MXF / TMF)                         |
