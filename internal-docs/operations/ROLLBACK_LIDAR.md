# Rollback Procedure — LiDAR Module

## Rollback trigger conditions

Trigger rollback immediately if one or more conditions are met:

- Geodesy validation failure rate exceeds agreed threshold.
- Pipeline failures exceed agreed threshold for 15+ minutes.
- Layer rendering failures are reproducible in Cesium after release.
- Worker pods enter crash loops related to projection/grid resolution.

## Required rollback inputs

- Last known stable immutable image tag.
- Commit SHA where stable tag is pinned in `k8s/backend-deployment.yaml`.

## Rollback steps

1. Re-pin stable immutable tag
   - Edit `k8s/backend-deployment.yaml` and set stable tag for:
     - `lidar-api`
     - `lidar-worker`

2. Commit and push rollback
   - Push rollback commit to `main`.

3. Verify ArgoCD reconciliation
   - Ensure `lidar` app becomes `Synced/Healthy`.

4. Verify deployed image versions
   - Confirm both deployments use the stable tag.

5. Validate service recovery
   - Run smoke flow (`process -> status`).
   - Confirm Cesium renders at least one known-good layer.

## Post-rollback actions

- Open incident with root-cause category:
  - geodesy
  - infra/proj-cache
  - conversion pipeline
  - serving/performance
- Freeze new releases until corrective actions and re-validation complete.

