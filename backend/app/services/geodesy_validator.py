"""Geodesy validator and dynamic CRS transformation helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import laspy
import pdal

from app.services.vertical_datum import resolve_ecef_source_crs


@dataclass
class GeodesyValidationResult:
    source_crs: str
    has_projection: bool


class GeodesyValidationError(ValueError):
    pass


def inspect_laz_crs(file_path: str, source_crs_override: Optional[str] = None) -> GeodesyValidationResult:
    if source_crs_override:
        return GeodesyValidationResult(source_crs=source_crs_override, has_projection=True)
    try:
        with laspy.open(file_path) as reader:
            header_crs = reader.header.parse_crs()
        if not header_crs:
            raise GeodesyValidationError("CRS_MISSING")
        return GeodesyValidationResult(source_crs=header_crs.to_string(), has_projection=True)
    except GeodesyValidationError:
        raise
    except Exception as exc:
        raise GeodesyValidationError(f"CRS_INSPECTION_FAILED:{exc}") from exc


def reproject_to_ecef(input_laz: str, output_laz: str, source_crs: str) -> dict:
    """Reproject a cloud to ECEF (EPSG:4978) for 3D Tiles.

    When the declared CRS is horizontal-only and its vertical datum is known
    (PNOA Spain → Alicante height / REDNAP), a compound CRS is used so PROJ
    converts orthometric Z to ellipsoidal.  See vertical_datum.py.

    Returns the vertical treatment applied (``vertical_reference``,
    ``geoid_shift_m``) for persistence on the DigitalAsset entity.
    """
    try:
        resolved = resolve_ecef_source_crs(source_crs)
    except Exception as exc:
        raise GeodesyValidationError(f"CRS_OPERATION_UNRESOLVED:{source_crs}") from exc

    pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": input_laz},
            {
                "type": "filters.reprojection",
                "in_srs": resolved.in_srs,
                "out_srs": "EPSG:4978",
            },
            {
                "type": "writers.las",
                "filename": output_laz,
                "compression": "laszip",
            },
        ]
    }
    env = os.environ.copy()
    env["PROJ_NETWORK"] = env.get("PROJ_NETWORK", "ON")
    pdal.Pipeline(json.dumps(pipeline)).execute()
    return {
        "vertical_reference": resolved.vertical_reference,
        "geoid_shift_m": resolved.geoid_shift_m,
    }
