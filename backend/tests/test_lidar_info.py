"""Tests for the geolibre-wasm lidar_info bounds parser (pure regex, no PDAL)."""
from app.services.lidar_info import parse_bounds


REAL_SAMPLE = """LiDAR File Summary

input: /work/cloud.laz
points: 138816
x range: [575082.323519, 576045.318519]
y range: [4720893.737175, 4721468.729175]
z range: [639.872815, 678.639815]
intensity range: [0, 0]
bbox point density: 0.250700 pts/unit^2

return counts (1..5):
  1: 138816
  2: 0
"""


def test_parses_real_lidar_info_output():
    bounds = parse_bounds(REAL_SAMPLE)
    assert bounds is not None
    minx, miny, minz, maxx, maxy, maxz = bounds
    assert minx == 575082.323519
    assert maxx == 576045.318519
    assert miny == 4720893.737175
    assert maxy == 4721468.729175
    assert minz == 639.872815
    assert maxz == 678.639815


def test_handles_negative_and_scientific_notation():
    text = "x range: [-1.2e3, 3000.5]\ny range: [1.0, 2.0]\nz range: [-15.25, 0.0]\n"
    minx, miny, minz, maxx, maxy, maxz = parse_bounds(text)
    assert minx == -1200.0 and maxx == 3000.5
    assert minz == -15.25 and maxz == 0.0


def test_returns_none_when_a_range_is_missing():
    assert parse_bounds("x range: [1, 2]\ny range: [3, 4]") is None
    assert parse_bounds("") is None


def test_does_not_confuse_intensity_range():
    text = "x range: [1, 2]\ny range: [3, 4]\nz range: [5, 6]\nintensity range: [7, 8]\n"
    bounds = parse_bounds(text)
    assert bounds == (1.0, 3.0, 5.0, 2.0, 4.0, 6.0)
