"""Link a LINE user to an existing Navi (Firebase) account.

Anyone who adds the bot gets a LINE-only account automatically on first contact,
so this script is only needed to make LINE use someone's web account instead,
e.g. your own, so LINE and the web app share quota, portfolio and conversations.

Sets:
- Firestore line_links/{line-user-id} = { uid, email, ... } (overwrites any previous link)

Usage:
    cd backend
    uv run python scripts/link_line.py <email-or-uid> <line-user-id>

Your own LINE user ID (U + 32 hex chars) is under "Your user ID" in the LINE
Developers Console; anyone who has messaged the bot shows up in the admin console
as uid line_<line-user-id>.
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import firebase_admin.auth as firebase_auth

from services.firestore_client import _init_firebase
from services.line.store import set_link

_LINE_USER_ID_RE = re.compile(r"^U[0-9a-f]{32}$")


def _resolve_user(identifier: str):
    if "@" in identifier:
        return firebase_auth.get_user_by_email(identifier)
    return firebase_auth.get_user(identifier)


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: uv run python scripts/link_line.py <email-or-uid> <line-user-id>")
        sys.exit(1)

    identifier = sys.argv[1]
    line_user_id = sys.argv[2].strip()
    if not _LINE_USER_ID_RE.match(line_user_id):
        print(f"Error: invalid LINE user ID '{line_user_id}'. Expected U + 32 hex chars.")
        sys.exit(1)

    _init_firebase()

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


if __name__ == "__main__":
    main()
