"""Coverage index service using read-only GeoJSON catalog."""

import json
import logging
from typing import Any, Dict, List, Optional

from shapely.geometry import shape
from shapely.wkt import loads as wkt_loads

from app.config import settings

logger = logging.getLogger(__name__)


class PNOAIndexer:
    def __init__(self):
        self._tiles = self._load_tiles()

    def _load_tiles(self) -> List[Dict[str, Any]]:
        try:
            with open(settings.COVERAGE_INDEX_GEOJSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            features = data.get("features", [])
            loaded: List[Dict[str, Any]] = []
            for feature in features:
                props = feature.get("properties", {})
                geom = feature.get("geometry")
                if not geom:
                    continue
                loaded.append(
                    {
                        "id": props.get("id") or props.get("tile_name") or "tile",
                        "tile_name": props.get("tile_name", ""),
                        "source": props.get("source", "PNOA"),
                        "flight_year": props.get("flight_year"),
                        "point_density": props.get("point_density"),
                        "laz_url": props.get("laz_url"),
                        "metadata": props,
                        "_geometry": shape(geom),
                    }
                )
            return loaded
        except FileNotFoundError:
            logger.warning("Coverage GeoJSON not found at %s", settings.COVERAGE_INDEX_GEOJSON_PATH)
            return []
        except Exception as exc:
            logger.error("Failed to load coverage catalog: %s", exc)
            return []
    
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
        target = wkt_loads(geometry_wkt)
        results: List[Dict[str, Any]] = []
        for tile in self._tiles:
            if source and tile["source"] != source:
                continue
            if tile["_geometry"].intersects(target):
                results.append({k: v for k, v in tile.items() if k != "_geometry"})
        results.sort(
            key=lambda item: (
                item.get("flight_year") or 0,
                item.get("point_density") or 0,
            ),
            reverse=True,
        )
        return results
    
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
    
    def seed_from_shapefile(self, *args, **kwargs) -> int:
        raise RuntimeError("Shapefile seeding removed from runtime. Build GeoJSON catalog offline.")
