"""Dependency injection for Navi API."""

import logging

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
