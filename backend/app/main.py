"""
FastAPI main application for LIDAR module.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import lidar
from app.db import init_db

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
    
    # Initialize database tables
    try:
        init_db()
        logger.info("Database tables initialized")
    except Exception as e:
        logger.warning(f"Database initialization warning: {e}")
    
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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(lidar.router, prefix="/api/lidar", tags=["LIDAR Processing"])


@app.get("/health")
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

