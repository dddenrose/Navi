# 🧚 Navi — AI-Powered Stock Analyzer

> _"Hey! Listen!"_ — 你的個人投資分析精靈
>
> 靈感來自《薩爾達傳說：時之笛》中的精靈嚮導 Navi，
> 她總是在冒險者身邊，提供關鍵情報與指引。
> 這個專案也是如此 — 用 AI 為你導航股海。

---

## 1. 專案概述

### 名稱

**Navi** (`navi`)

### 一句話描述

透過 RAG 技術整合財報、技術分析理論、財經新聞等知識庫，結合即時股票數據，提供個人化投資分析建議的 AI 助手。

### 目標

| 目標        | 說明                                          |
| ----------- | --------------------------------------------- |
| 🎓 技能訓練 | Python / FastAPI / LangChain / RAG / AI Agent |
| 🔧 自用工具 | 建立一個自己每天都會使用的投資分析助手        |
| 💼 作品集   | 展示 Full-Stack + AI 整合能力                 |

### 免責聲明

> ⚠️ 本專案僅供學習與研究用途，所有分析結果不構成投資建議。投資有風險，決策請自行判斷。

---

## 2. 系統架構

```
┌──────────────────┐         ┌───────────────────────────────┐
│                  │  REST   │         Cloud Run              │
│   Next.js        │────────▶│       FastAPI Backend          │
│   Frontend       │◀────────│                                │
│   (Vercel)       │   SSE   │  ┌───────────┐ ┌───────────┐  │
│                  │         │  │ LangChain  │ │ Data      │  │
└──────────────────┘         │  │ RAG Chain  │ │ Pipeline  │  │
                             │  └─────┬──┬──┘ └─────┬─────┘  │
                             │        │  │          │         │
                             └────────┼──┼──────────┼─────────┘
                                      │  │          │
                        ┌─────────────┘  │          │
                        ▼                ▼          ▼
                ┌──────────────┐  ┌──────────┐  ┌────────────┐
                │  Firestore   │  │ Gemini   │  │ yfinance   │
                │  Vector      │  │ 2.0      │  │ 公開資訊    │
                │  Search      │  │ Flash    │  │ 觀測站      │
                └──────────────┘  └──────────┘  └────────────┘
```

### 全 Google 生態系

所有基礎服務都使用 Google 生態系統，統一管理、統一帳單：

```
Google Cloud Console
├── Firebase（已有）
│   ├── Authentication（使用者認證）
│   ├── Firestore（資料庫 + Vector Search）
│   └── Cloud Storage（檔案儲存）
├── Cloud Run（Python 後端部署）
├── Vertex AI
│   ├── Gemini 2.0 Flash（LLM）
│   └── text-embedding-004（Embedding）
└── Cloud Scheduler（排程更新資料）
```

---

## 3. 技術選型

### Backend

| 類別      | 技術                     | 原因                               |
| --------- | ------------------------ | ---------------------------------- |
| 語言      | Python 3.12              | AI / 資料處理生態最完整            |
| Web 框架  | FastAPI                  | 非同步、自動 API 文件、型別安全    |
| AI 框架   | LangChain                | RAG chain / Agent / Tool calling   |
| LLM       | Gemini 2.0 Flash         | Google 生態、免費額度大、速度快    |
| Embedding | text-embedding-004       | Google 原生、搭配 Firestore Vector |
| Vector DB | Firestore Vector Search  | 已有 Firebase 專案，零額外成本     |
| 資料擷取  | yfinance / BeautifulSoup | 股價、財報、新聞                   |
| 排程      | Cloud Scheduler          | 定時更新資料                       |

### Frontend

| 類別     | 技術                          | 原因                                  |
| -------- | ----------------------------- | ------------------------------------- |
| 框架     | Next.js (App Router)          | 熟悉的技術棧                          |
| UI       | shadcn/ui 或 Ant Design       | 快速搭建 Dashboard                    |
| 圖表     | Recharts / Lightweight Charts | 股票 K 線圖                           |
| 狀態管理 | Zustand                       | 輕量、零 boilerplate、適合 App Router |
| 即時更新 | Server-Sent Events (SSE)      | LLM streaming response                |

