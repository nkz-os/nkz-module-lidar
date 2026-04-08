# Runbook — LiDAR SOTA Production Release

## Scope

This runbook defines the mandatory release flow for geodesy-safe LiDAR processing in production.
It is designed for deterministic GitOps deployments with immutable GHCR image tags.

## Preconditions

- Repository branch is clean and all required changes are merged in a release branch.
- Backend image is built and published to GHCR with an immutable tag.
- Kubernetes manifests pin the immutable backend image tag in:
  - `k8s/backend-deployment.yaml` (`lidar-api`)
  - `k8s/backend-deployment.yaml` (`lidar-worker`)
- ArgoCD app `lidar` exists and is auto-sync enabled.

## Mandatory Go/No-Go Gates

All gates must pass before production rollout:

1. Functional gate
   - Positive corpus passes (ES, UK, FR, DE).
   - End-to-end workflow succeeds (`process -> status -> tileset load in Cesium`).
2. Geodesy gate
   - CRS validation rejects invalid/missing composite CRS.
   - Dynamic reprojection to `EPSG:4978` confirmed in worker logs.
3. Performance gate
   - p95/p99 pipeline latency within agreed SLO for staging load profile.
4. Infrastructure gate
   - `PROJ_NETWORK=ON` enabled.
   - `PROJ_USER_WRITABLE_DIRECTORY` mounted to persistent storage.
5. Security gate
   - CORS origin allowlist active (no wildcard policy).
   - JWT/tenant headers validated in protected endpoints.

## Release Procedure

1. Build and push immutable image
   - Example tag: `2026-04-08-geodesy-sota-r1`
   - Push image:
     - `ghcr.io/nkz-os/nkz-module-lidar/lidar-backend:<immutable_tag>`

2. Pin immutable tag in manifests
   - Update `k8s/backend-deployment.yaml` image references for both deployments.

3. Commit and push
   - Commit message must mention immutable tag and release objective.
   - Push to `main`.

4. Verify ArgoCD reconciliation
   - Confirm `lidar` app is `Synced/Healthy`.
   - Confirm deployment images match pinned immutable tag.

5. Rollout verification
   - Check rollout status for `lidar-api` and `lidar-worker`.
   - Execute smoke API checks and load layer in Cesium.

6. Post-release observation window (24h)
   - Monitor geodesy errors, queue failures, and tileset streaming latency.
   - Track anomalies and file incidents if thresholds are exceeded.

## Evidence to attach to release

- GHCR image tag and digest.
- Commit SHA containing pinned manifest.
- ArgoCD status output (`Synced/Healthy`).
- Kubernetes deployment image output.
- Smoke test output and one successful job record.

