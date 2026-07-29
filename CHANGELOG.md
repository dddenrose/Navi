# Changelog

本文件記錄 Navi 專案的所有重要變更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)，
版本號遵循 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

---

## [Unreleased]

### Fixed（2026-07-29 個股頁走勢圖修復）

- **個股頁的收盤走勢圖從未被畫出來**：`Stock.tsx` 的 `PriceChart` 以 `priceData.history` 為渲染條件，但 `GET /api/stock/{ticker}` 的 `StockOverview` 從來沒有這個欄位；前端 `StockPrice.history?` 宣告成 optional，TypeScript 因此不報錯，整段圖表淪為無聲的死碼。修法是改由技術面端點供給序列——`get_technical_indicators()` 本來就抓了完整 OHLCV 才能算指標，收盤價算完即丟。
  - `TechnicalIndicators` / `TechnicalResponse` 新增 `history: list[PricePoint]`（`{date, close}`，由舊到新）。
  - 前端刪除誤導的 `StockPrice.history?`，改讀 `technicalData.history`。

### Added（2026-07-29 個股頁走勢圖修復）

- **走勢圖期間切換**：1個月 / 3個月 / 6個月 / 1年，對應 `GET /api/stock/{ticker}/technical?period=`。技術指標改由獨立 effect 依 `[symbol, chartPeriod]` 抓取，切換期間只重打這一支，報價與基本面等區塊不重載也不閃爍。

### Changed（2026-07-29 個股頁走勢圖修復）

- **技術指標的計算範圍與圖表期間脫鉤**：新增 `_PERIOD_SPEC` 對照表，後端一律以 ≥1 年的資料計算指標，`period` 只決定回傳給前端畫圖的長度。否則使用者把圖切到 1mo 時，MA60 等長週期指標會因樣本不足整排變成 `null`。實測 2330.TW 在 1mo/3mo/6mo/1y 下 MA60 恆為 2346.03、RSI 恆為 35.2。附帶效果是原本 `3mo` 僅 63 根、MA60 幾乎踩在 60 根下限的問題一併消失。未知的 `period` 值仍原樣透傳給 yfinance 並回傳整段序列，維持既有行為。

### Removed（2026-07-28 功能收斂：策略回測頁下架，能力收回 Chat）

- **移除 `/backtest` 頁面與 REST 端點**：刪除 `frontend/src/pages/Backtest.tsx`、`backend/api/routes/backtest.py`（含 `POST /api/backtest`、`GET /api/backtest/strategies`），連同 `lib/api.ts` 的 `runBacktest` / `getStrategies` 與型別、`Layout` 側邊欄項目、`Dashboard` 入口卡、`rate_limit.backtest_limiter`、`feature_access` 的 `backtest` feature key 與 `quota_service.FEATURE_DAILY_LIMITS` 的 backtest 額度。
  - **理由**：(1) 該功能限 `pro` 以上，而訪客與新註冊皆為 `free`，導覽列與 Dashboard 會直接濾除 → 在 Live Demo 上對任何訪客都不可見，展示價值為零；(2) 能力與 Chat 的 `run_strategy_backtest` agent tool 完全重疊，且 agent 路徑會強制搭配知識庫解讀（夏普／過度擬合），體驗優於裸表單；(3) 固定參數、單標的、全額進出的三個教科書策略，其量化說服力遠低於 Screener 已有的 8.4 年 momentum 回測與 T+5/20/60 forward tracking，並列反而稀釋後者。
- **保留（未受影響）**：`services/backtest_service.py`、`tools/backtest_tool.py`、`tests/test_backtest_service.py`、agent 的 `run_strategy_backtest` tool 與 backtest 意圖分類、知識庫 `tool_interpretation/backtest_results.md`、`scripts/backtest_momentum.py` 與 Screener 的 `backtested` 揭露。回測能力僅改為單一入口（Chat），未刪除。
- **線上資料**：Firestore `feature_access_configs/backtest` 文件不再被 `FEATURE_ORDER` 讀取，成為孤兒 doc；未刪除，保留以便日後復原。

### Added（2026-07-07 可驗證性批次：回測重建 + 實績追蹤）

- **Momentum 回測腳本重建**：`backend/scripts/backtest_momentum.py` 補回 repo（原腳本遺失）。指標口徑對齊線上 screener（Wilder RSI、SMA60/120、120 交易日相對強度），月底訊號→次一交易日開盤成交（無 look-ahead）、30bps 單邊成本，支援 `--rebalance/--top/--start/--end/--cost-bps/--limit/--exec`，輸出 equity curve CSV 與 yfinance 快取。
  - **重跑結論：舊宣稱數字不可重現**。忠實重建版 2018-03~2026-07 為 +214%（CAGR +14.7%，全期落後 ^TWII -4.5%/年），遠低於筆記舊宣稱 +668%；`--exec signal_close`（look-ahead 對照）亦僅 +313%。交易級統計（勝率/賺賠比）兩版高度吻合 → 規則邏輯一致、差異在組合層執行假設。MOMENTUM_BACKTEST_NOTES 已將舊數字標記失效並新增第八章重建結果。
