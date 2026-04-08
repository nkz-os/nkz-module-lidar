## Release Intent

- [ ] Standard change
- [ ] Production release
- [ ] Rollback

## Summary

Describe why this change exists and what risk it addresses.

## Immutable Image Evidence

- Backend image tag:
- Backend image digest:
- Manifest path pinned:

## Mandatory Evidence Checklist

- [ ] Go/No-Go gates passed (attach checklist).
- [ ] Positive corpus passed (ES, UK, FR, DE).
- [ ] Negative destructive tests passed (missing VLR, wrong EPSG, legacy vertical datum).
- [ ] ArgoCD `lidar` reached `Synced/Healthy`.
- [ ] `lidar-api` and `lidar-worker` run pinned immutable image.
- [ ] Smoke flow passed (`process -> status -> completed`).

## Risk and Rollback

- Risk level: Low / Medium / High
- Rollback tag:
- Rollback plan validated:

