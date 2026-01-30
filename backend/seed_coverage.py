#!/usr/bin/env python3
"""
PNOA/IDENA LiDAR Coverage Index Seeder

This script populates the lidar_coverage_index table with available LiDAR tile coverage.

Usage:
    # Seed with example tiles (Navarra region)
    python seed_coverage.py --example

    # Seed from CNIG shapefile
    python seed_coverage.py --shapefile /path/to/pnoa_coverage.shp --source PNOA

    # Seed from IDENA (Navarra) - predefined tiles
    python seed_coverage.py --idena

Environment variables required:
    DATABASE_URL - PostgreSQL connection string

Data sources:
    - CNIG (national): https://centrodedescargas.cnig.es/CentroDescargas/
    - IDENA (Navarra): https://idena.navarra.es/descargas/
"""

import os
import sys
import argparse
import logging
from datetime import datetime

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Example tiles for Navarra region (IDENA)
# These are real tile URLs from the public IDENA LiDAR service
EXAMPLE_TILES_NAVARRA = [
    {
        "tile_name": "PNOA_2023_NAV_569-4737",
        "source": "IDENA",
        "flight_year": 2023,
        "point_density": 4.0,
        "laz_url": "https://idena.navarra.es/descargas/lidar/LAZ/PNOA_2023_NAV_569-4737.laz",
        # Approximate bounding box for tile (WGS84)
        "geometry_wkt": "POLYGON((-1.75 42.80, -1.70 42.80, -1.70 42.75, -1.75 42.75, -1.75 42.80))"
    },
    {
        "tile_name": "PNOA_2023_NAV_570-4737",
        "source": "IDENA",
        "flight_year": 2023,
        "point_density": 4.0,
        "laz_url": "https://idena.navarra.es/descargas/lidar/LAZ/PNOA_2023_NAV_570-4737.laz",
        "geometry_wkt": "POLYGON((-1.70 42.80, -1.65 42.80, -1.65 42.75, -1.70 42.75, -1.70 42.80))"
    },
    {
        "tile_name": "PNOA_2023_NAV_571-4737",
        "source": "IDENA",
        "flight_year": 2023,
        "point_density": 4.0,
        "laz_url": "https://idena.navarra.es/descargas/lidar/LAZ/PNOA_2023_NAV_571-4737.laz",
        "geometry_wkt": "POLYGON((-1.65 42.80, -1.60 42.80, -1.60 42.75, -1.65 42.75, -1.65 42.80))"
    },
    {
        "tile_name": "PNOA_2023_NAV_569-4736",
        "source": "IDENA",
        "flight_year": 2023,
        "point_density": 4.0,
        "laz_url": "https://idena.navarra.es/descargas/lidar/LAZ/PNOA_2023_NAV_569-4736.laz",
        "geometry_wkt": "POLYGON((-1.75 42.75, -1.70 42.75, -1.70 42.70, -1.75 42.70, -1.75 42.75))"
    },
    {
        "tile_name": "PNOA_2023_NAV_570-4736",
        "source": "IDENA",
        "flight_year": 2023,
        "point_density": 4.0,
        "laz_url": "https://idena.navarra.es/descargas/lidar/LAZ/PNOA_2023_NAV_570-4736.laz",
        "geometry_wkt": "POLYGON((-1.70 42.75, -1.65 42.75, -1.65 42.70, -1.70 42.70, -1.70 42.75))"
    },
    # Pamplona area
    {
        "tile_name": "PNOA_2023_NAV_612-4722",
        "source": "IDENA",
        "flight_year": 2023,
        "point_density": 4.0,
        "laz_url": "https://idena.navarra.es/descargas/lidar/LAZ/PNOA_2023_NAV_612-4722.laz",
        "geometry_wkt": "POLYGON((-1.68 42.83, -1.63 42.83, -1.63 42.78, -1.68 42.78, -1.68 42.83))"
    },
]

# IDENA provides a WFS service with the full tile index
# This can be used to get all tiles programmatically
IDENA_WFS_URL = "https://idena.navarra.es/ogc/wfs"
IDENA_LAYER = "IDENA:LIDAR_Vuelo"


def seed_example_tiles(db_session):
    """Seed database with example tiles from Navarra."""
    from app.models import LidarCoverageIndex

    logger.info("Seeding example tiles for Navarra region...")
    count = 0

    for tile_data in EXAMPLE_TILES_NAVARRA:
        # Check if tile already exists
        existing = db_session.query(LidarCoverageIndex).filter(
            LidarCoverageIndex.tile_name == tile_data["tile_name"]
        ).first()

        if existing:
            logger.info(f"Tile {tile_data['tile_name']} already exists, skipping")
            continue

        tile = LidarCoverageIndex(
            tile_name=tile_data["tile_name"],
            source=tile_data["source"],
            flight_year=tile_data["flight_year"],
            point_density=tile_data["point_density"],
            laz_url=tile_data["laz_url"],
            geometry=f"SRID=4326;{tile_data['geometry_wkt']}",
            extra_metadata={"seeded": True, "seed_date": datetime.utcnow().isoformat()}
        )
        db_session.add(tile)
        count += 1

    db_session.commit()
    logger.info(f"Seeded {count} example tiles")
    return count


