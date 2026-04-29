# Changelog

本文件記錄 Navi 專案的所有重要變更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)，
版本號遵循 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

---

## [Unreleased]

> 尚未發布的變更將記錄於此。

---

## [0.5.0] - 2026-03-09

### Added

- **知識庫大幅擴充**：從 13 份文件擴充到 **24 份**，分類從 3 大類擴充到 **8 大類**
  - 新增 `taiwan_market/`：台股交易機制、籌碼資料來源、現股當沖規則
  - 新增 `macro/`：總體指標（利率、匯率、景氣循環）
  - 新增 `agent_persona/`：投資哲學與回覆風格指引
  - 新增 `compliance/`：免責聲明、風險提醒模板
  - 新增 `tool_interpretation/`：回測 / 分析輸出解讀眉角
  - `investment_theory/` 新增 `behavioral_finance.md`、`portfolio_theory.md`、`etf_passive_investing.md`
- **Prefetch 模式自動引用 KB**：`entry_analysis` / `comprehensive_analysis` 意圖現在會自動執行 `search_knowledge`，並在系統提示中強制要求「以「根據知識庫說明」「概念上需注意」「台股實務上」等用語引用 KB」
- **ThinkingPanel**：前端新增 Agent 思考過程串流顯示元件
- **混合式意圖分類器**：規則 fast path + LLM fallback 兩階段分類

### Changed

- **Agent 框架升級**：從 LangChain `AgentExecutor` 重構為 LangGraph `create_react_agent`，狀態管理與串流體驗更佳
- **Prefetch System Prompt 強化**：reasoning_process 新增「KB 眉角檢核」步驟（RSI 鈍化、法人單位張/股、目標價非承諾、行為偏誤）
- **`<tool_guide>` 新增 `<knowledge_base_usage>`**：列出 6 種應主動呼叫 `search_knowledge` 的觸發條件
- **Ticker 解析強化**：新增 lazy match + lookahead pattern，可正確擷取「幫我分析聯發科未來目標價格?」等格式
- **`ingest_knowledge.py` CATEGORY_MAP**：擴充以涵蓋 8 大新分類
- **`conversation_service.py`**：可讀性與結構性改善
- **README 全面更新**：根目錄 / backend / frontend README 全部對齊新架構（24 份 KB、8 大分類、LangGraph、9 工具）

### Removed

- 移除已合入 `agent_service.py` 的舊 `rag_service.py`（功能已整合至 agent + knowledge_search tool）

---

## [0.4.0] - 2026-03-08

### Added

- **ErrorBoundary 元件**：全域 + 每頁獨立隔離，防止任一頁面錯誤導致整個 App 白屏；提供中文 fallback UI 與「重試」按鈕

### Changed

- **Stock.tsx 垂直切割**：從 1442 行縮減至 405 行（slim coordinator），UI 邏輯分拆為四個獨立 tab 元件
  - `pages/stock/StockOverviewTab.tsx`：概覽頁（成交量、市值、52週高低）
  - `pages/stock/StockTechnicalTab.tsx`：技術分析頁（RSI、MACD、KD、MA、布林通道、RSI 圖表、支撐/阻力、費波那契、停損建議）
  - `pages/stock/StockFundamentalTab.tsx`：基本面頁（估值指標 12 格、便宜/合理/昂貴價格）
  - `pages/stock/StockInstitutionalTab.tsx`：籌碼面頁（三大法人、融資融券）
- **新增 `lib/format.ts`**：集中管理所有數字格式化工具（`fmtNum`、`fmtPct`、`fmtPrice`、`fmtLarge`、`fmt`、`pnlColor`、`pnlBg`），消除 Portfolio / Backtest / Stock 重複定義
- **新增 `types/stock.ts`**：集中管理股票相關型別（`StockPrice`、`Technicals`、`Fundamentals`、`InstitutionalData`、`MarginData` 等）
- **`api.ts` 重構**：新增 `apiFetch<T>` 泛型 wrapper，消除 12+ 處重複的 fetch / error-unwrap / JSON parse 樣板
- **`PriceChart` / `RsiChart` 效能修正**：CSS 變數讀取從每次 render 的 `getComputedStyle` 改為 `useMemo` keyed on `theme`，移除不必要的 layout reflow
- **`Portfolio.tsx` / `Backtest.tsx`**：移除本地 `fmt` / `pnlColor` 重複定義，改從 `@/lib/format` 匯入

---

## [0.3.0] - 2026-03-08

### Added

