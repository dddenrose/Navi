"""Portfolio Tool — Agent 可查詢使用者投資組合."""

from langchain_core.tools import tool

from services.portfolio_service import get_portfolio_summary


@tool
def get_portfolio(user_id: str) -> str:
    """查詢使用者的投資組合，包含持股明細、即時市值、損益。
    當使用者問到「我的持股」「投資組合表現」「我的股票賺了多少」時使用此工具。

    Args:
        user_id: 使用者 ID（從對話 context 取得）
    """
    try:
        summary = get_portfolio_summary(user_id)
    except Exception as e:
        return f"查詢投資組合時發生錯誤：{e}"

    if summary.holdings_count == 0:
        return "你目前還沒有任何持股。可以透過投資組合頁面新增持股。"

    lines = [
        f"💼 投資組合概覽",
        f"",
        f"📊 總市值：{summary.total_value:,.0f}",
        f"💰 總成本：{summary.total_cost:,.0f}",
        f"{'📈' if summary.total_pnl >= 0 else '📉'} 總損益：{summary.total_pnl:+,.0f}（{summary.total_pnl_percent:+.2f}%）",
        f"📦 持股檔數：{summary.holdings_count}",
        f"",
        f"═══ 持股明細 ═══",
    ]

    for h in summary.holdings:
        pnl_icon = "🟢" if h.pnl >= 0 else "🔴"
        lines.append(
            f"{pnl_icon} {h.ticker}"
            f"{'（' + h.name + '）' if h.name else ''}"
            f"  |  {h.shares:.0f}股 × ${h.current_price:,.2f}"
            f"  |  市值 ${h.market_value:,.0f}"
            f"  |  損益 {h.pnl:+,.0f}（{h.pnl_percent:+.2f}%）"
        )

    # 集中度分析
    if summary.holdings_count > 1 and summary.total_value > 0:
        lines.append("")
        lines.append("═══ 佔比分析 ═══")
        for h in sorted(summary.holdings, key=lambda x: x.market_value, reverse=True):
            pct = h.market_value / summary.total_value * 100
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            lines.append(f"{h.ticker}: {bar} {pct:.1f}%")

    return "\n".join(lines)
