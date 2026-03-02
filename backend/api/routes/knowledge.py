"""Knowledge base API — 知識庫管理."""

import logging

from fastapi import APIRouter, Depends

from api.dependencies import verify_firebase_token
from models.schemas import KnowledgeStats

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(verify_firebase_token)],
)


@router.get("/stats", response_model=KnowledgeStats)
async def get_stats():
    """取得知識庫統計資訊。"""
    try:
        from services.embedding_service import get_collection_stats

        stats = get_collection_stats()
        return KnowledgeStats(**stats)
    except Exception as e:
        logger.warning(f"Failed to get knowledge stats: {e}")
        return KnowledgeStats(total_documents=0, categories=[], last_updated=None)
