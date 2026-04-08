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
    
    # Worker settings
    WORKER_QUEUE_NAME: str = "lidar-processing"
    WORKER_TIMEOUT: int = 1800  # 30 minutes max per job

    # Security
    CORS_ORIGINS: str = "http://localhost:3000"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Singleton settings instance
settings = Settings()
