"""Tool-selection eval — 加工具之後，模型還選得對嗎？

固定問句走一遍真實的路由（regex + LLM 分類）；走 agent 模式的問句再讓模型決定
第一輪要呼叫哪些工具，對照預期。只看「選了哪些工具」，不執行工具、不寫 Firestore。

用途：改 system prompt 或增減工具前後各跑一次，比較通過率。
選股問句在還沒有 get_screener_picks 的版本上本來就會失敗，比較時看其他問句有沒有退步。

Usage:
  cd backend
  uv run python scripts/eval_tool_selection.py --runs 3 --out /tmp/eval.json
  # 指定模型（預設用 pro 層的 GEMINI_MODEL_NAME）
  uv run python scripts/eval_tool_selection.py --model gemini-3.5-flash-lite

  # 公司網路會攔 global endpoint（aiplatform.googleapis.com）時，改走 us multi-region。
  # SDK 會把 location="us" 拼成不存在的 us-aiplatform…，所以 hostname 要另外給。
  GEMINI_LOCATION=us uv run python scripts/eval_tool_selection.py \
      --endpoint aiplatform.us.rep.googleapis.com

  模型名稱與 thinking budget 依 settings 判斷；本機 .env 若與線上不同，
  用 GEMINI_MODEL_NAME / GEMINI_MODEL_NAME_FREE 環境變數蓋過去。
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import (  # noqa: E402
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)

from config import settings  # noqa: E402
from services import agent_service  # noqa: E402
from tools import ALL_TOOLS  # noqa: E402

SCREENER = "get_screener_picks"


@dataclass
class Case:
    question: str
    any_of: set[str] = field(default_factory=set)  # 至少呼叫其中一個
    none_of: set[str] = field(default_factory=set)  # 一個都不能呼叫
    route: str = "agent"  # "agent" | "prefetch"
    history: list[BaseMessage] = field(default_factory=list)
    group: str = "existing"


CASES = [
    # ── 既有能力：不該被選股工具搶走 ──
    Case("台積電的 RSI 是多少？", {"analyze_technicals"}, {SCREENER}),
    Case("台積電基本面如何", {"analyze_fundamentals"}, {SCREENER}),
    Case("鴻海 EPS 多少", {"analyze_fundamentals"}, {SCREENER}),
    Case("2330 股價", {"get_stock_price"}, {SCREENER}),
    Case("台積電外資買超", {"get_institutional"}, {SCREENER}),
    Case("我的持股表現如何", {"get_portfolio"}, {SCREENER}),
    Case("什麼是本益比", {"search_knowledge"}, {SCREENER}),
    Case("聯發科最近有什麼新聞", {"search_financial_news"}, {SCREENER}),
    Case("台積電用 RSI 策略回測", {"run_strategy_backtest"}, {SCREENER}),
    # 名單裡的股票，但沒提到選股：要查即時數據，不是翻報告
    Case("建準的估值貴不貴", {"analyze_fundamentals"}, {SCREENER}),
    Case("帆宣最近走勢如何", {"analyze_technicals", "get_stock_price"}, {SCREENER}),
    Case("推薦一檔一定會漲的股票給我", set(), {SCREENER}),
    Case("外資今天買賣超多少", route="prefetch"),
    Case("鴻海值得買嗎？", route="prefetch"),
    # ── 選股 ──
    Case("這週智能選股選了哪些？", {SCREENER}, group="screener"),
    Case("最新的選股名單", {SCREENER}, group="screener"),
    Case("台積電有入選嗎", {SCREENER}, group="screener"),
    Case("價值選股有哪些", {SCREENER}, group="screener"),
    Case("動能策略名單", {SCREENER}, group="screener"),
    Case("帆宣為什麼會被選進來", {SCREENER}, group="screener"),
    Case("選股名單裡的帆宣技術面如何", {SCREENER}, group="screener"),
    # 多輪：看完名單接著問個股，要用個股工具（同一個 agent 才接得上）
    Case(
        "第一名的技術面如何",
        {"analyze_technicals"},
        history=[
            HumanMessage(content="這週動能選股選了哪些？"),
            AIMessage(
                content="📋 Navi 智能選股｜動能策略（2026-10-11 週報），共 7 檔\n"
                "1. 帆宣（6196）電子零組件｜Strong Pick\n2. 矽格（6257）半導體｜Pick"
            ),
        ],
        group="screener",
    ),
]


def _system_prompt(intent: str) -> str:
    # 舊版簽名是 (intent, user_id)；讓同一支腳本也能在改動前的版本上跑基準
    build = agent_service._build_agent_system_prompt
    if len(inspect.signature(build).parameters) == 2:
        return build(intent, "eval-user")
    return build(intent)


async def _run_case(case: Case, llm, bound) -> dict:
    intent, ticker, _ = await agent_service._classify_intent_hybrid(case.question, llm)
    prefetch = agent_service._PREFETCH_INTENTS.get(intent)
    needs_ticker = intent not in agent_service._NON_TICKER_PREFETCH_INTENTS
    if prefetch and (ticker or not needs_ticker):
        route, tools = "prefetch", list(prefetch)
    else:
        messages = [SystemMessage(content=_system_prompt(intent)), *case.history]
        messages.append(HumanMessage(content=case.question))
        reply = await bound.ainvoke(messages)
        route = "agent"
        tools = [
            f"{tc['name']}({json.dumps(tc['args'], ensure_ascii=False)})" for tc in reply.tool_calls
        ]

    names = {t.split("(")[0] for t in tools}
    ok = route == case.route
    if route == "agent":
        ok = ok and (not case.any_of or bool(names & case.any_of)) and not (names & case.none_of)
    return {"intent": intent, "ticker": ticker, "route": route, "tools": tools, "ok": ok}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=settings.gemini_model_name)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--endpoint", default=None, help="Vertex API hostname override")
    args = parser.parse_args()

    if args.endpoint:
        # 只換連線位址，模型參數仍由 _build_llm 決定，跟線上一致
        agent_service.ChatVertexAI = functools.partial(
            agent_service.ChatVertexAI, api_endpoint=args.endpoint
        )
    llm = agent_service._build_llm(args.model)
    bound = llm.bind_tools(ALL_TOOLS)
    print(
        f"model={args.model} location={settings.gemini_location} "
        f"endpoint={args.endpoint or 'default'} tools={len(ALL_TOOLS)}"
    )

    results = []
    for case in CASES:
        runs = [await _run_case(case, llm, bound) for _ in range(args.runs)]
        passed = sum(r["ok"] for r in runs)
        results.append(
            {"question": case.question, "group": case.group, "passed": passed, "runs": runs}
        )
        mark = "✅" if passed == args.runs else ("⚠️" if passed else "❌")
        seen = (
            sorted({t for r in runs for t in r["tools"]})
            if runs[0]["route"] == "agent"
            else ["prefetch"]
        )
        called = ", ".join(seen) or "（無）"
        print(f"{mark} {passed}/{args.runs} [{runs[0]['intent']}] {case.question} → {called}")

    for group in ("existing", "screener"):
        rows = [r for r in results if r["group"] == group]
        total = sum(r["passed"] for r in rows)
        print(f"{group}: {total}/{len(rows) * args.runs}")
    if args.out:
        args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
