"""Parse geolibre-wasm ``lidar_info`` text output.

The summary prints one ``<axis> range: [min, max]`` line per axis::

    x range: [575082.323519, 576045.318519]
    y range: [4720893.737175, 4721468.729175]
    z range: [639.872815, 678.639815]

The previous implementation matched these with a single regex whose non-greedy
``.*?`` spanned the ``y``/``z``/``intensity range`` lines and misgrouped the
numbers, producing garbage bounds (e.g. ``([575082, 0.0],[576045, 0.0])``) that
made PDAL ``writers.gdal`` raise ``Grid width out of range``.
"""

from __future__ import annotations

import re

# minx, miny, minz, maxx, maxy, maxz
Bounds = tuple[float, float, float, float, float, float]

_RANGE_LINE = re.compile(
    r"^\s*([xyz])\s*range\s*:\s*\[\s*([-+\d.eE]+)\s*,\s*([-+\d.eE]+)\s*\]",
    re.IGNORECASE | re.MULTILINE,
)


def parse_bounds(info_text: str) -> Bounds | None:
    """Extract (minx, miny, minz, maxx, maxy, maxz) from lidar_info output.

    Returns None if any of the x/y/z range lines is missing or malformed, so
    the caller can fall back to reading the LAZ header via laspy.
    """
    values: dict[str, tuple[float, float]] = {}
    for m in _RANGE_LINE.finditer(info_text):
        axis = m.group(1).lower()
        values[axis] = (float(m.group(2)), float(m.group(3)))
    if not {"x", "y", "z"} <= values.keys():
        return None
    return (
        values["x"][0], values["y"][0], values["z"][0],
        values["x"][1], values["y"][1], values["z"][1],
    )
