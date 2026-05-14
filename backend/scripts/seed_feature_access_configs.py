"""Seed feature_access_configs collection with default permissions.

Usage:
    cd backend
    uv run python scripts/seed_feature_access_configs.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.cloud import firestore as firestore_module

from services.feature_access_service import (
    DEFAULT_FEATURE_ACCESS_CONFIGS,
    FEATURE_ACCESS_CONFIGS_COLLECTION,
)
from services.firestore_client import get_db


def main() -> None:
    db = get_db()
    coll = db.collection(FEATURE_ACCESS_CONFIGS_COLLECTION)
    for feature_key, cfg in DEFAULT_FEATURE_ACCESS_CONFIGS.items():
        doc = {
            **cfg,
            "updated_at": firestore_module.SERVER_TIMESTAMP,
            "updated_by": "seed_script",
        }
        coll.document(feature_key).set(doc, merge=True)
        tiers = ", ".join(cfg["allowed_tiers"])
        print(f"  ✓ {feature_key:10s} enabled={cfg['enabled']} tiers={tiers}")
    print("\nDone. feature_access_configs seeded.")


if __name__ == "__main__":
    main()
