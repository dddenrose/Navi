# Navi 智能選股架構說明

本文說明 Navi「智能選股 / Screener」功能的系統架構、資料流與實作細節。內容以目前程式碼實作為準，重點是：AI 不直接黑箱決定推薦股票，而是由規則引擎先完成篩選、估值與排序，再由 AI 負責把結果轉譯成投資人看得懂的分析文字。

## 1. 架構總覽

```mermaid
flowchart TD
  A[Cloud Scheduler 排程] -->|X-Scheduler-Token| B["FastAPI /api/screener/run"]
  B --> C[services.screener.orchestrator.run_screener_async]

  C --> D[Stage 1: Universe Filter]
  D --> D1[yfinance history/info]
  D --> D2[TWSE 注意股 / 處置股排除]
  D --> D3[20 日均成交額與市值門檻]

  D --> E[Stage 2: Rule Engine]
  E --> E1[技術 / 動能指標]
  E --> E2[財報衍生指標]
  E --> E3[籌碼資料]
  E --> E4[產業 PE/PB 分布]
  E --> E5[Value 或 Momentum 規則組]

  E --> F[Stage 2.5: Valuation]
  F --> F1[EPS TTM x 產業 PE 區間]
  F --> F2[合理價低 / 中 / 高、買進區、上行空間]

  F --> G[每產業取 Top N 候選]
  G --> H{是否 skip_stage3?}
  H -->|否| I[Stage 3: Gemini AI 解讀]
  H -->|是| J[保留規則結果，略過 AI 解讀]

  I --> K["Firestore: screener_reports/{report_id}/picks"]
  J --> K

  K --> L["Frontend /screener"]
  K --> M["/api/screener/notify"]
  M --> N[SendGrid Email 給訂閱者]
```

主要檔案：

- `backend/api/routes/screener.py`：Screener API 入口，包含觸發、查詢報告、查詢單檔 pick、Email 訂閱與通知。
- `backend/services/screener/orchestrator.py`：管線協調器，串接 Stage 1、Stage 2、Stage 3，並將結果寫入 Firestore。
- `backend/services/screener/universe.py`：Stage 1 股票池粗篩。
- `backend/services/screener/factor_scorer.py`：Stage 2 指標組裝、規則引擎執行、產業內排名。
- `backend/services/screener/rules.py`：Value / Momentum 兩套規則定義。
- `backend/services/screener/valuation.py`：規則化合理價計算。
- `backend/services/screener/ai_evaluator.py`：Stage 3 AI 解讀。
- `backend/services/screener/email_sender.py`：Email 報告渲染與寄送。
- `frontend/src/pages/Screener.tsx`：前端智能選股頁面。
- `frontend/src/lib/api/screener.ts`：前端 API client。

## 2. API 與排程入口

```mermaid
flowchart LR
  A[Cloud Scheduler] --> B["POST /api/screener/run"]
  B --> C[run_screener_async]
  C --> D[Firestore 報告]
  A --> E["POST /api/screener/notify"]
  E --> F[send_report_email]
  F --> G[Email 訂閱者]
  H["Frontend /screener"] --> I["GET /api/screener/reports/latest"]
  H --> J["GET /api/screener/reports/{report_id}"]
  H --> K["GET/PUT /api/screener/subscriptions"]
```

`POST /api/screener/run` 使用 `X-Scheduler-Token` shared-secret 保護，預期由 Cloud Scheduler 呼叫。Request body 會指定：

- `profile`：`momentum` 或 `value`。
- `frequency`：`daily` 或 `weekly`。
- `top_per_industry`：每個產業最後保留幾檔。
- `skip_stage3`：是否跳過 LLM 解讀，通常用於本機驗證或省成本測試。
- `enable_chips`：是否啟用籌碼資料。
- `tickers`：可選，限制本次只跑特定股票池。

排程腳本位於 `scripts/setup_screener_scheduler.sh`，目前設計會建立 run 與 notify 類型的 Cloud Scheduler jobs。

## 3. Stage 1: Universe Filter

Stage 1 目標是用低成本規則把市場股票池縮小，只留下流動性與市值足夠、且沒有明顯交易異常的股票。

```mermaid
flowchart TD
  A[industry_data.json 股票清單] --> B[並行抓 yfinance history/info]
  B --> C[抓 TWSE 注意 / 處置清單]
  C --> D{是否在排除清單?}
  D -->|是| X[剔除]
  D -->|否| E{20 日均成交額 >= 5000 萬?}
  E -->|否| X
  E -->|是| F{市值 >= 50 億?}
  F -->|否| X
  F -->|是| G[UniverseRecord]
```

實作檔案：`backend/services/screener/universe.py`

預設門檻：

