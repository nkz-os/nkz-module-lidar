"""
Configuration module for LIDAR backend.
Loads settings from environment variables with sensible defaults.
"""

import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    # Legacy compatibility: keep attribute for modules that still import db package.
    DATABASE_URL: str = "postgresql://postgres:postgres@postgresql:5432/nekazari"
    
    # Redis (for RQ job queue)
    REDIS_URL: str = "redis://redis:6379/0"
    
    # MinIO / S3 Storage
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_BUCKET: str = "lidar-tilesets"
    MINIO_SECURE: bool = False
    
    # Public URL for serving tilesets (used by frontend)
    TILESET_PUBLIC_URL: str = "/api/lidar/tilesets"
    MINIO_PUBLIC_BASE_URL: Optional[str] = None
    
    # Orion-LD Context Broker
    ORION_URL: str = "http://orion-ld:1026"
    ORION_CONTEXT_URL: Optional[str] = None
    
    # Keycloak (for token validation)
    KEYCLOAK_URL: str = "http://keycloak:8080/auth"
    KEYCLOAK_REALM: str = "nekazari"
    
    # PNOA / CNIG data source
    COVERAGE_INDEX_GEOJSON_PATH: str = "/app/data/lidar_coverage.geojson"
    
    # Processing settings
    DEFAULT_TREE_MIN_HEIGHT: float = 2.0  # meters
    DEFAULT_TREE_SEARCH_RADIUS: float = 3.0  # meters
    GEOBBOX_BUFFER_KM: float = 20.0
    EUROPE_BOUNDS_GEOJSON_PATH: str = "/app/data/eu_uk_bounds.geojson"
    
    # Processing settings
    DEFAULT_TREE_MIN_HEIGHT: float = 2.0  # meters
    DEFAULT_TREE_SEARCH_RADIUS: float = 3.0  # meters
    GEOBBOX_BUFFER_KM: float = 20.0
    # Adaptive downsampling guardrail to avoid py3dtiles worker OOM/SIGKILL on very dense clouds.
    # 0 disables the guard.
    MAX_POINTS_BEFORE_TILING_DECIMATION: int = 4_000_000
    # Target point budget after decimation when guardrail is triggered.
    TILING_TARGET_POINTS: int = 2_500_000

    # Extra LAS dimensions reserved for the eventual py3dtiles upgrade.
    # py3dtiles 7.0.0 (currently pinned) ignores anything beyond rgb and
    # classification; this list is consulted by the convert step once
    # --extra-fields lands in a future release.
    PY3DTILES_EXTRA_FIELDS: list = ["Classification", "ReturnNumber", "NumberOfReturns", "HeightAboveGround"]

    # Worker settings.
    # PY3DTILES_TIMEOUT must be strictly less than WORKER_TIMEOUT so a
    # stuck subprocess raises subprocess.TimeoutExpired (clean failure
    # path with an Orion job_status update) before RQ kills the entire
    # work-horse, which loses the failure context.
    WORKER_QUEUE_NAME: str = "lidar-processing"
    WORKER_TIMEOUT: int = 1800        # 30 min — RQ job_timeout
    PY3DTILES_TIMEOUT: int = 1500     # 25 min — subprocess.run timeout

    # py3dtiles defaults to os.cpu_count() workers and host_total_mem/10 of
    # cache, neither cgroup-aware. Cap to values compatible with the pod
    # memory limit (2 GiB → 4 jobs × ~150 MiB + 256 MiB cache + 400 MiB
    # parent worker keeps headroom for laspy/pdal buffers).
    PY3DTILES_JOBS: int = 4
    PY3DTILES_CACHE_SIZE_MB: int = 256

    # Security
    CORS_ORIGINS: str = "http://localhost:3000"
    PROJ_USER_WRITABLE_DIRECTORY: str = "/var/cache/proj"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Singleton settings instance
settings = Settings()