- **Screener picks 實績追蹤（forward tracking）**：`services/screener/picks_tracker.py` 以報告日還原收盤為基準，追蹤每個 pick 的 T+5/T+20/T+60 交易日報酬、相對 ^TWII 超額、期間最高/最低，寫回 pick doc `tracking` 欄位；聚合統計（勝率/平均報酬/超額/依 final_grade 分層）寫入 `screener_tracking/{profile}`。無倖存者偏差與 look-ahead，為策略有效性的乾淨證據來源。
  - **API**：`POST /api/screener/track`（Scheduler token 保護，每日盤後觸發）、`GET /api/screener/tracking/summary?profile=`。
  - **排程**：`setup_screener_scheduler.sh` 新增 `screener-track` job（平日 16:30 Asia/Taipei）。
  - **前端**：Screener 頁新增「推薦實績追蹤」面板（T+5/20/60 樣本數、勝率、平均報酬、超額大盤）；pick drawer 新增「發布後實績」區塊。
  - **測試**：`tests/test_screener_tracking.py`（15 項，純計算，無網路/Firestore）。
  - 已對既有 21 份報告回填完成（425 個推薦事件）。
- **Screener Stage 3 降級為 gemini-2.5-flash**：新增 `settings.screener_llm_model`（預設 `gemini-2.5-flash`，可用環境變數 `SCREENER_LLM_MODEL` 覆寫），Stage 3 解讀層改讀此設定，不再共用 chat 的 `gemini_model_name`。實測 Pro 每檔約 US$0.030（76% 為 thinking tokens），Flash 每檔約 US$0.0054 → 排程 LLM 成本降約 5.5 倍（月估 US$8-9 → 約 US$2）。解讀品質經真實 picks 煙霧測試驗證（structured output、敘事數字約束均正常）。

### Added（2026-07-07 產品審查修正批次）

- **投資組合交易紀錄與已實現損益**：新增 `POST/GET /api/portfolio/transactions` 與 `/transactions/estimate`。買賣交易自動計算台股手續費（0.1425%、最低 NT$20）與賣出證交稅（0.3%），以平均成本法維護持股（買入費用計入成本、賣出實現損益含費稅），前端 Portfolio 頁新增「記錄交易」模態框、已實現損益卡與交易紀錄表。
- **共用 TWSE 欄位解析層** `services/twse_parsers.py`：T86（19 欄新版 schema）與 MI_MARGN（16 欄）的唯一欄位對應來源，以 2026-07-02 真實 API 回應建立 fixture 回歸測試（`tests/test_twse_parsers.py`）。
- **模型分層（成本控制）**：free 層 chat 改用 `gemini-2.5-flash`，pro/unlimited/admin 用 `gemini-2.5-pro`（`config.model_for_tier`）。
- **回測/選股額度與限流**：`/api/backtest` 新增每日額度（free 5 / pro 50 次，`quota_service` feature-scoped 計數）與每分鐘限流（5/min，兼作 quota fail-open 時的硬上限）；screener 端點加 router 層限流。
- **回測模型假設揭露**：`BacktestResult.notes` 回傳成交假設、費稅、還原股價與夏普比率口徑，前端與 Agent 工具一律顯示。
- **測試**：新增 `test_backtest_service.py`（10 項，成交模型/費稅/指標完整性）、`test_portfolio_service.py`（13 項，平均成本/已實現損益帳務）、`test_conversation_ownership.py`（5 項，IDOR 防護）、`test_twse_parsers.py`（12 項）。

### Fixed（2026-07-07 產品審查修正批次）

