"""Set a user's tier (free / pro / unlimited / admin) for local testing.

Sets:
- Firestore users/{uid}.tier
- Firebase custom claims: { admin: bool, tier: "<tier>" }

Usage:
    cd backend
    uv run python scripts/set_tier.py <email-or-uid> <tier>

The user must sign out and sign back in for the new ID token to take effect.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import firestore as firestore_module

import firebase_admin.auth as firebase_auth

from services.firestore_client import _init_firebase, get_db
from services.quota_service import USERS_COLLECTION, VALID_TIERS


def _resolve_user(identifier: str):
    if "@" in identifier:
        return firebase_auth.get_user_by_email(identifier)
    return firebase_auth.get_user(identifier)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: uv run python scripts/set_tier.py <email-or-uid> <tier>")
        print(f"  tier: one of {sorted(VALID_TIERS)}")
        sys.exit(1)

    identifier = sys.argv[1]
    tier = sys.argv[2].strip().lower()
    if tier not in VALID_TIERS:
        print(f"Error: invalid tier '{tier}'. Must be one of {sorted(VALID_TIERS)}")
        sys.exit(1)

    _init_firebase()

    try:
        record = _resolve_user(identifier)
    except Exception as exc:
        print(f"Error: cannot find Firebase user for '{identifier}': {exc}")
        sys.exit(2)

    uid = record.uid
    email = record.email or ""
    display = record.display_name or ""
    is_admin = tier == "admin"
    print(f"Found user: uid={uid} email={email} display={display}")
    print(f"Setting tier → {tier} (admin claim={is_admin})")

    firebase_auth.set_custom_user_claims(uid, {"admin": is_admin, "tier": tier})
    print(f"  ✓ Firebase custom claims set: {{ admin: {is_admin}, tier: '{tier}' }}")

    db = get_db()
    doc_ref = db.collection(USERS_COLLECTION).document(uid)
    snap = doc_ref.get()
    now = firestore_module.SERVER_TIMESTAMP
    payload = {
        "uid": uid,
        "email": email,
        "display_name": display,
        "tier": tier,
        "status": "active",
        "updated_at": now,
        "last_active_at": now,
    }
    if not snap.exists:
        payload["created_at"] = now
        payload["custom_daily_limit"] = None
        payload["notes"] = f"Set via set_tier.py ({tier})"
    doc_ref.set(payload, merge=True)
    print(f"  ✓ Firestore users/{uid} → tier={tier}")

    print("\nDone. Sign out and sign back in to refresh the ID token.")


if __name__ == "__main__":
    main()
