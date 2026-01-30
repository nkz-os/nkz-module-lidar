"""
LIDAR API endpoints.

Provides REST endpoints for:
- Checking LiDAR coverage for a parcel
- Starting processing jobs
- Querying job status
- Managing point cloud layers
"""

import logging
import os
import tempfile
import json
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query, File, UploadFile, Form
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session

from app.middleware.auth import require_auth, get_tenant_id
from app.db import get_db
from app.config import settings
from app.models import LidarProcessingJob, LidarCoverageIndex, PointCloudLayer, JobStatus
from app.services.pnoa_indexer import PNOAIndexer
from app.services.lidar_pipeline import process_lidar_job

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class ProcessingConfig(BaseModel):
    """Configuration for LiDAR processing job."""
    colorize_by: str = Field(default="height", description="Color mode: height, ndvi, rgb, classification")
    detect_trees: bool = Field(default=False, description="Enable tree segmentation")
    tree_min_height: float = Field(default=2.0, description="Minimum tree height in meters")
    tree_search_radius: float = Field(default=3.0, description="Tree crown search radius in meters")
    ndvi_source_url: Optional[str] = Field(default=None, description="URL to NDVI GeoTIFF for colorization")


class ProcessRequest(BaseModel):
    """Request to start LiDAR processing for a parcel."""
    parcel_id: str = Field(..., description="Orion-LD AgriParcel entity ID")
    parcel_geometry_wkt: str = Field(..., description="WKT representation of parcel boundary")
    config: ProcessingConfig = Field(default_factory=ProcessingConfig)


