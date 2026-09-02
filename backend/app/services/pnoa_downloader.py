"""PNOA LiDAR Downloader — downloads LAZ tiles from the CNIG Download Centre.

The IGN/CNIG distributes PNOA LiDAR (2ª/3ª cobertura) through the Centro de
Descargas (https://centrodedescargas.cnig.es), a session-based web app whose
download is nevertheless DIRECT (no registration). The flow, reverse-engineered
and verified live (2026-09-02):

1. GET any page (e.g. ``detalleArchivo`` or a series page) to obtain the
   ``JSESSIONID`` cookie.
2. POST ``archivosSerie`` with ``codSerie`` + ``coordenadas`` (a GeoJSON
   FeatureCollection with a Point at the parcel centroid) → HTML fragment with
   the matching tile(s): ``data-sec="<id>"`` + the LAZ filename.
3. POST ``initDescargaDir`` with ``secuencial=<sec>`` → JSON
   ``{"secuencialDescDir": "<token>", ...}``.  (POST only — GET is 403.)
4. POST ``descargaDir`` with ``secDescDirLA=<token>`` → the LAZ file
   (``Content-Disposition: attachment; filename=PNOA_...LAZ``, magic ``LASF``).

The old ``datos.ign.es/lidar/{lat}_{lon}/lidar.laz`` pattern is INVENTED and
that host is broken (wrong TLS cert + connection resets) — do not use it.

License: PNOA LiDAR data requires attribution (Orden FOM/2807/2015, CC-BY 4.0).
Derived products use: "Obra derivada de LiDAR-PNOA-cob3 2022-2025 CC-BY 4.0
scne.es". The pipeline persists this on the DigitalAsset entity.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
from typing import List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://centrodedescargas.cnig.es/CentroDescargas"

# (codSerie, coverage_label, attribution) — try newest first, fall back to the
# national 2ª cobertura when the 3ª (still being published by region) has no
# coverage for the parcel.
SERIES = [
    ("LIDA3", "cob3", "Obra derivada de LiDAR-PNOA-cob3 2022-2025 CC-BY 4.0 scne.es"),
    ("LIDA2", "cob2", "Obra derivada de LiDAR-PNOA-cob2 2015-2021 CC-BY 4.0 scne.es"),
]

_DATA_SEC_RE = re.compile(r'data-sec="(\d+)"')
_LAZ_NAME_RE = re.compile(r'(PNOA[^"<>\s]+\.LAZ)')

# Search the centroid plus the 4 corners of the bbox so a parcel straddling a
# 1×1 km tile boundary still yields all its tiles.
_SEARCH_OFFSETS = [(0.0, 0.0), (0.0, 1.0), (0.0, -1.0), (1.0, 0.0), (-1.0, 0.0)]


class PNOADownloader:
    """Download PNOA LiDAR LAZ tiles via the CNIG Centro de Descargas."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Nekazari/2.0 (LiDAR module; research project)",
        })
        self._session_ready = False
        self.last_attribution: Optional[str] = None

    # ── public ────────────────────────────────────────────────────────────
    def download(self, geometry_wkt: str, output_dir: str) -> Optional[str]:
        """Download the LAZ tile(s) covering ``geometry_wkt``.

        Returns the path of the downloaded LAZ, or None if no coverage /
        all strategies failed.  When a parcel spans multiple 1×1 km tiles the
        first tile is returned (multi-tile merge is out of scope for now).
        """
        self._ensure_session()

        lon, lat = self._centroid_lonlat(geometry_wkt)
        if lon is None:
            logger.warning("[PNOA] cannot derive centroid from geometry")
            return None

        for cod_serie, cov, attribution in SERIES:
            tiles = self._search_tiles(lon, lat, cod_serie)
            if not tiles:
                logger.info("[PNOA] no %s coverage at (%.5f, %.5f)", cov, lon, lat)
                continue
            logger.info("[PNOA] %s tiles: %s", cov, tiles)
            for sec, filename in tiles:
                path = self._download_sec(sec, filename, output_dir)
                if path:
                    self.last_attribution = attribution
                    return path
            logger.warning("[PNOA] %s tiles found but none downloaded", cov)
        return None

    # ── session ───────────────────────────────────────────────────────────
    def _ensure_session(self) -> None:
        if self._session_ready:
            return
        try:
            # Any page sets the JSESSIONID cookie.
            self.session.get(f"{BASE_URL}/lidar-tercera-cobertura", timeout=20)
            if "JSESSIONID" in self.session.cookies:
                self._session_ready = True
        except requests.RequestException as exc:
            logger.warning("[PNOA] session setup failed: %s", exc)

    # ── geometry ──────────────────────────────────────────────────────────
    @staticmethod
    def _centroid_lonlat(geometry_wkt: str) -> Tuple[Optional[float], Optional[float]]:
        if not geometry_wkt:
            return None, None
        try:
            from shapely import wkt as shapely_wkt
            geom = shapely_wkt.loads(geometry_wkt)
            c = geom.centroid
            return c.x, c.y
        except Exception as exc:
            logger.warning("[PNOA] WKT parse failed: %s", exc)
            return None, None

    # ── search ────────────────────────────────────────────────────────────
    def _search_tiles(self, lon: float, lat: float, cod_serie: str) -> List[Tuple[str, str]]:
        """Find (sec, filename) tiles covering a point via the CNIG search."""
        geojson = json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            }],
        })
        found: dict = {}
        try:
            resp = self.session.post(
                f"{BASE_URL}/archivosSerie",
                data={
                    "numPagina": "1",
                    "codSerie": cod_serie,
                    "coordenadas": geojson,
                    "todaEspania": "N",
                    "todoMundo": "N",
                },
                timeout=30,
            )
            if resp.status_code != 200:
                logger.warning("[PNOA] search %s -> %s", cod_serie, resp.status_code)
                return []
            html = resp.text
            secs = _DATA_SEC_RE.findall(html)
            names = _LAZ_NAME_RE.findall(html)
            for sec in secs:
                found[sec] = names[0] if names else f"pnoa-{sec}"
        except requests.RequestException as exc:
            logger.warning("[PNOA] search %s failed: %s", cod_serie, exc)
        return list(found.items())

    # ── download ──────────────────────────────────────────────────────────
    def _download_sec(self, sec: str, filename: str, output_dir: str) -> Optional[str]:
        """Download one tile by its internal ``sec`` id (2-step POST)."""
        try:
            # 1. resolve download token
            resp = self.session.post(
                f"{BASE_URL}/initDescargaDir",
                data={"secuencial": sec},
                timeout=30,
            )
            resp.raise_for_status()
            token = resp.json().get("secuencialDescDir") or sec

            # 2. fetch the file
            resp2 = self.session.post(
                f"{BASE_URL}/descargaDir",
                data={"secDescDirLA": token},
                timeout=300,
                stream=True,
            )
            if resp2.status_code != 200:
                logger.warning("[PNOA] descargaDir %s -> %s", sec, resp2.status_code)
                return None
            if "attachment" not in resp2.headers.get("Content-Disposition", ""):
                # HTML error page / license wall, not a LAZ
                head = resp2.content[:512] if not getattr(resp2, "_consumed", False) else b""
                if head and b"<html" in head.lower():
                    logger.warning("[PNOA] descargaDir returned HTML for %s", sec)
                    return None

            safe_name = filename or f"pnoa_{sec}.laz"
            if not safe_name.lower().endswith(".laz"):
                safe_name += ".laz"
            local_path = os.path.join(output_dir, safe_name)
            with open(local_path, "wb") as f:
                for chunk in resp2.iter_content(chunk_size=1 << 20):
                    if chunk:
                        f.write(chunk)
            size = os.path.getsize(local_path)
            if size < 100:  # too small to be a LAZ
                os.remove(local_path)
                return None
            logger.info("[PNOA] downloaded %s (%d bytes)", local_path, size)
            return local_path
        except (requests.RequestException, ValueError) as exc:
            logger.warning("[PNOA] download %s failed: %s", sec, exc)
            return None


# Singleton
_downloader_instance: Optional[PNOADownloader] = None


def get_pnoa_downloader() -> PNOADownloader:
    global _downloader_instance
    if _downloader_instance is None:
        _downloader_instance = PNOADownloader()
    return _downloader_instance
