# Changelog

## 0.1.5

- Disable Docker's default init for the add-on so Home Assistant can hand control directly to the S6 `/init` process required by the base image.

## 0.1.4

- Replace the incomplete custom AppArmor profile with the Home Assistant S6/Bashio baseline and the add-on runtime paths.

## 0.1.3

- Allow the container entrypoint and run script in AppArmor so Home Assistant can execute the add-on process.

## 0.1.2

- Switch the add-on container to an explicit `run.sh` command so Home Assistant no longer falls back to `/init`.

## 0.1.1

- Fix Home Assistant container startup by disabling Docker init for the base image.
- Avoid crashing startup when PostgreSQL host auto-discovery is unavailable.

## 0.1.0

- Initial drink tracking add-on release.
