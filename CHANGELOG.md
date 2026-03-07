# Changelog

本文件記錄 Navi 專案的所有重要變更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.0.0/)，
版本號遵循 [Semantic Versioning](https://semver.org/lang/zh-TW/)。

---

## [Unreleased]

> 尚未發布的變更將記錄於此。

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

[Unreleased]: https://github.com/dddenrose/Navi/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/dddenrose/Navi/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dddenrose/Navi/releases/tag/v0.1.0
