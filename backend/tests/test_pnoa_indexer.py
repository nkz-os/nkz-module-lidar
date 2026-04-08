import json

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

