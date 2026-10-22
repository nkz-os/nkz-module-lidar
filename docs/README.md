# Documentation

This directory contains additional documentation and guides for developing Nekazari modules.

## Quick Reference

- **[Quick Reference Guide](./QUICK_REFERENCE.md)** - Common code snippets and quick lookup
  - SDK usage examples
  - UI component examples
  - API endpoints
  - Manifest.json structure

## Testing

- **[Testing Guide](./TESTING_GUIDE.md)** - How to test your module locally
  - Orion-LD first workflow (no SQL runtime state)
  - API + worker validation flow
  - Test commands for backend and frontend
  - Migration script usage

## Architecture Notes (2026 refactor)

- Runtime state (`jobs`, `layers`) is persisted in Orion-LD only.
- PostgreSQL runtime writes were removed from API/worker flow.
- Coverage lookup is loaded from a read-only GeoJSON catalog (`COVERAGE_INDEX_GEOJSON_PATH`).
- Tiles are stored in MinIO and referenced in Orion-LD DigitalAsset entities.

## External Resources

For complete documentation, see:

- **[External Developer Guide](https://github.com/nkz-os/nekazari-public/blob/main/docs/development/EXTERNAL_DEVELOPER_GUIDE.md)** - Complete guide with all details
- **[API Integration Guide](https://github.com/nkz-os/nekazari-public/blob/main/docs/api/README.md)** - API endpoints and data models
- **[SDK NPM Package](https://www.npmjs.com/package/@nekazari/sdk)** - SDK package documentation
- **[UI-Kit NPM Package](https://www.npmjs.com/package/@nekazari/ui-kit)** - UI components documentation

## Support

- **Email**: developers@nekazari.com
- **Issues**: Report via GitHub (if applicable)


















