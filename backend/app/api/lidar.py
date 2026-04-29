"""LIDAR API endpoints backed by Orion-LD entities."""

import json
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional
from uuid import uuid4

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import PlainTextResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field
from redis import Redis
from rq import Queue

from prometheus_client import Histogram

from app.config import settings
from app.main import limiter
from app.middleware.auth import get_tenant_id, require_auth
from app.services.lidar_pipeline import process_lidar_job, process_uploaded_file
from app.services.geodesy_validator import GeodesyValidationError, inspect_laz_crs
from app.services.orion_client import get_orion_client
from app.services.pnoa_indexer import PNOAIndexer

logger = logging.getLogger(__name__)

router = APIRouter()
ALLOWED_CORS_ORIGINS = {o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()}

# Prometheus metric: LiDAR processing job duration
lidar_job_duration = Histogram(
    'lidar_job_duration_seconds',
    'Duration of LiDAR processing jobs',
    buckets=[60, 300, 600, 1800, 3600, 7200]
)


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


def _prop(entity: Dict[str, Any], key: str, default: Any = None) -> Any:
    return entity.get(key, {}).get("value", default)


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/health")
async def router_health():
    """Public health endpoint (reachable via ingress /api/lidar/health)."""
    return {"status": "healthy", "module": "lidar", "version": "1.0.0"}


@router.get("/metrics")
async def router_metrics():
    """Public Prometheus metrics (reachable via ingress /api/lidar/metrics)."""
    import httpx
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get("http://localhost:8000/metrics")
        return PlainTextResponse(content=resp.text, media_type="text/plain; version=0.0.4")