### Infrastructure

| 類別     | 技術             | 原因                         |
| -------- | ---------------- | ---------------------------- |
| 前端部署 | Vercel           | 已在使用                     |
| 後端部署 | Google Cloud Run | Google 生態、按量計費        |
| 資料庫   | Firestore        | 已有、原生支援 Vector Search |
| 認證     | Firebase Auth    | 已有                         |
| CI/CD    | GitHub Actions   | 免費                         |

---

## 4. 知識庫設計（RAG 資料來源）

### 4.1 靜態知識（一次性匯入，定期更新）

```
knowledge_base/
├── technical_analysis/          # 技術分析理論
│   ├── candlestick_patterns.md  # K線型態（十字線、吞噬、錘子...）
│   ├── moving_averages.md       # 均線理論（MA、EMA、黃金交叉）
│   ├── rsi_macd.md              # 動量指標（RSI、MACD、KD）
│   ├── bollinger_bands.md       # 布林通道
│   └── volume_analysis.md       # 量價分析
│
├── fundamental_analysis/        # 基本面分析
│   ├── financial_ratios.md      # 財務比率（PE、PB、ROE、EPS）
│   ├── dcf_valuation.md         # DCF 估值模型
│   ├── industry_analysis.md     # 產業分析方法
│   └── earnings_analysis.md     # 財報解讀方法
│
├── investment_theory/           # 投資理論
│   ├── modern_portfolio.md      # 現代投資組合理論
│   ├── behavioral_finance.md    # 行為金融學
│   └── risk_management.md       # 風險管理
│
└── papers/                      # 學術論文摘要
    ├── momentum_strategy.md     # 動量策略研究
    └── value_investing.md       # 價值投資研究
```

### 4.2 動態資料（自動擷取、定期更新）

| 資料源     | 更新頻率 | 取得方法                   |
| ---------- | -------- | -------------------------- |
| 股價歷史   | 每日     | yfinance API               |
| 公司財報   | 每季     | 公開資訊觀測站 / SEC EDGAR |
| 法人買賣超 | 每日     | 台灣證交所 Open API        |
| 財經新聞   | 每小時   | RSS Feed / 爬蟲            |
| 分析師報告 | 每週     | 手動或半自動匯入           |

### 4.3 RAG Pipeline 流程

```
                    ┌─────────────────┐
                    │  使用者問題       │
                    │ 「台積電估值合理嗎」│
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Query Embedding │
                    │ text-embedding-004│
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Vector Search   │
                    │  Firestore       │
                    │  Top-K 相似文件   │
                    └────────┬────────┘
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
   │ 估值方法文件 │  │ 台積電財報    │  │ 產業分析      │
   └──────┬──────┘  └──────┬───────┘  └──────┬───────┘
          │                │                  │
          └────────────────┼──────────────────┘
                           ▼
                  ┌─────────────────┐
                  │  Gemini 2.0     │
                  │  Flash          │
                  │  + Prompt       │
                  │  + Context      │
                  │  + 即時股價數據   │
                  └────────┬────────┘
                           │
                           ▼
                  ┌─────────────────┐
                  │  結構化分析回答   │
                  │  + 參考來源標註   │
                  └─────────────────┘
```

---

## 5. 核心功能

### Feature 1：自然語言股票問答（RAG）

使用者輸入自然語言問題，系統結合知識庫與即時數據回答。

```
用戶：「台積電目前的估值合理嗎？」

Navi：
  根據最新財報數據，台積電目前本益比 25.3 倍，
  低於近五年平均的 28.1 倍。

  📊 關鍵數據：
  • PE: 25.3（歷史平均: 28.1）→ 偏低
  • ROE: 28.4% → 維持高水準
  • 營收年增: +35% → 受 AI 晶片需求帶動

  以 DCF 模型概估，合理區間約 $170-$195...

  📄 參考：
  [1] TSMC 2025 Q3 財報
  [2] DCF 估值理論 — knowledge_base
  [3] 半導體產業分析 — knowledge_base
```

### Feature 2：技術面自動分析

