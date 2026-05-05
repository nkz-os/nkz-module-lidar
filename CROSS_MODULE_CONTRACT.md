# LiDAR Module — Cross-Module Data Contract

**Version:** 1.0 (2026-05-04)
**Status:** Implemented and verified in production

Any Nekazari module can discover and consume LiDAR point cloud data without
depending on the LiDAR module's internal code. The contract has two layers:
**discovery** via the Orion-LD Context Broker and **download** via HTTP export
endpoints.

---

## 1. Discovery — Query Orion-LD

LiDAR layers are NGSI-LD `DigitalAsset` entities. Query them by parcel:

```http
GET /ngsi-ld/v1/entities?type=DigitalAsset&q=assetCategory=="LiDAR"&refAgriParcel=="urn:ngsi-ld:AgriParcel:<id>"
```

### Entity attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `resourceURL` | Property (string) | 3D Tiles tileset.json — Cesium `Cesium3DTileset.fromUrl()` |
| `dtmUrl` | Property (string) | GeoTIFF — Digital Terrain Model (bare-earth, 0.5 m) |
| `dsmUrl` | Property (string) | GeoTIFF — Digital Surface Model (canopy + structures) |
| `chmUrl` | Property (string) | GeoTIFF — Canopy Height Model (DSM − DTM) |
| `classifiedLazUrl` | Property (string) | LAZ — classified point cloud, cropped to parcel |
| `source` | Property (string) | `"PNOA"` (national coverage) or `"user_upload"` (drone) |
| `pointCount` | Property (integer) | Total points in the layer |
| `treeCount` | Property (integer) | Detected trees (0 if detection was off) |
| `dateObserved` | Property (ISO 8601) | Acquisition/flight date |
| `processingStatus` | Property (string) | `"completed"` when ready to consume |
| `refAgriParcel` | Relationship | Link to the AgriParcel entity |

Attributes with URLs (dtmUrl, dsmUrl, chmUrl, classifiedLazUrl) are
absent on layers created before 2026-05-04 — fall back gracefully.

---

## 2. Download — Export endpoints

Products are generated during ingestion and stored in MinIO. No on-demand
reprocessing is needed once `processingStatus == "completed"`.

```
GET /api/lidar/export/{layer_id}/dtm     → GeoTIFF  (bare-earth, IDW from ground class)
GET /api/lidar/export/{layer_id}/dsm     → GeoTIFF  (max-return surface)
GET /api/lidar/export/{layer_id}/chm     → GeoTIFF  (DSM − DTM = canopy height)
GET /api/lidar/export/{layer_id}/points  → LAZ      (classified, parcel-cropped)
```

- `{layer_id}` is the UUID portion of the entity id (after `urn:ngsi-ld:DigitalAsset:`)
- **Auth:** cookie session (`credentials: 'include'`), same as the host
- **Errors:** 404 (not found/not ready), 403 (wrong tenant), 400 (bad product key)

---

## 3. Integration Example (Python)

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
        # 1. Discover
        q = f'assetCategory=="LiDAR";refAgriParcel=="urn:ngsi-ld:AgriParcel:{parcel_id}"'
        resp = await client.get(
            f"{base}/ngsi-ld/v1/entities",
            params={"type": "DigitalAsset", "q": q, "limit": 10},
            headers={"Accept": "application/ld+json"},
        )
        resp.raise_for_status()
        layers = resp.json()

        # 2. Pick best completed layer
        completed = [
            e for e in layers
            if _prop(e, "processingStatus") == "completed"
        ]
        if not completed:
            return None
        completed.sort(key=lambda e: _prop(e, "dateObserved", ""), reverse=True)

        # 3. Download
        layer_id = completed[0]["id"].split(":")[-1]
        chm = await client.get(f"{base}/api/lidar/export/{layer_id}/chm")
        chm.raise_for_status()
        return chm.content  # GeoTIFF bytes — open with rasterio or GDAL
```

---

## 4. Integration Example (TypeScript)

```typescript
const { data: assets } = await apiGateway.get('/ngsi-ld/v1/entities', {
  params: {
    type: 'DigitalAsset',
    q: `assetCategory=="LiDAR";refAgriParcel=="${selectedEntityId}"`,
    limit: 10,
  },
  headers: { Accept: 'application/ld+json' },
});

for (const asset of assets) {
  if (asset.processingStatus?.value !== 'completed') continue;
  // asset.chmUrl.value    → download URL for CHM GeoTIFF
  // asset.dtmUrl.value    → download URL for DTM GeoTIFF
  // asset.resourceURL.value → Cesium 3D Tiles tileset
}
```

---

## 5. Available Products

| Product | Format | Source | Typical size (100k pts, 2 ha) | Use cases |
|---------|--------|--------|------|-----------|
| **DTM** | GeoTIFF, 0.5 m | Ground points (class 2), IDW interpolation | ~200 KB | Hydrology, slope stability, path planning |
| **DSM** | GeoTIFF, 0.5 m | Maximum-return surface | ~200 KB | Visibility, roughness, building detection |
| **CHM** | GeoTIFF, 0.5 m | DSM − DTM | ~200 KB | Biomass, canopy vigor, tree height |
| **Points** | LAZ (laszip) | Classified+cropped point cloud | ~1 MB | Custom PDAL pipelines, structural analysis |
| **3D Tiles** | tileset.json + .pnts | py3dtiles conversion | ~0.5 MB | CesiumJS visualization, fly-throughs |
