# LiDAR Point Cloud Classification — Design Spec

> **Goal:** Enable multi-mode point cloud visualization (classification, height-above-ground, canopy vs understory, vertical density) from PNOA and drone LAZ files. Preserve LAS attributes through the pipeline and expose them in Cesium 3D Tiles with a legend UI.

**Architecture:** PDAL preserves `Classification`, `ReturnNumber`, `NumberOfReturns` during ingest. A new PDAL step computes `HeightAboveGround` from ground-classified points. py3dtiles receives `--extra-fields` for all 4 attributes. Frontend adds color-mode pills with an inline legend showing the active mapping.

**Tech Stack:** PDAL filters.smrf + filters.hag, py3dtiles --extra-fields, Cesium 3D Tiles Styling, React (existing LidarLayer + LidarLayerControl)

---

## 1. Backend: Pipeline Changes

### 1.1 Preserve LAS extra fields in Phase A

**File:** `backend/app/services/lidar_pipeline.py`

In `phase_a_ingest`, after the crop+denoise PDAL pipeline, add a `filters.hag` (Height Above Ground) step that:

1. Runs `filters.smrf` to classify ground points if not already classified
2. Generates a DTM from ground points
3. Computes `HeightAboveGround` for every point via `filters.hag`

This applies to both PNOA downloads (already classified) and drone uploads (possibly unclassified). If the file already has `Classification`, smrf reuses it; otherwise it computes it.

PDAL pipeline snippet (appended after crop+denoise writer):
```json
{
  "type": "filters.hag",
  "count": 1
}
```

The `filters.hag` filter creates a temporary DTM from ground returns and writes `HeightAboveGround` as an extra dimension on every point. Combined with smrf earlier in the pipeline, this works for both classified and unclassified inputs.

### 1.2 Pass extra fields to py3dtiles

**Files:** `backend/app/services/lidar_pipeline.py` (Phase D), `backend/app/config.py`

Add configurable extra fields:
```python
PY3DTILES_EXTRA_FIELDS: list = ["Classification", "ReturnNumber", "NumberOfReturns", "HeightAboveGround"]
```

Update the `py3dtiles convert` command in `phase_d_tiling`:
```bash
py3dtiles convert input.laz --out tiles --overwrite \
  --extra-fields Classification \
  --extra-fields ReturnNumber \
  --extra-fields NumberOfReturns \
  --extra-fields HeightAboveGround
```

### 1.3 Auto-classify unclassified drone uploads

**File:** `backend/app/services/lidar_pipeline.py`

In `phase_a_ingest`, detect if the input LAZ lacks `Classification`. If so, run `filters.smrf` before `filters.hag`. PNOA files are already classified and skip this step.

Detection: read LAS header VLR for `LASF_Projection` → check point format → if raw, classify first.

---

## 2. Frontend: Visualization Modes

### 2.1 Color Modes (replace current COLOR_RAMPS)

**File:** `src/components/slots/LidarLayer.tsx`

| Mode | Cesium Style Logic | Legend |
|------|-------------------|--------|
| **Height** (existing, kept) | Blue→Red gradient by Z in local frame | Elevation |
| **Classification** (fixed) | Brown=2(ground), Green=3-5(veg), Gray=6(building), Blue=9(water), White=other | LAS classes |
| **HeightAboveGround** (new) | Brown(0m)→Yellow(1m)→Green(3m)→Red(>5m) gradient from `\${HeightAboveGround}` | Canopy layers |
| **Canopy vs Cover** (new) | Dark green = `ReturnNumber==1 && HeightAboveGround>3` (canopy top), Light green = `ReturnNumber>1 && HeightAboveGround<1` (understory cover), Brown = ground | Structure |
| **Vertical Density** (new) | Blue(0-25pct)→Green(25-50)→Yellow(50-75)→Red(75-100). Uses `\${HeightAboveGround}` normalized per-cell. Built-in Cesium point cloud shader limitation: true percentile needs tile-level stats. For v1, use a simpler approximation: `HeightAboveGround / 10` clamped. | Density proxy |
| **RGB** (existing, kept) | True color from `\${COLOR}` | Photo |

### 2.2 Inline Legend

**File:** `src/components/slots/LidarLayerControl.tsx`

Below the color-mode pills in the active layer section, add a compact legend bar (2-3 color swatches with labels). Renders dynamically based on the active color mode. CSS: `flex gap-2 text-[10px]`.

### 2.3 Upload Dialog: Classification Question

**File:** `src/components/slots/LidarLayerControl.tsx`

When user drags/drops or selects a .LAZ, show a quick modal with 2 radio options + 1 checkbox:

1. "Ya viene clasificado (PNOA, DJI Terra, Pix4D...)" — default
2. "Solo tiene coordenadas X,Y,Z" — pipeline auto-classifies
3. "No lo sé" — pipeline detects and auto-classifies if needed

Plus optional checkbox: "Tiene color RGB" (checked by default).

