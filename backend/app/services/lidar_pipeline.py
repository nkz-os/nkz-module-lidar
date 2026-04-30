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
import math
import os
import tempfile
import shutil
import json
import struct
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import uuid

import numpy as np
import laspy
import pdal
import rasterio
from rasterio.warp import transform_bounds
from rasterio.features import shapes
from shapely.geometry import shape, mapping
from shapely.ops import transform as shapely_transform
from shapely.wkt import loads as wkt_loads
import pyproj
from scipy import ndimage
from skimage.feature import peak_local_max
from skimage.segmentation import watershed
import requests

from app.config import settings
from app.services.geobounds_validator import GeoBoundsValidator
from app.services.geodesy_validator import GeodesyValidationError, inspect_laz_crs, reproject_to_ecef
from app.services.orion_client import get_orion_client
from app.services.pnoa_indexer import PNOAIndexer
from app.services.storage import storage_service
from app.services.tile_cache import tile_cache

logger = logging.getLogger(__name__)


class LidarPipeline:
    """
    LiDAR processing pipeline.
    
    Orchestrates the 4-phase processing workflow for point cloud data.
    """
    
    def __init__(self, job_id: str, tenant_id: str, parcel_id: str, work_dir: Optional[str] = None):
        """
        Initialize the pipeline.
        
        Args:
            job_id: UUID of the Orion-LD DataProcessingJob
            work_dir: Optional working directory (temp dir created if not provided)
        """
        self.job_id = job_id
        self.tenant_id = tenant_id
        self.parcel_id = parcel_id
        self.work_dir = work_dir or tempfile.mkdtemp(prefix="lidar_")
        self.input_laz: Optional[str] = None
        self.cropped_laz: Optional[str] = None
        self.colored_laz: Optional[str] = None
        self.output_tiles_dir: Optional[str] = None
        self.reprojected_laz: Optional[str] = None
        self.detected_trees: List[Dict[str, Any]] = []
        self.source_crs: Optional[str] = None
        self.bounds_validator = GeoBoundsValidator(
            settings.EUROPE_BOUNDS_GEOJSON_PATH,
            buffer_km=settings.GEOBBOX_BUFFER_KM,
        )
        
        # Ensure work directory exists
        Path(self.work_dir).mkdir(parents=True, exist_ok=True)
    
    def update_job_status(
        self,
        status: str,
        progress: int = 0,
        message: str = "",
        error: Optional[str] = None
    ):
        """Update job status in Orion-LD."""
        if error:
            message = f"{message} - Error: {error}"
            
        updates: Dict[str, Any] = {
            "status": status,
            "progress": progress,
            "statusMessage": message,
        }
        if status in ("completed", "failed"):
            updates["completedAt"] = datetime.utcnow().isoformat() + "Z"
        get_orion_client(self.tenant_id).update_job_sync(self.job_id, **updates)
    
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
            self.update_job_status("processing", 0, "Starting pipeline...")
            
            # Phase A: Download and Crop
            self.update_job_status("processing", 10, "Downloading and cropping point cloud...")
            self.phase_a_ingest(laz_url, geometry_wkt, config.get("source_crs"))
            
            # Phase B: Spectral Fusion (if NDVI source provided and color mode is rgb)
            ndvi_url = config.get("ndvi_source_url")
            colorize_by = config.get("colorize_by", "height")

            if colorize_by == "rgb" and ndvi_url:
                self.update_job_status("processing", 30, "Applying NDVI colorization...")
                self.phase_b_spectral_fusion(ndvi_url)
            else:
                # Just copy cropped to colored path
                self.colored_laz = self.cropped_laz
                self.update_job_status("processing", 30, "Skipping spectral fusion (no NDVI source)")
            
            # Phase C: Tree Segmentation (if enabled)
            detect_trees = config.get("detect_trees", False)
            if detect_trees:
                self.update_job_status("processing", 50, "Detecting individual trees...")
                min_height = config.get("tree_min_height", settings.DEFAULT_TREE_MIN_HEIGHT)
                search_radius = config.get("tree_search_radius", settings.DEFAULT_TREE_SEARCH_RADIUS)
                self.phase_c_tree_segmentation(min_height, search_radius)
            
            # Phase D: 3D Tiling
            self.update_job_status("processing", 70, "Converting to 3D Tiles...")
            self.phase_d_tiling()
            
            # Upload results to MinIO
            self.update_job_status("processing", 90, "Uploading results...")
            tileset_url = self._upload_results()
            
            # Create Orion-LD entities
            self.update_job_status("processing", 95, "Creating digital twin entities...")
            
            # Update job with results
            result = {
                "tileset_url": tileset_url,
                "tree_count": len(self.detected_trees),
                "trees": self.detected_trees,
                "point_count": self._count_points()
            }
            
            self._create_orion_entities(tileset_url, config, result)
            self.update_job_status("completed", 100, "Processing complete!")
            
            return result
            
        except Exception as e:
            logger.exception(f"Pipeline failed for job {self.job_id}")
            self.update_job_status("failed", 0, "Pipeline failed", str(e))
            raise
        finally:
            # Cleanup work directory
            self._cleanup()
    
    def phase_a_ingest(self, laz_url: str, geometry_wkt: str, source_crs_override: Optional[str] = None):
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
        validation = inspect_laz_crs(self.input_laz, source_crs_override=source_crs_override)
        self.source_crs = validation.source_crs
        
        # Step 2: Build PDAL pipeline for crop + denoise
        self.cropped_laz = os.path.join(self.work_dir, "cropped.laz")

        stages = [
            {"type": "readers.las", "filename": self.input_laz}
        ]

        # Crop to parcel geometry (if provided)
        if geometry_wkt and geometry_wkt.strip():
            crop_wkt = self._reproject_crop_polygon(geometry_wkt)
            stages.append({
                "type": "filters.crop",
                "polygon": crop_wkt
            })

        stages.extend([
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
        ])

        logger.info("Running PDAL crop + denoise pipeline")
        pipeline = pdal.Pipeline(json.dumps({"pipeline": stages}))
        count = pipeline.execute()

        if count == 0:
            logger.warning(
                "No points remain after cropping to parcel boundary. "
                "The uploaded file does not overlap with the parcel. "
                "Falling back to processing the entire un-cropped file."
            )
            # Remove the crop filter and run again
            stages_no_crop = [s for s in stages if s.get("type") != "filters.crop"]
            pipeline = pdal.Pipeline(json.dumps({"pipeline": stages_no_crop}))
            count = pipeline.execute()
            
            if count == 0:
                raise ValueError("The provided LAZ file contains 0 valid points even without cropping.")

        logger.info(f"Phase A complete. {count} points. Output: {self.cropped_laz}")

        # Compute HeightAboveGround for every point (required for canopy analysis)
        # Auto-classify if the input lacks classification (common for drone uploads)
        needs_classification = False
        try:
            with laspy.open(self.cropped_laz) as reader:
                las = reader.read()
                if hasattr(las, 'classification'):
                    unique_classes = set(int(c) for c in las.classification)
                    needs_classification = len(unique_classes) <= 1 and 0 in unique_classes
                else:
                    needs_classification = True
        except Exception:
            needs_classification = True

        if needs_classification:
            logger.info("Input lacks classification — auto-classifying with PDAL smrf")
            hag_pipeline = {
                "pipeline": [
                    {"type": "readers.las", "filename": self.cropped_laz},
                    {"type": "filters.smrf"},
                    {"type": "filters.hag"},
                    {
                        "type": "writers.las",
                        "filename": self.cropped_laz,
                        "compression": "laszip",
                        "extra_dims": "HeightAboveGround=float",
                    },
                ]
            }
            pdal.Pipeline(json.dumps(hag_pipeline)).execute()
            logger.info("Auto-classification and HAG complete")
        else:
            # Already classified — just run HAG
            hag_pipeline = {
                "pipeline": [
                    {"type": "readers.las", "filename": self.cropped_laz},
                    {"type": "filters.smrf"},
                    {"type": "filters.hag"},
                    {
                        "type": "writers.las",
                        "filename": self.cropped_laz,
                        "compression": "laszip",
                        "extra_dims": "HeightAboveGround=float",
                    },
                ]
            }
            pdal.Pipeline(json.dumps(hag_pipeline)).execute()
            logger.info("HAG computed on pre-classified data")

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
        self.reprojected_laz = os.path.join(self.work_dir, "reprojected_ecef.laz")
        try:
            reproject_to_ecef(source_laz, self.reprojected_laz, self.source_crs or "EPSG:4326")
        except GeodesyValidationError:
            raise
        except Exception as exc:
            raise GeodesyValidationError(f"CRS_OPERATION_UNRESOLVED:{exc}") from exc
        self._validate_bbox_is_europe(self.reprojected_laz)
        source_laz = self.reprojected_laz
        self.output_tiles_dir = os.path.join(self.work_dir, "tiles")

        # Verify the source file has points before conversion
        try:
            with laspy.open(source_laz) as f:
                point_count = f.header.point_count
            if point_count == 0:
                raise ValueError(
                    "Cannot convert to 3D Tiles: point cloud has 0 points. "
                    "The crop phase may have produced empty output."
                )
            logger.info(f"Converting {point_count} points to 3D Tiles")
        except (laspy.LaspyError, OSError) as e:
            raise ValueError(f"Cannot read source LAZ file for tiling: {e}")

        # Adaptive decimation guardrail: prevent OOM on dense clouds
        source_laz = self._prepare_tiling_input(source_laz)

        # Use py3dtiles command line (more reliable than Python API for large files)
        # Resolve full path - subprocess may not inherit conda PATH
        py3dtiles_bin = shutil.which("py3dtiles") or "/opt/conda/bin/py3dtiles"
        cmd = [
            py3dtiles_bin, "convert",
            source_laz,
            "--out", self.output_tiles_dir,
            "--overwrite"
        ]
        # Preserve LAS classification and structure attributes for Cesium styling
        for field in settings.PY3DTILES_EXTRA_FIELDS:
            cmd.extend(["--extra-fields", field])

        logger.info(f"Running: {' '.join(cmd)}")
        env = os.environ.copy()
        env["PATH"] = "/opt/conda/bin:" + env.get("PATH", "")
        env["PROJ_DATA"] = env.get("PROJ_DATA", "/opt/conda/share/proj")
        env["PROJ_LIB"] = env.get("PROJ_LIB", "/opt/conda/share/proj")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=settings.PY3DTILES_TIMEOUT, env=env)
        
        if result.returncode != 0:
            logger.error(f"py3dtiles failed: {result.stderr}")
            raise RuntimeError(f"py3dtiles conversion failed: {result.stderr}")
        
        # Verify tileset.json was created
        tileset_path = os.path.join(self.output_tiles_dir, "tileset.json")
        if not os.path.exists(tileset_path):
            raise RuntimeError("tileset.json not found after conversion")

        # Fix py3dtiles bounding volumes (known bug: Z extent can be 0,
        # causing Cesium frustum culling to discard tiles).
        self._fix_tileset_bounding_volumes(tileset_path)

        logger.info(f"Phase D complete. Tiles at: {self.output_tiles_dir}")
    
    def _fix_tileset_bounding_volumes(self, tileset_path: str) -> None:
        """
        Post-process tileset.json to fix py3dtiles bounding volume bug.

        py3dtiles 7.0.0 sometimes computes bounding volumes with Z half-axis=0,
        which causes Cesium to cull tiles via frustum culling. This reads actual
        point data from .pnts files and corrects the bounding boxes.
        """
        with open(tileset_path, "r") as f:
            tileset = json.load(f)

        root = tileset.get("root", {})
        root_transform = root.get("transform")
        self._fix_tile_bv(root, root_transform, os.path.dirname(tileset_path))

        for child in root.get("children", []):
            self._fix_tile_bv(child, root_transform, os.path.dirname(tileset_path))

        with open(tileset_path, "w") as f:
            json.dump(tileset, f, indent=2)

        logger.info("Fixed tileset bounding volumes for Cesium compatibility")

    def _fix_tile_bv(self, tile: dict, parent_transform: Optional[list], tiles_dir: str) -> None:
        """Fix a single tile's bounding volume by reading actual point data."""
        bv = tile.get("boundingVolume", {})
        if "box" not in bv:
            return

        box = bv["box"]
        content = tile.get("content", {})
        uri = content.get("uri", "")

        if uri and uri.endswith(".pnts"):
            pnts_path = os.path.join(tiles_dir, uri)
            if os.path.exists(pnts_path):
                xyz_range = self._read_pnts_xyz_range(pnts_path)
                if xyz_range:
                    cx, cy, cz = box[0], box[1], box[2]
                    # X half-axis (element 3,4,5)
                    box[3] = max(box[3], (xyz_range["x_max"] - xyz_range["x_min"]) / 2, 0.01)
                    box[4] = max(box[4], 0.001)
                    box[5] = max(box[5], 0.001)
                    # Y half-axis (element 6,7,8)
                    box[6] = max(box[6], 0.001)
                    box[7] = max(box[7], (xyz_range["y_max"] - xyz_range["y_min"]) / 2, 0.01)
                    box[8] = max(box[8], 0.001)
                    # Z half-axis (element 9,10,11) — this is the critical fix
                    box[9] = max(box[9], 0.001)
                    box[10] = max(box[10], (xyz_range["z_max"] - xyz_range["z_min"]) / 2, 0.01)
                    box[11] = max(box[11], 0.001)
                    # Ensure center matches data range
                    box[0] = (xyz_range["x_max"] + xyz_range["x_min"]) / 2
                    box[1] = (xyz_range["y_max"] + xyz_range["y_min"]) / 2
                    box[2] = (xyz_range["z_max"] + xyz_range["z_min"]) / 2

    def _read_pnts_xyz_range(self, pnts_path: str) -> Optional[dict]:
        """Read XYZ coordinate ranges from a .pnts file."""
        try:
            with open(pnts_path, "rb") as f:
                data = f.read()

            feature_json_len = struct.unpack("<I", data[12:16])[0]
            fj_start = 28
            fj = json.loads(data[fj_start : fj_start + feature_json_len])
            pts_count = fj.get("POINTS_LENGTH", 0)
            if pts_count == 0:
                return None

            pos_off = fj_start + feature_json_len
            # Read first 100 points and last 100 to estimate range
            sample_count = min(100, pts_count)
            xs, ys, zs = [], [], []

            for i in range(sample_count):
                off = pos_off + i * 12
                x, y, z = struct.unpack("<fff", data[off : off + 12])
                xs.append(x); ys.append(y); zs.append(z)

            if pts_count > sample_count * 2:
                for i in range(max(0, pts_count - sample_count), pts_count):
                    off = pos_off + i * 12
                    if off + 12 > len(data):
                        break
                    x, y, z = struct.unpack("<fff", data[off : off + 12])
                    xs.append(x); ys.append(y); zs.append(z)

            return {
                "x_min": min(xs), "x_max": max(xs),
                "y_min": min(ys), "y_max": max(ys),
                "z_min": min(zs), "z_max": max(zs),
            }
        except Exception as exc:
            logger.debug("Could not read pnts range from %s: %s", pnts_path, exc)
            return None

    def _upload_results(self) -> str:
        """Upload tiles to MinIO and return the public URL."""
        prefix = str(self.job_id)
        tileset_url = storage_service.upload_directory(
            self.output_tiles_dir,
            prefix
        )
        return tileset_url
    
    def _prepare_tiling_input(self, source_laz: str) -> str:
        """
        Apply adaptive decimation before heavy tiling when clouds are too large.

        This is a deterministic guardrail against work-horse SIGKILL/OOM during
        py3dtiles conversion. It only activates above a configurable threshold.
        """
        max_points = settings.MAX_POINTS_BEFORE_TILING_DECIMATION
        target_points = max(settings.TILING_TARGET_POINTS, 1)
        if max_points <= 0:
            return source_laz

        try:
            with laspy.open(source_laz) as f:
                point_count = int(f.header.point_count or 0)
        except Exception as exc:
            logger.warning("Could not read point count before tiling: %s", exc)
            return source_laz

        if point_count <= max_points:
            return source_laz

        step = max(2, math.ceil(point_count / target_points))
        decimated_laz = os.path.join(self.work_dir, "tiling_input_decimated.laz")
        logger.warning(
            "Adaptive decimation enabled for tiling: %s -> target~%s points (step=%s)",
            point_count,
            target_points,
            step,
        )

        pipeline = pdal.Pipeline(json.dumps({
            "pipeline": [
                {"type": "readers.las", "filename": source_laz},
                {"type": "filters.decimation", "step": step},
                {"type": "writers.las", "filename": decimated_laz, "compression": "laszip"},
            ]
        }))
        reduced_count = pipeline.execute()
        if reduced_count <= 0:
            raise RuntimeError(
                "Adaptive decimation produced 0 points; refusing to continue tiling."
            )
        logger.info(
            "Adaptive decimation complete: %s -> %s points",
            point_count,
            reduced_count,
        )
        return decimated_laz

    def _count_points(self) -> int:
        """Count points in the processed file."""
        source = self.reprojected_laz or self.colored_laz or self.cropped_laz
        if not source or not os.path.exists(source):
            return 0
        
        pipeline = pdal.Pipeline(json.dumps({
            "pipeline": [{"type": "readers.las", "filename": source}]
        }))
        pipeline.execute()
        return pipeline.metadata.get('metadata', {}).get('readers.las', {}).get('count', 0)

    def _validate_bbox_is_europe(self, laz_path: str):
        with laspy.open(laz_path) as reader:
            mins = reader.header.mins
            maxs = reader.header.maxs
        transformer = pyproj.Transformer.from_crs("EPSG:4978", "EPSG:4326", always_xy=True)
        cx = (mins[0] + maxs[0]) / 2
        cy = (mins[1] + maxs[1]) / 2
        cz = (mins[2] + maxs[2]) / 2
        lon, lat, _ = transformer.transform(cx, cy, cz)
        if not self.bounds_validator.validate_lon_lat(lon, lat):
            raise GeodesyValidationError("CRS_BBOX_OUTLIER")
    
    def _create_orion_entities(self, tileset_url: str, config: Dict[str, Any], result: Dict[str, Any]):
        """
        Create Orion-LD entities for the processed data.
        
        Creates:
        - DigitalAsset entity for the tileset
        - AgriTree entities for detected trees (if any)
        """
        client = get_orion_client(self.tenant_id)
        asset_id = self.job_id.split(":")[-1]
        client.create_digital_asset_sync(
            asset_id=asset_id,
            parcel_id=self.parcel_id,
            tileset_url=tileset_url,
            source=config.get("source", "PNOA"),
            point_count=result.get("point_count", 0),
            tree_count=result.get("tree_count", 0),
        )
        self.update_job_status(
            "completed", 
            100, 
            f"Processed tileset: {tileset_url}"
        )
    
    def _cleanup(self):
        """Clean up temporary working directory."""
        try:
            if self.work_dir and os.path.exists(self.work_dir):
                shutil.rmtree(self.work_dir)
                logger.info(f"Cleaned up work directory: {self.work_dir}")
        except Exception as e:
            logger.warning(f"Failed to cleanup work directory: {e}")

    def _get_laz_crs(self) -> Optional[pyproj.CRS]:
        """Read CRS from the input LAZ file header (lightweight, header-only read)."""
        try:
            with laspy.open(self.input_laz) as reader:
                for vlr in reader.header.vlrs:
                    # laspy 2.7+ parses WKT VLRs into WktCoordinateSystemVlr objects
                    if hasattr(vlr, 'parse_crs'):
                        try:
                            crs = vlr.parse_crs()
                            if crs:
                                return crs
                        except Exception:
                            pass

                    # Fallback: read raw bytes from any projection VLR
                    if getattr(vlr, 'user_id', '') == "LASF_Projection":
                        # OGC WKT (record_id 2112)
                        if vlr.record_id == 2112:
                            raw = getattr(vlr, 'record_data_bytes', None) or getattr(vlr, 'record_data', None)
                            if raw:
                                wkt_str = raw.decode('utf-8', errors='ignore').rstrip('\x00').strip()
                                if wkt_str:
                                    return pyproj.CRS.from_wkt(wkt_str)

                        # GeoTIFF GeoKeyDirectoryTag (record_id 34735) for EPSG code
                        if vlr.record_id == 34735:
                            raw = getattr(vlr, 'record_data_bytes', None) or getattr(vlr, 'record_data', None)
                            if raw and len(raw) >= 16:
                                n_keys = struct.unpack('<H', raw[6:8])[0]
                                for i in range(n_keys):
                                    off = 8 + i * 8
                                    if off + 8 > len(raw):
                                        break
                                    key_id, loc, _, val = struct.unpack('<4H', raw[off:off+8])
                                    if key_id in (3072, 2048) and loc == 0 and val > 0:
                                        return pyproj.CRS.from_epsg(val)
        except Exception as e:
            logger.warning(f"Could not read CRS from LAZ header: {e}")

        return None

    def _reproject_crop_polygon(self, geometry_wkt: str) -> str:
        """Reproject crop polygon from WGS84 to match the LAZ file's CRS if needed."""
        laz_crs = self._get_laz_crs()
        if not laz_crs:
            logger.warning("Could not determine LAZ CRS, using crop polygon as-is (WGS84)")
            return geometry_wkt

        parcel_crs = pyproj.CRS("EPSG:4326")

        if laz_crs.equals(parcel_crs):
            logger.info("LAZ file is in WGS84, no reprojection needed")
            return geometry_wkt

        try:
            laz_epsg = laz_crs.to_epsg() or laz_crs.name
            logger.info(f"Reprojecting crop polygon from EPSG:4326 to {laz_epsg}")

            geom = wkt_loads(geometry_wkt)
            transformer = pyproj.Transformer.from_crs(
                parcel_crs, laz_crs, always_xy=True
            )
            reprojected = shapely_transform(transformer.transform, geom)

            return reprojected.wkt
        except Exception as e:
            logger.warning(f"CRS reprojection failed, using polygon as-is: {e}")
            return geometry_wkt