- **股票搜尋自動完成**：輸入代碼或中文名稱即時顯示下拉選單，支援 TWSE / TPEx 全部股票
- **技術分析高價值欄位**：前端新增支撐/阻力位表格、費波那契回檔、停損建議與風報比面板
- **籌碼面分頁**：新增「籌碼面」Tab，包含三大法人買賣超（逐日明細 + 匯總卡片）與融資融券數據（餘額、增減、使用率）
- **法人買賣超 API**：`GET /api/stock/{ticker}/institutional` 端點，取得 TWSE/TPEx 三大法人逐日買賣超資料
- **融資融券 API**：`GET /api/stock/{ticker}/margin` 端點，取得 TWSE 融資融券逐日明細
- **52 週高低點**：概覽頁新增 52 週最高 / 最低價顯示

### Changed

- **TechnicalResponse schema 擴充**：新增 `supports`、`resistances`、`fibonacci_levels`、`swing_high`、`swing_low`、`stop_loss`、`stop_loss_note`、`risk_reward_note` 欄位
- **Stock.tsx 完整重構**：4 個分頁（概覽 / 技術分析 / 基本面 / 籌碼面），台股 UI 適配（NT$ 前綴、上市/上櫃標籤）

---

## [0.2.0] - 2026-03-07

### Added

- **動態台股代碼解析**：串接 TWSE + TPEx Open APIs，支援中文名稱 → 代碼查詢（2339 檔股票，24 小時快取）
- **支撐壓力分析**：5 種來源（MA、布林通道、波段高低點、Fibonacci 回撤、心理關卡）
- **基本面估值**：PE 百分位 × EPS 計算便宜/合理/昂貴價格
- **停損建議**：自動計算停損點位與風險報酬比
- **意圖分類前處理器**：LLM 分類使用者意圖（10 種類別），依分類決定 Prefetch 或 Agent 模式
- **雙模式分派架構**：Prefetch 模式（平行工具呼叫 → 組合報告）vs Agent 模式（AgentExecutor 自主決策）
- **信心度評分**：分類器輸出 confidence 分數，低信心度自動 fallback 至 Agent 模式
- **對話歷史 API**：`GET /api/chat/conversations/{id}/messages` 端點，含所有權驗證
- **前端對話載入**：選擇對話時自動載入歷史訊息

### Changed

- **AGENT_SYSTEM_PROMPT 瘦身**：從 ~50 行精簡至 ~10 行，每次請求節省 ~200 tokens
- **分類 Prompt 強化**：新增 7 個 few-shot 範例 + confidence 欄位
- **Prefetch 推理引導**：新增 6 步 Chain-of-Thought 分析框架（技術面→基本面→籌碼面→新聞→矛盾檢查→整合結論）
- **意圖提示升級**：`_INTENT_HINTS` → `_INTENT_TOOL_DIRECTIVES`，改為系統層級的指令式語言
- **Prompts 統一**：models/prompts.py 與 agent_service.py 共用一致的 Navi 角色定義
- **工具輸出格式更新**：技術分析含支撐壓力/停損、基本面含估值三區間

---

## [0.1.0] - 2026-03-02

### Added

- 專案初始架構：FastAPI 後端、LangChain RAG 流程、Cloud Run 部署設定
- `EmbeddingService`：使用 Vertex AI `text-multilingual-embedding-002` 產生向量並存入 Firestore
- `RAGService`：結合 Firestore 向量搜尋與 Gemini，實現知識庫問答
- `StockService`：透過 `yfinance` 取得即時與歷史股票資料
- `AgentService`：LangChain Agent 整合多工具（技術分析、基本面分析、知識搜尋、股價查詢）
- `ConversationService`：Firestore 多輪對話歷史管理
- 知識庫文件：技術分析（MA、MACD、RSI）、基本面分析、風險管理
- 資料管線 `ingest_knowledge.py`：將知識庫 Markdown 文件分塊向量化並寫入 Firestore
- API 路由：`/chat`（SSE 串流）、`/stock`、`/knowledge`
- CLI 工具 `cli.py`：本地端互動測試

### Changed

- Phase 1 重構：調整專案目錄結構，提升可讀性與可維護性（services / tools / models / api 分層）

### Fixed

- 修正 `EmbeddingService` 從 Firestore 取回文件時，`content` 與 `metadata` 欄位解析錯誤的問題

---

[Unreleased]: https://github.com/dddenrose/Navi/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/dddenrose/Navi/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/dddenrose/Navi/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dddenrose/Navi/releases/tag/v0.1.0
