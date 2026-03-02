"""Tool: 投資知識庫搜尋（RAG Vector Search）."""

from langchain_core.tools import tool

from services.embedding_service import search_similar


@tool
def search_knowledge(query: str) -> str:
    """搜尋投資知識庫，找到與問題最相關的專業知識（技術分析、基本面分析、風險管理等）。

    當使用者問到投資理論、指標定義、分析方法時，使用此工具。

    Args:
        query: 要搜尋的問題或關鍵字，例如「RSI 超買超賣」、「均線黃金交叉」。
    """
    results = search_similar(query, top_k=5)

    if not results:
        return "知識庫中沒有找到與此問題相關的內容。"

    parts = ["📚 知識庫搜尋結果：", ""]
    for i, doc in enumerate(results, 1):
        meta = doc.get("metadata", {})
        title = meta.get("title", "未知")
        category = meta.get("category", "")
        content = doc.get("content", "")
        # Truncate overly long content
        if len(content) > 600:
            content = content[:600] + "…"
        parts.append(f"[{i}] {title}（{category}）")
        parts.append(content)
        parts.append("")

    return "\n".join(parts)
