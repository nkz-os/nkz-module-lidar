# Release Checklist — LiDAR SOTA

## Release metadata

- Release owner:
- Date:
- Target tag:
- Commit SHA:

## Pre-release checks

- [ ] Frontend parser runs in Web Worker (no main-thread parsing).
- [ ] Upload is blocked when composite CRS is missing.
- [ ] Backend re-validates CRS independently from client metadata.
- [ ] Dynamic PDAL pipeline resolves input CRS and outputs `EPSG:4978`.
- [ ] BBox geodesy heuristic is enabled with configured buffer.
- [ ] `PROJ_NETWORK=ON` is enabled in worker environment.
- [ ] `PROJ_USER_WRITABLE_DIRECTORY` points to persistent volume.
- [ ] Positive corpus tests (ES, UK, FR, DE) pass.
- [ ] Negative destructive tests pass:
  - [ ] Missing VLR metadata case rejected.
  - [ ] Malicious wrong EPSG case rejected by heuristic.
  - [ ] Legacy vertical datum case handled by transformation pipeline.
- [ ] Security checks pass (CORS allowlist, JWT, tenant validation).

## Deployment checks

- [ ] Immutable GHCR image is published.
- [ ] Manifest pins immutable tag in both `lidar-api` and `lidar-worker`.
- [ ] Changes are committed and pushed to `main`.
- [ ] ArgoCD app `lidar` is `Synced`.
- [ ] ArgoCD app `lidar` is `Healthy`.
- [ ] Kubernetes rollout for `lidar-api` is complete.
- [ ] Kubernetes rollout for `lidar-worker` is complete.

## Post-deploy validation

- [ ] API smoke flow passes (`process -> status -> completed`).
- [ ] Tileset URL is reachable through module API endpoint.
- [ ] Cesium layer renders correctly.
- [ ] 24h observation period started with dashboards/alerts enabled.

## Sign-off

- [ ] Technical sign-off
- [ ] Operations sign-off
- [ ] Product sign-off

