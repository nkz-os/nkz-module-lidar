"""Tests for LiDAR pipeline CRS handling and geobounds validation."""
import pytest
from pathlib import Path


class TestGeodesyValidator:
    """CRS inspection tests."""

    def test_inspect_laz_crs_reads_from_valid_file(self):
        """inspect_laz_crs should detect projection from a valid LAZ."""
        from app.services.geodesy_validator import inspect_laz_crs

        fixture = Path(__file__).parent / "fixtures" / "synthetic_epsg4326.laz"
        if not fixture.exists():
            pytest.skip("Test fixture not available -- run create_fixture.py first")

        result = inspect_laz_crs(str(fixture), source_crs_override=None)
        assert result.has_projection is True
        assert "4326" in result.source_crs

    def test_inspect_laz_crs_accepts_manual_override(self):
        """inspect_laz_crs should accept manual CRS override without reading file."""
        from app.services.geodesy_validator import inspect_laz_crs

        result = inspect_laz_crs(
            "/nonexistent/file.laz", source_crs_override="EPSG:25830+5782"
        )
        assert result.source_crs == "EPSG:25830+5782"
        assert result.has_projection is True


class TestGeoBoundsValidator:
    """EU/UK geobounds validation tests."""

    @pytest.fixture
    def validator(self):
        from app.services.geobounds_validator import GeoBoundsValidator

        bounds_path = (
            Path(__file__).resolve().parent.parent / "data" / "eu_uk_bounds.geojson"
        )
        if not bounds_path.exists():
            pytest.skip(f"Geobounds file not found: {bounds_path}")

        return GeoBoundsValidator(str(bounds_path), buffer_km=20.0)

    def test_accepts_madrid(self, validator):
        """Should accept coordinates in Madrid, Spain."""
        assert validator.validate_lon_lat(-3.7038, 40.4168) is True

    def test_accepts_london(self, validator):
        """Should accept coordinates in London, UK."""
        assert validator.validate_lon_lat(-0.1276, 51.5074) is True

    def test_rejects_beijing(self, validator):
        """Should reject coordinates in Beijing, China."""
        assert validator.validate_lon_lat(116.4074, 39.9042) is False

    def test_rejects_sao_paulo(self, validator):
        """Should reject coordinates in Sao Paulo, Brazil."""
        assert validator.validate_lon_lat(-46.6333, -23.5505) is False

    def test_rejects_moscow(self, validator):
        """Should reject coordinates in Moscow, Russia (outside EU+UK+buffer)."""
        assert validator.validate_lon_lat(37.6173, 55.7558) is False