def seed_from_shapefile(db_session, shapefile_path: str, source: str = "PNOA"):
    """Seed from CNIG shapefile."""
    from app.services.pnoa_indexer import PNOAIndexer

    logger.info(f"Seeding from shapefile: {shapefile_path}")
    indexer = PNOAIndexer(db_session)

    # Field names vary by CNIG shapefile version
    # Common fields: URL, NOMBRE, AÑO, DENSIDAD
    count = indexer.seed_from_shapefile(
        shapefile_path,
        source=source,
        url_field="URL",
        name_field="NOMBRE",
        year_field="AÑO",
        density_field="DENSIDAD",
        clear_existing=False
    )

    logger.info(f"Seeded {count} tiles from shapefile")
    return count


def seed_from_idena_wfs(db_session):
    """Seed from IDENA WFS service (Navarra full coverage)."""
    import requests
    from app.models import LidarCoverageIndex

    logger.info("Querying IDENA WFS for LiDAR coverage...")

    # WFS GetFeature request for all LiDAR tiles
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeName": IDENA_LAYER,
        "outputFormat": "application/json",
        "srsName": "EPSG:4326"
    }

    try:
        response = requests.get(IDENA_WFS_URL, params=params, timeout=120)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        logger.error(f"Failed to query IDENA WFS: {e}")
        return 0

    features = data.get("features", [])
    logger.info(f"Found {len(features)} features in IDENA WFS")

    count = 0
    for feature in features:
        props = feature.get("properties", {})
        geom = feature.get("geometry", {})

        if not geom or geom.get("type") != "Polygon":
            continue

        # Extract properties (field names may vary)
        tile_name = props.get("FICHERO") or props.get("NOMBRE") or f"IDENA_{count}"
        laz_url = props.get("URL_DESCARGA") or props.get("URL")

        if not laz_url:
            continue

        # Build WKT from GeoJSON coordinates
        coords = geom.get("coordinates", [[]])[0]
        wkt_coords = ", ".join([f"{c[0]} {c[1]}" for c in coords])
        geometry_wkt = f"POLYGON(({wkt_coords}))"

        # Check if exists
        existing = db_session.query(LidarCoverageIndex).filter(
            LidarCoverageIndex.tile_name == tile_name
        ).first()

        if existing:
            continue

        tile = LidarCoverageIndex(
            tile_name=tile_name,
            source="IDENA",
            flight_year=props.get("ANYO"),
            point_density=props.get("DENSIDAD"),
            laz_url=laz_url,
            geometry=f"SRID=4326;{geometry_wkt}",
            extra_metadata=props
        )
        db_session.add(tile)
        count += 1

        if count % 100 == 0:
            db_session.commit()
            logger.info(f"Processed {count} tiles...")

    db_session.commit()
    logger.info(f"Seeded {count} tiles from IDENA WFS")
    return count


def verify_coverage(db_session):
    """Verify and print coverage statistics."""
    from app.models import LidarCoverageIndex
    from sqlalchemy import func

    total = db_session.query(func.count(LidarCoverageIndex.id)).scalar()

    by_source = db_session.query(
        LidarCoverageIndex.source,
        func.count(LidarCoverageIndex.id)
    ).group_by(LidarCoverageIndex.source).all()

    print("\n=== LiDAR Coverage Index Statistics ===")
    print(f"Total tiles: {total}")
    print("\nBy source:")
    for source, count in by_source:
        print(f"  {source}: {count}")
    print("=" * 40)


def main():
    parser = argparse.ArgumentParser(description="Seed LiDAR coverage index")
    parser.add_argument("--example", action="store_true", help="Seed example tiles (Navarra)")
    parser.add_argument("--idena", action="store_true", help="Seed from IDENA WFS (Navarra full)")
    parser.add_argument("--shapefile", type=str, help="Path to CNIG shapefile")
    parser.add_argument("--source", type=str, default="PNOA", help="Source name for shapefile")
    parser.add_argument("--verify", action="store_true", help="Only verify current coverage")
    args = parser.parse_args()

    # Import database session
    from app.db import SessionLocal

    db = SessionLocal()
    try:
        if args.verify:
            verify_coverage(db)
            return

        if args.example:
            seed_example_tiles(db)

        if args.idena:
            seed_from_idena_wfs(db)

        if args.shapefile:
            seed_from_shapefile(db, args.shapefile, args.source)

        if not any([args.example, args.idena, args.shapefile]):
            parser.print_help()
            print("\nNo action specified. Use --example, --idena, or --shapefile")
            return

        # Always verify after seeding
        verify_coverage(db)

    finally:
        db.close()


if __name__ == "__main__":
    main()
