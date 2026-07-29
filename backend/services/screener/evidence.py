"""Strategy evidence gate — 每個 profile 的回測證據與誠實揭露.

原則：任何策略沒有對口回測（訊號頻率、持有期與實際用法一致）就標
experimental；有回測則不論數字好壞一律揭露，含倖存者偏差等警語。
報告產生時由 orchestrator 蓋章進 report doc，前端常駐顯示。

Momentum 回測口徑（backend/scripts/backtest_momentum.py，2026-07-11 執行）：
  uv run python scripts/backtest_momentum.py --hold-weeks 13 \
      --select global --total 10 --max-per-industry 2

數字更新流程：改規則 → 重跑上述指令 → 更新本檔常數 → 更新
docs/MOMENTUM_BACKTEST_NOTES.md。規則與回測數字不同步就是說謊，
寧可標 experimental。
"""

from __future__ import annotations

from typing import Any

# 與線上規則對齊的回測結果（含倖存者偏差 — 樂觀上界，非期望值）
_MOMENTUM_EVIDENCE: dict[str, Any] = {
    "status": "backtested",
    "headline": "回測顯示超額報酬為正，但為樂觀上界且近三年落後大盤",
    "backtest_period": "2018-02 ~ 2026-07（8.4 年）",
    "method": (
        "週頻訊號、次一交易日開盤成交（無 look-ahead）、持有 13/26 週重疊分批、"
        "全市場 top 10（單一產業 ≤ 2）、單邊成本 30bps"
    ),
    "metrics": {
        "hold_13w": {
            "strategy_cagr": 0.2400,
            "benchmark_cagr": 0.1838,
            "excess_cagr": 0.0562,
            "max_drawdown": -0.3533,
            "sharpe_monthly": 1.00,
        },
        "hold_26w": {
            "strategy_cagr": 0.2124,
            "benchmark_cagr": 0.1838,
            "excess_cagr": 0.0286,
            "max_drawdown": -0.3569,
            "sharpe_monthly": 0.95,
        },
    },
    "benchmark": "^TWII",
    "caveats": [
        "Universe 為今日仍存在的股票回溯 — 含倖存者偏差，數字是樂觀上界而非期望值",
        "2024–2026 連續三年超額報酬為負（動能策略有長期落後期，2025 年 -30pp）",
        "回測僅含技術規則（M1/M2/M3/MB3/MB4）；財報與籌碼規則無歷史時點資料，未驗證",
        "最大回撤 -35%，深於同期大盤的 -32%",
        "過去績效不代表未來報酬",
    ],
}

_VALUE_EVIDENCE: dict[str, Any] = {
    "status": "experimental",
    "headline": "實驗性策略 — 尚無回測依據",
    "backtest_period": None,
    "method": None,
    "metrics": {},
    "benchmark": "^TWII",
    "caveats": [
        "Value 規則以財報為主，缺乏歷史時點財報資料，無法誠實回測"
        "（用今日財報回溯會引入 look-ahead bias）",
        "目前僅以發布後實績追蹤（T+120 為主要指標）累積前瞻證據",
        "金融保險業因負債結構特性不適用本策略規則（V3/V4），不會出現在名單中",
    ],
}


def get_evidence(profile: str) -> dict[str, Any]:
    """回傳該 profile 的證據揭露 dict（寫入 report doc 用）。"""
    base = _MOMENTUM_EVIDENCE if profile == "momentum" else _VALUE_EVIDENCE
    return {"profile": profile, **base}
