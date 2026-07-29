# 設計筆記

本文記錄 Navi 的技術選型理由、以及開發過程中「原本打算這樣做、後來改成那樣」的取捨。
內容以**目前程式碼實作為準**；純粹的實作前企劃書已於 2026-07 移除（可在 git 歷史中找到）。

架構與資料流細節見 [`SCREENER_ARCHITECTURE.md`](SCREENER_ARCHITECTURE.md)；
回測方法論與實證見 [`MOMENTUM_BACKTEST_NOTES.md`](MOMENTUM_BACKTEST_NOTES.md)。

---

## 1. 為什麼做這個

台股散戶要判斷一檔股票，資料散在證交所、櫃買、期交所、財報與新聞裡，各自格式不同；
坊間的 AI 選股工具則多半直接讓 LLM 給結論，看不到它憑什麼。

Navi 想同時解決兩件事：**把分散的台股資料整合成一次問答就能拿到的分析**，以及
**讓每個結論都能被追溯到來源**——數字來自 API、方法論來自知識庫、選股來自規則引擎。

---

## 2. 技術選型與理由

### 後端

| 類別      | 選擇                          | 理由                                             |
| --------- | ----------------------------- | ------------------------------------------------ |
| 語言      | Python 3.12                   | AI / 資料處理生態最完整                          |
| Web 框架  | FastAPI                       | 原生非同步（平行工具呼叫的前提）、型別安全、自動 API 文件 |
| AI 框架   | LangChain + LangGraph         | Tool calling 抽象、ReAct agent 現成               |
| LLM       | Gemini 2.5 Flash / Flash-Lite | 依 tier 分層選模型控成本，見下方 §3               |
| Embedding | text-embedding-004            | Google 原生，與 Firestore Vector 同生態           |
| Vector DB | Firestore Vector Search       | 專案已有 Firebase，零額外基礎設施成本             |

### 前端

| 類別     | 選擇                     | 理由                                     |
| -------- | ------------------------ | ---------------------------------------- |
| 框架     | React 19 + TypeScript    | 純 client-side SPA，不需要 SSR           |
| 建構工具 | Vite 7                   | HMR 快、bundle 輕                        |
| 樣式     | Tailwind CSS 4           | 不引入 component library，減少相依        |
| 圖表     | Recharts                 | 需求只到折線 / 面積圖，不需要專業 K 線庫  |
| 狀態管理 | Zustand                  | 只有 auth / theme / quota 三塊全域狀態    |
| 串流     | Server-Sent Events       | LLM 單向串流，不需要 WebSocket 的雙向能力 |

### 基礎設施

| 類別     | 選擇                        | 理由                                  |
| -------- | --------------------------- | ------------------------------------- |
| 後端部署 | Cloud Run (asia-east1)      | 按量計費，冷啟動可接受                 |
| 前端部署 | Firebase Hosting            | 與 Firebase Auth 同專案，CDN 免費額度大 |
| 認證     | Firebase Auth               | 前後端共用同一份 JWT 驗證              |
| CI       | GitHub Actions              | 每次 push / PR 跑後端測試              |
| CD       | Cloud Build → Cloud Run     | push 到 `main` 自動部署                |
| 排程     | Cloud Scheduler             | 選股管線的 run / track / notify 三個 job |

---

## 3. 後來改掉的決定

這節記錄選型當時想錯、實作後修正的地方。

**LLM 從 Gemini 2.5 Pro 降為 Flash / Flash-Lite。**
原本規劃用 Pro 換取推理品質。實測後發現：單次 chat 輸入 5k–20k tokens，Pro 約
US$0.02–0.15/則，Flash 低一個數量級，而在「工具已經把數字算好、LLM 只負責組織敘述」
的架構下，兩者的輸出品質差距遠小於成本差距。最終改為依 tier 選模型
（免費層 Flash-Lite、付費層 Flash，見 `config.model_for_tier`），把省下的成本
換成「免費層也能用完整功能」。

**放棄 component library。**
原本打算用 shadcn/ui 快速搭 dashboard，實際只用 Tailwind 手刻。原因是這個專案的
UI 元件數量不多但客製化程度高（圖表卡片、選股結果、額度徽章），套件反而帶來
覆寫成本。同理放棄了 lightweight-charts——需求只到折線圖，Recharts 已足夠。

**回測從獨立頁面退回成 agent tool。**
原本有一個 `/backtest` 前端頁面可以直接跑回測、看權益曲線。後來整頁下架，只保留
`run_strategy_backtest` 這個 agent tool。理由是：一張裸的績效表（年化 28%、
夏普 1.4）會讓人高估策略可信度，卻不會提醒使用者這裡面有倖存者偏差與參數過擬合。
做成 agent tool 之後，LLM 一定會搭配知識庫的「如何解讀回測輸出」來說明，
數字旁邊永遠帶著它的限制。這是刻意犧牲便利性換取正確性的取捨。

**選股的 AI 從「決策者」退成「翻譯者」。**
初期構想是讓 LLM 讀完各項指標後給出推薦。實作時改為：規則引擎完成篩選、評分、
估值與排序，LLM 只能改寫已經算好的數字。這讓每一檔推薦都可重現、可稽核，
也讓推薦實績追蹤（T+5/20/60 對比 TWII）變得有意義——因為選股邏輯是固定的。

---

## 4. 風險與對策

| 風險                | 對策                                                                 |
| ------------------- | -------------------------------------------------------------------- |
| AI 幻覺出數字       | 數字一律由工具 / API 產生，LLM 不得自行生成。選股敘述層有數字 token 白名單，違規即重試（`ai_evaluator.py` 零容忍門檻），重試耗盡改用 rule-based 敘述 |
| AI 幻覺出質性宣稱   | 業務背景類敘述（客戶、市占）在 UI 與 email 明示「由 AI 生成、未經查證」 |
| 回測失真            | 次一交易日開盤成交（消除 look-ahead）、計入台股費稅與滑價、明白揭露倖存者偏差 |
| 法律風險            | 全站免責聲明，不輸出具體買賣價位指令                                  |
| 資料時效            | 顯示資料日期；報價來源可切換即時 / T-1 收盤（`TW_QUOTE_PROVIDER`）     |
| 外部 API 限流       | 分層 TTL 快取（台股清單／報價 30 分鐘、yfinance info 5 分鐘）+ rate limiter |
| LLM 成本失控        | 每位使用者每日訊息額度（`quota_service`）+ 依 tier 選模型              |
| Gemini API 介面變動 | 透過 LangChain 抽象層隔離                                             |

---

## 5. 已知限制

誠實記錄目前撐不住的地方，這些不是 bug 而是尚未做到的工程強度：

- **前端無自動化測試**——型別檢查與 lint 有跑，但沒有單元測試
- **限流為 in-memory per-instance**——Cloud Run 冷啟動會歸零，換 IP 可繞過
- **排程失敗無告警**——Cloud Scheduler 觸發失敗目前只留 Cloud Logging 一筆紀錄
- **處置 / 全額交割股排除不完整**——依賴 TWSE 公告抓取，變更交易方法目前無資料源
- **選股回測的 universe 含倖存者偏差**——詳見 [`MOMENTUM_BACKTEST_NOTES.md`](MOMENTUM_BACKTEST_NOTES.md)
