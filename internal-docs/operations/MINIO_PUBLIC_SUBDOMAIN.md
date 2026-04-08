---
title: MinIO public S3 subdomain (LiDAR tiles)
description: Secure rollout of minio.robotika.cloud for browser tile delivery, TLS, and strict bucket CORS.
---

# MinIO public S3 API — `minio.robotika.cloud`

This document describes the **secure** pattern for serving LiDAR 3D Tiles directly from MinIO over HTTPS.

## Design principles

1. **S3 API only on the public hostname** — MinIO **Console** (port 9001) must remain off the public Ingress. Use `kubectl port-forward` or a separate, authenticated route for admin.
2. **No wildcard CORS** — Bucket CORS allowlists **only** origins configured in `CORS_ORIGINS` (same list as the LiDAR FastAPI app). The worker/API applies this via `put_bucket_cors` on startup (`StorageService._sync_bucket_cors`).
3. **Separate TLS secret** — Certificate `Certificate/minio-tls` + secret `minio-tls` for `minio.robotika.cloud`.
4. **Public read only for tile objects** — Bucket policy remains `s3:GetObject` for `lidar-tilesets/*` (anonymous read for tiles). **Do not** enable anonymous `PUT/DELETE`.

## Platform manifests (core repo `nkz/`)

| File | Purpose |
|------|---------|
| `k8s/core/networking/certificate-minio.yaml` | cert-manager certificate for `minio.robotika.cloud` |
| `k8s/core/networking/minio-public-ingress.yaml` | Traefik ingress → `minio-service:9000` only |
| `k8s/core/networking/ingress-http-redirect.yaml` | HTTP→HTTPS redirect for `minio.robotika.cloud` |
| `k8s/core/infrastructure/minio-deployment.yaml` | `MINIO_SERVER_URL=https://minio.robotika.cloud` |

## Rollout checklist

1. **DNS** — Create `A`/`AAAA` record for `minio.robotika.cloud` pointing to the cluster ingress IP(s).
2. **Apply TLS** — `kubectl apply -f k8s/core/networking/certificate-minio.yaml` (namespace `nekazari`).
3. **Wait** — Until `minio-tls` secret exists and is populated.
4. **Apply ingress** — `kubectl apply -f k8s/core/networking/minio-public-ingress.yaml` and updated `ingress-http-redirect.yaml`.
5. **Restart MinIO** (if `MINIO_SERVER_URL` was added/changed) — rollout `deployment/minio`.
6. **LiDAR backend** — Ensure `MINIO_PUBLIC_BASE_URL=https://minio.robotika.cloud` and `CORS_ORIGINS` lists **exact** browser origins (e.g. `https://nekazari.robotika.cloud`). Redeploy LiDAR API/worker so `_sync_bucket_cors` runs.
7. **Verify** — From browser devtools, load a tile URL; response must include `Access-Control-Allow-Origin: https://nekazari.robotika.cloud` (not `*`).

## Manual CORS override (break-glass)

If you must set CORS without redeploying the LiDAR service:

```bash
mc alias set prod https://minio.robotika.cloud "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD"
# Use a JSON file with AllowedOrigin matching only trusted hosts (never "*").
mc cors set prod/lidar-tilesets ./cors-strict.json
```

## Security notes

- Re-check **bucket policy** after MinIO upgrades.
- **Do not** expose `root` credentials to the browser; tiles rely on **anonymous GetObject** only for `lidar-tilesets`.
- Prefer **immutable** LiDAR image tags in production; pin manifests after validation.
