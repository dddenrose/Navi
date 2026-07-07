"""Screener picks forward tracking — 推薦後實際績效追蹤.

回測（往過去驗證）有倖存者偏差治不好；本模組做的是 forward tracking：
每份報告發布當下的 picks 是「事前」決定的，事後追蹤 T+N 交易日報酬
即為統計上乾淨的實績證據。

設計:
  - 追蹤基準：報告日的還原收盤價（yfinance auto_adjust）。screener 於
    盤後產報，snapshot.price ≈ 當日收盤；改用還原價是為了讓後續報酬
    含股利且與比較序列自洽（除息不會造成假下跌）。
  - 追蹤節點：T+5 / T+20 / T+60 交易日，另含最新報酬與期間最大漲跌幅。
  - 相對基準：^TWII 同視窗報酬 → excess return。
  - 結果寫回 pick doc 的 `tracking` 欄位；報告全部 picks 追滿 T+60 後
    在報告 doc 標記 `tracking_complete=True`，之後不再重算。
  - 聚合統計寫入 `screener_tracking/{profile}`，供前端展示。

注意：同一檔股票在連續多份報告入選會重複計入 —
統計單位是「推薦事件」而非「個股」。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from services.firestore_client import get_db

logger = logging.getLogger(__name__)

BENCHMARK = "^TWII"
HORIZONS: dict[str, int] = {"t5": 5, "t20": 20, "t60": 60}
FINAL_HORIZON_DAYS = max(HORIZONS.values())
REPORTS_COLLECTION = "screener_reports"
TRACKING_COLLECTION = "screener_tracking"
DOWNLOAD_BATCH_SIZE = 100


# ── Pure computation（無網路 / 無 Firestore，單元測試對象）──────────────────


def compute_tracking(
    entry_date: date,
    closes: pd.Series,
    bench_closes: pd.Series,
    *,
    entry_price_snapshot: float | None = None,
) -> dict[str, Any] | None:
    """對單一 pick 計算追蹤結果.

    closes / bench_closes: 完整還原收盤序列（DatetimeIndex, tz-naive）。
    回傳 None 表示無法建立基準（如報告日該股無價格資料）。
    """
    closes = closes.dropna()
    bench = bench_closes.dropna()
    entry_ts = pd.Timestamp(entry_date)

    basis_series = closes.loc[:entry_ts]
    if basis_series.empty:
        return None
    basis = float(basis_series.iloc[-1])
    if basis <= 0:
        return None

    bench_basis_series = bench.loc[:entry_ts]
    bench_basis = (
        float(bench_basis_series.iloc[-1]) if not bench_basis_series.empty else None
    )

    post = closes.loc[closes.index > entry_ts]
    bench_post = bench.loc[bench.index > entry_ts]

    result: dict[str, Any] = {
        "entry_date": entry_ts.strftime("%Y-%m-%d"),
        "entry_close_adj": round(basis, 4),
        "entry_price_snapshot": entry_price_snapshot,
        "trading_days_elapsed": int(len(post)),
        "complete": len(post) >= FINAL_HORIZON_DAYS,
    }

    if len(post) == 0:
        result["as_of"] = entry_ts.strftime("%Y-%m-%d")
        return result

    result["as_of"] = post.index[-1].strftime("%Y-%m-%d")
    result["return_current"] = round(float(post.iloc[-1] / basis - 1), 6)
    result["max_return"] = round(float(post.max() / basis - 1), 6)
    result["max_drawdown"] = round(float(post.min() / basis - 1), 6)

    for key, n in HORIZONS.items():
        if len(post) < n:
            continue
        ret = float(post.iloc[n - 1] / basis - 1)
        result[f"return_{key}"] = round(ret, 6)
        if bench_basis and len(bench_post) >= n:
            bench_ret = float(bench_post.iloc[n - 1] / bench_basis - 1)
            result[f"excess_{key}"] = round(ret - bench_ret, 6)
    return result


def aggregate_tracking(picks: list[dict[str, Any]]) -> dict[str, Any]:
    """把多個 pick（含 tracking 欄位）聚合成統計摘要.

    picks 元素需含 `final_grade` 與 `tracking`（compute_tracking 的輸出）。
    """

    def _stats(values: list[float]) -> dict[str, Any]:
        if not values:
            return {"n": 0}
        s = pd.Series(values)
        return {
            "n": int(len(s)),
            "win_rate": round(float((s > 0).mean()), 4),
            "avg_return": round(float(s.mean()), 6),
            "median_return": round(float(s.median()), 6),
        }

    horizons: dict[str, Any] = {}
    for key in HORIZONS:
        rets = [
            p["tracking"][f"return_{key}"]
            for p in picks
            if p.get("tracking", {}).get(f"return_{key}") is not None
        ]
        excesses = [
            p["tracking"][f"excess_{key}"]
            for p in picks
            if p.get("tracking", {}).get(f"excess_{key}") is not None
        ]
        entry = _stats(rets)
        if excesses:
            es = pd.Series(excesses)
            entry["avg_excess"] = round(float(es.mean()), 6)
            entry["beat_benchmark_rate"] = round(float((es > 0).mean()), 4)
        horizons[key] = entry

    by_grade: dict[str, Any] = {}
    for grade in sorted({p.get("final_grade", "") for p in picks if p.get("final_grade")}):
        subset = [p for p in picks if p.get("final_grade") == grade]
        by_grade[grade] = {
            key: _stats(
                [
                    p["tracking"][f"return_{key}"]
                    for p in subset
                    if p.get("tracking", {}).get(f"return_{key}") is not None
                ]
            )
            for key in HORIZONS
        }

    tracked = [p for p in picks if p.get("tracking")]
    return {
        "pick_events": len(tracked),
        "horizons": horizons,
        "by_grade": by_grade,
    }


# ── Firestore + yfinance orchestration ──────────────────────────────────────


@dataclass
class TrackingRunStats:
    reports_scanned: int = 0
    reports_completed: int = 0
    picks_updated: int = 0
    picks_skipped: int = 0


def _entry_date_from_report_id(report_id: str) -> date | None:
    try:
        return datetime.strptime(report_id.split("-")[0], "%Y%m%d").date()
    except (ValueError, IndexError):
        return None


def _download_closes(tickers: list[str], start: date) -> pd.DataFrame:
    """批次抓還原收盤價寬表（含 ^TWII）。"""
    import yfinance as yf

    symbols = sorted({*tickers, BENCHMARK})
    parts: list[pd.DataFrame] = []
    for i in range(0, len(symbols), DOWNLOAD_BATCH_SIZE):
        batch = symbols[i : i + DOWNLOAD_BATCH_SIZE]
        df = yf.download(
            batch, start=start.strftime("%Y-%m-%d"),
            auto_adjust=True, group_by="column",
            threads=True, progress=False,
        )
        if df.empty:
            continue
        closes = df["Close"] if isinstance(df.columns, pd.MultiIndex) else df[["Close"]]
        if not isinstance(df.columns, pd.MultiIndex):
            closes.columns = batch
        parts.append(closes)
    if not parts:
        return pd.DataFrame()
    wide = pd.concat(parts, axis=1).sort_index()
    wide = wide.loc[:, ~wide.columns.duplicated()]
    wide.index = pd.DatetimeIndex(wide.index).tz_localize(None)
    return wide


def update_all_tracking(*, max_reports: int = 200) -> TrackingRunStats:
    """更新所有未追蹤完成報告的 picks 追蹤資料."""
    db = get_db()
    stats = TrackingRunStats()

    report_docs = [
        snap.to_dict() or {} for snap in db.collection(REPORTS_COLLECTION).stream()
    ]
    pending = sorted(
        (
            d for d in report_docs
            if d.get("status") == "completed"
            and not d.get("tracking_complete")
            and _entry_date_from_report_id(d.get("report_id", ""))
        ),
        key=lambda d: d.get("report_id", ""),
        reverse=True,
    )[:max_reports]
    stats.reports_scanned = len(pending)
    if not pending:
        return stats

    # 先讀出所有待追蹤 picks，統一批次下載價格
    report_picks: dict[str, list[dict]] = {}
    for rep in pending:
        rid = rep["report_id"]
        picks = [
            {**(snap.to_dict() or {}), "_doc_id": snap.id}
            for snap in db.collection(REPORTS_COLLECTION)
            .document(rid).collection("picks").stream()
        ]
        report_picks[rid] = picks

    all_tickers = sorted(
        {p["ticker"] for picks in report_picks.values() for p in picks if p.get("ticker")}
    )
    if not all_tickers:
        return stats

    earliest = min(
        _entry_date_from_report_id(rid) for rid in report_picks
    )
    closes = _download_closes(all_tickers, earliest - timedelta(days=10))
    if closes.empty or BENCHMARK not in closes:
        logger.warning("Tracking aborted: price download failed (no %s)", BENCHMARK)
        return stats
    bench = closes[BENCHMARK]

    for rep in pending:
        rid = rep["report_id"]
        entry_date = _entry_date_from_report_id(rid)
        assert entry_date is not None  # pending 已過濾
        picks = report_picks[rid]
        all_complete = bool(picks)
        picks_coll = (
            db.collection(REPORTS_COLLECTION).document(rid).collection("picks")
        )
        for p in picks:
            ticker = p.get("ticker", "")
            if ticker not in closes:
                stats.picks_skipped += 1
                all_complete = False
                continue
            tracking = compute_tracking(
                entry_date,
                closes[ticker],
                bench,
                entry_price_snapshot=(p.get("snapshot") or {}).get("price"),
            )
            if tracking is None:
                stats.picks_skipped += 1
                all_complete = False
                continue
            picks_coll.document(p["_doc_id"]).update({"tracking": tracking})
            stats.picks_updated += 1
            if not tracking["complete"]:
                all_complete = False

        update: dict[str, Any] = {"tracking_updated_at": datetime.now().isoformat()}
        if all_complete:
            update["tracking_complete"] = True
            stats.reports_completed += 1
        db.collection(REPORTS_COLLECTION).document(rid).update(update)
        logger.info("Tracking updated: %s (%d picks)", rid, len(picks))

    return stats


def rebuild_tracking_summary(profile: str) -> dict[str, Any]:
    """重算單一 profile 的聚合統計並寫入 screener_tracking/{profile}."""
    db = get_db()
    report_docs = [
        snap.to_dict() or {} for snap in db.collection(REPORTS_COLLECTION).stream()
    ]
    reports = sorted(
        (
            d for d in report_docs
            if d.get("profile") == profile and d.get("status") == "completed"
        ),
        key=lambda d: d.get("report_id", ""),
    )

    picks: list[dict] = []
    for rep in reports:
        rid = rep.get("report_id", "")
        for snap in (
            db.collection(REPORTS_COLLECTION).document(rid)
            .collection("picks").stream()
        ):
            doc = snap.to_dict() or {}
            if doc.get("tracking"):
                picks.append(doc)

    summary = aggregate_tracking(picks)
    summary.update(
        {
            "profile": profile,
            "report_count": len(reports),
            "first_report_id": reports[0]["report_id"] if reports else None,
            "last_report_id": reports[-1]["report_id"] if reports else None,
            "updated_at": datetime.now().isoformat(),
            "methodology": (
                "以報告日還原收盤價為基準，追蹤 T+5/T+20/T+60 交易日報酬；"
                "超額報酬相對 ^TWII 同視窗。統計單位為推薦事件，"
                "同檔多次入選會重複計入。"
            ),
        }
    )
    db.collection(TRACKING_COLLECTION).document(profile).set(summary)
    logger.info(
        "Tracking summary rebuilt: %s (%d pick events)",
        profile, summary["pick_events"],
    )
    return summary


def get_tracking_summary(profile: str) -> dict[str, Any] | None:
    db = get_db()
    snap = db.collection(TRACKING_COLLECTION).document(profile).get()
    return (snap.to_dict() or None) if snap.exists else None