- **【嚴重】T86 三大法人欄位錯位**：舊程式以 12 欄舊版 schema 解析現行 19 欄回應，導致「投信買賣超」實際顯示的是外資自營商、「自營商」實際是投信、合計淨額錯位。已以真實回應核對修正（外資=外陸資+外資自營商，與三大法人合計自洽）。
- **【嚴重】MI_MARGN 融資融券欄位錯誤**：融券買進/賣出對調（row 8/9）、screener 誤用「前日」融券餘額（row 11）當今日餘額、資券互抵誤用融券限額欄（row 13）。三處消費端統一改走 `twse_parsers`。
- **Chat SSE 中斷永久卡死**：`streamChat` 無 try/catch，行動網路斷線後輸入框永久鎖死。加 try/catch/finally 強制復位並顯示中文重試提示。
- **對話歷史 IDOR**：`load_history`/`save_history` 未驗證擁有權，可用他人 conversation_id 注入/續寫歷史（含持股 PII）。已加 user_id 擁有權檢查。
- **回測 look-ahead bias**：訊號當日收盤成交改為「次一交易日開盤 ± 0.1% 滑價」成交；補最低手續費 NT$20；夏普比率扣年化 1.5% 無風險利率；期間 <1 年時對年化報酬附外推警語。
- **估值方法論失真**：歷史 PE 改以「未還原股價 ÷ 各年度 EPS（point-in-time，年報淨利/流通股數近似）」計算；移除「當前 PE ±30%」fallback（數學上恆等於「現價=合理價」，具誤導性），資料不足時不給價位帶。
- **RSI 與券商不一致**：`stock_service` 與回測引擎的 RSI 從 SMA 改為 Wilder 平滑（ewm alpha=1/14），與看盤軟體一致；KD 對連續一字板（分母為 0）視為中性 50。
- **RAG 檢索性幻覺**：`search_similar` 加 COSINE distance 門檻（0.45）並回傳分數，無相關內容時明確告知 LLM 不得引用知識庫；知識庫截斷改在段落邊界（600→1200 字）。
- **錯誤訊息品質**：前端不再顯示後端原始 body/HTML（改中文可行動訊息）、Login 的 Firebase 錯誤碼在地化、Stock 分頁失敗顯示提示而非空白、SSE 錯誤事件不再洩漏內部例外字串。
- **手機可用性**：Portfolio/Chat 的 hover-only 刪除鈕在觸控裝置改為常駐可見。

### Changed（2026-07-07 產品審查修正批次）

- **法遵三層一致化**：技術分析工具的「🛑 建議停損」改為「📉 趨勢警戒參考位」教育性描述並移除「風險報酬比」輸出；知識庫 persona 範例移除「停損設在 950/分批 30-30-40/設定目標價」等投顧式示範；agent prompt reasoning_process 同步修正；Screener「建議買進區」改「估值偏低參考區（非買進建議）」。
- **免責聲明改由系統保證**：後端串流結束時自動補上免責聲明（不再依賴 LLM 自律）；Chat/Stock/Screener/Portfolio/技術分析頁加常駐免責與資料時效聲明。
- **全站信任訊號**：Stock 頁顯示「盤中/收盤 · 截至日期 · 來源」；Citations 顯示資料取得時間；漲跌配色全站統一為台股慣例（紅漲綠跌），含權益曲線與價格圖。
- **Tier 價值重新對齊**：`stock`（便宜的 deterministic 查詢）開放 free 層作為轉換漏斗；貴的 chat 由 Flash+額度控制、backtest/screener 維持付費層。FeatureGuard 與額度用盡處加升級引導文案。
- **文件對齊現實**：PROPOSAL 費用預估改以 Gemini 2.5 分層模型重算；標注 Phase 6 快照/績效曲線未實作；MOMENTUM_BACKTEST_NOTES 加註腳本缺失與倖存者偏差警告。

### Added

- **使用者額度與權限管理系統**：新增 4 個 tier（free/pro/unlimited/admin）的每日訊息額度與每分鐘速率限制，所有 chat 請求需通過 `quota_service.check_and_consume` 原子性扣額。
  - **後端**：`services/quota_service.py`（Firestore Transaction + Asia/Taipei 自然日重置 + 失敗開放）、`api/routes/admin.py`（後台 API：使用者管理、額度設定、使用統計、Audit Log）、`api/dependencies.require_admin` 透過 Firebase custom claims + Firestore 雙重檢查。
  - **前端**：`/admin` 後台（總覽 / 使用者 / 額度設定 / Audit Log）、Chat 頁面額度徽章 `QuotaBadge`、429 額度耗盡時顯示警示並停用輸入。
  - **管理工具**：`backend/scripts/seed_quota_configs.py`（初始化 tier 設定）、`set_admin.py`（提升 admin）、`set_tier.py`（切換 tier 供本地驗證）。
  - **新 API**：`GET /api/chat/quota`、`/api/admin/me`、`/api/admin/users`、`/api/admin/quota-configs`、`/api/admin/usage/summary`、`/api/admin/logs`。

### Fixed

- **台股三大法人單位錯誤**：TWSE T86 API 回傳單位為「股」，先前直接顯示為「張」導致數值膨脹 1000 倍（例如「外資買超 3,677,223 張」應為 3,677 張）。`institutional_service` 統一在資料來源換算成張。
- **yfinance `dividendYield` 二次放大**：yfinance 0.2.40+ 將 `dividendYield` 從小數（0.025）改為百分比（2.5），下游 `*100` 顯示會變成 250%。新增 `_normalize_yield()` 在資料源頭統一正規化為小數。
- **成交量單位標註**：`stock_price` 工具與 `format_stock_data_for_prompt` 在 volume 數值補上「股」字尾，避免 LLM 在台股情境誤稱為「張」。

### Changed

- **ThinkingPanel**：展開區塊移除多餘左側框線。
- **Backtest 資金欄位**：`step` 改為 `any`，輸入更彈性。

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
