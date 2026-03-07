"""Tool: 基本面分析（PE, PB, ROE, EPS 等財報數據 + 合理價位估算）."""

from langchain_core.tools import tool

from services.stock_service import get_fundamental_data


@tool
def analyze_fundamentals(ticker: str) -> str:
    """取得股票的基本面財報數據，包含估值指標、獲利能力、成長性，以及基於本益比的合理價位估算（便宜價/合理價/昂貴價）。

    Args:
        ticker: 股票代碼，可以是中文名稱（台積電）、數字代碼（2330）或美股代碼（AAPL）。
    """
    data = get_fundamental_data(ticker)

    def _pct(val: float | None) -> str:
        return f"{val * 100:.1f}%" if val is not None else "N/A"

    def _num(val: float | None, d: int = 2) -> str:
        return f"{val:.{d}f}" if val is not None else "N/A"

    parts = [
        f"📈 {data.name} ({data.ticker}) 基本面數據",
        "",
        "【估值】",
        f"  PE (TTM)：{_num(data.pe_ratio)} | Forward PE：{_num(data.forward_pe)}",
        f"  PB：{_num(data.pb_ratio)} | PS：{_num(data.ps_ratio)}",
        "",
        "【獲利能力】",
        f"  ROE：{_pct(data.roe)} | ROA：{_pct(data.roa)}",
        f"  淨利率：{_pct(data.profit_margin)} | 營業利益率：{_pct(data.operating_margin)}",
        "",
        "【成長性】",
        f"  營收成長：{_pct(data.revenue_growth)} | 獲利成長：{_pct(data.earnings_growth)}",
        "",
        "【每股數據】",
        f"  EPS (TTM)：{_num(data.eps)} | Forward EPS：{_num(data.forward_eps)}",
    ]

    if data.dividend_yield is not None:
        parts.append(f"  殖利率：{_pct(data.dividend_yield)}")

    if data.sector:
        parts.extend(["", f"產業：{data.sector} / {data.industry}"])

    # 合理價位估算
    if data.fair_price is not None:
        parts.extend([
            "",
            "🎯【合理價位估算】",
            f"  🟢 便宜價：{_num(data.cheap_price)}  （PE {_num(data.pe_low, 1)}）",
            f"  🟡 合理價：{_num(data.fair_price)}  （PE {_num(data.pe_mid, 1)}）",
            f"  🔴 昂貴價：{_num(data.expensive_price)}  （PE {_num(data.pe_high, 1)}）",
            f"  📝 {data.valuation_note}",
        ])
    elif data.valuation_note:
        parts.extend(["", f"⚠️ 估值說明：{data.valuation_note}"])

    return "\n".join(parts)
