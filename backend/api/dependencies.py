"""Dependency injection for Navi API."""

import logging
from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import settings

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def verify_firebase_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Verify Firebase ID Token from Authorization: Bearer <token> header.

    When AUTH_REQUIRED=false (development), skips verification and returns
    a mock user so all endpoints remain accessible without a token.
    """
    if not settings.auth_required:
        # Dev mode — skip auth, return a stub user
        return {"uid": "dev-user", "email": "dev@localhost"}

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header. Use: Authorization: Bearer <firebase-id-token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        import firebase_admin.auth as firebase_auth

        # Ensure Firebase app is initialized (may not be if Firestore hasn't been used yet)
        from services.firestore_client import _init_firebase

        _init_firebase()
        decoded = firebase_auth.verify_id_token(credentials.credentials)
        return decoded
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase ID token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_settings():
    """Return the application settings singleton."""
    return settings


async def require_admin(user: dict = Depends(verify_firebase_token)) -> dict:
    """Ensure the caller is an admin.

    Verifies BOTH the Firebase ID token claim ``admin == true`` AND the
    Firestore ``users/{uid}.tier == 'admin'``. Either failure → 403.
    """
    if not settings.auth_required:
        # Dev mode: trust the stub user
        return user

    uid = user.get("uid", "")
    if not uid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No uid")

    if not user.get("admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")

    # Defense in depth: also check Firestore (in case claims drifted)
    try:
        from services.quota_service import get_user

        record = get_user(uid)
        if not record or record.get("tier") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin tier check failed",
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Admin check failed")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Admin check error")

    return user


def require_feature_access(feature_key: str) -> Callable:
    """Return a dependency that ensures the caller can access a feature."""

    async def _require_feature_access(
        user: dict = Depends(verify_firebase_token),
    ) -> dict:
        if not settings.auth_required:
            return user

        uid = user.get("uid", "")
        if not uid:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No uid")

        try:
            from services import feature_access_service

            result = feature_access_service.check_feature_access(
                feature_key,
                uid,
                email=user.get("email", ""),
                display_name=user.get("name", "") or user.get("display_name", ""),
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("Feature access check failed for %s", feature_key)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Feature access check error",
            )

        if result.allowed:
            return user

        message = "此功能目前不開放。"
        code = "FEATURE_ACCESS_DENIED"
        if result.reason == "account_suspended":
            message = "帳號已被停用，請聯絡管理員。"
            code = "ACCOUNT_SUSPENDED"
        elif result.reason == "feature_disabled":
            message = "此功能目前已被管理員停用。"
            code = "FEATURE_DISABLED"

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": code,
                "message": message,
                "feature_key": result.feature_key,
                "display_name": result.display_name,
                "tier": result.tier,
                "allowed_tiers": result.allowed_tiers,
                "reason": result.reason,
            },
        )

    return _require_feature_access