```
用戶：「分析鴻海的技術面」

Navi：
  📈 鴻海 (2317.TW) 技術面分析

  均線：多頭排列（5MA > 20MA > 60MA）✅
  RSI(14): 62.4 — 中性偏強
  MACD: 金叉，DIF > DEA，量能增
  KD: K=68, D=55 — 偏多但未超買
  布林通道：股價位於中軌與上軌之間

  📋 綜合判斷：短期偏多，但接近前高壓力區...
```

### Feature 3：AI Agent（進階 — 多步驟推理）

```
用戶：「幫我比較台積電和三星在 AI 晶片的競爭力」

Navi 自動執行：
  🔧 [搜尋] 台積電最新財報 → 取得代工營收數據
  🔧 [搜尋] Samsung 晶圓代工資訊
  🔧 [搜尋] AI 晶片產業分析文件
  🔧 [取得] 兩家近 1 年股價走勢比較
  🤔 [分析] 綜合以上資料生成比較報告
```

### Feature 4：個人投資 Dashboard

```
┌───────────────────────────────────────────────────┐
│ 🧚 Navi — Stock AI Analyzer            [🔍 搜尋] │
├───────────────────────────────────────────────────┤
│                                                   │
│ 💬 AI 對話                                        │
│ ┌───────────────────────────────────────────────┐ │
│ │ 🧚 根據分析，台積電目前技術面偏多...           │ │
│ │    建議關注 $180 支撐位...                     │ │
│ └───────────────────────────────────────────────┘ │
│                                                   │
│ ┌────────────────┐  ┌──────────────────────────┐  │
│ │ 📈 K 線圖       │  │ 📋 關鍵指標              │  │
│ │                 │  │  PE     : 25.3           │  │
│ │   ~~~~/\~~~     │  │  RSI    : 62.4           │  │
│ │   ~~/    \~~/   │  │  MACD   : 看多           │  │
│ │   /       \/    │  │  MA20   : $175.2         │  │
│ └────────────────┘  └──────────────────────────┘  │
│                                                   │
│ 📰 相關新聞                                       │
│ • 台積電法說會重點整理...              2 小時前    │
│ • AI 晶片需求持續成長...              5 小時前    │
│ • 外資連三買 半導體族群回溫...        1 天前      │
└───────────────────────────────────────────────────┘
```

---

## 6. 專案結構

```
navi/
├── backend/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # 環境變數設定
│   ├── requirements.txt
│   ├── Dockerfile
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── chat.py            # 對話 API（含 SSE streaming）
│   │   │   ├── stock.py           # 股票數據 API
│   │   │   └── knowledge.py       # 知識庫管理 API
│   │   └── dependencies.py        # 依賴注入
│   │
│   ├── services/
│   │   ├── rag_service.py         # RAG pipeline 核心
│   │   ├── stock_service.py       # 股票數據擷取（yfinance）
│   │   ├── embedding_service.py   # Embedding 處理
│   │   ├── agent_service.py       # AI Agent（Phase 3）
│   │   └── news_service.py        # 新聞擷取
│   │
│   ├── tools/                     # LangChain Tools（給 Agent 使用）
│   │   ├── stock_price.py         # 查詢即時股價
│   │   ├── technical_analysis.py  # 計算技術指標
│   │   ├── fundamental_analysis.py# 基本面分析
│   │   └── knowledge_search.py    # 知識庫搜尋
│   │
│   ├── models/
│   │   ├── schemas.py             # Pydantic request/response models
│   │   └── prompts.py             # Prompt templates
│   │
│   ├── data_pipeline/
│   │   ├── ingest_knowledge.py    # 知識庫文件匯入腳本
│   │   ├── update_financials.py   # 定期更新財報數據
│   │   └── scrape_news.py         # 新聞爬蟲
│   │
│   ├── knowledge_base/            # 靜態知識文件（Markdown）
│   │   ├── technical_analysis/
│   │   ├── fundamental_analysis/
│   │   └── investment_theory/
│   │
│   └── tests/
│       ├── test_rag.py
│       ├── test_stock_service.py
│       └── test_agent.py
│
├── frontend/                      # Next.js Dashboard
│   ├── app/
│   │   ├── page.tsx               # 首頁 / Dashboard
│   │   ├── chat/
│   │   │   └── page.tsx           # AI 對話頁
│   │   └── stock/
│   │       └── [ticker]/
│   │           └── page.tsx       # 個股分析頁
│   ├── components/
│   │   ├── ChatPanel/             # 對話面板（SSE streaming）
│   │   ├── StockChart/            # K 線圖
│   │   ├── IndicatorCard/         # 技術指標卡片
│   │   └── NewsFeed/              # 新聞列表
│   └── lib/
│       └── api.ts                 # Backend API client
│
├── docker-compose.yml             # 本地開發環境
├── cloudbuild.yaml                # Cloud Run 部署設定
├── .github/
│   └── workflows/
│       └── deploy.yml             # CI/CD
└── README.md
```

