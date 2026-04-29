"""
FastAPI main application for LIDAR module.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from redis import Redis
import os

from app.config import settings

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("Starting LIDAR Module API...")
    # Validate coverage index exists
    coverage_path = Path(settings.COVERAGE_INDEX_GEOJSON_PATH)
    if not coverage_path.exists():
        logger.error(
            "COVERAGE_INDEX_GEOJSON_PATH not found: %s. Coverage checks will return empty.",
            coverage_path,
        )
    else:
        logger.info("Coverage index loaded from %s", coverage_path)
    yield
    logger.info("Shutting down LIDAR Module API...")


# Create FastAPI app
app = FastAPI(
    title="LIDAR Module API",
    description="""
    LIDAR point cloud processing and visualization for Nekazari Platform.
    
    ## Features
    - Check LiDAR coverage from PNOA/CNIG database
    - Process point clouds (crop, denoise, colorize, segment)
    - Generate 3D Tiles for Cesium visualization
    - Detect individual trees with crown analysis
    
    ## Processing Pipeline
    1. **Ingest**: Download and crop point cloud to parcel boundary
    2. **Spectral Fusion**: Colorize points with NDVI values
    3. **Segmentation**: Detect individual trees using CHM
    4. **Tiling**: Convert to 3D Tiles for web visualization
    """,
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiter: Redis-backed with in-memory fallback
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


def _get_redis_connection():
    try:
        return Redis.from_url(REDIS_URL)
    except Exception:
        return None


redis_conn = _get_redis_connection()
limiter_storage_uri = REDIS_URL if redis_conn else "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=limiter_storage_uri,
    default_limits=["60 per minute"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include routers
from app.api import lidar
app.include_router(lidar.router, prefix="/api/lidar", tags=["LIDAR Processing"])

# Prometheus metrics (no auth — internal cluster use)
Instrumentator(
    should_group_status_codes=True,
    should_ignore_untemplated=True,
    should_respect_env_var=True,
).instrument(app).expose(app, endpoint="/metrics")


@app.get("/health")
@limiter.exempt
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "module": "lidar",
        "version": "1.0.0"
    }


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "module": "nkz-module-lidar",
        "version": "1.0.0",
        "description": "LIDAR Point Cloud Processing Module for Nekazari",
        "docs": "/docs",
        "health": "/health"
    }

