#!/usr/bin/env python3
"""Generate PNOA LiDAR coverage index GeoJSON."""

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

# PNOA LiDAR LAZ URL pattern (to be confirmed with IGN actual CDN)
# IGN distributes LiDAR by 1°×1° grid cells
LAZ_URL_TEMPLATE = "https://datos.ign.es/lidar/{lat:+03d}_{lon:+03d}/lidar.laz"


def generate_grid(bbox: tuple) -> List[Dict[str, Any]]:
    """Generate 1°×1° grid tiles within bbox."""
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


if __name__ == '__main__':
    main()
