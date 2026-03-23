#!/usr/bin/env python3
"""
One-time migration: seed PostgreSQL from data/properties.json.

Run from project root:
    python scripts/migrate_to_postgres.py

Requires POSTGRES_DSN in .env (or environment).
Tables must already exist — run scripts/init_schema.sql first.
"""
import sys
import json
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncpg
from app.config import settings


async def main():
    # Load properties.json
    properties_path = Path(__file__).parent.parent / "data" / "properties.json"
    with open(properties_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conn = await asyncpg.connect(dsn=settings.postgres_dsn)

    try:
        # ── general_policies ─────────────────────────────────────────────────
        general = data.get("general", {})
        await conn.execute("""
            INSERT INTO general_policies (
                row_id, pet_policy, checkout_time, checkin_time,
                late_checkout_policy, early_checkin_policy,
                noise_policy, visitor_policy, suite_directory
            ) VALUES (1, $1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (row_id) DO UPDATE SET
                pet_policy           = EXCLUDED.pet_policy,
                checkout_time        = EXCLUDED.checkout_time,
                checkin_time         = EXCLUDED.checkin_time,
                late_checkout_policy = EXCLUDED.late_checkout_policy,
                early_checkin_policy = EXCLUDED.early_checkin_policy,
                noise_policy         = EXCLUDED.noise_policy,
                visitor_policy       = EXCLUDED.visitor_policy,
                suite_directory      = EXCLUDED.suite_directory,
                updated_at           = NOW()
        """,
            general.get("pet_policy", ""),
            general.get("checkout_time", ""),
            general.get("checkin_time", ""),
            general.get("late_checkout_policy", ""),
            general.get("early_checkin_policy", ""),
            general.get("noise_policy", ""),
            general.get("visitor_policy", ""),
            general.get("suite_directory", ""),
        )
        print("✓ general_policies: 1 row upserted")

        # ── buildings + units ─────────────────────────────────────────────────
        buildings = data.get("buildings", {})
        building_count = 0
        unit_count = 0

        for building_id, building in buildings.items():
            amenities = building.get("amenities", [])

            await conn.execute("""
                INSERT INTO buildings (building_id, name, address, amenities, lift_access)
                VALUES ($1, $2, $3, $4::jsonb, $5)
                ON CONFLICT (building_id) DO UPDATE SET
                    name        = EXCLUDED.name,
                    address     = EXCLUDED.address,
                    amenities   = EXCLUDED.amenities,
                    lift_access = EXCLUDED.lift_access,
                    updated_at  = NOW()
            """,
                building_id,
                building.get("name", ""),
                building.get("address", ""),
                json.dumps(amenities),
                building.get("lift_access", ""),
            )
            building_count += 1

            for unit_id, unit in building.get("units", {}).items():
                await conn.execute("""
                    INSERT INTO units (
                        building_id, unit_id, suite_name, description, room_type,
                        floor, max_pax, price_per_night,
                        wifi_ssid, wifi_password, parking_bay, checkin_code,
                        extra_beds_available, extra_bed_fee
                    ) VALUES (
                        $1, $2, $3, $4, $5,
                        $6, $7, $8,
                        $9, $10, $11, $12,
                        $13, $14
                    )
                    ON CONFLICT (building_id, unit_id) DO UPDATE SET
                        suite_name           = EXCLUDED.suite_name,
                        description          = EXCLUDED.description,
                        room_type            = EXCLUDED.room_type,
                        floor                = EXCLUDED.floor,
                        max_pax              = EXCLUDED.max_pax,
                        price_per_night      = EXCLUDED.price_per_night,
                        wifi_ssid            = EXCLUDED.wifi_ssid,
                        wifi_password        = EXCLUDED.wifi_password,
                        parking_bay          = EXCLUDED.parking_bay,
                        checkin_code         = EXCLUDED.checkin_code,
                        extra_beds_available = EXCLUDED.extra_beds_available,
                        extra_bed_fee        = EXCLUDED.extra_bed_fee,
                        updated_at           = NOW()
                """,
                    building_id,
                    unit_id,
                    unit.get("suite_name", ""),
                    unit.get("description", ""),
                    unit.get("room_type", ""),
                    unit.get("floor", 0),
                    unit.get("max_pax", 1),
                    unit.get("price_per_night", 0),
                    unit.get("wifi_ssid", ""),
                    unit.get("wifi_password", ""),
                    unit.get("parking_bay"),
                    unit.get("checkin_code", ""),
                    unit.get("extra_beds_available", False),
                    unit.get("extra_bed_fee"),
                )
                unit_count += 1

        print(f"✓ buildings: {building_count} rows upserted")
        print(f"✓ units:     {unit_count} rows upserted")
        print("\nMigration complete.")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
