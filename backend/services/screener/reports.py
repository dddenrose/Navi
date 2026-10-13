"""Read persisted screener reports — shared by the API routes and the agent tool."""

from __future__ import annotations

from typing import Any

from services.firestore_client import get_db
from services.screener.orchestrator import REPORTS_COLLECTION


def find_latest_report(profile: str, frequency: str | None = None) -> dict[str, Any] | None:
    """Return the newest report doc for a profile (optionally one frequency).

    report_id 是 "YYYYMMDD-frequency-profile"，字串排序即時間排序。
    量小（< 1000 份）全部拉回來在 Python 端篩，避免 composite index。
    """
    docs = [snap.to_dict() or {} for snap in get_db().collection(REPORTS_COLLECTION).stream()]
    docs.sort(key=lambda d: d.get("report_id", ""), reverse=True)
    for doc in docs:
        if doc.get("profile") != profile:
            continue
        if frequency and doc.get("frequency") != frequency:
            continue
        return doc
    return None


def load_pick_docs(report_id: str) -> list[dict[str, Any]]:
    """Return a report's picks ordered by overall rank."""
    picks_coll = get_db().collection(REPORTS_COLLECTION).document(report_id).collection("picks")
    picks = [snap.to_dict() or {} for snap in picks_coll.stream()]
    picks.sort(key=lambda p: p.get("rank_overall") or 0)
    return picks
