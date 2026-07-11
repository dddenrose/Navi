"""Local validator for the screener pipeline.

Usage examples:

  # Stage 1+2 only (zero LLM cost) — 全部產業 universe
  cd backend
  uv run python scripts/run_screener_local.py --skip-stage3 --profile momentum

  # Stage 1+2 only with low thresholds（驗證資料管線）
  uv run python scripts/run_screener_local.py --skip-stage3 \
      --min-turnover 10000000 --min-market-cap 0

  # Stage 3 小量驗證：全市場取 3 檔 + Flash model + 不寫 Firestore
  uv run python scripts/run_screener_local.py --total 3 \
      --model gemini-2.5-flash --no-persist --tickers 2330.TW,2317.TW,2454.TW
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.screener.orchestrator import run_screener  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Navi screener locally for validation")
    parser.add_argument("--profile", choices=["value", "momentum"], default="momentum")
    parser.add_argument("--frequency", choices=["daily", "weekly"], default="weekly")
    parser.add_argument("--total", type=int, default=10, help="全市場取前 N 檔送 Stage 3")
    parser.add_argument("--max-per-industry", type=int, default=2, help="單一產業上限")
    parser.add_argument("--model", default=None, help="覆寫 LLM model 名稱（如 gemini-2.5-flash）")
    parser.add_argument("--skip-stage3", action="store_true", help="只跑 Stage 1+2 (零 LLM 成本)")
    parser.add_argument("--no-chips", action="store_true", help="關閉 Stage 2 chips 因子（TWSE bulk fetch）")
    parser.add_argument("--no-persist", action="store_true", help="不寫入 Firestore")
    parser.add_argument(
        "--tickers",
        default=None,
        help="逗號分隔自訂股票池，如 '2330.TW,2317.TW'",
    )
    parser.add_argument("--min-turnover", type=float, default=None)
    parser.add_argument("--min-market-cap", type=float, default=None)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    tickers = (
        [t.strip() for t in args.tickers.split(",") if t.strip()] if args.tickers else None
    )

    result = run_screener(
        profile=args.profile,
        frequency=args.frequency,
        tickers=tickers,
        total_picks=args.total,
        max_per_industry=args.max_per_industry,
        model_name=args.model,
        persist=not args.no_persist,
        skip_stage3=args.skip_stage3,
        enable_chips=not args.no_chips,
        min_turnover=args.min_turnover,
        min_market_cap=args.min_market_cap,
    )

    print()
    print("=" * 70)
    print(f"Report: {result['report_id']}")
    print(
        f"Profile={result['profile']} | Stage1={result['stage1_passed']} "
        f"→ Qualified={result['stage2_qualified']} → Picks={result['final_count']}"
    )
    print(f"Duration: {result['duration_seconds']}s | Industries: {result['industries_covered']}")
    print("=" * 70)

    # Stage 2 候選（全市場排名 + 產業上限）
    print("\n📊 Stage 2 candidates (全市場排名):")
    for es in result["candidates"]:
        d = es.data
        t = es.trace
        print(
            f"    #{es.rank_overall:>2} {d.ticker} {d.name:<8} [{d.industry}] "
            f"grade={t.final_grade:<12} "
            f"must={t.must_pass_count}/{t.must_pass_total} "
            f"bonus={t.bonus_passed}/{len(t.bonus)} "
            f"DQ={'Y' if t.disqualifier_triggered else 'N'}"
        )

    # 全量診斷（含被剔除的）—— 用 --verbose 看
    if args.verbose:
        print("\n🔬 全量診斷（含 rejected）:")
        for es in result["evaluated"]:
            d = es.data
            t = es.trace
            failed_must = [c.rule_id for c in t.must_pass if not c.passed]
            dq = t.disqualifier_triggered
            print(
                f"  {d.ticker} {d.name:<8} {d.industry:<10} "
                f"grade={t.final_grade:<12} "
                f"must={t.must_pass_count}/{t.must_pass_total} "
                f"bonus={t.bonus_passed}/{len(t.bonus)} "
                f"failed_must={failed_must} dq={dq}"
            )
            for c in t.must_pass:
                if not c.passed:
                    print(f"    ✗ {c.rule_id} {c.name}: {c.actual} | {c.reference}")
            if args.verbose:
                bonus_pass = [c.rule_id for c in t.bonus if c.passed]
                bonus_fail = [c.rule_id for c in t.bonus if not c.passed]
                print(f"    bonus pass={bonus_pass} fail={bonus_fail}")

    # Stage 3 解讀
    if not args.skip_stage3 and result["pick_docs"]:
        print("\n💎 Stage 3 interpretations:")
        for d in result["pick_docs"]:
            interp = d.get("interpretation") or {}
            val = d.get("valuation") or {}
            print(f"\n  {d['ticker']} {d['name']} ({d['industry']}) — {d['final_grade']}")
            if val.get("fair_value_mid"):
                print(
                    f"    Fair value: {val.get('fair_value_low')}/{val.get('fair_value_mid')}"
                    f"/{val.get('fair_value_high')}  buy_zone≤{val.get('buy_zone_upper')}  "
                    f"upside={val.get('implied_upside_mid_pct'):.1f}%"
                )
            print(f"    Value-trap: {interp.get('value_trap_check', '-')}")
            print(f"    Narrative: {(interp.get('narrative') or '')[:200]}…")


if __name__ == "__main__":
    main()