---

## 7. API 設計

```yaml
# ========== AI 對話 ==========

POST   /api/chat
       Description: 與 Navi 對話（支援 SSE streaming）
       Body:
         message: string           # 使用者問題
         conversation_id?: string  # 對話 ID（多輪對話）
       Response: text/event-stream (SSE)

GET    /api/conversations
       Description: 取得歷史對話列表

GET    /api/conversations/{id}
       Description: 取得單一對話紀錄

# ========== 股票數據 ==========

GET    /api/stock/{ticker}
       Description: 取得股票概覽
       Response: { price, change, change_percent, volume, market_cap }

GET    /api/stock/{ticker}/technical
       Description: 技術面分析
       Response: { rsi, macd, kd, ma, bollinger, signals, summary }

GET    /api/stock/{ticker}/fundamental
       Description: 基本面數據
       Response: { pe, pb, roe, eps, revenue_growth, margins }

GET    /api/stock/{ticker}/chart?period=1y
       Description: 歷史價格（圖表用）
       Response: { dates[], prices[], volumes[] }

# ========== 知識庫管理 ==========

POST   /api/knowledge/ingest
       Description: 匯入文件到知識庫
       Body: { documents: [{ content, metadata }] }

GET    /api/knowledge/search?q=估值方法
       Description: 搜尋知識庫
       Response: { results: [{ content, metadata, score }] }

GET    /api/knowledge/stats
       Description: 知識庫統計
       Response: { total_documents, categories, last_updated }
```

---

## 8. 核心程式碼範例

### 8.1 Firestore Vector Search

```python
# backend/services/embedding_service.py

from google.cloud import firestore
from vertexai.language_models import TextEmbeddingModel

db = firestore.Client()
embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")

async def store_document(text: str, metadata: dict):
    """將文件 Embedding 後存入 Firestore"""
    embeddings = embedding_model.get_embeddings([text])
    vector = embeddings[0].values

    db.collection("knowledge").add({
        "content": text,
        "metadata": metadata,
        "embedding": firestore.VectorValue(vector),
        "created_at": firestore.SERVER_TIMESTAMP,
    })

async def search_similar(query: str, top_k: int = 5):
    """向量相似度搜尋"""
    query_embedding = embedding_model.get_embeddings([query])[0].values

    results = (
        db.collection("knowledge")
        .find_nearest(
            vector_field="embedding",
            query_vector=firestore.VectorValue(query_embedding),
            distance_measure=firestore.DistanceMeasure.COSINE,
            limit=top_k,
        )
        .get()
    )

    return [{"content": doc.get("content"), "metadata": doc.get("metadata")} for doc in results]
```

### 8.2 RAG + Gemini 分析

