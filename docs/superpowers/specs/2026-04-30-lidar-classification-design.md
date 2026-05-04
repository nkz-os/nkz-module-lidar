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


## 5. Inter-Module Data Contract (IMPLEMENTED — verified 2026-05-04)

LiDAR layers are Orion-LD `DigitalAsset` entities. Any module (Vegetation, Risks, Cadastral, Robotics, BioOrchestrator, GIS-Routing, EU-Elevation...) can discover and consume them via standard NGSI-LD queries.

### 5.1 Discovery

```http
GET /ngsi-ld/v1/entities?type=DigitalAsset&q=assetCategory=="LiDAR"&refAgriParcel=="urn:ngsi-ld:AgriParcel:<id>"
```

The response is an array of NGSI-LD entities with these attributes:

| Attribute | Type | Description | Use Case |
|-----------|------|-------------|----------|
| `resourceURL` | Property (string) | URL to tileset.json (3D Tiles, Cesium-compatible) | 3D visualization |
| `dtmUrl` | Property (string) | GeoTIFF — Digital Terrain Model (bare-earth elevation) | Hydrology, slope, path planning |
| `dsmUrl` | Property (string) | GeoTIFF — Digital Surface Model (canopy+buildings) | Roughness, line-of-sight |
| `chmUrl` | Property (string) | GeoTIFF — Canopy Height Model (DSM minus DTM) | Biomass, vigor, vegetation analysis |
| `classifiedLazUrl` | Property (string) | LAZ — classified+cropped point cloud | Custom PDAL pipelines, structural analysis |
| `source` | Property (string) | `"PNOA"` or `"user_upload"` | Data quality assessment |
| `pointCount` | Property (integer) | Number of points in the layer | Performance estimation |
| `treeCount` | Property (integer) | Number of detected trees (0 if tree detection off) | Inventory |
| `dateObserved` | Property (ISO 8601) | Flight/acquisition date | Temporal comparison |
| `processingStatus` | Property (string) | `"completed"` when ready | Readiness gate |
| `refAgriParcel` | Relationship | Link to AgriParcel entity | Spatial context |

### 5.2 Download / Export API

Derived products (DTM, DSM, CHM, classified LAZ) are generated during
ingestion and persisted in MinIO alongside the 3D Tiles tileset. They
are available as soon as `processingStatus == "completed"` — no
reprocessing needed.

```http
GET /api/lidar/export/{layer_id}/dtm     → GeoTIFF  (0.5 m, IDW from class 2 ground points)
GET /api/lidar/export/{layer_id}/dsm     → GeoTIFF  (0.5 m, max-return surface)
GET /api/lidar/export/{layer_id}/chm     → GeoTIFF  (0.5 m, DSM minus DTM = canopy height)
GET /api/lidar/export/{layer_id}/points  → LAZ      (classified, cropped to parcel boundary)
```

- **Auth:** cookie-based session (`credentials: 'include'`) via `nkz_token`
- **CORS:** allowed from `nekazari.robotika.cloud`
- **Cache:** `Cache-Control: public, max-age=86400`
- **`{layer_id}`**: the UUID portion of the DigitalAsset id (after `urn:ngsi-ld:DigitalAsset:`). This is the same value the frontend uses as `selectedLayerId`.

**Error codes:**
- `404` — layer not found, processing not complete, or product unavailable (layers from before 2026-05-04 lack derived products)
- `403` — tenant does not own the layer
- `400` — unknown product key (valid: `dtm`, `dsm`, `chm`, `points`)

### 5.3 Complete Integration Example — Vegetation Module

This is the canonical pattern for consuming LiDAR data from another module:

```python
import httpx


def _prop(entity: dict, key: str, default=None):
    """Extract an NGSI-LD Property value."""
    v = entity.get(key, {})
    return v.get("value", default) if isinstance(v, dict) else default


async def get_lidar_chm(tenant_id: str, parcel_id: str) -> bytes | None:
    """Return the CHM GeoTIFF for the most recent LiDAR layer on a parcel."""
    base = "https://nkz.robotika.cloud"
    async with httpx.AsyncClient() as client:
        # 1. Discover layers via Orion-LD
        q = f'assetCategory=="LiDAR";refAgriParcel=="urn:ngsi-ld:AgriParcel:{parcel_id}"'
        resp = await client.get(
            f"{base}/ngsi-ld/v1/entities",
            params={"type": "DigitalAsset", "q": q, "limit": 10},
            headers={"Accept": "application/ld+json"},
        )
        resp.raise_for_status()
        layers = resp.json()

        # 2. Filter to completed layers only
        completed = [
            e for e in layers
            if _prop(e, "processingStatus") == "completed"
        ]
        if not completed:
            return None

        # 3. Pick the most recent
        completed.sort(key=lambda e: _prop(e, "dateObserved", ""), reverse=True)
        layer_id = completed[0]["id"].split(":")[-1]

        # 4. Fetch the CHM
        chm_resp = await client.get(
            f"{base}/api/lidar/export/{layer_id}/chm",
        )
        chm_resp.raise_for_status()
        return chm_resp.content  # GeoTIFF bytes — open with rasterio
```

### 5.4 Discoverability from a module frontend (JavaScript/TypeScript)

```typescript
// Query Orion-LD for LiDAR layers on the currently-selected parcel
const { data: assets } = await apiGateway.get('/ngsi-ld/v1/entities', {
  params: {
    type: 'DigitalAsset',
    q: `assetCategory=="LiDAR";refAgriParcel=="${selectedEntityId}"`,
    limit: 10,
  },
  headers: { Accept: 'application/ld+json' },
});

// Each asset contains download URLs directly:
for (const asset of assets) {
  console.log(asset.resourceURL?.value);        // 3D Tiles for Cesium
  console.log(asset.chmUrl?.value);             // CHM GeoTIFF
  console.log(asset.classifiedLazUrl?.value);   // Classified point cloud
}
```

### 5.5 Agent Instructions

When building a module that consumes LiDAR data:

1. **Query Orion-LD for available layers** — see example in §5.3.
2. **For 3D visualization** — pass `resourceURL` directly to
   `Cesium.Cesium3DTileset.fromUrl()`.
3. **For analysis** — use `dtmUrl`/`dsmUrl`/`chmUrl`/`classifiedLazUrl`
   directly. They point to MinIO via the public-read bucket. No further
   API call is needed beyond the initial Orion query.
4. **Tenant isolation** — always include `NGSILD-Tenant` header on Orion
   requests. Export endpoints use cookie auth.
5. **Error handling** — skip layers with `processingStatus != "completed"`.
   The `dtmUrl` and similar attributes may be absent on layers created
   before 2026-05-04.

---

## 6. Out of Scope / Pending

- **Contour lines** — `GET /export/{id}/contours` not yet implemented.
- **Per-class point filtering** — the export endpoint returns the full
  classified LAZ; the caller filters client-side.
- **On-the-fly resolution control** — DTM/DSM/CHM are generated at 0.5 m
  resolution during ingestion. A `?resolution=` query param may be added
  if needed.
- **Multi-layer temporal diff** — two DigitalAssets for the same parcel
  can already be retrieved; a dedicated differencing endpoint is deferred.
- **HeightAboveGround / CanopyCover / VerticalDensity viewer modes** —
  blocked on py3dtiles upgrade for `--extra-fields` support.
- **Upload classification modal** (native vs auto vs detect) — spec §2.3,
  not yet wired to UI.
- **Inline legend** in LidarLayerControl — spec §2.2, pending frontend work.
- **True per-cell vertical density percentiles** — needs tile-level stats.