Append these as form fields in the upload FormData: `classification_mode: native|auto|detect`, `has_rgb: true|false`.

**Backend:** `POST /api/lidar/upload` already accepts `config` as JSON string. Add these fields to the config dict that gets passed through to `LidarPipeline.process()`.

---

## 3. Data Flow (per upload)

```
1. User uploads LAZ → classification_mode + has_rgb in config
2. API stores file in MinIO lidar-source-tiles
3. Worker downloads file → Phase A:
   a. Read LAS header → detect if Classification exists
   b. If mode=auto or (mode=detect && no classification) → PDAL filters.smrf
   c. PDAL filters.hag → HeightAboveGround
   d. Crop+denoise (existing)
4. Phase D: py3dtiles convert --extra-fields Classification ReturnNumber NumberOfReturns HeightAboveGround
5. Tileset uploaded to MinIO with all 4 extra dimensions
6. Frontend loads tileset → Cesium3DTileStyle reads \${Classification}, \${HeightAboveGround}, etc.
```

---

## 4. Verification

- [ ] PNOA download: Classification mode shows brown/green/gray points
- [ ] Drone upload (classified): same
- [ ] Drone upload (unclassified): auto-classified, HeightAboveGround computed
- [ ] HeightAboveGround mode: gradient shows canopy structure (low=cover, high=treetops)
- [ ] Canopy vs Cover mode: distinct colors for treetop vs understory
- [ ] Legend updates when switching color modes
- [ ] Upload modal asks classification question, respects the choice
- [ ] 6 locales have new keys (uploadClassification, classificationNative, classificationAuto, classificationDetect, hasRgb, legend)

---

## 5. Inter-Module Data Contract

LiDAR layers are Orion-LD `DigitalAsset` entities. Any module (hydrology, vegetation, risks, intelligence…) can discover and consume them via standard NGSI-LD queries.

### 5.1 Discovery

```http
GET /ngsi-ld/v1/entities?type=DigitalAsset&q=assetCategory=="LiDAR"&refAgriParcel=="urn:ngsi-ld:AgriParcel:<id>"
```

Response is an array of NGSI-LD entities with these attributes:

| Attribute | Type | Description | Use Case |
|-----------|------|-------------|----------|
| `resourceURL` | Property (string) | URL to tileset.json (3D Tiles, Cesium-compatible) | 3D visualization |
| `source` | Property (string) | `"PNOA"` or `"user_upload"` | Data quality assessment |
| `pointCount` | Property (integer) | Number of points | Performance estimation |
| `dateObserved` | Property (ISO 8601) | Flight date | Temporal comparison |
| `processingStatus` | Property (string) | `"completed"` when ready | Readiness check |
| `refAgriParcel` | Relationship | Link to AgriParcel entity | Spatial context |

### 5.2 Raw Point Cloud Access (for hydrology, DTM, analysis)

For modules that need raw XYZ data (not just visualization tiles), the LiDAR module will expose:

```http
GET /api/lidar/export/{layer_id}/dtm?resolution=1.0       # DTM GeoTIFF (ground points only)
GET /api/lidar/export/{layer_id}/dsm?resolution=1.0       # DSM GeoTIFF (first returns)
GET /api/lidar/export/{layer_id}/chm?resolution=1.0       # CHM GeoTIFF (DSM - DTM)
GET /api/lidar/export/{layer_id}/points?class=2           # Raw points as LAZ (filtered by LAS class)
GET /api/lidar/export/{layer_id}/contours?interval=1.0    # Contour lines as GeoJSON
```

These endpoints are **read-only** and generate the output on-demand from the cached source LAZ in MinIO. They are scoped to the tenant via `X-Tenant-ID` header.

### 5.3 Agent Instructions for Cross-Module Integration

When building a module that consumes LiDAR data, an agent should:

1. **Query Orion-LD for available layers:**
   ```python
   client = get_orion_client(tenant_id)
   layers = client.list_assets(parcel_id=parcel_id)
   # Filter by assetCategory == "LiDAR" and processingStatus == "completed"
   ```

2. **For 3D visualization:** pass `resourceURL` directly to Cesium `Cesium3DTileset.fromUrl()`.

3. **For analysis/raster data:** call the `/api/lidar/export/` endpoints. The `source` attribute tells you if data is public PNOA (higher point density, pre-classified) or user drone (varies).

4. **Tenant isolation:** always include `NGSILD-Tenant` or `X-Tenant-ID` header. Orion-LD returns only the tenant's own entities.

5. **Error handling:** DigitalAsset may have `processingStatus: "failed"` — skip those. Check `pointCount` to estimate processing cost before requesting export.

---

## 6. Out of Scope (v2)

- True per-cell vertical density percentiles (needs tile-level compute in py3dtiles or a post-processing pass)
- Temporal comparison (two-layer diff)
- Slope/aspect/hillshade from DTM
- Crown polygon export (already partially implemented in Phase C, not wired to UI)
- Export endpoints (defined above as contract, implementation deferred to hydrology module integration)