- `MIN_AVG_TURNOVER_TWD = 50_000_000`：20 日均成交額大於 5,000 萬台幣。
- `MIN_MARKET_CAP_TWD = 5_000_000_000`：市值大於 50 億台幣。
- `HISTORY_PERIOD = "8mo"`：抓 8 個月歷史資料，讓後續能計算 6 個月報酬、SMA120、相對強弱等指標。

輸出資料型別是 `UniverseRecord`，包含：

- `ticker`、`name`、`industry`
- `price`
- `market_cap`
- `avg_turnover_20d`
- `history`：下游 Stage 2 會重用，避免重抓股價。
- `info`：yfinance info，包含 PE、PB、EPS 等基礎欄位。

注意股 / 處置股資料來自 TWSE endpoint，實作上是 best-effort：如果 TWSE API 暫時失敗，不會阻塞整個選股流程。

## 4. Stage 2: Rule Engine

Stage 2 是目前智能選股的核心。它不是舊 proposal 中的 z-score 加權打分，而是規則化、可追蹤、可向使用者解釋的 rule engine。

```mermaid
flowchart TD
  A[UniverseRecord] --> B[組成 StockData]
  B --> C[計算技術 / 動能資料]
  B --> D[抓財報衍生指標]
  B --> E[抓籌碼資料]
  C --> F[計算產業 PE/PB 統計]
  D --> F
  E --> F
  F --> G[套用 RuleSet]
  G --> H[Must Pass 規則]
  G --> I[Bonus 規則]
  G --> J[Disqualifier 規則]
  H --> K[ScoringTrace]
  I --> K
  J --> K
  K --> L{qualified?}
  L -->|是| M[進入估值與排名]
  L -->|否| N[Reject 或 Watch]
```

實作檔案：

- `backend/services/screener/factor_scorer.py`
- `backend/services/screener/rules.py`
- `backend/services/screener/fundamentals_fetcher.py`
- `backend/services/screener/chips_data.py`

### 4.1 StockData 組裝

`factor_scorer.evaluate_universe()` 會把 Stage 1 的 `UniverseRecord` 轉成規則引擎使用的 `StockData`。

技術與動能指標包含：

- 3 個月報酬：`return_3m`
- 6 個月報酬：`return_6m`
- 6 個月相對大盤強弱：`rel_strength_6m`
- SMA60 / SMA120
- 5 日均量 / 20 日均量：`volume_ratio_5_20`
- RSI 14
- 60 日高點

財報衍生指標包含：

- 近 3 年平均 ROE
- 近 3 年營收 CAGR
- 近 3 年自由現金流為正的年數
- 近 4 季 EPS 為正的季數
- 負債比
- 流動比
- 近 4 季毛利率標準差
- 最新一季營收 YoY
- EPS TTM

籌碼資料目前主要用在 Momentum profile：

- 外資近 5 日累積買超
- 外資近 20 日累積買超
- 外資連續買超 / 賣超天數

### 4.2 Value Hunter 規則

Value profile 的設計偏向中長期價值與品質。必要規則全部通過、bonus 達門檻、沒有 critical disqualifier，才會變成 qualified pick。

Must Pass：

| ID  | 名稱         | 條件                              |
| --- | ------------ | --------------------------------- |
| V1  | 估值不貴     | PE 或 PB 任一低於產業中位數 x 1.2 |
| V2  | 獲利能力     | 近 3 年平均 ROE >= 12%            |
| V3  | 現金流真實   | 近 3 年自由現金流至少 2 年為正    |
| V4  | 財務安全     | 負債比 < 60%，且流動比 > 1.0      |
| V5  | 不在虧損循環 | 近 4 季 EPS 至少 3 季為正         |

Bonus：

| ID  | 名稱       | 條件                     |
| --- | ---------- | ------------------------ |
| VB1 | 成長性     | 營收 3 年 CAGR >= 8%     |
| VB2 | 毛利穩定   | 近 4 季毛利率標準差 < 2% |
| VB3 | 資金關注度 | 5/20 日量比 >= 1.0       |
| VB4 | 下檔保護   | 現金殖利率 > 2.5%        |

Disqualifier：

| ID  | 名稱              | 條件                     |
| --- | ----------------- | ------------------------ |
| VD1 | 連續虧損          | 近 4 季 EPS 為負季數過多 |
| VD2 | 處置股 / 全額交割 | TWSE 公布清單            |
| VD4 | 估值異常          | PE < 0 或 PE > 50        |

### 4.3 Momentum Rider 規則

Momentum profile 偏向趨勢、量能、相對強勢與籌碼延續。

Must Pass：

