"""Tool: 大盤指數、三大法人總額、期貨未平倉（macro 級資料）。"""

from langchain_core.tools import tool

from services.macro_service import (
    get_futures_positions,
    get_institutional_aggregate,
    get_market_index,
)


def _format_amount_ntd(amount_ntd: int) -> str:
    """金額（元）→ 易讀的「億元」標示，例如 +52,344 → +0.01 億元。"""
    yi = amount_ntd / 100_000_000  # 1 億 = 1e8
    if abs(yi) >= 100:
        return f"{yi:+,.0f} 億元"
    if abs(yi) >= 1:
        return f"{yi:+,.2f} 億元"
    # 小於 1 億時改用「百萬元」（萬萬元）
    mn = amount_ntd / 1_000_000
    return f"{mn:+,.0f} 百萬元"


@tool
def get_market_overview(market: str = "TWSE") -> str:
    """查詢台股大盤指數即時/最新報價（盤中即時，盤後改為當日收盤）。

    可回答「大盤怎麼看」「加權指數現在多少」「櫃買怎麼樣」等問題。
    用戶問「大盤」「加權」「TAIEX」→ 用 TWSE；問「櫃買」「OTC」→ 用 TPEx。

    Args:
        market: "TWSE"（加權指數）或 "TPEx"（櫃買指數）；預設 TWSE。
    """
    data = get_market_index(market)
    if data.error or data.price is None:
        return data.error or f"無法取得 {market} 指數資料，稍後再試。"

    label = "現價" if data.is_intraday else f"收盤（{data.as_of_date}）"
    sign = "+" if (data.change or 0) >= 0 else ""
    parts = [
        f"📈 {data.name}（{data.market}）",
        f"{label}：{data.price:,.2f}",
        f"漲跌：{sign}{data.change} ({sign}{data.change_percent}%)",
    ]
    if data.open is not None:
        parts.append(
            f"今日 開盤 {data.open:,.2f}｜最高 {data.high:,.2f}｜最低 {data.low:,.2f}"
        )
    if data.is_intraday and data.as_of_time:
        parts.append(f"資料時間：{data.as_of_date} {data.as_of_time}（{data.data_source}）")
    else:
        parts.append(f"資料來源：{data.data_source}")
    return "\n".join(parts)


@tool
def get_market_institutional_flows(days: int = 3) -> str:
    """查詢台股市場三大法人（外資、投信、自營商）整體買賣超彙總。

    與 `get_institutional` 不同：本工具回傳「整個台股市場」的法人買賣超總額（金額），
    `get_institutional` 則是單一個股的買賣超「張數」。
    可回答「外資今天買賣超多少」「最近法人動向」「外資是不是在賣」等大盤級問題。

    Args:
        days: 查詢天數（預設 3，最大 20 個交易日）。
    """
    data = get_institutional_aggregate(days=days)
    if data.error or not data.records:
        return data.error or "無法取得三大法人買賣超資料，稍後再試。"

    parts = [f"🏦 三大法人買賣超彙總（近 {len(data.records)} 個交易日，市場合計）", ""]

    # 逐日明細
    for r in data.records:
        parts.append(
            f"  {r.date}：外資 {_format_amount_ntd(r.foreign_total_net)}｜"
            f"投信 {_format_amount_ntd(r.investment_trust_net)}｜"
            f"自營商 {_format_amount_ntd(r.dealer_net)}｜"
            f"合計 {_format_amount_ntd(r.total_net)}"
        )

    parts.append("")
    # 累計
    foreign_sum = sum(r.foreign_total_net for r in data.records)
    trust_sum = sum(r.investment_trust_net for r in data.records)
    dealer_sum = sum(r.dealer_net for r in data.records)
    total_sum = sum(r.total_net for r in data.records)
    parts.append(
        f"📊 累計：外資 {_format_amount_ntd(foreign_sum)}｜"
        f"投信 {_format_amount_ntd(trust_sum)}｜"
        f"自營商 {_format_amount_ntd(dealer_sum)}｜"
        f"合計 {_format_amount_ntd(total_sum)}"
    )
    parts.append("（金額為市場買賣差額，正值 = 淨買超，負值 = 淨賣超）")
    return "\n".join(parts)


@tool
def get_market_futures_positions(commodity: str = "TXF") -> str:
    """查詢台指期/小台/微台三大法人多空未平倉部位（TAIFEX 期貨日報）。

    可回答「外資多空單怎麼看」「期貨大戶在做空嗎」「未平倉淨多單多少」等。
    重點觀察外資的「多空未平倉淨額」：正值=淨多單偏多頭，負值=淨空單偏空頭。
    通常於收盤後 14:30 左右更新；盤中查詢回傳前一日資料。

    Args:
        commodity: 期貨商品代號，預設 "TXF"（臺股期貨）。可選 MXF（小台）、TMF（微台）、
                   EXF（電子期貨）、FXF（金融期貨）。
    """
    data = get_futures_positions(commodity)
    if data.error or not data.parties:
        return data.error or f"無法取得 {commodity} 期貨資料，稍後再試。"

    parts = [
        f"📐 {data.commodity_name}（{data.commodity}）三大法人未平倉｜資料日：{data.date}",
        "",
    ]
    for p in data.parties:
        parts.append(
            f"  {p.party}：多單 {p.long_oi_lots:,} 口、空單 {p.short_oi_lots:,} 口、"
            f"淨額 {p.net_oi_lots:+,} 口"
        )

    # 焦點摘要：外資淨多空
    foreign = next((p for p in data.parties if "外資" in p.party), None)
    if foreign:
        bias = "偏多" if foreign.net_oi_lots > 0 else ("偏空" if foreign.net_oi_lots < 0 else "中性")
        parts.append("")
        parts.append(
            f"📊 外資未平倉淨額 {foreign.net_oi_lots:+,} 口（{bias}）；"
            f"當日多空交易淨額 {foreign.net_trade_lots:+,} 口"
        )
    parts.append("（口數為合約口數；正值=淨多單偏多頭，負值=淨空單偏空頭）")
    return "\n".join(parts)
