# LIDAR Module - Nekazari Platform

LIDAR Point Cloud Viewer module for the Nekazari Platform. This module enables visualization of LIDAR point cloud data (LAZ files) from IDENA (Infraestructura de Datos Espaciales de Navarra) in the unified CesiumJS viewer.

## Features

- Download LAZ files from IDENA for selected parcels
- Automatic conversion to 3D Tiles format for CesiumJS
- Interactive point cloud visualization in the unified viewer
- Integration with unified viewer slots (layer-toggle, map-layer, context-panel)

## Architecture

### Backend
- FastAPI service for LIDAR data download and conversion
- REST API endpoints for layer management
- Integration with IDENA data sources

### Frontend
- React application compiled as a single-file IIFE bundle (runtime script injection)
- Integration with unified viewer via slots
- CesiumJS 3D Tiles visualization

## Development

### Prerequisites
- Node.js 20+
- Python 3.11+
- Docker (for containerized deployment)

### Local Development

#### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### Frontend
```bash
npm install
npm run dev  # Starts on port 5004
```

## Deployment

### Build Frontend IIFE Bundle

The Nekazari host loads modules at runtime by injecting a `<script>` tag that points to a single-file IIFE bundle.

```bash
# Frontend (IIFE bundle)
npm install
npm run build
# outputs: dist/nkz-module.js
```

### Backend Docker Image

Build context matters: the backend Dockerfile expects files from `backend/` (e.g. `environment.yml`), so use `./backend` as context.

```bash
# Backend (context = ./backend)
docker build -f backend/Dockerfile -t ghcr.io/k8-benetis/nkz-module-lidar/lidar-backend:latest ./backend
docker push ghcr.io/k8-benetis/nkz-module-lidar/lidar-backend:latest
sudo kubectl rollout restart deployment/lidar-api deployment/lidar-worker -n nekazari
sudo kubectl rollout status deployment/lidar-api deployment/lidar-worker -n nekazari
```

### Frontend Deployment (Production)

Upload the IIFE bundle to MinIO so it becomes available at:

- `/modules/lidar/nkz-module.js`

This must match `marketplace_modules.remote_entry_url` (see `k8s/registration.sql`).

### Kubernetes Deployment (backend only)

```bash
# Apply backend deployments (use -n nekazari if not default)
kubectl apply -f k8s/backend-deployment.yaml -n nekazari

# Register module in platform database
psql -h <db-host> -U <user> -d nekazari -f k8s/registration.sql
```

### Deploy to production (GitOps, manual)

From your machine: commit and push. On the server:

```bash
ssh g@<production-server>
cd ~/nkz-module-lidar
git pull origin main

# Build and push images (requires Docker login to GHCR)
docker build -f backend/Dockerfile -t ghcr.io/k8-benetis/nkz-module-lidar/lidar-backend:latest ./backend
docker push ghcr.io/k8-benetis/nkz-module-lidar/lidar-backend:latest

docker build -f frontend/Dockerfile -t ghcr.io/k8-benetis/nkz-module-lidar/lidar-frontend:latest .
docker push ghcr.io/k8-benetis/nkz-module-lidar/lidar-frontend:latest

# Rollout so pods use the new images (imagePullPolicy: Always)
sudo kubectl rollout restart deployment/lidar-frontend deployment/lidar-api deployment/lidar-worker -n nekazari
sudo kubectl rollout status deployment/lidar-frontend deployment/lidar-api deployment/lidar-worker -n nekazari
```

## Module Integration

This module integrates with the Nekazari Platform through:

1. **Runtime Script Injection (IIFE)**: the host injects `/modules/lidar/nkz-module.js`
2. **Slot System**: provides widgets for:
   - `layer-toggle`: Layer control widget
   - `map-layer`: CesiumJS 3D Tiles layer
   - `context-panel`: Configuration panel

## API Endpoints

- `GET /api/lidar/layers` - List available LIDAR layers
- `POST /api/lidar/layers` - Create new LIDAR layer (download and convert)
- `GET /api/lidar/layers/{layer_id}` - Get layer details
- `DELETE /api/lidar/layers/{layer_id}` - Delete layer

## Notes

- LAZ to 3D Tiles conversion requires additional tooling (PDAL, 3d-tiles-tools, etc.)
- IDENA data access may require authentication/API keys
- Large point clouds may require significant storage and processing resources

## License

Apache-2.0
