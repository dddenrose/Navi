"""Tool: 基本面分析（PE, PB, ROE, EPS 等財報數據）."""

from langchain_core.tools import tool

from services.stock_service import get_fundamental_data


@tool
def analyze_fundamentals(ticker: str) -> str:
    """取得股票的基本面財報數據，包含估值指標、獲利能力、成長性等。

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

    return "\n".join(parts)
