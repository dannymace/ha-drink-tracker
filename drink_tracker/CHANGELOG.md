# Changelog

## 0.1.2

- Switch the add-on container to an explicit `run.sh` command so Home Assistant no longer falls back to `/init`.

## 0.1.1

- Fix Home Assistant container startup by disabling Docker init for the base image.
- Avoid crashing startup when PostgreSQL host auto-discovery is unavailable.

## 0.1.0

- Initial drink tracking add-on release.
