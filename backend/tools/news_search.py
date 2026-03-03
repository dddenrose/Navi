"""Tool: 財經新聞搜尋（Google News RSS）."""

from langchain_core.tools import tool

from services.news_service import search_news


@tool
def search_financial_news(query: str, max_results: int = 5) -> str:
    """搜尋最新的財經新聞，了解市場動態與個股相關報導。

    當使用者問到「最近有什麼新聞」、「市場動態」、「某某股票新聞」時使用。

    Args:
        query: 搜尋關鍵字，例如「台積電」、「NVDA earnings」、「Fed 利率」。
        max_results: 回傳新聞數量上限（預設 5 則）。
    """
    result = search_news(query, max_results=max_results)

    if result.error:
        return result.error

    parts = [f"📰 「{query}」相關新聞（共 {len(result.articles)} 則）", ""]

    for i, article in enumerate(result.articles, 1):
        source_tag = f"（{article.source}）" if article.source else ""
        time_tag = f" — {article.published}" if article.published else ""
        parts.append(f"[{i}] {article.title}{source_tag}{time_tag}")

    parts.append("")
    parts.append("💡 提示：以上新聞來自 Google News，僅供參考。")

    return "\n".join(parts)
