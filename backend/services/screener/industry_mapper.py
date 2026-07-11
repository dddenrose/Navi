"""Industry mapper — ticker → 11 類自建產業。

MVP 階段使用手動 seed 的 industry_data.json；後續可由
scripts/seed_industry_mapping.py 擴充為完整上市櫃名單。
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "industry_data.json"

FALLBACK_INDUSTRY = "公用其他"


@lru_cache(maxsize=1)
def _load_data() -> dict:
    with _DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _ticker_to_industry() -> dict[str, str]:
    """Build {ticker: industry_name} 反向索引。"""
    data = _load_data()
    out: dict[str, str] = {}
    for industry, items in data["industries"].items():
        for item in items:
            out[item["ticker"]] = industry
    return out


@lru_cache(maxsize=1)
def _ticker_to_name() -> dict[str, str]:
    data = _load_data()
    out: dict[str, str] = {}
    for items in data["industries"].values():
        for item in items:
            out[item["ticker"]] = item["name"]
    return out


@lru_cache(maxsize=1)
def _ticker_to_fine_industry() -> dict[str, str]:
    """ticker → TWSE 原始產業別（32 類，較 Navi-11 細）。"""
    data = _load_data()
    out: dict[str, str] = {}
    for items in data["industries"].values():
        for item in items:
            cat = item.get("twse_category")
            if cat:
                out[item["ticker"]] = cat
    return out


def get_fine_industry(ticker: str) -> str | None:
    """回傳 TWSE 細產業別（如「半導體業」）；資料缺失回 None。

    估值錨優先用細分類（同業可比性高），樣本不足才 fallback 到 Navi-11 大類。
    """
    return _ticker_to_fine_industry().get(ticker)


def get_industry(ticker: str) -> str:
    """回傳該 ticker 的自建產業類別；找不到時 fallback 至『公用其他』。"""
    return _ticker_to_industry().get(ticker, FALLBACK_INDUSTRY)


def get_name(ticker: str) -> str:
    return _ticker_to_name().get(ticker, "")


def all_tickers() -> list[str]:
    return sorted(_ticker_to_industry().keys())


def industries() -> list[str]:
    return list(_load_data()["industries"].keys())
