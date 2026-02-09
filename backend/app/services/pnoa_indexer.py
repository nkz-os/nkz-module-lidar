"""
PNOA LiDAR Coverage Indexer.

This service manages the spatial index of available LiDAR data from CNIG/PNOA.
It provides functionality to:
1. Load/seed the coverage index from official shapefiles
2. Query coverage for a given parcel geometry
3. Get download URLs for .LAZ files

The CNIG provides shapefiles with the coverage grid. Each cell contains
metadata and the URL to download the corresponding .LAZ file.

Usage:
    # Check if a parcel has coverage
    indexer = PNOAIndexer(db_session)
    coverage = indexer.find_coverage(parcel_wkt)
    
    # Seed the database (run once, or on updates)
    indexer.seed_from_shapefile("/path/to/coverage.shp")
"""

import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from geoalchemy2.functions import ST_Intersects, ST_GeomFromText, ST_Transform
import fiona
from shapely.geometry import shape, mapping
from shapely.wkt import loads as wkt_loads

from app.models import LidarCoverageIndex
from app.config import settings

logger = logging.getLogger(__name__)


class PNOAIndexer:
    """
    Service for managing PNOA LiDAR coverage index.
    
    The index is stored in PostGIS and queried using spatial operations.
    """
    
    # Known PNOA download base URLs (varies by region/provider)
    PNOA_BASE_URLS = {
        "centrodedescargas": "https://centrodedescargas.cnig.es/CentroDescargas/",
        "idena": "https://idena.navarra.es/descargas/",
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def find_coverage(
        self,
        geometry_wkt: str,
        source: Optional[str] = None,
        srid: int = 4326
    ) -> List[Dict[str, Any]]:
        """
        Find LiDAR coverage tiles that intersect with the given geometry.
        
        Args:
            geometry_wkt: WKT representation of the area of interest
            source: Optional filter by source (PNOA, IDENA, etc.)
            srid: SRID of the input geometry (default: 4326)
        
        Returns:
            List of coverage tiles with their metadata and LAZ URLs
        """
        try:
            # Build the spatial query
            geom_expr = ST_GeomFromText(geometry_wkt, srid)
            
            query = self.db.query(LidarCoverageIndex).filter(
                ST_Intersects(LidarCoverageIndex.geometry, geom_expr)
            )
            
            if source:
                query = query.filter(LidarCoverageIndex.source == source)
            
            # Order by flight year (newest first) and point density (highest first)
            query = query.order_by(
                LidarCoverageIndex.flight_year.desc().nullslast(),
                LidarCoverageIndex.point_density.desc().nullslast()
            )
            
            results = query.all()
            
            return [
                {
                    "id": str(tile.id),
                    "tile_name": tile.tile_name,
                    "source": tile.source,
                    "flight_year": tile.flight_year,
                    "point_density": tile.point_density,
                    "laz_url": tile.laz_url,
                    "metadata": tile.extra_metadata
                }
                for tile in results
            ]
            
        except Exception as e:
            logger.error(f"Error querying coverage: {e}")
            raise
    
    def has_coverage(self, geometry_wkt: str, srid: int = 4326) -> bool:
        """
        Quick check if any coverage exists for the geometry.
        """
        coverage = self.find_coverage(geometry_wkt, srid=srid)
        return len(coverage) > 0
    
    def get_best_tile(
        self,
        geometry_wkt: str,
        prefer_source: Optional[str] = None,
        srid: int = 4326
    ) -> Optional[Dict[str, Any]]:
        """
        Get the single best tile for the given geometry.
        Prefers newest data with highest point density.
        
        Args:
            geometry_wkt: WKT of the area
            prefer_source: Prefer tiles from this source if available
            srid: SRID of input geometry
        
        Returns:
            Best tile info or None if no coverage
        """
        coverage = self.find_coverage(geometry_wkt, source=prefer_source, srid=srid)
        
        if not coverage and prefer_source:
            # Fall back to any source
            coverage = self.find_coverage(geometry_wkt, srid=srid)
        
        return coverage[0] if coverage else None
    
    def seed_from_shapefile(
        self,
        shapefile_path: str,
        source: str = "PNOA",
        url_field: str = "URL",
        name_field: str = "NOMBRE",
        year_field: Optional[str] = "AÑO",
        density_field: Optional[str] = "DENSIDAD",
        clear_existing: bool = False
    ) -> int:
        """
        Seed the coverage index from a CNIG/PNOA shapefile.
        
        Args:
            shapefile_path: Path to the .shp file
            source: Source identifier (PNOA, IDENA, etc.)
            url_field: Field name containing the LAZ download URL
            name_field: Field name containing the tile name
            year_field: Optional field for flight year
            density_field: Optional field for point density
            clear_existing: If True, remove existing entries for this source
        
        Returns:
            Number of tiles imported
        """
        logger.info(f"Seeding coverage index from {shapefile_path}")
        
        if clear_existing:
            self.db.query(LidarCoverageIndex).filter(
                LidarCoverageIndex.source == source
            ).delete()
            self.db.commit()
            logger.info(f"Cleared existing {source} entries")
        
        count = 0
        
        try:
            with fiona.open(shapefile_path, 'r') as shp:
                logger.info(f"Shapefile CRS: {shp.crs}")
                logger.info(f"Fields: {list(shp.schema['properties'].keys())}")
                
                for feature in shp:
                    props = feature['properties']
                    geom = shape(feature['geometry'])
                    
                    # Get URL (required)
                    laz_url = props.get(url_field)
                    if not laz_url:
                        logger.warning(f"Skipping feature without URL: {props}")
                        continue
                    
                    # Get name
                    tile_name = props.get(name_field, f"tile_{count}")
                    
                    # Get optional fields
                    flight_year = None
                    if year_field and year_field in props:
                        try:
                            flight_year = int(props[year_field])
                        except (ValueError, TypeError):
                            pass
                    
                    point_density = None
                    if density_field and density_field in props:
                        try:
                            point_density = float(props[density_field])
                        except (ValueError, TypeError):
                            pass
                    
                    # Create entry
                    entry = LidarCoverageIndex(
                        tile_name=tile_name,
                        source=source,
                        flight_year=flight_year,
                        point_density=point_density,
                        laz_url=laz_url,
                        geometry=f"SRID=4326;{geom.wkt}",
                        metadata=dict(props)
                    )
                    
                    self.db.add(entry)
                    count += 1
                    
                    if count % 1000 == 0:
                        self.db.commit()
                        logger.info(f"Imported {count} tiles...")
                
                self.db.commit()
                logger.info(f"Finished importing {count} tiles from {source}")
                
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error seeding from shapefile: {e}")
            raise
        
        return count
    
    def seed_from_idena_wfs(self, bbox: Optional[tuple] = None) -> int:
        """
        Seed coverage index from IDENA WFS service (Navarra).
        
        IDENA provides a WFS service for LiDAR coverage.
        This is an alternative to shapefile loading.
        
        Args:
            bbox: Optional bounding box (minx, miny, maxx, maxy)
        
        Returns:
            Number of tiles imported
        """
        # TODO: Implement WFS-based seeding for IDENA
        # This would use requests to query the WFS and parse GML/JSON
        logger.warning("IDENA WFS seeding not yet implemented")
        return 0


def create_coverage_index_table(db: Session):
    """
    Ensure the coverage index table exists with proper indexes.
    """
    # The table is created by SQLAlchemy, but we may want to add
    # additional indexes for performance
    try:
        db.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_lidar_coverage_geometry_gist 
            ON lidar_coverage_index 
            USING GIST (geometry);
        """))
        db.commit()
        logger.info("Coverage index spatial index created/verified")
    except Exception as e:
        logger.warning(f"Could not create spatial index (may already exist): {e}")
        db.rollback()
