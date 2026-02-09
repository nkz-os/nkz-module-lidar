#!/usr/bin/env python3
"""
PNOA/IDENA LiDAR Coverage Index Seeder

This script populates the lidar_coverage_index table with available LiDAR tile coverage.

Usage:
    # Seed with example tiles (Navarra region)
    python seed_coverage.py --example

    # Seed from CNIG shapefile
    python seed_coverage.py --shapefile /path/to/pnoa_coverage.shp --source PNOA

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



def seed_from_navarra_shapefile(db_session, shapefile_path: str, clear_existing: bool = False):
    """
    Seed from official Navarra/IDENA shapefile (Malla_Lidar_2024_EPSG25830.shp).

    This shapefile contains 12,428 tiles with direct download URLs.
    Fields: name, DL_LAS (download URL), Dens_Lidar, geometry (EPSG:25830)

    Download from: https://filescartografia.navarra.es/5_LIDAR/Mallas/2024/
    """
    import fiona
    from shapely.geometry import shape
    from pyproj import Transformer
    from app.models import LidarCoverageIndex

    logger.info(f"Seeding from Navarra shapefile: {shapefile_path}")

    if clear_existing:
        deleted = db_session.query(LidarCoverageIndex).filter(
            LidarCoverageIndex.source == "NAVARRA_2024"
        ).delete()
        db_session.commit()
        logger.info(f"Cleared {deleted} existing NAVARRA_2024 entries")

    # Transformer from EPSG:25830 (UTM 30N) to EPSG:4326 (WGS84)
    transformer = Transformer.from_crs("EPSG:25830", "EPSG:4326", always_xy=True)

    count = 0
    skipped = 0

    with fiona.open(shapefile_path, 'r') as shp:
        logger.info(f"Shapefile CRS: {shp.crs}")
        logger.info(f"Total features: {len(shp)}")
        logger.info(f"Fields: {list(shp.schema['properties'].keys())}")

        for feature in shp:
            props = feature['properties']
            geom = shape(feature['geometry'])

            # Get tile name and download URL
            tile_name = props.get('name', '')
            laz_url = props.get('DL_LAS', '')

            if not laz_url:
                skipped += 1
                continue

            # Parse density (format: "14 p/m2" or similar)
            density_str = props.get('Dens_Lidar', '')
            point_density = None
            if density_str:
                try:
                    point_density = float(density_str.split()[0])
                except (ValueError, IndexError):
                    pass

            # Check if tile already exists
            existing = db_session.query(LidarCoverageIndex).filter(
                LidarCoverageIndex.tile_name == tile_name
            ).first()

            if existing:
                skipped += 1
                continue

            # Transform geometry to WGS84
            transformed_coords = []
            if geom.geom_type == 'Polygon':
                exterior_coords = []
                for x, y in geom.exterior.coords:
                    lon, lat = transformer.transform(x, y)
                    exterior_coords.append(f"{lon} {lat}")
                wkt = f"POLYGON(({', '.join(exterior_coords)}))"
            else:
                logger.warning(f"Skipping non-polygon geometry: {geom.geom_type}")
                skipped += 1
                continue

            # Create entry
            tile = LidarCoverageIndex(
                tile_name=tile_name,
                source="NAVARRA_2024",
                flight_year=2024,
                point_density=point_density,
                laz_url=laz_url,
                geometry=f"SRID=4326;{wkt}",
                extra_metadata={
                    "original_crs": "EPSG:25830",
                    "lidar_system": props.get('LiDAR_Sys', ''),
                    "classification": props.get('Clasific', ''),
                    "seed_date": datetime.utcnow().isoformat()
                }
            )
            db_session.add(tile)
            count += 1

            if count % 1000 == 0:
                db_session.commit()
                logger.info(f"Processed {count} tiles...")

    db_session.commit()
    logger.info(f"Seeded {count} tiles from Navarra shapefile (skipped {skipped})")
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
    parser.add_argument("--navarra", type=str, metavar="PATH",
                        help="Seed from Navarra 2024 shapefile (Malla_Lidar_2024_EPSG25830.shp)")
    parser.add_argument("--shapefile", type=str, help="Path to CNIG shapefile")
    parser.add_argument("--source", type=str, default="PNOA", help="Source name for shapefile")
    parser.add_argument("--clear", action="store_true", help="Clear existing entries before seeding")
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

        if args.navarra:
            seed_from_navarra_shapefile(db, args.navarra, clear_existing=args.clear)

        if args.shapefile:
            seed_from_shapefile(db, args.shapefile, args.source)

        if not any([args.example, args.navarra, args.shapefile]):
            parser.print_help()
            print("\nNo action specified. Use --navarra, --shapefile, or --example")
            print("\nRecommended for Navarra:")
            print("  1. Download: https://filescartografia.navarra.es/5_LIDAR/Mallas/2024/")
            print("  2. Run: python seed_coverage.py --navarra Malla_Lidar_2024_EPSG25830.shp")
            return

        # Always verify after seeding
        verify_coverage(db)

    finally:
        db.close()


if __name__ == "__main__":
    main()
