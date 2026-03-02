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

| 方法   | 路徑                              | 說明                     |
| ------ | --------------------------------- | ------------------------ |
| GET    | `/`                               | Health check             |
| GET    | `/health`                         | Health check             |
| POST   | `/api/chat`                       | AI 對話（SSE Streaming） |
| GET    | `/api/conversations`              | 列出對話紀錄             |
| DELETE | `/api/conversations/{id}`         | 刪除指定對話             |
| GET    | `/api/stock/{ticker}`             | 股票概覽                 |
| GET    | `/api/stock/{ticker}/technical`   | 技術面分析               |
| GET    | `/api/stock/{ticker}/fundamental` | 基本面分析               |
| GET    | `/api/stock/{ticker}/chart`       | 歷史K線數據              |
| GET    | `/api/knowledge/stats`            | 知識庫統計               |

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
│   ├── routes/
│   │   ├── chat.py                # POST /api/chat (SSE) + 對話管理
│   │   ├── stock.py               # GET /api/stock/{ticker}
│   │   └── knowledge.py           # GET /api/knowledge/stats
│   └── dependencies.py
├── services/
│   ├── firestore_client.py        # Firestore singleton
│   ├── embedding_service.py       # text-embedding-004 + Vector Search
│   ├── rag_service.py             # RAG pipeline (Search → Gemini)
│   ├── stock_service.py           # yfinance 股價、技術指標、財報
│   ├── agent_service.py           # LangChain Tool-calling Agent（Phase 3）
│   └── conversation_service.py    # 多輪對話記憶（Firestore）（Phase 3）
├── tools/                         # LangChain Agent 可用工具（Phase 3）
│   ├── stock_price.py             # get_stock_price
│   ├── technical_analysis.py      # analyze_technicals
│   ├── fundamental_analysis.py    # analyze_fundamentals
│   └── knowledge_search.py        # search_knowledge
├── models/
│   ├── schemas.py                 # Pydantic models
│   └── prompts.py                 # Prompt templates
├── data_pipeline/
│   └── ingest_knowledge.py        # 知識庫匯入腳本
├── knowledge_base/                # Markdown 知識文件
│   ├── technical_analysis/
│   ├── fundamental_analysis/
│   └── investment_theory/
└── tests/
    ├── test_firestore.py
    ├── test_embedding.py
    ├── test_rag.py
    ├── test_stock_service.py
    └── test_agent.py              # Agent 單元測試（Phase 3）
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