@router.post("/process", response_model=ProcessResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("5 per minute")
async def start_processing(
    request: Request,
    body: ProcessRequest,
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Start LiDAR processing for a parcel.

    This endpoint:
    1. Validates the parcel has LiDAR coverage
    2. Creates a processing job record
    3. Enqueues the job in Redis for worker processing

    Returns immediately with job ID for status polling.
    """
    logger.info(f"Processing request for parcel {body.parcel_id} by tenant {tenant_id}")

    # Check coverage first
    indexer = PNOAIndexer()
    if not indexer.has_coverage(body.parcel_geometry_wkt):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No LiDAR coverage available for this parcel"
        )

    job_id = str(uuid4())
    job_entity_id = await get_orion_client(tenant_id).create_processing_job(
        job_id=job_id,
        parcel_id=body.parcel_id,
        geometry_wkt=body.parcel_geometry_wkt,
        config=body.config.model_dump(),
        user_id=current_user.get("sub", "unknown"),
    )
    
    # Enqueue job for worker
    try:
        queue = get_redis_queue()
        rq_job = queue.enqueue(
            process_lidar_job,
            job_entity_id,
            tenant_id,
            job_timeout=settings.WORKER_TIMEOUT
        )
        await get_orion_client(tenant_id).update_job(job_entity_id, statusMessage=f"Queued RQ: {rq_job.id}")
        logger.info(f"Job {job_entity_id} enqueued successfully (RQ: {rq_job.id})")
        
    except Exception as e:
        logger.error(f"Failed to enqueue job: {e}")
        await get_orion_client(tenant_id).update_job(
            job_entity_id, status="failed", statusMessage=f"Failed to enqueue: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Processing queue unavailable. Please try again later."
        )
    
    return ProcessResponse(
        job_id=job_id,
        status="queued",
        message="Processing job queued. Poll /status/{job_id} for updates."
    )


@router.post("/process/{job_id}/cancel")
async def cancel_processing(
    job_id: str,
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Cancel a running or queued processing job.
    """
    entity_id = f"urn:ngsi-ld:DataProcessingJob:{job_id}"
    try:
        job = await get_orion_client(tenant_id).get_job(entity_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    status = _prop(job, "status", "")
    if status in ("completed", "failed", "cancelled"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel job with status '{status}'"
        )

    # Remove from RQ queue if queued
    if status in ("queued", "pending"):
        try:
            queue = get_redis_queue()
            for rq_job in queue.get_jobs():
                if rq_job.meta.get("job_entity_id") == entity_id:
                    rq_job.cancel()
                    break
        except Exception as e:
            logger.warning(f"Could not remove job from RQ queue: {e}")

    await get_orion_client(tenant_id).cancel_job(entity_id)
    return {"job_id": job_id, "status": "cancelled"}


@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get status of a processing job.
    
    Poll this endpoint to track job progress.
    """
    entity_id = f"urn:ngsi-ld:DataProcessingJob:{job_id}"
    try:
        job = await get_orion_client(tenant_id).get_job(entity_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        job_id=job_id,
        status=_prop(job, "status", "queued"),
        progress=_prop(job, "progress", 0),
        status_message=_prop(job, "statusMessage"),
        error_message=_prop(job, "errorMessage"),
        tileset_url=_prop(job, "tilesetUrl"),
        tree_count=_prop(job, "treeCount"),
        point_count=_prop(job, "pointCount")
    )


@router.post("/coverage", response_model=CoverageResponse)
async def check_coverage(
    request: CoverageCheckRequest,
    current_user: dict = Depends(require_auth)
):
    """
    Check if LiDAR coverage is available for a given area.
    
    Returns list of available tiles with their metadata.
    """
    indexer = PNOAIndexer()
    tiles = indexer.find_coverage(request.geometry_wkt, source=request.source)
    
    return CoverageResponse(
        has_coverage=len(tiles) > 0,
        tiles=tiles
    )


@router.get("/layers", response_model=List[LayerResponse])
async def get_layers(
    parcel_id: Optional[str] = Query(None, description="Filter by parcel ID"),
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get available point cloud layers for the tenant.
    """
    layers = await get_orion_client(tenant_id).list_assets(parcel_id=parcel_id)
    return [
        LayerResponse(
            id=l.get("id", "").split(":")[-1],
            parcel_id=l.get("refAgriParcel", {}).get("object", ""),
            tileset_url=_prop(l, "resourceURL", ""),
            source=_prop(l, "source", "PNOA"),
            point_count=_prop(l, "pointCount"),
            date_observed=_prop(l, "dateObserved"),
        )
        for l in layers
    ]


@router.get("/layers/{layer_id}", response_model=LayerResponse)
async def get_layer(
    layer_id: str,
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Get details of a specific point cloud layer.
    """
    entity_id = f"urn:ngsi-ld:DigitalAsset:{layer_id}"
    try:
        layer = await get_orion_client(tenant_id).get_asset(entity_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Layer not found")

    return LayerResponse(
        id=layer_id,
        parcel_id=layer.get("refAgriParcel", {}).get("object", ""),
        tileset_url=_prop(layer, "resourceURL", ""),
        source=_prop(layer, "source", "PNOA"),
        point_count=_prop(layer, "pointCount"),
        date_observed=_prop(layer, "dateObserved"),
    )


@router.delete("/layers/{layer_id}")
async def delete_layer(
    layer_id: str,
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    Delete a point cloud layer.

    This also removes the tileset from storage.
    """
    entity_id = f"urn:ngsi-ld:DigitalAsset:{layer_id}"
    try:
        await get_orion_client(tenant_id).get_asset(entity_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Layer not found")

    from app.services.storage import storage_service
    prefix = layer_id
    storage_service.delete_prefix(prefix)
    await get_orion_client(tenant_id).delete_asset(entity_id)

    logger.info(f"Deleted layer {layer_id} for tenant {tenant_id}")
    
    return {"status": "deleted", "layer_id": layer_id}


@router.get("/jobs")
async def list_jobs(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    parcel_id: Optional[str] = Query(None, description="Filter by parcel"),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id)
):
    """
    List processing jobs for the tenant.
    """
    jobs = await get_orion_client(tenant_id).list_jobs(limit=limit, offset=offset)
    if status_filter:
        jobs = [j for j in jobs if _prop(j, "status") == status_filter]
    if parcel_id:
        jobs = [j for j in jobs if j.get("refAgriParcel", {}).get("object", "").endswith(parcel_id)]
    
    return {
        "jobs": [
            {
                "id": job.get("id", "").split(":")[-1],
                "parcel_id": job.get("refAgriParcel", {}).get("object", ""),
                "status": _prop(job, "status", "queued"),
                "progress": _prop(job, "progress", 0),
                "created_at": _prop(job, "createdAt", ""),
                "completed_at": _prop(job, "completedAt")
            }
            for job in jobs
        ],
        "total": len(jobs),
        "limit": limit,
        "offset": offset
    }


@router.post("/upload", response_model=ProcessResponse, status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("3 per minute")
async def upload_laz_file(
    request: Request,
    file: UploadFile = File(..., description="LAZ or LAS file to upload"),
    parcel_id: str = Form(..., description="Parcel entity ID"),
    geometry_wkt: Optional[str] = Form(None, description="Optional WKT geometry for cropping"),
    config: str = Form(default="{}", description="Processing config as JSON string"),
    source_crs: Optional[str] = Form(None, description="Optional source CRS override (e.g. EPSG:25830+5782)"),
    current_user: dict = Depends(require_auth),
    tenant_id: str = Depends(get_tenant_id)
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
    
    # Parse config JSON
    try:
        config_dict = json.loads(config) if config else {}
    except json.JSONDecodeError:
        config_dict = {}

    # Save file to temp location, streaming in chunks to avoid loading into memory
    max_size = 500 * 1024 * 1024
    temp_dir = tempfile.mkdtemp(prefix="lidar_upload_")
    temp_file_path = os.path.join(temp_dir, f"upload.{file_ext}")

    try:
        bytes_written = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        with open(temp_file_path, 'wb') as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > max_size:
                    f.close()
                    os.remove(temp_file_path)
                    os.rmdir(temp_dir)
                    raise HTTPException(
                        status_code=413,
                        detail="File too large. Maximum size is 500MB."
                    )
                f.write(chunk)
        
        logger.info(f"Uploaded file saved to {temp_file_path} ({bytes_written} bytes)")
        inspect_laz_crs(temp_file_path, source_crs_override=source_crs)
        
        job_id = str(uuid4())
        
        # Upload the file to MinIO temp location so the worker can download it
        from app.services.storage import storage_service
        s3_key = f"user_uploads/{tenant_id}/{job_id}/upload.{file_ext}"
        storage_service.ensure_bucket("lidar-source-tiles")
        storage_service.upload_file(
            bucket="lidar-source-tiles",
            key=s3_key,
            file_path=temp_file_path,
            content_type="application/octet-stream"
        )
        logger.info(f"Uploaded file stored in MinIO at lidar-source-tiles/{s3_key}")
        
        # Cleanup local API temp file immediately after upload to MinIO
        try:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
        except Exception as cleanup_err:
            logger.warning(f"Failed to cleanup local temp file: {cleanup_err}")

        config_payload = {
            **config_dict,
            "uploaded_file_path": s3_key,
            "source": "user_upload",
            "source_crs": source_crs,
        }
        job_entity_id = await get_orion_client(tenant_id).create_processing_job(
            job_id=job_id,
            parcel_id=parcel_id,
            geometry_wkt=geometry_wkt,
            config=config_payload,
            user_id=current_user.get("sub", "unknown"),
        )
        
        # Enqueue job for worker
        try:
            queue = get_redis_queue()
            rq_job = queue.enqueue(
                process_uploaded_file,
                job_entity_id,
                tenant_id,
                s3_key,
                geometry_wkt,
                job_timeout=settings.WORKER_TIMEOUT
            )
            # Update statusMessage instead of rqJobId to avoid NGSI-LD context errors
            await get_orion_client(tenant_id).update_job(job_entity_id, statusMessage=f"Queued RQ: {rq_job.id}")
            logger.info(f"Upload job {job_entity_id} enqueued (RQ: {rq_job.id})")
            
        except Exception as e:
            logger.error(f"Failed to enqueue upload job: {e}")
            await get_orion_client(tenant_id).update_job(
                job_entity_id, status="failed", statusMessage=f"Failed to enqueue: {str(e)}"
            )

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
            job_id=job_id,
            status="queued",
            message="File uploaded and queued for processing. Poll /status/{job_id} for updates."
        )
        
    except GeodesyValidationError as e:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)
        raise


# ============================================================================
# Tileset File Proxy (serves 3D Tiles from MinIO)
# ============================================================================

TILESET_CONTENT_TYPES = {
    ".json": "application/json",
    ".pnts": "application/octet-stream",
    ".b3dm": "application/octet-stream",
    ".i3dm": "application/octet-stream",
    ".cmpt": "application/octet-stream",
    ".glb": "model/gltf-binary",
    ".gltf": "model/gltf+json",
}


@router.get("/tilesets/{file_path:path}")
async def serve_tileset_file(file_path: str, request: Request):
    """
    Proxy endpoint that streams tileset files from MinIO.

    Cesium requests tileset.json and .pnts files via this route.
    No auth required — tilesets are public read.
    """
    from app.services.storage import storage_service

    # Files are stored in MinIO under "{job_id}/tileset.json", "{job_id}/r.pnts", etc.
    # The route strips "/api/lidar/tilesets/" leaving "{job_id}/..."
    object_key = file_path
    if settings.MINIO_PUBLIC_BASE_URL:
        direct_url = f"{settings.MINIO_PUBLIC_BASE_URL.rstrip('/')}/{settings.MINIO_BUCKET}/{object_key}"
        return RedirectResponse(url=direct_url, status_code=307)

    # Determine content type from extension
    ext = os.path.splitext(file_path)[1].lower()
    content_type = TILESET_CONTENT_TYPES.get(ext, "application/octet-stream")

    try:
        body = storage_service.get_file_stream(object_key)
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in ("404", "NoSuchKey"):
            raise HTTPException(status_code=404, detail="Tileset file not found")
        logger.error(f"MinIO error serving {object_key}: {e}")
        raise HTTPException(status_code=502, detail="Storage error")

    origin = request.headers.get("origin", "")
    cors_origin = origin if origin in ALLOWED_CORS_ORIGINS else ""
    return StreamingResponse(
        body.iter_chunks(chunk_size=65536),
        media_type=content_type,
        headers={
            "Access-Control-Allow-Origin": cors_origin,
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "Cache-Control": "public, max-age=3600",
        },
    )


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

