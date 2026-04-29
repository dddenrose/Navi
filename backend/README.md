# Navi Backend — AI-Powered Stock Analyzer

> 🧚 _"Hey! Listen!"_ — Navi AI 投資分析助手後端

## 環境需求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) 套件管理工具
- Google Cloud 專案（含 Firestore、Vertex AI）

## 快速開始

### 1. 安裝依賴

```bash
cd backend
uv sync
```

### 2. 設定環境變數

```bash
cp .env.example .env
```

編輯 `.env`，填入你的 GCP 設定：

```env
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_APPLICATION_CREDENTIALS=.secrets/service-account.json
```

### 3. 放入 GCP Service Account Key

```bash
mkdir -p .secrets
# 將從 GCP Console 下載的 JSON key 放到 .secrets/service-account.json
```

### 4. 匯入知識庫

```bash
uv run python data_pipeline/ingest_knowledge.py
```

重新匯入（覆蓋已存在的 chunks）：

```bash
uv run python data_pipeline/ingest_knowledge.py --force
```

### 5. 啟動開發伺服器

```bash
uv run uvicorn main:app --reload --port 8000
```

打開 http://localhost:8000/docs 查看 API 文件。

### 6. 使用 CLI 對話

```bash
uv run python cli.py
```

## 常用指令

| 指令                                              | 說明           |
| ------------------------------------------------- | -------------- |
| `uv run uvicorn main:app --reload --port 8000`    | 啟動開發伺服器 |
| `uv run python data_pipeline/ingest_knowledge.py` | 匯入知識庫     |
| `uv run python cli.py`                            | CLI 互動式問答 |
| `uv run pytest tests/ -v`                         | 執行測試       |
| `uv run ruff check .`                             | 程式碼檢查     |
| `uv run ruff format .`                            | 自動格式化     |

## API 端點

| 方法     | 路徑                                    | 說明                       |
| -------- | --------------------------------------- | -------------------------- |
| GET      | `/health`                               | Health check               |
| POST     | `/api/chat`                             | AI 對話（SSE Streaming）   |
| GET      | `/api/chat/conversations`               | 列出使用者對話             |
| GET      | `/api/chat/conversations/{id}/messages` | 取得對話歷史             |
| DELETE   | `/api/chat/conversations/{id}`          | 刪除對話                   |
| GET      | `/api/stock/{ticker}`                   | 股票概覽                   |
| GET      | `/api/stock/{ticker}/technical`         | 技術面分析                 |
| GET      | `/api/stock/{ticker}/fundamental`       | 基本面分析                 |
| GET      | `/api/stock/{ticker}/institutional`     | 三大法人買賣超             |
| GET      | `/api/stock/{ticker}/margin`            | 融資融券                   |
| GET/POST | `/api/portfolio` ・ `/holdings`         | 投資組合 CRUD             |
| POST     | `/api/backtest`                         | 策略回測                   |
| GET      | `/api/knowledge/stats`                  | 知識庫統計                 |

### Chat API 範例

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "什麼是 RSI？何時該使用？"}' \
  --no-buffer
```

## 專案結構

```
backend/
├── main.py                        # FastAPI app 入口
├── config.py                      # 環境設定 (pydantic-settings)
├── cli.py                         # CLI 互動式問答
├── api/
│   ├── dependencies.py            # JWT / Firebase Auth
│   ├── rate_limit.py              # IP-based rate limit
│   └── routes/
│       ├── chat.py                # POST /api/chat (SSE) + 對話歷史
│       ├── stock.py               # 概覽 / 技術 / 基本 / 法人 / 融資
│       ├── portfolio.py           # 投資組合 CRUD
│       ├── backtest.py            # 策略回測
│       └── knowledge.py           # 知識庫統計
├── services/
│   ├── agent_service.py           # LangGraph ReAct + 混合意圖分類 + Prefetch
│   ├── conversation_service.py    # 多輪對話歷史（Firestore）
│   ├── stock_service.py           # yfinance + 台股代碼解析
│   ├── institutional_service.py   # TWSE/OTC 三大法人
│   ├── margin_service.py          # 融資融券
│   ├── news_service.py            # Google News RSS
│   ├── portfolio_service.py       # 投資組合
│   ├── backtest_service.py        # 回測引擎
│   ├── embedding_service.py       # text-embedding-004 + Vector Search
│   └── firestore_client.py        # Firestore singleton
├── tools/                         # LangChain / LangGraph Agent Tools（9 種）
│   ├── stock_price.py             # get_stock_price
│   ├── technical_analysis.py      # analyze_technicals
│   ├── fundamental_analysis.py    # analyze_fundamentals
│   ├── knowledge_search.py        # search_knowledge (RAG)
│   ├── institutional.py           # get_institutional
│   ├── margin_trading.py          # get_margin_trading
│   ├── news_search.py             # search_financial_news
│   ├── portfolio_tool.py          # get_portfolio
│   └── backtest_tool.py           # run_strategy_backtest
├── models/
│   └── schemas.py                 # Pydantic models
├── data_pipeline/
│   └── ingest_knowledge.py        # 知識庫匯入腳本
├── knowledge_base/                # 24 份 Markdown、8 大分類
│   ├── technical_analysis/        # RSI、MACD、KD、MA、布林、量能、K 線、支撐壓力
│   ├── fundamental_analysis/      # 財務比率、財報解讀、估值方法、產業分析
│   ├── investment_theory/         # 風險管理、資產配置、行為金融、ETF
│   ├── taiwan_market/             # 台股交易機制與資料來源
│   ├── macro/                     # 總體指標
│   ├── agent_persona/             # 投資哲學與回覆風格
│   ├── compliance/                # 免責聲明與風險提醒
│   └── tool_interpretation/       # 回測 / 分析輸出解讀
└── tests/
    ├── test_app.py
    ├── test_firestore.py
    ├── test_embedding.py
    ├── test_rag.py
    └── test_stock_service.py
```

## Firestore Vector Index 設定

在 Firestore Console 或使用 CLI 建立 Vector Index：

- **Collection**: `knowledge`
- **Field**: `embedding`
- **Dimension**: 768
- **Distance measure**: COSINE

```bash
gcloud firestore indexes composite create \
  --collection-group=knowledge \
  --field-config=vector-config='{"dimension":"768","flat": "{}"}',field-path=embedding
```