class ProcessResponse(BaseModel):
    """Response from starting a processing job."""
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Response for job status query."""
    job_id: str
    status: str
    progress: int
    status_message: Optional[str]
    error_message: Optional[str]
    tileset_url: Optional[str]
    tree_count: Optional[int]
    point_count: Optional[int]


class CoverageCheckRequest(BaseModel):
    """Request to check LiDAR coverage."""
    geometry_wkt: str = Field(..., description="WKT of area to check")
    source: Optional[str] = Field(default=None, description="Filter by data source (PNOA, IDENA, etc.)")


class CoverageResponse(BaseModel):
    """Response for coverage check."""
    has_coverage: bool
    tiles: List[dict]


class LayerResponse(BaseModel):
    """Response for point cloud layer."""
    id: str
    parcel_id: str
    tileset_url: str
    source: str
    point_count: Optional[int]
    date_observed: Optional[str]


# ============================================================================
# Helper Functions
# ============================================================================

def get_redis_queue() -> Queue:
    """Get RQ queue for job submission."""
    redis_conn = Redis.from_url(settings.REDIS_URL)
    return Queue(settings.WORKER_QUEUE_NAME, connection=redis_conn)


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/process", response_model=ProcessResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_processing(
    request: ProcessRequest,
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Start LiDAR processing for a parcel.
    
    This endpoint:
    1. Validates the parcel has LiDAR coverage
    2. Creates a processing job record
    3. Enqueues the job in Redis for worker processing
    
    Returns immediately with job ID for status polling.
    """
    logger.info(f"Processing request for parcel {request.parcel_id} by tenant {tenant_id}")
    
    # Check coverage first
    indexer = PNOAIndexer(db)
    if not indexer.has_coverage(request.parcel_geometry_wkt):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No LiDAR coverage available for this parcel"
        )
    
    # Create job record
    job = LidarProcessingJob(
        tenant_id=tenant_id,
        user_id=current_user.get("sub", "unknown"),
        parcel_id=request.parcel_id,
        parcel_geometry_wkt=request.parcel_geometry_wkt,
        config=request.config.model_dump(),
        status=JobStatus.QUEUED
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    
    # Enqueue job for worker
    try:
        queue = get_redis_queue()
        rq_job = queue.enqueue(
            process_lidar_job,
            str(job.id),
            job_timeout=settings.WORKER_TIMEOUT
        )
        
        # Store RQ job ID
        job.rq_job_id = rq_job.id
        db.commit()
        
        logger.info(f"Job {job.id} enqueued successfully (RQ: {rq_job.id})")
        
    except Exception as e:
        logger.error(f"Failed to enqueue job: {e}")
        job.status = JobStatus.FAILED
        job.error_message = f"Failed to enqueue: {str(e)}"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Processing queue unavailable. Please try again later."
        )
    
    return ProcessResponse(
        job_id=str(job.id),
        status="queued",
        message="Processing job queued. Poll /status/{job_id} for updates."
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Get status of a processing job.
    
    Poll this endpoint to track job progress.
    """
    try:
        job_uuid = UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    job = db.query(LidarProcessingJob).filter(
        LidarProcessingJob.id == job_uuid,
        LidarProcessingJob.tenant_id == tenant_id
    ).first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(
        job_id=str(job.id),
        status=job.status.value,
        progress=job.progress or 0,
        status_message=job.status_message,
        error_message=job.error_message,
        tileset_url=job.tileset_url,
        tree_count=job.tree_count,
        point_count=job.point_count
    )


@router.post("/coverage", response_model=CoverageResponse)
async def check_coverage(
    request: CoverageCheckRequest,
    current_user: dict = Depends(require_auth),
    db: Session = Depends(get_db)
):
    """
    Check if LiDAR coverage is available for a given area.
    
    Returns list of available tiles with their metadata.
    """
    indexer = PNOAIndexer(db)
    tiles = indexer.find_coverage(request.geometry_wkt, source=request.source)
    
    return CoverageResponse(
        has_coverage=len(tiles) > 0,
        tiles=tiles
    )


@router.get("/layers", response_model=List[LayerResponse])
async def get_layers(
    parcel_id: Optional[str] = Query(None, description="Filter by parcel ID"),
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Get available point cloud layers for the tenant.
    """
    query = db.query(PointCloudLayer).filter(
        PointCloudLayer.tenant_id == tenant_id
    )
    
    if parcel_id:
        query = query.filter(PointCloudLayer.parcel_id == parcel_id)
    
    layers = query.all()
    
    return [
        LayerResponse(
            id=str(layer.id),
            parcel_id=layer.parcel_id,
            tileset_url=layer.tileset_url,
            source=layer.source,
            point_count=layer.point_count,
            date_observed=layer.date_observed.isoformat() if layer.date_observed else None
        )
        for layer in layers
    ]


@router.get("/layers/{layer_id}", response_model=LayerResponse)
async def get_layer(
    layer_id: str,
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Get details of a specific point cloud layer.
    """
    try:
        layer_uuid = UUID(layer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid layer ID format")
    
    layer = db.query(PointCloudLayer).filter(
        PointCloudLayer.id == layer_uuid,
        PointCloudLayer.tenant_id == tenant_id
    ).first()
    
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    
    return LayerResponse(
        id=str(layer.id),
        parcel_id=layer.parcel_id,
        tileset_url=layer.tileset_url,
        source=layer.source,
        point_count=layer.point_count,
        date_observed=layer.date_observed.isoformat() if layer.date_observed else None
    )


@router.delete("/layers/{layer_id}")
async def delete_layer(
    layer_id: str,
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Delete a point cloud layer.
    
    This also removes the tileset from storage.
    """
    try:
        layer_uuid = UUID(layer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid layer ID format")
    
    layer = db.query(PointCloudLayer).filter(
        PointCloudLayer.id == layer_uuid,
        PointCloudLayer.tenant_id == tenant_id
    ).first()
    
    if not layer:
        raise HTTPException(status_code=404, detail="Layer not found")
    
    # Delete from storage
    from app.services.storage import storage_service
    prefix = f"tilesets/{layer.id}"
    storage_service.delete_prefix(prefix)
    
    # Delete database record
    db.delete(layer)
    db.commit()
    
    logger.info(f"Deleted layer {layer_id} for tenant {tenant_id}")
    
    return {"status": "deleted", "layer_id": layer_id}


@router.get("/jobs")
async def list_jobs(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    parcel_id: Optional[str] = Query(None, description="Filter by parcel"),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    List processing jobs for the tenant.
    """
    query = db.query(LidarProcessingJob).filter(
        LidarProcessingJob.tenant_id == tenant_id
    )
    
    if status_filter:
        try:
            status_enum = JobStatus(status_filter)
            query = query.filter(LidarProcessingJob.status == status_enum)
        except ValueError:
            pass
    
    if parcel_id:
        query = query.filter(LidarProcessingJob.parcel_id == parcel_id)
    
    query = query.order_by(LidarProcessingJob.created_at.desc())
    total = query.count()
    jobs = query.offset(offset).limit(limit).all()
    
    return {
        "jobs": [
            {
                "id": str(job.id),
                "parcel_id": job.parcel_id,
                "status": job.status.value,
                "progress": job.progress or 0,
                "created_at": job.created_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None
            }
            for job in jobs
        ],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("/upload", response_model=ProcessResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_laz_file(
    file: UploadFile = File(..., description="LAZ or LAS file to upload"),
    parcel_id: str = Form(..., description="Parcel entity ID"),
    geometry_wkt: Optional[str] = Form(None, description="Optional WKT geometry for cropping"),
    config: str = Form(default="{}", description="Processing config as JSON string"),
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db)
):
    """
    Upload a custom LAZ/LAS file for processing.
    
    This endpoint allows users to upload their own point cloud files
    (e.g., from drone flights) instead of downloading from PNOA.
    
    The file must be georeferenced (contain proper CRS metadata).
    Maximum file size: 500MB.
    """
    # Validate file extension
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    
    file_ext = file.filename.lower().split('.')[-1]
    if file_ext not in ('laz', 'las'):
        raise HTTPException(
            status_code=400,
            detail="Only .LAZ and .LAS files are supported"
        )
    
    # Validate file size (500MB max)
    max_size = 500 * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is 500MB."
        )
    
    # Parse config JSON
    try:
        config_dict = json.loads(config) if config else {}
    except json.JSONDecodeError:
        config_dict = {}
    
    # Save file to temp location
    temp_dir = tempfile.mkdtemp(prefix="lidar_upload_")
    temp_file_path = os.path.join(temp_dir, f"upload.{file_ext}")
    
    try:
        with open(temp_file_path, 'wb') as f:
            f.write(content)
        
        logger.info(f"Uploaded file saved to {temp_file_path} ({len(content)} bytes)")
        
        # Create job record
        job = LidarProcessingJob(
            tenant_id=tenant_id,
            user_id=current_user.get("sub", "unknown"),
            parcel_id=parcel_id,
            parcel_geometry_wkt=geometry_wkt,
            config={
                **config_dict,
                "uploaded_file_path": temp_file_path,
                "source": "user_upload"
            },
            status=JobStatus.QUEUED
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        
        # Import the upload-specific worker function
        from app.services.lidar_pipeline import process_uploaded_file
        
        # Enqueue job for worker
        try:
            queue = get_redis_queue()
            rq_job = queue.enqueue(
                process_uploaded_file,
                str(job.id),
                temp_file_path,
                geometry_wkt,
                job_timeout=settings.WORKER_TIMEOUT
            )
            
            job.rq_job_id = rq_job.id
            db.commit()
            
            logger.info(f"Upload job {job.id} enqueued (RQ: {rq_job.id})")
            
        except Exception as e:
            logger.error(f"Failed to enqueue upload job: {e}")
            job.status = JobStatus.FAILED
            job.error_message = f"Failed to enqueue: {str(e)}"
            db.commit()
            
            # Cleanup temp file
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
            
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Processing queue unavailable. Please try again later."
            )
        
        return ProcessResponse(
            job_id=str(job.id),
            status="queued",
            message="File uploaded and queued for processing. Poll /status/{job_id} for updates."
        )
        
    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        raise


# ============================================================================
# Cache Statistics
# ============================================================================

@router.get("/cache/stats")
async def get_cache_stats(
    user=Depends(require_auth)
):
    """
    Get PNOA tile cache statistics.
    
    Shows how many tiles are cached and how many downloads were avoided
    by reusing cached tiles for overlapping parcels.
    """
    from app.services.tile_cache import tile_cache
    
    stats = tile_cache.get_cache_stats()
    return {
        "cache": stats,
        "description": "Tiles are cached in MinIO to avoid re-downloading for overlapping parcels"
    }

