"""
LiDAR Processing Pipeline.

This is the core processing engine that handles:
- Phase A: Download + Crop + Denoise
- Phase B: Spectral Fusion (NDVI colorization)
- Phase C: Tree Segmentation (CHM + Watershed)
- Phase D: 3D Tiling (py3dtiles conversion)

This module contains functions designed to be run by RQ workers,
NOT within the API process.
"""

import logging
import os
import tempfile
import shutil
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import uuid

import numpy as np
import pdal
import rasterio
from rasterio.warp import transform_bounds
from rasterio.features import shapes
from shapely.geometry import shape, mapping
from shapely.ops import transform as shapely_transform
import pyproj
from scipy import ndimage
from skimage.feature import peak_local_max
from skimage.segmentation import watershed
import requests

from app.config import settings
from app.services.storage import storage_service
from app.services.tile_cache import tile_cache
from app.db import SessionLocal
from app.models import LidarProcessingJob, LidarCoverageIndex, JobStatus

logger = logging.getLogger(__name__)


class LidarPipeline:
    """
    LiDAR processing pipeline.
    
    Orchestrates the 4-phase processing workflow for point cloud data.
    """
    
    def __init__(self, job_id: str, work_dir: Optional[str] = None):
        """
        Initialize the pipeline.
        
        Args:
            job_id: UUID of the LidarProcessingJob
            work_dir: Optional working directory (temp dir created if not provided)
        """
        self.job_id = job_id
        self.work_dir = work_dir or tempfile.mkdtemp(prefix="lidar_")
        self.input_laz: Optional[str] = None
        self.cropped_laz: Optional[str] = None
        self.colored_laz: Optional[str] = None
        self.output_tiles_dir: Optional[str] = None
        self.detected_trees: List[Dict[str, Any]] = []
        
        # Ensure work directory exists
        Path(self.work_dir).mkdir(parents=True, exist_ok=True)
    
    def update_job_status(
        self,
        status: JobStatus,
        progress: int = 0,
        message: str = "",
        error: Optional[str] = None
    ):
        """Update job status in database."""
        db = SessionLocal()
        try:
            job = db.query(LidarProcessingJob).filter(
                LidarProcessingJob.id == self.job_id
            ).first()
            
            if job:
                job.status = status
                job.progress = progress
                job.status_message = message
                if error:
                    job.error_message = error
                if status == JobStatus.PROCESSING and not job.started_at:
                    job.started_at = datetime.utcnow()
                if status in (JobStatus.COMPLETED, JobStatus.FAILED):
                    job.completed_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
    
    def process(
        self,
        laz_url: str,
        geometry_wkt: str,
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Run the full processing pipeline.
        
        Args:
            laz_url: URL or path to the input LAZ file
            geometry_wkt: WKT of the area to crop
            config: Processing configuration dict
        
        Returns:
            Result dict with tileset_url, tree_count, etc.
        """
        try:
            logger.info(f"Starting pipeline for job {self.job_id}")
            self.update_job_status(JobStatus.PROCESSING, 0, "Starting pipeline...")
            
            # Phase A: Download and Crop
            self.update_job_status(JobStatus.PROCESSING, 10, "Downloading and cropping point cloud...")
            self.phase_a_ingest(laz_url, geometry_wkt)
            
            # Phase B: Spectral Fusion (if NDVI source provided)
            ndvi_url = config.get("ndvi_source_url")
            colorize_by = config.get("colorize_by", "height")
            
            if colorize_by == "ndvi" and ndvi_url:
                self.update_job_status(JobStatus.PROCESSING, 30, "Applying NDVI colorization...")
                self.phase_b_spectral_fusion(ndvi_url)
            else:
                # Just copy cropped to colored path
                self.colored_laz = self.cropped_laz
                self.update_job_status(JobStatus.PROCESSING, 30, "Skipping spectral fusion (no NDVI source)")
            
            # Phase C: Tree Segmentation (if enabled)
            detect_trees = config.get("detect_trees", False)
            if detect_trees:
                self.update_job_status(JobStatus.PROCESSING, 50, "Detecting individual trees...")
                min_height = config.get("tree_min_height", settings.DEFAULT_TREE_MIN_HEIGHT)
                search_radius = config.get("tree_search_radius", settings.DEFAULT_TREE_SEARCH_RADIUS)
                self.phase_c_tree_segmentation(min_height, search_radius)
            
            # Phase D: 3D Tiling
            self.update_job_status(JobStatus.PROCESSING, 70, "Converting to 3D Tiles...")
            self.phase_d_tiling()
            
            # Upload results to MinIO
            self.update_job_status(JobStatus.PROCESSING, 90, "Uploading results...")
            tileset_url = self._upload_results()
            
            # Create Orion-LD entities
            self.update_job_status(JobStatus.PROCESSING, 95, "Creating digital twin entities...")
            self._create_orion_entities(tileset_url, config)
            
            # Update job with results
            result = {
                "tileset_url": tileset_url,
                "tree_count": len(self.detected_trees),
                "trees": self.detected_trees,
                "point_count": self._count_points()
            }
            
            self._finalize_job(result)
            self.update_job_status(JobStatus.COMPLETED, 100, "Processing complete!")
            
            return result
            
        except Exception as e:
            logger.exception(f"Pipeline failed for job {self.job_id}")
            self.update_job_status(JobStatus.FAILED, 0, "Pipeline failed", str(e))
            raise
        finally:
            # Cleanup work directory
            self._cleanup()
    
    def phase_a_ingest(self, laz_url: str, geometry_wkt: str):
        """
        Phase A: Download, Crop, and Denoise the point cloud.
        
        Args:
            laz_url: URL or path to input LAZ
            geometry_wkt: WKT polygon for cropping
        """
        logger.info("Phase A: Ingesting point cloud")
        
        # Step 1: Get tile from cache or download
        # The tile cache stores raw PNOA tiles in MinIO so they can be reused
        # for parcels in the same area (big win for overlapping requests)
        if laz_url.startswith(('http://', 'https://')):
            logger.info(f"Getting tile from cache or downloading: {laz_url}")
            self.input_laz = tile_cache.get_or_download_tile(laz_url, self.work_dir)
            logger.info(f"Tile ready at: {self.input_laz}")
        else:
            # Local file - just copy (user uploads)
            self.input_laz = os.path.join(self.work_dir, "input.laz")
            shutil.copy(laz_url, self.input_laz)
        
        # Step 2: Build PDAL pipeline for crop + denoise
        self.cropped_laz = os.path.join(self.work_dir, "cropped.laz")
        
        pipeline_json = {
            "pipeline": [
                {
                    "type": "readers.las",
                    "filename": self.input_laz
                },
                {
                    "type": "filters.crop",
                    "polygon": geometry_wkt
                },
                {
                    "type": "filters.outlier",
                    "method": "statistical",
                    "mean_k": 12,
                    "multiplier": 2.0
                },
                {
                    "type": "filters.elm"  # Extended Local Minimum (ground enhancement)
                },
                {
                    "type": "writers.las",
                    "filename": self.cropped_laz,
                    "compression": "laszip"
                }
            ]
        }
        
        logger.info("Running PDAL crop + denoise pipeline")
        pipeline = pdal.Pipeline(json.dumps(pipeline_json))
        pipeline.execute()
        
        logger.info(f"Phase A complete. Output: {self.cropped_laz}")
    
    def phase_b_spectral_fusion(self, ndvi_raster_url: str):
        """
        Phase B: Colorize points with NDVI values from a GeoTIFF.
        
        Maps NDVI values from a raster to each point's ExtraByte dimension.
        
        Args:
            ndvi_raster_url: URL or path to NDVI GeoTIFF
        """
        logger.info("Phase B: Spectral fusion (NDVI)")
        
        # Download NDVI raster
        ndvi_path = os.path.join(self.work_dir, "ndvi.tif")
        if ndvi_raster_url.startswith(('http://', 'https://')):
            response = requests.get(ndvi_raster_url, stream=True, timeout=120)
            response.raise_for_status()
            with open(ndvi_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        else:
            shutil.copy(ndvi_raster_url, ndvi_path)
        
        self.colored_laz = os.path.join(self.work_dir, "colored.laz")
        
        # Use PDAL colorization filter
        pipeline_json = {
            "pipeline": [
                {
                    "type": "readers.las",
                    "filename": self.cropped_laz
                },
                {
                    "type": "filters.colorization",
                    "raster": ndvi_path,
                    "dimensions": "NDVI:1:256.0"  # Map band 1 to NDVI dimension
                },
                {
                    "type": "writers.las",
                    "filename": self.colored_laz,
                    "compression": "laszip",
                    "extra_dims": "NDVI=float"
                }
            ]
        }
        
        logger.info("Running PDAL colorization pipeline")
        pipeline = pdal.Pipeline(json.dumps(pipeline_json))
        pipeline.execute()
        
        logger.info(f"Phase B complete. Output: {self.colored_laz}")
    
    def phase_c_tree_segmentation(
        self,
        min_height: float = 2.0,
        search_radius: float = 3.0,
        chm_resolution: float = 0.5
    ):
        """
        Phase C: Detect individual trees using CHM and watershed segmentation.
        
        Steps:
        1. Generate CHM (Canopy Height Model) from point cloud
        2. Find local maxima (tree tops)
        3. Apply watershed segmentation
        4. Extract tree statistics
        
        Args:
            min_height: Minimum tree height to detect (meters)
            search_radius: Search radius for local maxima (meters)
            chm_resolution: Resolution of CHM raster (meters)
        
        Returns:
            List of detected trees with their properties
        """
        logger.info("Phase C: Tree segmentation")
        
        # Generate CHM using PDAL
        dtm_path = os.path.join(self.work_dir, "dtm.tif")
        dsm_path = os.path.join(self.work_dir, "dsm.tif")
        chm_path = os.path.join(self.work_dir, "chm.tif")
        
        source_laz = self.colored_laz or self.cropped_laz
        
        # Step 1: Generate DTM (ground points only)
        dtm_pipeline = {
            "pipeline": [
                {"type": "readers.las", "filename": source_laz},
                {"type": "filters.smrf"},  # Ground classification
                {"type": "filters.range", "limits": "Classification[2:2]"},  # Ground only
                {
                    "type": "writers.gdal",
                    "filename": dtm_path,
                    "resolution": chm_resolution,
                    "output_type": "idw"
                }
            ]
        }
        pdal.Pipeline(json.dumps(dtm_pipeline)).execute()
        
        # Step 2: Generate DSM (highest points)
        dsm_pipeline = {
            "pipeline": [
                {"type": "readers.las", "filename": source_laz},
                {
                    "type": "writers.gdal",
                    "filename": dsm_path,
                    "resolution": chm_resolution,
                    "output_type": "max"
                }
            ]
        }
        pdal.Pipeline(json.dumps(dsm_pipeline)).execute()
        
        # Step 3: Calculate CHM = DSM - DTM
        with rasterio.open(dtm_path) as dtm_src, rasterio.open(dsm_path) as dsm_src:
            dtm = dtm_src.read(1)
            dsm = dsm_src.read(1)
            transform = dtm_src.transform
            crs = dtm_src.crs
            
            # Calculate CHM
            chm = dsm - dtm
            chm[chm < 0] = 0  # Remove negative values
            chm[np.isnan(chm)] = 0
            
            # Save CHM
            profile = dtm_src.profile.copy()
            with rasterio.open(chm_path, 'w', **profile) as dst:
                dst.write(chm, 1)
        
        # Step 4: Find tree tops (local maxima)
        logger.info("Finding tree tops...")
        
        # Apply minimum height threshold
        chm_masked = np.where(chm >= min_height, chm, 0)
        
        # Smooth CHM slightly to reduce noise
        chm_smooth = ndimage.gaussian_filter(chm_masked, sigma=1)
        
        # Find local maxima
        min_distance = int(search_radius / chm_resolution)
        coordinates = peak_local_max(
            chm_smooth,
            min_distance=min_distance,
            threshold_abs=min_height
        )
        
        logger.info(f"Found {len(coordinates)} potential tree tops")
        
        # Step 5: Watershed segmentation (optional, for crown delineation)
        # Create markers for watershed
        markers = np.zeros(chm.shape, dtype=np.int32)
        for idx, (row, col) in enumerate(coordinates, start=1):
            markers[row, col] = idx
        
        # Run watershed
        labels = watershed(-chm_smooth, markers, mask=chm_smooth > 0)
        
        # Step 6: Extract tree properties with canopy polygons
        self.detected_trees = []

        # Setup coordinate transformation if needed (raster CRS to WGS84)
        raster_crs = crs
        target_crs = pyproj.CRS("EPSG:4326")

        # Create transformer if CRS is not already WGS84
        transformer = None
        if raster_crs and raster_crs != target_crs:
            try:
                transformer = pyproj.Transformer.from_crs(
                    raster_crs, target_crs, always_xy=True
                )
            except Exception as e:
                logger.warning(f"Could not create CRS transformer: {e}")

        # Vectorize watershed labels to get canopy polygons
        logger.info("Extracting canopy polygons from watershed...")
        canopy_polygons = {}

        try:
            # Use rasterio.features.shapes to vectorize the labels
            for geom, value in shapes(labels.astype(np.int32), transform=transform):
                if value > 0:  # Skip background (0)
                    canopy_polygons[int(value)] = shape(geom)
        except Exception as e:
            logger.warning(f"Could not vectorize canopy polygons: {e}")

        for idx, (row, col) in enumerate(coordinates, start=1):
            # Get pixel coordinates in raster CRS
            px_x = transform.c + col * transform.a
            px_y = transform.f + row * transform.e

            # Get tree height at peak
            height = float(chm[row, col])

            # Get crown area (count pixels with this label)
            crown_pixels = np.sum(labels == idx)
            crown_area = crown_pixels * (chm_resolution ** 2)  # m²
            crown_diameter = np.sqrt(crown_area / np.pi) * 2  # Approximate diameter

            # Transform coordinates to WGS84 if transformer available
            lon, lat = px_x, px_y
            if transformer:
                try:
                    lon, lat = transformer.transform(px_x, px_y)
                except Exception:
                    pass

            tree = {
                "id": f"tree_{idx}",
                "location": {
                    "type": "Point",
                    "coordinates": [round(lon, 7), round(lat, 7)]
                },
                "height": round(height, 2),
                "crown_diameter": round(crown_diameter, 2),
                "crown_area": round(crown_area, 2)
            }

            # Add canopy polygon if available
            if idx in canopy_polygons:
                canopy_geom = canopy_polygons[idx]

                # Simplify polygon slightly to reduce size (tolerance ~10cm)
                canopy_geom = canopy_geom.simplify(0.1, preserve_topology=True)

                # Transform to WGS84 if needed
                if transformer:
                    try:
                        canopy_geom = shapely_transform(
                            lambda x, y: transformer.transform(x, y),
                            canopy_geom
                        )
                    except Exception as e:
                        logger.debug(f"Could not transform canopy polygon: {e}")

                # Only include if polygon is valid
                if canopy_geom.is_valid and not canopy_geom.is_empty:
                    # Round coordinates to 7 decimal places
                    canopy_coords = mapping(canopy_geom)
                    tree["canopy_geometry"] = {
                        "type": canopy_coords["type"],
                        "coordinates": canopy_coords["coordinates"]
                    }

            self.detected_trees.append(tree)

        logger.info(f"Phase C complete. Detected {len(self.detected_trees)} trees with canopy polygons")
    
    def phase_d_tiling(self):
        """
        Phase D: Convert point cloud to 3D Tiles format.
        
        Uses py3dtiles to create a tileset suitable for Cesium.
        """
        logger.info("Phase D: 3D Tiling")
        
        source_laz = self.colored_laz or self.cropped_laz
        self.output_tiles_dir = os.path.join(self.work_dir, "tiles")
        
        # Use py3dtiles command line (more reliable than Python API for large files)
        cmd = [
            "py3dtiles", "convert",
            source_laz,
            "--out", self.output_tiles_dir,
            "--overwrite"
        ]
        
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        
        if result.returncode != 0:
            logger.error(f"py3dtiles failed: {result.stderr}")
            raise RuntimeError(f"py3dtiles conversion failed: {result.stderr}")
        
        # Verify tileset.json was created
        tileset_path = os.path.join(self.output_tiles_dir, "tileset.json")
        if not os.path.exists(tileset_path):
            raise RuntimeError("tileset.json not found after conversion")
        
        logger.info(f"Phase D complete. Tiles at: {self.output_tiles_dir}")
    
    def _upload_results(self) -> str:
        """Upload tiles to MinIO and return the public URL."""
        prefix = f"tilesets/{self.job_id}"
        tileset_url = storage_service.upload_directory(
            self.output_tiles_dir,
            prefix
        )
        return tileset_url
    
    def _count_points(self) -> int:
        """Count points in the processed file."""
        source = self.colored_laz or self.cropped_laz
        if not source or not os.path.exists(source):
            return 0
        
        pipeline = pdal.Pipeline(json.dumps({
            "pipeline": [{"type": "readers.las", "filename": source}]
        }))
        pipeline.execute()
        return pipeline.metadata.get('metadata', {}).get('readers.las', {}).get('count', 0)
    
    def _finalize_job(self, result: Dict[str, Any]):
        """Update job record with final results."""
        db = SessionLocal()
        try:
            job = db.query(LidarProcessingJob).filter(
                LidarProcessingJob.id == self.job_id
            ).first()
            
            if job:
                job.tileset_url = result.get("tileset_url")
                job.tree_count = result.get("tree_count", 0)
                job.point_count = result.get("point_count", 0)
                db.commit()
        finally:
            db.close()
    
    def _create_orion_entities(self, tileset_url: str, config: Dict[str, Any]):
        """
        Create Orion-LD entities for the processed data.
        
        Creates:
        - PointCloudLayer entity for the tileset
        - AgriTree entities for detected trees (if any)
        """
        import httpx
        
        db = SessionLocal()
        try:
            job = db.query(LidarProcessingJob).filter(
                LidarProcessingJob.id == self.job_id
            ).first()
            
            if not job:
                logger.warning("Job not found for Orion entity creation")
                return
            
            tenant_id = job.tenant_id
            parcel_id = job.parcel_id
            
            headers = {
                "Content-Type": "application/ld+json",
                "Accept": "application/ld+json",
                "NGSILD-Tenant": tenant_id
            }
            
            context = [
                "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"
            ]
            
            # Create PointCloudLayer entity
            layer_entity = {
                "@context": context,
                "id": f"urn:ngsi-ld:PointCloudLayer:{self.job_id}",
                "type": "PointCloudLayer",
                "refAgriParcel": {
                    "type": "Relationship",
                    "object": parcel_id if parcel_id.startswith("urn:") else f"urn:ngsi-ld:AgriParcel:{parcel_id}"
                },
                "tilesetUrl": {"type": "Property", "value": tileset_url},
                "source": {"type": "Property", "value": config.get("source", "PNOA")},
                "dateObserved": {"type": "Property", "value": datetime.utcnow().isoformat() + "Z"},
                "pipelineStatus": {"type": "Property", "value": "COMPLETED"},
                "treeCount": {"type": "Property", "value": len(self.detected_trees)}
            }
            
            try:
                with httpx.Client(timeout=30.0) as client:
                    response = client.post(
                        f"{settings.ORION_URL}/ngsi-ld/v1/entities",
                        json=layer_entity,
                        headers=headers
                    )
                    if response.status_code in (201, 204):
                        logger.info(f"Created PointCloudLayer entity: {layer_entity['id']}")
                    else:
                        logger.warning(f"Failed to create PointCloudLayer: {response.status_code}")
            except Exception as e:
                logger.warning(f"Orion-LD PointCloudLayer creation failed: {e}")
            
            # Create AgriTree entities for detected trees
            if self.detected_trees and config.get("detect_trees", False):
                trees_created = 0
                for tree in self.detected_trees[:100]:  # Limit to 100 trees per batch
                    tree_entity = {
                        "@context": context,
                        "id": f"urn:ngsi-ld:AgriTree:{self.job_id}_{tree['id']}",
                        "type": "AgriTree",
                        "refAgriParcel": {
                            "type": "Relationship",
                            "object": parcel_id if parcel_id.startswith("urn:") else f"urn:ngsi-ld:AgriParcel:{parcel_id}"
                        },
                        "location": {"type": "GeoProperty", "value": tree["location"]},
                        "height": {"type": "Property", "value": tree["height"], "unitCode": "MTR"},
                        "crownDiameter": {"type": "Property", "value": tree.get("crown_diameter", 0), "unitCode": "MTR"},
                        "crownArea": {"type": "Property", "value": tree.get("crown_area", 0), "unitCode": "MTK"},
                        "source": {"type": "Property", "value": config.get("source", "LIDAR_PNOA")},
                        "dateDetected": {"type": "Property", "value": datetime.utcnow().isoformat() + "Z"}
                    }

                    # Add canopy geometry if available (required for zonal stats)
                    if "canopy_geometry" in tree and tree["canopy_geometry"]:
                        tree_entity["canopyGeometry"] = {
                            "type": "GeoProperty",
                            "value": tree["canopy_geometry"]
                        }

                    try:
                        with httpx.Client(timeout=10.0) as client:
                            response = client.post(
                                f"{settings.ORION_URL}/ngsi-ld/v1/entities",
                                json=tree_entity,
                                headers=headers
                            )
                            if response.status_code in (201, 204):
                                trees_created += 1
                            else:
                                logger.debug(f"Tree entity creation: {response.status_code}")
                    except Exception as e:
                        logger.debug(f"Tree entity creation failed: {e}")

                logger.info(f"Created {trees_created} AgriTree entities with canopy polygons")
            
        finally:
            db.close()
    
    def _cleanup(self):
        """Clean up temporary working directory."""
        try:
            if self.work_dir and os.path.exists(self.work_dir):
                shutil.rmtree(self.work_dir)
                logger.info(f"Cleaned up work directory: {self.work_dir}")
        except Exception as e:
            logger.warning(f"Failed to cleanup work directory: {e}")


def process_lidar_job(job_id: str):
    """
    RQ task entry point for processing a LiDAR job.
    
    This function is called by the RQ worker.
    
    Args:
        job_id: UUID of the LidarProcessingJob to process
    """
    logger.info(f"Worker starting job: {job_id}")
    
    # Load job from database
    db = SessionLocal()
    try:
        job = db.query(LidarProcessingJob).filter(
            LidarProcessingJob.id == job_id
        ).first()
        
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        # Get LAZ URL from PNOA index
        from app.services.pnoa_indexer import PNOAIndexer
        indexer = PNOAIndexer(db)
        
        tile = indexer.get_best_tile(job.parcel_geometry_wkt)
        if not tile:
            raise ValueError("No LiDAR coverage found for parcel")
        
        laz_url = tile["laz_url"]
        config = job.config or {}
        
    finally:
        db.close()
    
    # Run the pipeline
    pipeline = LidarPipeline(job_id)
    result = pipeline.process(laz_url, job.parcel_geometry_wkt, config)
    
    return result


def process_uploaded_file(job_id: str, file_path: str, geometry_wkt: Optional[str] = None):
    """
    RQ task entry point for processing an uploaded LiDAR file.
    
    This function is called by the RQ worker for user-uploaded files.
    
    Args:
        job_id: UUID of the LidarProcessingJob
        file_path: Path to the uploaded LAZ/LAS file
        geometry_wkt: Optional WKT for cropping (if None, use entire file)
    """
    logger.info(f"Worker starting upload job: {job_id} (file: {file_path})")
    
    # Load job from database
    db = SessionLocal()
    try:
        job = db.query(LidarProcessingJob).filter(
            LidarProcessingJob.id == job_id
        ).first()
        
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        config = job.config or {}
        
    finally:
        db.close()
    
    # Run the pipeline with the uploaded file
    pipeline = LidarPipeline(job_id)
    
    # If no geometry provided, skip cropping
    if not geometry_wkt:
        # Modify the pipeline to skip cropping
        # The phase_a_ingest will just copy the file
        logger.info("No geometry provided, processing entire file")
    
    result = pipeline.process(file_path, geometry_wkt or "", config)
    
    # Cleanup the uploaded file after processing
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            parent_dir = os.path.dirname(file_path)
            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                os.rmdir(parent_dir)
    except Exception as e:
        logger.warning(f"Failed to cleanup uploaded file: {e}")
    
    return result

