"""Promote a user to admin tier.

Sets:
- Firestore users/{uid}.tier = "admin"
- Firebase custom claims: { admin: true, tier: "admin" }

Usage:
    cd backend
    uv run python scripts/set_admin.py <email-or-uid>

The user must have logged in at least once for Firebase Auth to know them.
After running, the user must sign out and sign back in (or wait up to 1h)
for the new ID token to carry the claims.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import firestore as firestore_module

import firebase_admin.auth as firebase_auth

from services.firestore_client import _init_firebase, get_db
from services.quota_service import USERS_COLLECTION


def _resolve_user(identifier: str):
    if "@" in identifier:
        return firebase_auth.get_user_by_email(identifier)
    return firebase_auth.get_user(identifier)


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: uv run python scripts/set_admin.py <email-or-uid>")
        sys.exit(1)

    identifier = sys.argv[1]
    _init_firebase()

    try:
        record = _resolve_user(identifier)
    except Exception as exc:
        print(f"Error: cannot find Firebase user for '{identifier}': {exc}")
        sys.exit(2)

    uid = record.uid
    email = record.email or ""
    display = record.display_name or ""
    print(f"Found user: uid={uid} email={email} display={display}")

    # Set custom claims
    firebase_auth.set_custom_user_claims(uid, {"admin": True, "tier": "admin"})
    print("  ✓ Firebase custom claims set: { admin: true, tier: 'admin' }")

    # Upsert Firestore user doc
    db = get_db()
    doc_ref = db.collection(USERS_COLLECTION).document(uid)
    snap = doc_ref.get()
    now = firestore_module.SERVER_TIMESTAMP
    payload = {
        "uid": uid,
        "email": email,
        "display_name": display,
        "tier": "admin",
        "status": "active",
        "updated_at": now,
        "last_active_at": now,
    }
    if not snap.exists:
        payload["created_at"] = now
        payload["custom_daily_limit"] = None
        payload["notes"] = "Promoted via set_admin.py"
    doc_ref.set(payload, merge=True)
    print(f"  ✓ Firestore users/{uid} → tier=admin")

    print("\nDone. The user should sign out and sign back in to refresh their ID token.")


if __name__ == "__main__":
    main()
