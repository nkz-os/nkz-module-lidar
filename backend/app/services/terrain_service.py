"""MDS Terrain Tile Service — serves DSM as Cesium Quantized Mesh tiles."""

import json
import logging
from typing import Optional

from app.services.storage import storage_service

logger = logging.getLogger(__name__)


def get_terrain_tile(layer_id: str, z: int, x: int, y: int) -> Optional[bytes]:
    """Get a single quantized mesh terrain tile for a DSM layer from MinIO."""
    key = f"terrain/lidar/{layer_id}/{z}/{x}/{y}.terrain"
    try:
        return storage_service.get_file_bytes(key)
    except Exception:
        return None


def get_layer_json(layer_id: str) -> Optional[dict]:
    """Get Cesium layer.json metadata for a DSM terrain tileset."""
    # Check if tiles exist by looking for layer.json
    key = f"terrain/lidar/{layer_id}/layer.json"
    try:
        data = storage_service.get_file_bytes(key)
        return json.loads(data)
    except Exception:
        pass

    # Generate minimal layer.json for tiles that haven't been fully indexed
    # Check if at least one tile exists at zoom 8
    test_key = f"terrain/lidar/{layer_id}/8/0/0.terrain"
    try:
        storage_service.get_file_bytes(test_key)
        return {
            "tilejson": "2.1.0",
            "name": f"LiDAR DSM {layer_id}",
            "description": "Digital Surface Model from LiDAR — trees and buildings",
            "format": "quantized-mesh-1.0",
            "scheme": "tms",
            "tiles": [f"/api/lidar/terrain/{layer_id}/{{z}}/{{x}}/{{y}}.terrain"],
            "projection": "EPSG:4326",
            "minzoom": 8,
            "maxzoom": 14,
        }
    except Exception:
        return None


def has_terrain_tiles(layer_id: str) -> bool:
    """Check if MDS terrain tiles exist for a layer."""
    key = f"terrain/lidar/{layer_id}/layer.json"
    try:
        storage_service.get_file_bytes(key)
        return True
    except Exception:
        # Try a tile at zoom 8
        test_key = f"terrain/lidar/{layer_id}/8/0/0.terrain"
        try:
            storage_service.get_file_bytes(test_key)
            return True
        except Exception:
            return False
