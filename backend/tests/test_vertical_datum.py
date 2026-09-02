"""Tests for vertical datum resolution (compound CRS for orthometric LiDAR).

Pure pyproj tests — no PDAL required, runnable outside the Docker image.
"""
import pytest

pyproj = pytest.importorskip("pyproj")

from app.services.vertical_datum import (  # noqa: E402
    PNOA_HORIZONTAL_EPSGS,
    resolve_ecef_source_crs,
)


@pytest.fixture(scope="module", autouse=True)
def _proj_network():
    """Enable the PROJ grid CDN so the geoid verification can actually run.

    Without the es_ign grid, PROJ silently degrades the compound transform to
    a ballpark no-op and the resolver must report the fallback instead.
    """
    try:
        pyproj.network.set_network_enabled(True)
    except Exception:
        pass
    yield
    try:
        pyproj.network.set_network_enabled(False)
    except Exception:
        pass


class TestCompoundForPnoa:
    @pytest.mark.parametrize("epsg", sorted(PNOA_HORIZONTAL_EPSGS))
    def test_pnoa_zones_get_alicante_height(self, epsg):
        res = resolve_ecef_source_crs(f"EPSG:{epsg}")
        assert res.vertical_reference == "compound:EPSG:5782"
        # The effective CRS must be 3-axis (2D horizontal + vertical)
        parsed = pyproj.CRS.from_wkt(res.in_srs)
        assert len(parsed.axis_info) == 3
        assert res.geoid_shift_m is not None
        # Geoid undulation over peninsular Spain: ~+47..+56 m (higher in the NW)
        assert 40.0 <= res.geoid_shift_m <= 60.0

    def test_effective_crs_transforms_z(self):
        """The resolved CRS must produce a ~+50 m shift when sent to ECEF."""
        res = resolve_ecef_source_crs("EPSG:25830")
        to_ecef = pyproj.Transformer.from_crs(res.in_srs, "EPSG:4978")
        X, Y, Z = to_ecef.transform(440000.0, 4475000.0, 650.0)
        to_geodetic = pyproj.Transformer.from_crs("EPSG:4978", "EPSG:4979")
        _, _, h = to_geodetic.transform(X, Y, Z)
        assert 695.0 <= h <= 705.0  # 650 m orthometric + ~50 m geoid


class TestPassthrough:
    def test_declared_vertical_crs_is_passthrough(self):
        res = resolve_ecef_source_crs("EPSG:25830+5782")
        assert res.vertical_reference == "declared"
        assert len(pyproj.CRS.from_wkt(res.in_srs).axis_info) == 3

    def test_unknown_2d_crs_is_untreated(self):
        # French Lambert-93: no vertical table entry — leave untouched
        res = resolve_ecef_source_crs("EPSG:2154")
        assert res.vertical_reference is None
        assert res.geoid_shift_m is None
        parsed = pyproj.CRS.from_wkt(res.in_srs)
        assert parsed == pyproj.CRS.from_epsg(2154)


class TestFallback:
    def test_ballpark_transform_falls_back_to_untreated(self, monkeypatch):
        """If PROJ cannot apply the geoid grid (no-op shift), do NOT claim
        the compound datum was applied — the tileset would float ~50 m with
        a marker claiming it is fixed."""
        import app.services.vertical_datum as vd

        monkeypatch.setattr(vd, "_measure_geoid_shift", lambda *a, **k: 0.0)
        res = vd.resolve_ecef_source_crs("EPSG:25830")
        assert res.vertical_reference is None
        assert res.in_srs == "EPSG:25830"

    def test_invalid_crs_raises(self):
        with pytest.raises(ValueError):
            resolve_ecef_source_crs("NOT_A_CRS")
