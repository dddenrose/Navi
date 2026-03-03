"""Tool: 融資融券查詢."""

from langchain_core.tools import tool

from services.margin_service import get_margin_data


@tool
def get_margin_trading(ticker: str, days: int = 5) -> str:
    """查詢個股融資融券數據，包含融資餘額、融券餘額、使用率、資券互抵等。

    可用來判斷散戶追多程度（融資）和空方力道（融券）。
    目前僅支援台灣上市（TWSE）個股。

    Args:
        ticker: 股票代碼，例如 2330、台積電、2317.TW。
        days: 查詢天數（預設 5 個交易日）。
    """
    data = get_margin_data(ticker, days=days)

    if data.error:
        return data.error

    parts = [f"💳 {data.name or data.ticker} 融資融券（近 {len(data.records)} 日）", ""]

    latest = data.latest
    if latest:
        parts.extend([
            "【最新一日】",
            f"  融資餘額：{latest.margin_balance:,} 張（使用率 {latest.margin_utilization:.1f}%）",
            f"  融券餘額：{latest.short_balance:,} 張",
            f"  資券互抵：{latest.offset:,} 張",
            "",
        ])

    # Daily breakdown (condensed)
    parts.append("【近期明細】")
    for r in data.records:
        parts.append(
            f"  {r.date}｜融資餘額 {r.margin_balance:,}（使用率 {r.margin_utilization:.1f}%）"
            f"｜融券餘額 {r.short_balance:,}"
        )

    parts.append("")

    # Trend
    if data.margin_change != 0:
        direction = "增加" if data.margin_change > 0 else "減少"
        parts.append(f"📊 融資餘額期間{direction} {abs(data.margin_change):,} 張")
    if data.short_change != 0:
        direction = "增加" if data.short_change > 0 else "減少"
        parts.append(f"   融券餘額期間{direction} {abs(data.short_change):,} 張")

    # Interpretation hints
    if latest and latest.margin_utilization < 20:
        parts.append("   → 融資使用率偏低，散戶追多力道不強")
    elif latest and latest.margin_utilization > 50:
        parts.append("   → 融資使用率偏高，注意追繳風險")

    return "\n".join(parts)
