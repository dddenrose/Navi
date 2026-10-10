"""Link a LINE user to a Navi account so they can chat with Navi on LINE.

Two modes:
- Link to an existing Navi account (e.g. your own web account).
- ``--create``: for friends who only use LINE and have no Navi account. Creates a
  LINE-only account first, then links it.

Sets:
- Firestore line_links/{line-user-id} = { uid, email, ... }
- With --create, also the Firebase Auth user ``line_<line-user-id>`` (no email or
  password, so it cannot sign in to the web app) and Firestore users/{uid} on the
  free tier. The Auth user keeps set_tier.py and the other ops scripts working.

Usage:
    cd backend
    uv run python scripts/link_line.py <email-or-uid> <line-user-id>
    uv run python scripts/link_line.py --create <line-user-id> [display-name]

Without a display name, --create reads it from the LINE profile (the user must
have added the bot as a friend), which needs the channel access token:
    LINE_CHANNEL_ACCESS_TOKEN=$(gcloud secrets versions access latest \\
        --secret=line-channel-access-token) \\
      uv run python scripts/link_line.py --create <line-user-id>

The LINE user ID (U + 32 hex chars) is shown in the bot's reply to an unlinked
user, and under "Your user ID" in the LINE Developers Console.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import firebase_admin.auth as firebase_auth

from services import quota_service
from services.firestore_client import _init_firebase
from services.line.client import get_display_name
from services.line.store import get_link, set_link

USAGE = (
    "Usage:\n"
    "  uv run python scripts/link_line.py <email-or-uid> <line-user-id>\n"
    "  uv run python scripts/link_line.py --create <line-user-id> [display-name]"
)
LINE_ONLY_UID_PREFIX = "line_"
_LINE_USER_ID_RE = re.compile(r"^U[0-9a-f]{32}$")


def _validate_line_user_id(raw: str) -> str:
    line_user_id = raw.strip()
    if not _LINE_USER_ID_RE.match(line_user_id):
        print(f"Error: invalid LINE user ID '{line_user_id}'. Expected U + 32 hex chars.")
        sys.exit(1)
    return line_user_id


def _resolve_user(identifier: str):
    if "@" in identifier:
        return firebase_auth.get_user_by_email(identifier)
    return firebase_auth.get_user(identifier)


def link_existing_account(identifier: str, line_user_id: str) -> None:
    """Link a LINE user to an existing Navi account (overwrites any previous link)."""
    try:
        record = _resolve_user(identifier)
    except Exception as exc:
        print(f"Error: cannot find Firebase user for '{identifier}': {exc}")
        sys.exit(2)

    uid = record.uid
    email = record.email or ""
    print(f"Found user: uid={uid} email={email}")
    print(f"Linking LINE user {line_user_id} → {uid}")
    set_link(line_user_id, uid, email)
    print("✅ Done. Messages from this LINE user now run as this Navi account.")


def create_line_only_account(line_user_id: str, display_name: str) -> str:
    """Create the LINE-only Navi account for this LINE user, or reuse it; return its uid."""
    uid = f"{LINE_ONLY_UID_PREFIX}{line_user_id}"
    try:
        firebase_auth.get_user(uid)
        print(f"Account already exists: uid={uid}")
    except firebase_auth.UserNotFoundError:
        firebase_auth.create_user(uid=uid, display_name=display_name or None)
        print(f"Created account: uid={uid} display={display_name or '—'}")
    quota_service.get_or_create_user(uid, display_name=display_name)
    return uid


def link_new_account(line_user_id: str, display_name: str = "") -> None:
    """Create a LINE-only account and link it. Leaves an existing link untouched."""
    existing = get_link(line_user_id)
    if existing and existing.get("uid"):
        print(f"Already linked: {line_user_id} → uid={existing['uid']}. Nothing changed.")
        return

    name = display_name or get_display_name(line_user_id)
    if not name:
        print("Note: no display name (pass one, or set LINE_CHANNEL_ACCESS_TOKEN to read it).")
    uid = create_line_only_account(line_user_id, name)
    set_link(line_user_id, uid)
    print(f"✅ Done. {name or line_user_id} can now ask Navi on LINE (free tier).")


def main() -> None:
    args = sys.argv[1:]
    if args[:1] == ["--create"] and len(args) in (2, 3):
        line_user_id = _validate_line_user_id(args[1])
        display_name = args[2].strip() if len(args) == 3 else ""
        _init_firebase()
        link_new_account(line_user_id, display_name)
    elif len(args) == 2 and not args[0].startswith("--"):
        line_user_id = _validate_line_user_id(args[1])
        _init_firebase()
        link_existing_account(args[0], line_user_id)
    else:
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
