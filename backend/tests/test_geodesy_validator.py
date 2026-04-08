import tempfile
from pathlib import Path

import pytest

from app.services.geodesy_validator import GeodesyValidationError, inspect_laz_crs


def test_inspect_laz_crs_requires_projection_without_override():
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "not_a_las.laz"
        bad.write_bytes(b"invalid")
        with pytest.raises(GeodesyValidationError):
            inspect_laz_crs(str(bad), source_crs_override=None)


def test_inspect_laz_crs_accepts_manual_override():
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "not_a_las.laz"
        bad.write_bytes(b"invalid")
        result = inspect_laz_crs(str(bad), source_crs_override="EPSG:25830+5782")
        assert result.source_crs == "EPSG:25830+5782"
