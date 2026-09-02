"""Vertical datum resolution for orthometric LiDAR heights.

Most European .laz files (PNOA/IGN in Spain) store ORTHOMETRIC heights
referred to a national vertical datum (Spain: REDNAP, i.e. Alicante height,
EPSG:5782).  Cesium 3D Tiles render over the WGS84 ellipsoid, so
reprojecting a 2D-only horizontal CRS straight to EPSG:4978 silently treats
orthometric Z as ellipsoidal and the point cloud floats ~50 m above the
terrain (geoid undulation over peninsular Spain is ~+47..+52 m).

This module appends the correct vertical datum (compound CRS) when the
declared source CRS is horizontal-only and its vertical reference is known.

CRITICAL: if PROJ lacks the geoid grid, the compound transform degrades to a
silent BALLPARK NO-OP (Z passes through unchanged, no error raised).  The
resolver therefore *measures* the actual shift at a representative point and
falls back to the untreated CRS when no meaningful shift is applied — we
never claim a vertical fix that was not performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pyproj

# Horizontal EPSG codes (2D-only) whose native LiDAR heights are referred to
# the Spanish national vertical datum (Alicante height / REDNAP).
PNOA_HORIZONTAL_EPSGS = frozenset({25829, 25830, 25831})  # ETRS89 UTM 29N/30N/31N
ALICANTE_HEIGHT_EPSG = 5782

# Representative onshore points (lon, lat) used to verify that the geoid
# grid actually applies.  The bbox centre of a UTM zone can fall in
# Portugal or the sea, outside the IGN grid coverage, yielding inf.
PROBE_LONLAT_BY_EPSG = {
    25829: (-5.66, 40.97),  # Salamanca
    25830: (-3.70, 40.40),  # Madrid
    25831: (2.17, 41.39),   # Barcelona
}

# A compound transform that shifts Z by less than this is considered a
# ballpark no-op (grid missing) and is rejected.
_MIN_VALID_SHIFT_M = 1.0


@dataclass
class EcefSourceCrs:
    """Result of resolving the CRS to use when reprojecting to EPSG:4978."""

    in_srs: str
    vertical_reference: Optional[str]
    geoid_shift_m: Optional[float]


def _measure_geoid_shift(compound_crs: "pyproj.CRS", horizontal_crs: "pyproj.CRS") -> float:
    """Measure the orthometric→ellipsoidal shift at a representative point.

    Uses the centre of the horizontal CRS area of use, which for the Spanish
    UTM zones is peninsular Spain (geoid undulation ~+50 m).  Returns 0.0
    when PROJ applied a ballpark (no-op) transformation.
    """
    area = horizontal_crs.area_of_use or compound_crs.area_of_use
    if not area:
        return 0.0
    lon = (area.west + area.east) / 2.0
    lat = (area.south + area.north) / 2.0

    horizontal_epsg = horizontal_crs.to_epsg()
    if horizontal_epsg in PROBE_LONLAT_BY_EPSG:
        lon, lat = PROBE_LONLAT_BY_EPSG[horizontal_epsg]

    to_utm = pyproj.Transformer.from_crs("EPSG:4326", compound_crs, always_xy=True)
    x, y = to_utm.transform(lon, lat)
    if x == float("inf") or y == float("inf"):
        return 0.0

    try:
        # allow_ballpark=False: refuse the silent no-op transformation PROJ
        # picks when the geoid grid is unavailable.  With the grid present
        # (baked in the image or downloaded via PROJ_NETWORK) this selects
        # the real geoid operation.
        to_ecef = pyproj.Transformer.from_crs(
            compound_crs, "EPSG:4978", allow_ballpark=False
        )
    except Exception:
        return 0.0
    try:
        X, Y, Z = to_ecef.transform(x, y, 100.0)
    except Exception:
        return 0.0
    to_geodetic = pyproj.Transformer.from_crs("EPSG:4978", "EPSG:4979")
    _, _, h = to_geodetic.transform(X, Y, Z)
    if not (abs(h) < 1e9):
        return 0.0
    return h - 100.0


def resolve_ecef_source_crs(source_crs: str) -> EcefSourceCrs:
    """Resolve the CRS to feed PDAL when reprojecting a cloud to ECEF.

    Returns the effective input CRS (WKT2) plus a marker describing the
    vertical treatment:

    - ``declared``          — the source already declares a vertical datum.
    - ``compound:EPSG:xxxx``— a vertical datum was appended and VERIFIED.
    - ``None``              — no vertical treatment (legacy behaviour; the
      frontend keeps its manual offset fallback).
    """
    try:
        crs = pyproj.CRS.from_user_input(source_crs)
    except Exception as exc:
        raise ValueError(f"CRS_OPERATION_UNRESOLVED:{source_crs}") from exc

    # Already 3D (compound or ellipsoidal vertical): trust the declaration.
    if len(crs.axis_info) >= 3:
        return EcefSourceCrs(
            in_srs=crs.to_wkt(version="WKT2_2019"),
            vertical_reference="declared",
            geoid_shift_m=None,
        )

    horizontal_epsg = crs.to_epsg()
    if horizontal_epsg in PNOA_HORIZONTAL_EPSGS:
        compound = pyproj.CRS.from_user_input(
            f"EPSG:{horizontal_epsg}+{ALICANTE_HEIGHT_EPSG}"
        )
        shift = _measure_geoid_shift(compound, crs)
        if abs(shift) >= _MIN_VALID_SHIFT_M:
            return EcefSourceCrs(
                in_srs=compound.to_wkt(version="WKT2_2019"),
                vertical_reference=f"compound:EPSG:{ALICANTE_HEIGHT_EPSG}",
                geoid_shift_m=round(shift, 3),
            )
        # Ballpark no-op (geoid grid unavailable): do NOT claim a fix.
        return EcefSourceCrs(
            in_srs=source_crs,
            vertical_reference=None,
            geoid_shift_m=None,
        )

    return EcefSourceCrs(
        in_srs=crs.to_wkt(version="WKT2_2019"),
        vertical_reference=None,
        geoid_shift_m=None,
    )
