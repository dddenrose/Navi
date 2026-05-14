"""Feature access discovery API."""

from fastapi import APIRouter, Depends

from api.dependencies import verify_firebase_token
from config import settings
from services import feature_access_service

router = APIRouter(prefix="/api/features", tags=["features"])


@router.get("/access")
async def get_feature_access(user: dict = Depends(verify_firebase_token)):
    """Return the current user's effective access for all known features."""
    if not settings.auth_required:
        return {
            "tier": "dev",
            "status": "active",
            "features": [
                {**config, "allowed": True, "reason": None}
                for config in feature_access_service.list_feature_configs()
            ],
        }

    return feature_access_service.list_feature_access_for_user(
        user.get("uid", ""),
        email=user.get("email", ""),
        display_name=user.get("name", "") or user.get("display_name", ""),
    )
