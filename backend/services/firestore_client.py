"""Firestore client singleton for Navi."""

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.client import Client

from config import settings

_db: Client | None = None


def _init_firebase() -> None:
    """Initialize Firebase Admin SDK (idempotent)."""
    if firebase_admin._apps:
        return

    cred_path = settings.google_application_credentials
    if cred_path:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {"projectId": settings.google_cloud_project})
    else:
        # Fall back to Application Default Credentials (e.g. on Cloud Run)
        firebase_admin.initialize_app(options={"projectId": settings.google_cloud_project})


def get_db() -> Client:
    """Return the Firestore client singleton."""
    global _db
    if _db is None:
        _init_firebase()
        _db = firestore.client()
    return _db
