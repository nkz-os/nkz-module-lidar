# Changelog

## [1.1.0] - 2026-04-29

### Security
- Rate limiting with Redis fallback (memory://) on all API endpoints
- /health endpoint exempt from rate limiting for K8s probes

### Added
- Job cancellation endpoint (POST /api/lidar/process/{id}/cancel)
- Prometheus metrics endpoint (/metrics)
- Tileset loading indicator in Cesium viewer
- Frontend AbortController support for polling cancellation
- Pipeline CRS and geobounds validation tests
- Coverage GeoJSON path validation at startup

### Changed
- Orion-LD client uses httpx.AsyncClient in API handlers (sync fallback for worker)
- Dead SQLAlchemy models removed (Orion-LD is sole state store)

### Fixed
- Complete i18n coverage: ca/fr/pt now have all 98 keys
- Spanish typo fixed ("s sentsor" → "sensor")

### Removed
- Deprecated lidar-frontend K8s deployment (IIFE only)
- Unused ngsildclient dependency

## [1.0.0] - December 2025

### Added
- SDK packages from NPM (`@nekazari/sdk`, `@nekazari/ui-kit`)
- Real SDK usage in App.tsx (no mocks)
- UI-Kit components (Button, Card) in example
- Full TypeScript support with published packages

### Changed
- Updated `package.json` to include published SDK packages
- Updated `src/App.tsx` to use real SDK imports instead of mocks
- Updated README with NPM package information

### Removed
- Mock implementations of SDK functions
- Type definition placeholders (now using real types from packages)
