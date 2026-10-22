"""
Tile Cache Service for PNOA LAZ files.

Manages downloading and caching of source LAZ tiles in MinIO to avoid
re-downloading large files for overlapping parcels.

The cache is shared across all tenants since PNOA data is public.
"""

import logging
import os
from typing import Tuple
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.config import settings
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

# Separate bucket for source tiles (raw LAZ files from PNOA)
SOURCE_TILES_BUCKET = "lidar-source-tiles"


class TileCacheService:
    """
    Service for caching downloaded PNOA LAZ tiles.
    
    Tiles are stored in MinIO only (no SQL runtime state).
    """
    
    def __init__(self):
        self.bucket = SOURCE_TILES_BUCKET
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Create the source tiles bucket if it doesn't exist."""
        try:
            storage_service.ensure_bucket(self.bucket)
            logger.info(f"Source tiles bucket '{self.bucket}' ready")
        except Exception as e:
            logger.warning(f"Could not create bucket '{self.bucket}': {e}")
    
    def _extract_tile_name(self, url: str) -> str:
        """
        Extract a unique tile name from the URL.
        
        For PNOA URLs like:
        https://centrodedescargas.cnig.es/...../PNOA_2023_NAV_0001.laz
        
        Returns: PNOA_2023_NAV_0001
        """
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path)
        # Remove extension
        tile_name = Path(filename).stem
        return tile_name
    
    def get_tile_local_path(self, tile_name: str, work_dir: str) -> str:
        """
        Download a cached tile from MinIO to a local path.
        
        Args:
            tile_name: Tile identifier
            work_dir: Local working directory
            
        Returns:
            Local file path to the LAZ file
        """
        local_path = os.path.join(work_dir, f"{tile_name}.laz")
        minio_key = f"{tile_name}.laz"
        
        # Download from MinIO
        storage_service.download_file(
            bucket=self.bucket,
            key=minio_key,
            local_path=local_path
        )
        
        logger.info(f"Downloaded cached tile to: {local_path}")
        return local_path
    
    def download_and_cache_tile(
        self,
        source_url: str,
        work_dir: str
    ) -> Tuple[str, str]:
        """
        Download a tile from source and cache it in MinIO.
        
        Args:
            source_url: URL to download from (PNOA/CNIG)
            work_dir: Local working directory
            
        Returns:
            Tuple of (local_file_path, tile_name)
        """
        tile_name = self._extract_tile_name(source_url)
        local_path = os.path.join(work_dir, f"{tile_name}.laz")
        minio_key = f"{tile_name}.laz"

        logger.info(f"Downloading tile from: {source_url}")
        response = requests.get(source_url, stream=True, timeout=600)
        response.raise_for_status()

        file_size = 0
        with open(local_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                file_size += len(chunk)

        logger.info(f"Downloaded {file_size / 1024 / 1024:.1f} MB to {local_path}")
        logger.info(f"Uploading to MinIO cache: {self.bucket}/{minio_key}")
        storage_service.upload_file(
            bucket=self.bucket,
            key=minio_key,
            file_path=local_path,
            content_type="application/octet-stream"
        )
        return local_path, tile_name
    
    def get_or_download_tile(
        self,
        source_url: str,
        work_dir: str
    ) -> str:
        """
        Main entry point: Get a tile from cache or download it.
        
        This is the method that should be called from the pipeline.
        
        Args:
            source_url: URL to the LAZ file
            work_dir: Local working directory
            
        Returns:
            Local file path to the LAZ file (either from cache or freshly downloaded)
        """
        tile_name = self._extract_tile_name(source_url)
        
        # Check cache first
        minio_key = f"{tile_name}.laz"
        if storage_service.file_exists_in_bucket(self.bucket, minio_key):
            logger.info(f"Cache HIT for tile: {tile_name}")
            return self.get_tile_local_path(tile_name, work_dir)
        local_path, _ = self.download_and_cache_tile(source_url, work_dir)
        return local_path
    
    def get_cache_stats(self) -> dict:
        """Get statistics about the tile cache."""
        return {
            "total_cached_tiles": None,
            "total_size_mb": None,
            "total_accesses": None,
            "cache_hits_saved_downloads": None,
            "mode": "minio-only-no-sql",
        }


# Singleton instance
tile_cache = TileCacheService()
