"""Chat API — 與 Navi 對話（支援 SSE streaming）."""

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from models.schemas import ChatRequest
from services.rag_service import analyze

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


async def _sse_generator(question: str, ticker: str | None = None):
    """Wrap RAG streaming output in SSE format."""
    try:
        async for chunk in analyze(question, ticker=ticker):
            data = json.dumps({"text": chunk}, ensure_ascii=False)
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception("Error during RAG analysis")
        error_data = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"data: {error_data}\n\n"


@router.post("/chat")
async def chat(request: ChatRequest):
    """與 Navi 對話，回傳 SSE streaming response."""
    return StreamingResponse(
        _sse_generator(request.message, ticker=request.ticker),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
