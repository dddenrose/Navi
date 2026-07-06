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
        # 明確告訴 LLM「不要引用知識庫」，避免硬引用不相干內容
        return (
            "知識庫中沒有與此問題足夠相關的內容。"
            "請直接以工具數據回答，不要聲稱引用知識庫。"
        )

    parts = ["📚 知識庫搜尋結果：", ""]
    for i, doc in enumerate(results, 1):
        meta = doc.get("metadata", {})
        title = meta.get("title", "未知")
        category = meta.get("category", "")
        content = doc.get("content", "")
        # 過長截斷：切在段落邊界，避免把「眉角」的後半段警語截掉
        if len(content) > 1200:
            cut = content.rfind("\n\n", 0, 1200)
            content = content[: cut if cut > 400 else 1200] + "\n…（內容過長已截斷）"
        parts.append(f"[{i}] {title}（{category}）")
        parts.append(content)
        parts.append("")

    return "\n".join(parts)
