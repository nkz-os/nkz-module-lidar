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

    # Worker settings
    WORKER_QUEUE_NAME: str = "lidar-processing"
    WORKER_TIMEOUT: int = 1800  # 30 minutes max per job
    # External converter timeout (py3dtiles). Keep below/near worker timeout guardrail.
    PY3DTILES_TIMEOUT: int = 5400  # 90 minutes

    # Security
    CORS_ORIGINS: str = "http://localhost:3000"
    PROJ_USER_WRITABLE_DIRECTORY: str = "/var/cache/proj"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Singleton settings instance
settings = Settings()
