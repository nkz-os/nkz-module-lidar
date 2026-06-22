import json

import pytest

from app.config import settings
from app.services.pnoa_indexer import PNOAIndexer


def test_find_coverage_intersects_geometry(tmp_path, monkeypatch):
    coverage = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": "tile-1",
                    "tile_name": "tile-1",
                    "source": "PNOA",
                    "laz_url": "https://example.com/tile-1.laz",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    }
    geojson_path = tmp_path / "coverage.geojson"
    geojson_path.write_text(json.dumps(coverage), encoding="utf-8")
    monkeypatch.setattr(settings, "COVERAGE_INDEX_GEOJSON_PATH", str(geojson_path))

    indexer = PNOAIndexer()
    tiles = indexer.find_coverage("POLYGON((0.2 0.2,0.8 0.2,0.8 0.8,0.2 0.8,0.2 0.2))")
    assert len(tiles) == 1
    assert tiles[0]["tile_name"] == "tile-1"


def test_pnoa_indexer_loads_real_coverage(tmp_path, monkeypatch):
    """Verify PNOA indexer loads tiles from the bundled coverage file."""
    import os

    real_path = os.path.join(os.path.dirname(__file__), "..", "data", "lidar_coverage.geojson")
    if not os.path.exists(real_path):
        pytest.skip("Coverage file not found — run scripts/generate_pnoa_index.py first")
    monkeypatch.setattr(settings, "COVERAGE_INDEX_GEOJSON_PATH", real_path)

    indexer = PNOAIndexer()
    assert len(indexer._tiles) > 0, "Should load tiles from real coverage"

    # Madrid parcel — should find coverage
    madrid = "POLYGON((-3.8 40.3, -3.8 40.5, -3.5 40.5, -3.5 40.3, -3.8 40.3))"
    assert indexer.has_coverage(madrid), "Madrid should have PNOA coverage"

    # Navarra parcel
    navarra = "POLYGON((-1.8 42.7, -1.8 42.9, -1.5 42.9, -1.5 42.7, -1.8 42.7))"
    assert indexer.has_coverage(navarra), "Navarra should have PNOA coverage"

    # Canarias parcel
    canarias = "POLYGON((-16.5 28.3, -16.5 28.5, -16.2 28.5, -16.2 28.3, -16.5 28.3))"
    assert indexer.has_coverage(canarias), "Canarias should have PNOA coverage"

    # Best tile returns LAZ URL
    tile = indexer.get_best_tile(madrid)
    assert tile is not None
    assert "laz_url" in tile
    assert "http" in tile["laz_url"]


def test_pnoa_indexer_no_coverage_outside_spain(tmp_path, monkeypatch):
    """Verify no coverage for points outside Spain."""
    import os

    real_path = os.path.join(os.path.dirname(__file__), "..", "data", "lidar_coverage.geojson")
    if not os.path.exists(real_path):
        pytest.skip("Coverage file not found")
    monkeypatch.setattr(settings, "COVERAGE_INDEX_GEOJSON_PATH", real_path)

    indexer = PNOAIndexer()

    # UK — no coverage
    uk = "POLYGON((-0.5 51.3, -0.5 51.5, 0.0 51.5, 0.0 51.3, -0.5 51.3))"
    assert not indexer.has_coverage(uk), "UK should not have PNOA coverage"

    # South Atlantic — no coverage
    atlantic = "POLYGON((-30 10, -30 15, -20 15, -20 10, -30 10))"
    assert not indexer.has_coverage(atlantic), "Mid-Atlantic should not have PNOA coverage"