| ID  | 名稱         | 條件                                              |
| --- | ------------ | ------------------------------------------------- |
| M1  | 中期趨勢確立 | 收盤價 > SMA60 > SMA120                           |
| M2  | 相對大盤強勢 | 6 個月相對大盤報酬 > +5%                          |
| M3  | 量能配合     | 5/20 日量比 >= 1.0                                |
| M5  | 基本面不爛   | 近 4 季 EPS 至少 3 季為正，且近 3 年平均 ROE > 8% |

Bonus：

| ID  | 名稱         | 條件                     |
| --- | ------------ | ------------------------ |
| M4  | 籌碼面正向   | 外資近 20 日累積買超為正 |
| MB1 | 法人持續買進 | 外資連續買超 5 日以上    |
| MB2 | 業績配合     | 最近一季營收 YoY > 10%   |
| MB3 | 突破訊號     | 價格接近近 60 日高點     |
| MB4 | RSI 健康     | RSI 14 在 50-75 區間     |

Disqualifier：

| ID  | 名稱              | 條件                       |
| --- | ----------------- | -------------------------- |
| MD1 | 估值過熱          | PE > 產業中位數 x 2.0      |
| MD2 | 量價背離          | 價格創高但 RSI 明顯落後    |
| MD3 | 處置股 / 全額交割 | TWSE 公布清單              |
| MD4 | 籌碼背離          | 20 日買超，但近 5 日轉賣超 |

### 4.4 ScoringTrace

每檔股票跑完規則後，會得到 `ScoringTrace`。這是前端展示「為什麼推薦」的關鍵資料。

`ScoringTrace` 會記錄：

- `verdict`：`qualified` 或 `rejected`
- `final_grade`：`Strong Pick`、`Pick`、`Watch`、`Reject`
- `rejection_reason`
- `must_pass` 規則檢查結果
- `bonus` 規則檢查結果
- `disqualifier` 規則檢查結果
- `missing_data_count` 與 `missing_data_rule_ids`

資料缺失的處理策略：

- must pass 缺資料：保守視為不通過。
- bonus 缺資料：不給加分。
- disqualifier 缺資料：不觸發剔除。
- 若 must pass + bonus 中資料不足規則超過 2 條，即使其他條件看起來不錯，也會強制 reject，避免靠資料缺失取得推薦資格。

## 5. Stage 2.5: Valuation

估值邏輯集中在 `backend/services/screener/valuation.py`，由系統規則計算，不交給 LLM 編數字。

```mermaid
flowchart LR
  A[Qualified Pick] --> B[EPS TTM]
  A --> C[產業 PE P25 / Median / P75]
  B --> D[Fair Value = EPS x 產業 PE]
  C --> D
  D --> E[合理價 low / mid / high]
  E --> F[買進區上緣 = low x 1.05]
  E --> G[上行空間 = mid / 現價 - 1]
```

估值方法：

```text
fair_value = EPS TTM x 產業 PE 區間
```

輸出欄位：

- `fair_value_low`
- `fair_value_mid`
- `fair_value_high`
- `buy_zone_upper`
- `implied_upside_mid_pct`
- `data_used`
- `notes`

如果 EPS TTM 缺失、EPS 為負，或產業 PE 樣本不足，會回傳 unavailable 狀態，而不是產生不可靠估值。

## 6. 產業內排名與候選名單

Stage 2 會回傳所有 evaluated stocks，包含 qualified 與 rejected。真正送進下一階段的是 qualified stocks。

排名邏輯在 `factor_scorer._rank_within_industry()`：

- Value profile：優先 bonus 通過數多，其次 PE 較低，再其次市值較大。
- Momentum profile：優先 bonus 通過數多，其次 6 個月報酬較強。

最後由 `top_n_per_industry()` 每個產業取前 N 檔，避免推薦名單被少數熱門產業壟斷。

## 7. Stage 3: AI 解讀層

Stage 3 的角色是「解讀員」，不是「裁判」。

```mermaid
flowchart TD
  A[Top N Qualified Picks] --> B[建立 XML snapshot]
  B --> C[Gemini structured output]
  C --> D[narrative]
  C --> E[key_context]
  C --> F[warnings]
  C --> G[value_trap_check]
  D --> H[Pick interpretation]
  E --> H
  F --> H
  G --> H
```

實作檔案：

- `backend/services/screener/ai_evaluator.py`
- `backend/services/screener/prompts.py`

AI 會輸出 `StockInterpretation`：

- `narrative`：200-300 字投資邏輯解讀。
- `key_context`：3-5 條質性脈絡。
- `warnings`：2-4 條風險提醒。
- `value_trap_check`：`no_concern`、`watch` 或 `warning`。
- `value_trap_reason`：若有價值陷阱疑慮，說明原因。

AI 明確不做：