def process_lidar_job(job_entity_id: str, tenant_id: str):
    """
    RQ task entry point for processing a LiDAR job.
    
    This function is called by the RQ worker.
    
    Args:
        job_id: UUID of the Orion-LD DataProcessingJob to process
    """
    logger.info("Worker starting job: %s", job_entity_id)
    client = get_orion_client(tenant_id)
    job = client.get_job_sync(job_entity_id)
    parcel_urn = job.get("refAgriParcel", {}).get("object", "")
    parcel_id = parcel_urn.split(":")[-1] if parcel_urn else ""
    geometry_wkt = job.get("parcelGeometryWKT", {}).get("value", "")
    config = job.get("config", {}).get("value", {}) or {}
    indexer = PNOAIndexer()
    tile = indexer.get_best_tile(geometry_wkt)
    if not tile:
        raise ValueError("No LiDAR coverage found for parcel")
    laz_url = tile["laz_url"]
    pipeline = LidarPipeline(job_entity_id, tenant_id=tenant_id, parcel_id=parcel_id)
    result = pipeline.process(laz_url, geometry_wkt, config)
    return result


def process_uploaded_file(job_entity_id: str, tenant_id: str, file_path: str, geometry_wkt: Optional[str] = None):
    """
    RQ task entry point for processing an uploaded LiDAR file.
    
    This function is called by the RQ worker for user-uploaded files.
    
    Args:
        job_id: UUID of the Orion-LD DataProcessingJob
        file_path: S3 key of the uploaded LAZ/LAS file in lidar-source-tiles
        geometry_wkt: Optional WKT for cropping (if None, use entire file)
    """
    logger.info("Worker starting upload job: %s (file key: %s)", job_entity_id, file_path)
    client = get_orion_client(tenant_id)
    job = client.get_job_sync(job_entity_id)
    parcel_urn = job.get("refAgriParcel", {}).get("object", "")
    parcel_id = parcel_urn.split(":")[-1] if parcel_urn else ""
    config = job.get("config", {}).get("value", {}) or {}
    pipeline = LidarPipeline(job_entity_id, tenant_id=tenant_id, parcel_id=parcel_id)
    
    import tempfile
    import os
    from app.services.storage import storage_service
    import boto3
    
    # Download file from MinIO
    ext = file_path.split('.')[-1]
    temp_dir = tempfile.mkdtemp(prefix="lidar_worker_")
    local_file_path = os.path.join(temp_dir, f"upload.{ext}")
    
    try:
        storage_service.download_file("lidar-source-tiles", file_path, local_file_path)
        logger.info(f"Downloaded uploaded file from MinIO to {local_file_path}")
        
        # If no geometry provided, skip cropping
        if not geometry_wkt:
            logger.info("No geometry provided, processing entire file")
        
        result = pipeline.process(local_file_path, geometry_wkt or "", config)
    finally:
        # Cleanup the downloaded file after processing
        try:
            if os.path.exists(local_file_path):
                os.remove(local_file_path)
            if os.path.exists(temp_dir):
                os.rmdir(temp_dir)
        except Exception as e:
            logger.warning(f"Failed to cleanup local downloaded file: {e}")
        
        # Cleanup original upload from MinIO
        try:
            prefix_to_delete = "/".join(file_path.split("/")[:-1])
            storage_service.delete_prefix(prefix_to_delete)
            logger.info(f"Cleaned up uploaded file from MinIO prefix {prefix_to_delete}")
        except Exception as e:
            logger.warning(f"Failed to cleanup MinIO uploaded file: {e}")
            
    return result

