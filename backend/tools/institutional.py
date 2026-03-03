"""Tool: 三大法人買賣超查詢（外資、投信、自營商）."""

from langchain_core.tools import tool

from services.institutional_service import get_institutional_data


@tool
def get_institutional(ticker: str, days: int = 5) -> str:
    """查詢個股三大法人（外資、投信、自營商）近期買賣超數據。

    可判斷法人籌碼動向，了解外資是否連續買超或賣超。
    目前僅支援台灣上市（TWSE）個股。

    Args:
        ticker: 股票代碼，例如 2330、台積電、2317.TW。
        days: 查詢天數（預設 5 個交易日）。
    """
    data = get_institutional_data(ticker, days=days)

    if data.error:
        return data.error

    parts = [f"🏦 {data.name or data.ticker} 三大法人買賣超（近 {len(data.records)} 日）", ""]

    # Daily breakdown
    for r in data.records:
        parts.append(
            f"  {r.date}｜外資 {r.foreign_net:+,}、投信 {r.investment_trust_net:+,}、"
            f"自營商 {r.dealer_net:+,}｜合計 {r.total_net:+,}"
        )

    parts.append("")

    # Summary
    consec = data.foreign_consecutive_days
    if consec > 0:
        parts.append(f"📊 外資連續買超 {consec} 日，累計淨買 {data.foreign_total_net:+,} 張")
    elif consec < 0:
        parts.append(f"📊 外資連續賣超 {abs(consec)} 日，累計淨賣 {data.foreign_total_net:+,} 張")
    else:
        parts.append(f"📊 外資近期累計淨買賣 {data.foreign_total_net:+,} 張")

    parts.append(f"   投信累計 {data.investment_trust_total_net:+,} 張")
    parts.append(f"   自營商累計 {data.dealer_total_net:+,} 張")
    parts.append(f"   三大法人合計 {data.total_net:+,} 張")

    return "\n".join(parts)
