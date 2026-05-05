# Changelog

## [1.2.0] - 2026-05-04

### Fixed (post-audit remediation)
- Phase D: revert py3dtiles Python API → CLI subprocess; the Python `convert()`
  API hung indefinitely (master at 100% CPU, ZMQ workers idle, zero tiles
  emitted) while the CLI binary completed in <1 min on the same input.
- Memory: cap `py3dtiles convert` with `--jobs 4 --cache_size 256` to respect
  the 2 GiB pod limit; without caps py3dtiles uses `os.cpu_count()` and
  `host_total_mem/10` (12 workers, 3.2 GiB cache on this host) → OOMKilled.
- Worker name: include pod hostname + uuid suffix to avoid
  `ValueError("There exists an active worker named ... already")` on container
  restart; the old name was a constant which collided with the not-yet-expired
  Redis registration of the dying container.
- Bounding volumes: `_read_pnts_xyz_range` now detects `POSITION_QUANTIZED`
  (uint16, 6 bytes/point) vs `POSITION` (float32, 12 bytes/point) from the
  Feature Table JSON; py3dtiles 7.x emits quantized .pnts by default.
- NDVI gate: Phase B spectral fusion now triggers on `colorize_by == "ndvi"`
  instead of `"rgb"`.
- Cesium styles: `COLOR_RAMPS` rewritten to the valid Cesium 3D Tiles Styling
  subset (`color()`, `mix()`, ternary, `conditions[]`); previous GLSL-style
  code (`vec4`, `var`, `if`) was silently rejected by `Cesium3DTileStyle`.
- Build: remove dangling `import './index.css'` in App.tsx (the file was
  deleted in the design-system v1 migration).

### Removed
- Phase A HAG computation (`filters.hag_nn`); py3dtiles 7.0.0 has no
  `--extra-fields` flag, so HeightAboveGround was discarded during conversion.
  Will be reinstated when py3dtiles is upgraded.

### Operations
- `PY3DTILES_TIMEOUT` (25 min) is now strictly less than `WORKER_TIMEOUT`
  (30 min) so a stuck subprocess fails cleanly instead of being RQ-killed.
- Worker reconciliation now plays back 21+ previously-failed jobs from the
  queue and syncs their Orion entities to `failed`.

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
