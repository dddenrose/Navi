"""Local validator for the screener pipeline.

Usage examples:

  # Stage 1+2 only (zero LLM cost) — 全部產業 universe
  cd backend
  uv run python scripts/run_screener_local.py --skip-stage3 --profile momentum

  # Stage 1+2 only with low thresholds（驗證資料管線）
  uv run python scripts/run_screener_local.py --skip-stage3 \
      --min-turnover 10000000 --min-market-cap 0

  # Stage 3 小量驗證：限制 top 1/產業 + Flash model + 不寫 Firestore
  uv run python scripts/run_screener_local.py --top 1 \
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
    parser.add_argument("--frequency", choices=["daily", "weekly"], default="daily")
    parser.add_argument("--top", type=int, default=3, help="每產業前 N 檔送 Stage 3")
    parser.add_argument("--threshold", type=int, default=70, help="Stage 3 信心過濾門檻")
    parser.add_argument("--model", default=None, help="覆寫 LLM model 名稱（如 gemini-2.5-flash）")
    parser.add_argument("--skip-stage3", action="store_true", help="只跑 Stage 1+2 (零 LLM 成本)")
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
        top_per_industry=args.top,
        confidence_threshold=args.threshold,
        model_name=args.model,
        persist=not args.no_persist,
        skip_stage3=args.skip_stage3,
        min_turnover=args.min_turnover,
        min_market_cap=args.min_market_cap,
    )

    print()
    print("=" * 70)
    print(f"Report: {result['report_id']}")
    print(
        f"Profile={result['profile']} | Stage1={result['stage1_passed']} "
        f"→ Stage2={result['stage2_passed']} → Picks={result['final_count']}"
    )
    print(f"Duration: {result['duration_seconds']}s | Industries: {result['industries_covered']}")
    print("=" * 70)

    # 印 Stage 2 排名（每產業 top）
    print("\n📊 Stage 2 candidates (每產業 top):")
    by_industry: dict[str, list] = {}
    for sc in result["candidates"]:
        by_industry.setdefault(sc.factors.industry, []).append(sc)
    for industry, group in by_industry.items():
        print(f"\n  [{industry}]")
        for sc in group:
            f = sc.factors
            print(
                f"    #{sc.rank_in_industry} {f.ticker} {f.name:<8} "
                f"final={sc.final_score:>5.1f} | "
                f"value={sc.factor_scores.get('value', '-')} "
                f"momentum={sc.factor_scores.get('momentum', '-')} "
                f"quality={sc.factor_scores.get('quality', '-')}"
            )

    # 印 Stage 3 picks
    if result["picks"]:
        print("\n💎 Stage 3 picks:")
        for p in result["picks"]:
            sc = p.scored
            e = p.evaluation
            print(f"\n  {sc.factors.ticker} {sc.factors.name} ({sc.factors.industry})")
            print(f"    Confidence: {e.confidence}/100  Upside: {e.upside_pct:.1f}%")
            print(f"    Target: {e.target_price.low}/{e.target_price.mid}/{e.target_price.high}")
            print(f"    Stop: {e.stop_loss}  R/R: {e.risk_reward_ratio}")
            print(f"    Risks: {', '.join(e.risks[:3])}")
            print(f"    Citations: {e.kb_citations}")
            print(f"    Thesis: {e.thesis[:200]}…")


if __name__ == "__main__":
    main()
