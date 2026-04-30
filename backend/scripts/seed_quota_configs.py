"""Seed quota_configs collection with default tier limits.

Usage:
    cd backend
    uv run python scripts/seed_quota_configs.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import firestore as firestore_module

from services.firestore_client import get_db
from services.quota_service import (
    DEFAULT_TIER_CONFIGS,
    QUOTA_CONFIGS_COLLECTION,
)


def main() -> None:
    db = get_db()
    coll = db.collection(QUOTA_CONFIGS_COLLECTION)
    for tier, cfg in DEFAULT_TIER_CONFIGS.items():
        doc = {
            **cfg,
            "tier": tier,
            "updated_at": firestore_module.SERVER_TIMESTAMP,
            "updated_by": "seed_script",
        }
        coll.document(tier).set(doc, merge=True)
        print(f"  ✓ {tier:10s} daily_limit={cfg['daily_limit']:>4d}  per_minute={cfg['per_minute_limit']}")
    print("\nDone. quota_configs seeded.")


if __name__ == "__main__":
    main()
