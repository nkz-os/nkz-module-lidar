"""
Configuration module for LIDAR backend.
Loads settings from environment variables with sensible defaults.
"""

import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database (PostGIS)
    DATABASE_URL: str = "postgresql://postgres:postgres@postgresql:5432/nekazari"
    
    # Redis (for RQ job queue)
    REDIS_URL: str = "redis://redis:6379/0"
    
    # MinIO / S3 Storage
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str  # Required - no default
    MINIO_SECRET_KEY: str  # Required - no default
    MINIO_BUCKET: str = "lidar-tilesets"
    MINIO_SECURE: bool = False
    
    # Public URL for serving tilesets (used by frontend)
    TILESET_PUBLIC_URL: str = "/api/lidar/tilesets"
    
    # Orion-LD Context Broker
    ORION_URL: str = "http://orion-ld:1026"
    
    # Keycloak (for token validation)
    KEYCLOAK_URL: str = "http://keycloak:8080/auth"
    KEYCLOAK_REALM: str = "nekazari"
    
    # PNOA / CNIG data source
    PNOA_SHAPEFILE_PATH: Optional[str] = None  # Path to local shapefile if downloaded
    
    # Processing settings
    DEFAULT_TREE_MIN_HEIGHT: float = 2.0  # meters
    DEFAULT_TREE_SEARCH_RADIUS: float = 3.0  # meters
    
    # Worker settings
    WORKER_QUEUE_NAME: str = "lidar-processing"
    WORKER_TIMEOUT: int = 1800  # 30 minutes max per job
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Singleton settings instance
settings = Settings()
