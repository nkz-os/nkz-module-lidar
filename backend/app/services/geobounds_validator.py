"""Geospatial outlier validation for transformed coordinates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from shapely.geometry import Point, shape
from shapely.ops import unary_union


class GeoBoundsValidator:
    def __init__(self, geojson_path: str, buffer_km: float = 20.0):
        data = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
        polygons = [shape(f["geometry"]) for f in data.get("features", [])]
        self.eu_uk = unary_union(polygons).buffer(buffer_km / 111.0)

    def validate_lon_lat(self, lon: float, lat: float) -> bool:
        return self.eu_uk.contains(Point(lon, lat))

    def validate_bbox(self, bbox: Tuple[float, float, float, float]) -> bool:
        min_lon, min_lat, max_lon, max_lat = bbox
        cx = (min_lon + max_lon) / 2
        cy = (min_lat + max_lat) / 2
        return self.validate_lon_lat(cx, cy)
