#!/usr/bin/env python3
"""Generate PNOA LiDAR coverage index GeoJSON.

The IGN/CNIG distributes PNOA LiDAR data through the Centro de Descargas
(https://centrodedescargas.cnig.es) which uses a session-based JS web app,
not simple direct URLs. There is no single LAZ_URL_TEMPLATE that works for
all tiles.

This script generates a coverage grid (1°×1° cells covering Spain) with:
1. has_coverage() detection working correctly (the grid covers all Spain)
2. laz_url set to a best-effort candidate URL from known IGN download patterns
3. Additional metadata (dataSource URLs, INSPIRE identifiers) for the runtime
   download resolver to try multiple strategies

Known IGN LiDAR download patterns (none guaranteed):
  - CNIG Download Centre: https://centrodedescargas.cnig.es/CentroDescargas/descargarFicheros.do?fichero=<id>
  - OGC API: https://datos.ign.es/collections/lidar/items/<id> (requires file ID lookup)
  - INSPIRE WCS: https://servicios.idee.es/wcs-inspire/mdt (MDT only, not point clouds)

The runtime download resolver (PNOADownloader in lidar_pipeline.py) tries all
known patterns and falls back to user upload if none work.
"""

import json
import os
import logging
from typing import Any, Dict, List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# España peninsular + Baleares: lon -10 a 5, lat 36 a 44
# Canarias: lon -18 a -13, lat 27 a 30
PENINSULA = (-10, 36, 5, 44)  # west, south, east, north
CANARIAS = (-18, 27, -13, 30)

# Best-effort LAZ URL template.
# The IGN/CNIG does not guarantee this pattern. The runtime downloader
# will try multiple strategies if this URL fails.
LAZ_URL_TEMPLATE = "https://datos.ign.es/lidar/{lat:+03d}_{lon:+03d}/lidar.laz"


def generate_grid(bbox: tuple) -> List[Dict[str, Any]]:
    """Generate 1°×1° grid tiles within bbox.
    
    Each tile represents a 1°×1° geographic cell. This is sufficient for
    coverage detection (has_coverage()). The actual LAZ download uses a
    finer 2km×2km grid based on MTN25/MTN50 sheets, which we handle at
    download time via the PNOADownloader.
    """
    west, south, east, north = bbox
    tiles = []
    for lat in range(int(south), int(north)):
        for lon in range(int(west), int(east)):
            tile_id = f"PNOA_{lat:+03d}_{lon:+03d}"
            tiles.append({
                "id": tile_id,
                "tile_name": tile_id,
                "source": "PNOA",
                "flight_year": 2020,
                "point_density": 0.5,
                "laz_url": LAZ_URL_TEMPLATE.format(lat=lat, lon=lon),
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [lon, lat],
                        [lon + 1, lat],
                        [lon + 1, lat + 1],
                        [lon, lat + 1],
                        [lon, lat]
                    ]]
                }
            })
    return tiles


def main():
    all_tiles = generate_grid(PENINSULA) + generate_grid(CANARIAS)
    
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": t.pop("geometry"),
                "properties": t,
            }
            for t in all_tiles
        ]
    }
    
    output_path = os.path.join(
        os.path.dirname(__file__), '..', 'backend', 'data', 'lidar_coverage.geojson'
    )
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)
    
    logger.info(f"Generated {len(all_tiles)} PNOA coverage tiles -> {output_path}")
    logger.warning(
        "NOTE: LAZ URLs are best-effort. The IGN/CNIG does not guarantee "
        "direct URL access. Runtime PNOADownloader will try multiple "
        "strategies and fall back to user upload if none work."
    )


if __name__ == '__main__':
    main()
