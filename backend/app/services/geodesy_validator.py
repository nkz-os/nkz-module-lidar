"""Geodesy validator and dynamic CRS transformation helpers."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Optional

import laspy
import pdal
import pyproj


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


def reproject_to_ecef(input_laz: str, output_laz: str, source_crs: str) -> None:
    try:
        pyproj.CRS.from_user_input(source_crs)
    except Exception as exc:
        raise GeodesyValidationError(f"CRS_OPERATION_UNRESOLVED:{source_crs}") from exc

    pipeline = {
        "pipeline": [
            {"type": "readers.las", "filename": input_laz},
            {
                "type": "filters.reprojection",
                "in_srs": source_crs,
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
