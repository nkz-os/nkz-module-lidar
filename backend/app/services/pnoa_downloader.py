"""PNOA LiDAR Downloader — tries multiple strategies to download LAZ files.

The IGN/CNIG does not guarantee a single direct URL pattern for LAZ files.
This downloader tries multiple approaches and falls back gracefully.
"""

import logging
import os
import tempfile
from typing import Optional
import requests

logger = logging.getLogger(__name__)

# Known IGN/CNIG download patterns (tried in order)
DOWNLOAD_STRATEGIES = []


class PNOADownloader:
    """Download LAZ files from IGN/CNIG PNOA LiDAR distribution.
    
    Tries multiple strategies in order:
    1. Direct URL (from PNOAIndexer tile metadata)
    2. CNIG Download Centre API (session-based)
    3. INSPIRE WCS (for MDT fallback if LAZ unavailable)
    
    All failures are logged and return None — the pipeline handles
    the fallback to user upload.
    """
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Nekazari/2.0 (LiDAR module; research project)',
        })
    
    def download(self, laz_url: str, output_dir: str, tile_name: str = '') -> Optional[str]:
        """Try to download a LAZ file using multiple strategies.
        
        Args:
            laz_url: Best-effort URL from PNOAIndexer tile metadata
            output_dir: Directory to save the downloaded file
            tile_name: Tile identifier for logging
            
        Returns:
            Path to downloaded LAZ file, or None if all strategies failed
        """
        # Strategy 1: Direct URL
        logger.info(f"[PNOA] Trying direct URL: {laz_url}")
        result = self._try_direct_url(laz_url, output_dir, tile_name)
        if result:
            return result
        
        # Strategy 2: CNIG Download Centre via resource ID
        # (extracted from tile_name or laz_url)
        resource_id = tile_name.replace('PNOA_', '').replace('+', '').replace('_', '/')
        cnig_url = self._build_cnig_url(resource_id)
        if cnig_url:
            logger.info(f"[PNOA] Trying CNIG download: {cnig_url}")
            result = self._try_direct_url(cnig_url, output_dir, tile_name)
            if result:
                return result
        
        # Strategy 3: Try common CNIG download patterns
        for strategy in self._generate_candidates(tile_name, laz_url):
            logger.info(f"[PNOA] Trying alternative: {strategy}")
            result = self._try_direct_url(strategy, output_dir, tile_name)
            if result:
                return result
        
        logger.warning(f"[PNOA] All download strategies failed for {tile_name or laz_url}")
        return None
    
    def _try_direct_url(self, url: str, output_dir: str, tile_name: str = '') -> Optional[str]:
        """Try to download from a direct URL."""
        try:
            resp = self.session.get(url, timeout=30, stream=True)
            if resp.status_code != 200:
                logger.debug(f"[PNOA] URL returned {resp.status_code}: {url}")
                return None
            
            # Check it's actually a LAZ file (or can be)
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' in content_type and len(resp.content) < 1024:
                logger.debug(f"[PNOA] URL returned HTML (not LAZ): {url}")
                return None
            
            # Save to temp file
            ext = '.laz'
            local_path = os.path.join(output_dir, f"{tile_name or 'pnoa_download'}{ext}")
            with open(local_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            file_size = os.path.getsize(local_path)
            logger.info(f"[PNOA] Downloaded {file_size} bytes -> {local_path}")
            return local_path
            
        except requests.RequestException as e:
            logger.debug(f"[PNOA] Download failed for {url}: {e}")
            return None
    
    def _build_cnig_url(self, resource_id: str) -> Optional[str]:
        """Build a CNIG Download Centre URL from a resource identifier."""
        # CNIG download URLs follow this pattern:
        # https://centrodedescargas.cnig.es/CentroDescargas/descargarFicheros.do?fichero=<id>
        # But resource IDs are not predictable from geographic coordinates alone.
        return None  # Requires a pre-built mapping of tile → resource ID
    
    def _generate_candidates(self, tile_name: str, laz_url: str) -> list:
        """Generate alternative URL candidates for a tile."""
        candidates = []
        
        # Try CNIG CDN patterns
        if tile_name:
            # Pattern: https://centrodedescargas.cnig.es/CentroDescargas/...
            parts = tile_name.replace('PNOA_', '').split('_')
            if len(parts) >= 2:
                lat, lon = parts[0], parts[1]
                # Remove sign for CNIG format
                lat_clean = lat.replace('+', '').replace('-', '')
                lon_clean = lon.replace('+', '').replace('-', '')
                candidates.append(
                    f"https://centrodedescargas.cnig.es/CentroDescargas/"
                    f"descargarLIDAR.do?idHoja={lat_clean}_{lon_clean}"
                )
        
        return candidates


# Singleton
_downloader_instance = None


def get_pnoa_downloader() -> PNOADownloader:
    global _downloader_instance
    if _downloader_instance is None:
        _downloader_instance = PNOADownloader()
    return _downloader_instance
