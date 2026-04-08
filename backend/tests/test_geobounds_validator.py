from app.services.geobounds_validator import GeoBoundsValidator


def test_geobounds_validator_accepts_europe_bbox():
    validator = GeoBoundsValidator("backend/data/eu_uk_bounds.geojson", buffer_km=20.0)
    assert validator.validate_bbox((-4.5, 43.0, -2.0, 44.0))


def test_geobounds_validator_rejects_outlier_bbox():
    validator = GeoBoundsValidator("backend/data/eu_uk_bounds.geojson", buffer_km=20.0)
    assert not validator.validate_bbox((120.0, -30.0, 125.0, -25.0))