- 不重新決定是否入選。
- 不寫目標價。
- 不寫停損。
- 不寫信心分數。
- 不編造 trace 裡沒有的數字。

Momentum profile 會強制將 `value_trap_check` 設為 `no_concern`。

## 8. Firestore 資料模型

報告主文件：

```text
screener_reports/{report_id}
```

`report_id` 格式：

```text
YYYYMMDD-{frequency}-{profile}
```

範例：

```text
20260504-weekly-momentum
```

主文件欄位包含：

- `report_id`
- `generated_at`
- `profile`
- `frequency`
- `universe_size`
- `stage1_passed`
- `stage2_qualified`
- `final_count`
- `industries_covered`
- `duration_seconds`
- `status`

個股文件：

```text
screener_reports/{report_id}/picks/{ticker}
```

每個 pick 包含：

- `ticker`
- `name`
- `industry`
- `rank_in_industry`
- `industry_size`
- `final_grade`
- `verdict`
- `snapshot`
- `scoring_trace`
- `valuation`
- `interpretation`

## 9. 前端呈現

前端頁面位於 `frontend/src/pages/Screener.tsx`。

```mermaid
flowchart TD
  A[/screener 頁面] --> B[選擇 profile: Momentum / Value]
  A --> C[選擇 frequency: 日報 / 週報]
  B --> D[getLatestReport]
  C --> D
  D --> E[報告摘要]
  D --> F[產業 chips]
  D --> G[Pick cards]
  G --> H[Pick detail drawer]
  H --> I[AI 投資觀點]
  H --> J[估值帶狀圖]
  H --> K[數據快照]
  H --> L[規則引擎 trace]
  H --> M[丟到 Chat 深入問]
```

頁面功能：

- 切換 `Momentum Rider` / `Value Hunter`。
- 切換週報 / 日報。
- 顯示最新報告的報告編號、入選檔數、涵蓋產業、耗時。
- 依產業 chips 篩選。
- 個股卡片顯示：公司名稱、ticker、產業排名、等級、AI 摘要、現價、合理價中值、上行空間。
- 點開 drawer 後顯示：AI 投資觀點、警示、價值陷阱檢查、估值區間、數據快照、完整規則軌跡。
- 可將該檔股票與 Screener 結果帶入 Chat 頁面深入追問。

## 10. Email 訂閱與通知

Email 功能位於 `backend/services/screener/email_sender.py`。

資料集合：

```text
screener_email_subscribers/{user_id}
```

訂閱資料包含：

- `user_id`
- `email`
- `enabled`
- `profiles`
- `frequencies`

寄送流程：

```mermaid
flowchart LR
  A["POST /api/screener/notify"] --> B[找到最新 matching report]
  B --> C[list_active_subscribers]
  C --> D[render_email_html]
  D --> E[SendGrid]
  E --> F[使用者 Email]
```

退訂連結使用 HMAC token：

- `make_unsubscribe_token(user_id)` 產生 token。
- `/api/screener/unsubscribe?token=...` 驗證 token。
- 驗證成功後將訂閱者 `enabled` 設為 `False`。

若沒有設定 `SENDGRID_API_KEY`，寄信流程會進入 dry-run，只記錄 log，不會真的寄出。

## 11. 本機驗證方式

本機驗證腳本位於 `backend/scripts/run_screener_local.py`。

只跑 Stage 1 + Stage 2，跳過 LLM：

```bash
cd backend
uv run python scripts/run_screener_local.py --skip-stage3 --profile momentum
```

用較低門檻驗證資料管線：

```bash
cd backend
uv run python scripts/run_screener_local.py --skip-stage3 \
  --min-turnover 10000000 \
  --min-market-cap 0
```

只跑少數股票並使用較便宜模型測 Stage 3：

```bash
cd backend
uv run python scripts/run_screener_local.py --top 1 \
  --model gemini-2.5-flash \
  --no-persist \
  --tickers 2330.TW,2317.TW,2454.TW
```

## 12. 設計重點

這個功能的核心設計是「可解釋的主動推薦」。

1. 先用便宜、可控、可測試的規則縮小股票池。
2. 將推薦原因寫成 `ScoringTrace`，讓前端能展示每條規則的實際值與門檻。
3. 估值由系統公式計算，避免 LLM 編造目標價。
4. AI 只做質性解讀與風險整理，不負責決定推薦名單。
5. 每產業取 Top N，避免推薦結果集中在單一產業。
6. 前端把規則結果、估值、AI narrative 放在同一個 detail drawer 裡，讓使用者能快速理解「為什麼這檔被選出來」。

一句話總結：Navi Screener 是一條「排程掃市場 → 規則引擎篩選 → 系統估值 → AI 解讀 → Firestore 儲存 → 前端與 Email 呈現」的主動式選股管線。
