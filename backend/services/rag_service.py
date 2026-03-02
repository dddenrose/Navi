"""RAG Service — Vector Search + Gemini for investment analysis."""

import logging
from collections.abc import AsyncGenerator

import vertexai

logger = logging.getLogger(__name__)
from vertexai.generative_models import GenerativeModel

from config import settings
from models.prompts import ANALYST_PROMPT, SYSTEM_PROMPT
from services.embedding_service import search_similar

_model: GenerativeModel | None = None


def _get_model() -> GenerativeModel:
    """Return Gemini model singleton."""
    global _model
    if _model is None:
        vertexai.init(project=settings.google_cloud_project)
        _model = GenerativeModel(
            model_name=settings.gemini_model_name,
            system_instruction=SYSTEM_PROMPT,
        )
    return _model


async def analyze(
    question: str,
    ticker: str | None = None,
    top_k: int = 5,
) -> AsyncGenerator[str, None]:
    """Run RAG pipeline: search knowledge → build prompt → stream Gemini response.

    Args:
        question: User's natural language question.
        ticker: Optional stock ticker for real-time data (Phase 2).
        top_k: Number of knowledge documents to retrieve.

    Yields:
        Text chunks from the streaming Gemini response.
    """
    # 1. Retrieve relevant knowledge via vector search
    relevant_docs = search_similar(question, top_k=top_k)

    context_parts = []
    sources = []
    for i, doc in enumerate(relevant_docs, 1):
        meta = doc.get("metadata", {})
        content = doc.get("content", "")
        context_parts.append(f"[{i}] {meta.get('title', 'Unknown')}:\n{content}")
        sources.append(
            {
                "index": i,
                "title": meta.get("title", ""),
                "source_file": meta.get("source_file", ""),
                "category": meta.get("category", ""),
            }
        )

    context = "\n\n---\n\n".join(context_parts) if context_parts else "（知識庫中沒有找到相關內容）"

    # 2. Real-time stock data
    stock_data = "（未指定股票代碼，僅基於知識庫回答）"
    if ticker:
        try:
            from services.stock_service import get_full_stock_data

            stock_data = get_full_stock_data(ticker)
        except Exception as e:
            logger.warning("Failed to fetch stock data for %s: %s", ticker, e)
            stock_data = f"（取得 {ticker} 數據失敗：{e}）"

    # 3. Build prompt and call Gemini with streaming
    prompt = ANALYST_PROMPT.format(
        context=context,
        stock_data=stock_data,
        question=question,
    )

    model = _get_model()
    response = model.generate_content(prompt, stream=True)

    for chunk in response:
        if chunk.text:
            yield chunk.text

    # Yield source references at the end
    if sources:
        yield "\n\n---\n📄 **參考來源：**\n"
        for src in sources:
            yield f"[{src['index']}] {src['title']} ({src['source_file']})\n"


def get_sources_from_search(question: str, top_k: int = 5) -> list[dict]:
    """Search knowledge base and return source metadata (non-streaming)."""
    docs = search_similar(question, top_k=top_k)
    return [
        {
            "title": doc.get("metadata", {}).get("title", ""),
            "source_file": doc.get("metadata", {}).get("source_file", ""),
            "category": doc.get("metadata", {}).get("category", ""),
        }
        for doc in docs
    ]
