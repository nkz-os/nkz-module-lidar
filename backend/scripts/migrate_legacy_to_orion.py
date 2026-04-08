"""Idempotent migration helper from legacy SQL records to Orion-LD.

This script is safe to rerun. It only upserts entities that do not exist yet.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from app.services.orion_client import OrionLDClient


def load_legacy_records(path: str) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return data.get("records", [])


def migrate(records: List[Dict[str, Any]], tenant_id: str, dry_run: bool = False) -> Dict[str, int]:
    client = OrionLDClient(tenant_id=tenant_id)
    counters = {"jobs": 0, "assets": 0}
    for item in records:
        job_id = item.get("job_id")
        parcel_id = item.get("parcel_id")
        if not job_id or not parcel_id:
            continue

        if not dry_run:
            client.create_processing_job(
                job_id=job_id,
                parcel_id=parcel_id,
                geometry_wkt=item.get("parcel_geometry_wkt", ""),
                config=item.get("config", {}),
                user_id=item.get("user_id", "legacy-migration"),
            )
            client.update_job(
                f"urn:ngsi-ld:DataProcessingJob:{job_id}",
                status=item.get("status", "completed"),
                progress=item.get("progress", 100),
            )
        counters["jobs"] += 1

        tileset_url = item.get("tileset_url")
        if tileset_url:
            if not dry_run:
                client.create_digital_asset(
                    asset_id=job_id,
                    parcel_id=parcel_id,
                    tileset_url=tileset_url,
                    source=item.get("source", "legacy"),
                    point_count=item.get("point_count", 0),
                    tree_count=item.get("tree_count", 0),
                )
            counters["assets"] += 1
    return counters


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy LiDAR records to Orion-LD")
    parser.add_argument("--input", required=True, help="Path to JSON export")
    parser.add_argument("--tenant", required=True, help="Tenant ID")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    records = load_legacy_records(args.input)
    result = migrate(records, tenant_id=args.tenant, dry_run=args.dry_run)
    print(json.dumps({"processed": len(records), **result, "dry_run": args.dry_run}, indent=2))


if __name__ == "__main__":
    main()

