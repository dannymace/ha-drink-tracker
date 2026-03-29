# Changelog

## 0.1.15

- Accept more BlueBubbles webhook payload variants for inbound replies, including nested message bodies and alternate message event names.
- Log compact ignore/store reasons for inbound BlueBubbles webhooks so reply failures can be diagnosed from add-on logs.

## 0.1.14

- Reformat the confirmation and weekly summary texts so the labels, arrows, and drink/target values line up in cleaner fixed-width columns.

## 0.1.13

- Fix `Send Weekly Summary` hanging by rendering the summary from the current transaction instead of opening a second database session that blocks on `weekly_goals`.
- Show an explicit dashboard notice after `Send Weekly Summary` succeeds.

## 0.1.12

- Show an explicit dashboard notice after `Send Daily Prompt` when the prompt is sent, still waiting for a reply, or already tracked for that day.

## 0.1.11

- Stop failing inbound BlueBubbles reply webhooks when confirmation delivery by `chatGuid` returns `400`, and fall back to the configured recipient address instead.

## 0.1.10

- Fix Home Assistant ingress form actions and redirects so dashboard buttons like `Send Daily Prompt` and `Send Weekly Summary` no longer 404.

## 0.1.9

- Normalize Home Assistant add-on slugs like `db21ed7f_postgres_latest` into the actual DNS hostname form `db21ed7f-postgres-latest`.

## 0.1.8

- Keep the add-on running when PostgreSQL connection setup fails and show a clearer error message for invalid Home Assistant hostnames like `homeassistant.local`.

## 0.1.7

- Normalize PostgreSQL host values that already contain a port so inputs like `host:5432` or `host:5432:5432` no longer crash SQLAlchemy URL parsing.

## 0.1.6

- Persist password-style add-on options in `/data/persisted_secrets.json` and reuse them on restart when Home Assistant provides blank secret fields.

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
