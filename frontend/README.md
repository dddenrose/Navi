# Navi Frontend — AI Stock Analyzer Web App

> 🧚 _"Hey! Listen!"_ — Navi AI 投資分析助手前端（React + Vite + TypeScript）

## 環境需求

- Node.js 20+
- npm
- Firebase 專案（Authentication 已啟用）

## 快速開始

```bash
cd frontend

# 1. 安裝依賴
npm install

# 2. 設定 Firebase
#    將你的 Firebase config 填入 src/lib/firebase.ts
#    （API Key / Auth Domain / Project ID 等）

# 3. 啟動開發伺服器（HMR）
npm run dev

# 4. 建置 production bundle（輸出到 dist/）
npm run build

# 5. 預覽 production build
npm run preview

# 6. Lint
npm run lint
```

## 技術棧

| 類別     | 技術                    |
| -------- | ----------------------- |
| 框架     | React 19 + TypeScript   |
| 建構工具 | Vite 7                  |
| 樣式     | Tailwind CSS 4          |
| 圖表     | Recharts                |
| 路由     | React Router DOM 7      |
| 狀態管理 | Zustand                 |
| 認證     | Firebase Authentication |
| 部署     | Firebase Hosting        |

## 專案結構

```
frontend/
├── src/
│   ├── App.tsx                    # 路由入口（含 ErrorBoundary）
│   ├── main.tsx                   # React root
│   ├── pages/
│   │   ├── Dashboard.tsx          # 首頁
│   │   ├── Chat.tsx               # AI 對話（SSE Streaming）
│   │   ├── Stock.tsx              # 個股分析（slim coordinator）
│   │   ├── stock/                 #   四個分頁：概覽 / 技術 / 基本面 / 籌碼
│   │   ├── Portfolio.tsx          # 投資組合
│   │   ├── Backtest.tsx           # 策略回測
│   │   └── Login.tsx              # Firebase 登入
│   ├── components/
│   │   ├── Layout.tsx             # 主版型
│   │   ├── ErrorBoundary.tsx      # 全域 + 每頁錯誤隔離
│   │   ├── ProtectedRoute.tsx     # 路由守衛
│   │   ├── ThinkingPanel.tsx      # Agent 思考過程串流顯示
│   │   ├── MarkdownRenderer.tsx   # Markdown / KaTeX 渲染
│   │   ├── PriceChart.tsx         # K 線 / 趨勢圖
│   │   ├── RsiChart.tsx           # RSI 指標圖
│   │   └── StatCard.tsx           # 統計卡片
│   ├── lib/
│   │   ├── api.ts                 # apiFetch<T> 泛型 wrapper（含 SSE）
│   │   ├── firebase.ts            # Firebase 設定
│   │   └── format.ts              # 數字 / 百分比 / 損益顏色格式化
│   ├── store/
│   │   ├── authStore.ts           # Zustand auth state
│   │   └── themeStore.ts          # Zustand theme state
│   └── types/                     # 共享型別（stock、chat 等）
├── firebase.json                  # Hosting 設定（rewrites + cache + headers）
├── vite.config.ts
└── tsconfig.json
```

## 與後端對接

- **API base URL**：在 `src/lib/api.ts` 中由 `VITE_API_BASE_URL` 環境變數控制（dev 預設 `http://localhost:8000`）
- **認證**：所有 `/api/*` 請求自動附加 Firebase ID Token
- **SSE 串流**：`/api/chat` 走 SSE，前端透過 `fetch` + `ReadableStream` 解析 `event:` 區塊（intent / thinking / token / final / error）

## 部署到 Firebase Hosting

```bash
npm run build              # tsc -b && vite build
firebase deploy --only hosting
```

詳細部署流程請參考根目錄 [`.github/skills/navi-deployment/SKILL.md`](../.github/skills/navi-deployment/SKILL.md)。