```python
# backend/services/rag_service.py

from vertexai.generative_models import GenerativeModel
from services.embedding_service import search_similar
from services.stock_service import get_stock_data

model = GenerativeModel("gemini-2.0-flash")

ANALYST_PROMPT = """
你是 Navi，一位專業的 AI 投資分析助手。
你的風格是精確、有條理，並且總是附上數據佐證。

分析時請遵守：
1. 先呈現關鍵數據
2. 結合知識庫的理論框架分析
3. 給出客觀判斷，標明看多/看空/中性
4. 附上參考來源
5. 最後加上免責聲明

相關知識庫內容：
{context}

即時股票數據：
{stock_data}

使用者問題：{question}
"""

async def analyze(question: str, ticker: str | None = None):
    # 1. RAG: 搜尋相關知識
    relevant_docs = await search_similar(question, top_k=5)
    context = "\n---\n".join([doc["content"] for doc in relevant_docs])

    # 2. 取得即時數據（如果有指定股票）
    stock_data = ""
    if ticker:
        data = await get_stock_data(ticker)
        stock_data = format_stock_data(data)

    # 3. 組合 Prompt，呼叫 Gemini
    prompt = ANALYST_PROMPT.format(
        context=context,
        stock_data=stock_data,
        question=question,
    )

    response = model.generate_content(prompt, stream=True)

    # 4. Streaming 回傳
    for chunk in response:
        yield chunk.text
```

### 8.3 AI Agent（Tool Calling）

```python
# backend/services/agent_service.py

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.tools import tool

@tool
def get_stock_price(ticker: str) -> str:
    """取得股票的即時價格和基本資訊"""
    import yfinance as yf
    stock = yf.Ticker(ticker)
    info = stock.info
    return f"價格: {info.get('currentPrice')}, PE: {info.get('trailingPE')}, 市值: {info.get('marketCap')}"

@tool
def analyze_technicals(ticker: str) -> str:
    """計算股票的技術指標（RSI, MACD, KD, 均線）"""
    # 計算各項技術指標...
    return formatted_indicators

@tool
def search_knowledge(query: str) -> str:
    """從知識庫搜尋相關投資理論、分析方法或財報資訊"""
    docs = search_similar(query, top_k=5)
    return "\n".join([doc["content"] for doc in docs])

@tool
def get_financial_report(ticker: str) -> str:
    """取得公司最近一季的財報摘要"""
    # 取得財報數據...
    return formatted_report

# 建立 Agent
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash")

agent = create_tool_calling_agent(
    llm=llm,
    tools=[get_stock_price, analyze_technicals, search_knowledge, get_financial_report],
    prompt=agent_prompt,
)

executor = AgentExecutor(agent=agent, tools=tools, verbose=True)
```

---

## 9. 開發排程

### Phase 1 — 基礎建設 & 第一個 RAG（第 1-2 週）

| #   | 任務                    | 產出                                  |
| --- | ----------------------- | ------------------------------------- |
| 1   | Python 環境建置         | pyproject.toml / requirements.txt     |
| 2   | FastAPI 專案初始化      | Hello World API                       |
| 3   | Firebase Admin SDK 串接 | 連上現有 Firestore                    |
| 4   | 撰寫 5-10 篇知識庫文件  | Markdown 檔案                         |
| 5   | Embedding Pipeline      | 文件 → chunks → embedding → Firestore |
| 6   | 基礎 RAG query          | 問問題 → 搜尋 → Gemini 回答           |

**✅ 驗收**：在終端機問「什麼是 RSI？何時該使用？」，得到基於知識庫的回答

---

### Phase 2 — 股票數據整合（第 3-4 週）

| #   | 任務               | 產出                        |
| --- | ------------------ | --------------------------- |
| 1   | yfinance 整合      | 即時股價、歷史數據          |
| 2   | 技術指標計算       | RSI, MACD, KD, MA, 布林通道 |
| 3   | 財報數據取得       | PE, PB, ROE, EPS            |
| 4   | RAG + 即時數據結合 | 回答時同時引用知識和數據    |
| 5   | 台股資料源         | 公開資訊觀測站串接          |

**✅ 驗收**：問「分析台積電」，得到結合即時數據 + 理論分析的回答

---

### Phase 3 — AI Agent + Streaming API（第 5-7 週）

| #   | 任務                 | 產出                        |
| --- | -------------------- | --------------------------- |
| 1   | LangChain Tools 封裝 | 4-5 個 Tool                 |
| 2   | Agent 實作           | 自動選擇工具的 AI Agent     |
| 3   | SSE Streaming 回應   | FastAPI SSE endpoint        |
| 4   | 多輪對話記憶         | Conversation memory         |
| 5   | Docker 化            | Dockerfile + docker-compose |
| 6   | Cloud Run 部署       | 後端上線                    |

**✅ 驗收**：API 上線，用 curl/Postman 測試 streaming 對話

---

### Phase 4 — 前端 Dashboard（第 8-10 週）

| #   | 任務             | 產出               |
| --- | ---------------- | ------------------ |
| 1   | Next.js 專案建置 | 基本頁面路由       |
| 2   | Chat UI          | Streaming 對話介面 |
| 3   | 股票圖表         | K 線圖 + 技術指標  |
| 4   | Dashboard 頁面   | 關鍵數據一覽       |
| 5   | 認證整合         | Firebase Auth      |
| 6   | Vercel 部署      | 前端上線           |

**✅ 驗收**：完整的 Web App，可以登入、對話、查看圖表

---

### Phase 5 — 進階功能（第 11-12 週）

| #   | 任務            | 產出             |
| --- | --------------- | ---------------- |
| 1   | 新聞爬蟲        | 自動抓取財經新聞 |
| 2   | Cloud Scheduler | 定時更新資料     |
| 3   | 自選股清單      | 使用者追蹤股票   |
| 4   | 知識庫持續擴充  | 更多文件和論文   |
| 5   | 效能優化        | Cache, 回應速度  |

---

## 10. 費用預估

### 開發期（~$0/月）

```
Firebase Firestore          → 免費額度（50K reads/day）
Gemini 2.0 Flash API        → 免費額度（1,500 requests/day）
text-embedding-004           → 免費額度
Cloud Run                    → 免費額度（200萬次 requests/month）
Vercel                       → 免費方案
GitHub                       → 免費
──────────────────────────────────────────────
總計：$0/月
```

### 上線後 — 個人使用（~$5-15/月）

```
Firebase Firestore           → ~$0-5（低用量）
Gemini API                   → ~$3-5（超出免費額度部分）
Cloud Run                    → ~$3-5（低 traffic）
Vercel                       → 免費
──────────────────────────────────────────────
總計：~$5-15/月
```

### 上線後 — 多人使用（~$15-30/月）

```
Firebase Firestore           → ~$5-10
Gemini API                   → ~$5-10
Cloud Run                    → ~$5-10
Vercel                       → 免費
──────────────────────────────────────────────
總計：~$15-30/月
```

---

## 11. 風險與對策

| 風險            | 影響                 | 對策                                            |
| --------------- | -------------------- | ----------------------------------------------- |
| AI 幻覺         | 生成不正確的財務數字 | 數字一律從 API 取得，不讓 LLM 自行生成          |
| 法律風險        | 投資建議的責任       | 加入免責聲明，明確標示「僅供參考」              |
| 資料時效        | 財報過期             | 排程自動更新 + 顯示資料日期                     |
| yfinance 限流   | API 請求被擋         | 加入 Cache 層 + Rate Limiter                    |
| Scope Creep     | 功能膨脹             | 每個 Phase 有明確驗收標準，完成後才進入下一階段 |
| Gemini API 變動 | API 介面改變         | 透過 LangChain 抽象層隔離，方便切換 LLM         |

---

## 12. 技能成長地圖

```
你會學到的技術：

Phase 1 ──▶ Python 基礎、FastAPI、Embedding、Vector DB、RAG Pipeline
Phase 2 ──▶ 資料處理（Pandas）、外部 API 整合、技術指標計算
Phase 3 ──▶ LangChain Agent、Tool Calling、SSE Streaming、Docker、GCP 部署
Phase 4 ──▶ 前後端整合、即時串流 UI、資料視覺化（K 線圖）
Phase 5 ──▶ 爬蟲、排程任務、系統維運、效能優化
```

---

## 13. 下一步

- [ ] 建立 GitHub Repo `navi`
- [ ] 初始化 Python 環境（FastAPI + LangChain）
- [ ] 撰寫第一批知識庫文件（3-5 篇技術分析基礎）
- [ ] 完成第一個 RAG Query：問問題 → 回答

---

> 🧚 _"Hey! Listen!"_ — Navi 已準備好陪你冒險了。
