# Drink Tracker

The Drink Tracker add-on sends a daily BlueBubbles message asking for yesterday's drink total, stores responses in PostgreSQL, and serves a dashboard for review and correction.

## Configuration

All settings are exposed in the Home Assistant add-on UI.

- `time_zone`: IANA time zone used for schedules and summaries.
- `recipient_address`: The BlueBubbles address to message, such as `dmace@icloud.com`.
- `bluebubbles.host`: BlueBubbles base URL.
- `bluebubbles.password`: BlueBubbles server password.
- `bluebubbles.ssl`: Whether to verify TLS for BlueBubbles requests.
- `bluebubbles.send_method`: BlueBubbles send method. Use `private-api` when available.
- `bluebubbles.webhook_secret`: Optional fixed webhook secret. If blank, one is generated on first start.
- `schedules.daily_prompt_time`: Daily prompt time in `HH:MM`.
- `schedules.weekly_summary_day`: Weekly summary day. Monday is recommended.
- `schedules.weekly_summary_time`: Weekly summary time in `HH:MM`.
- `schedules.reminder_delay_minutes`: Delay before the reminder is sent.
- `schedules.reminder_window_minutes`: Window after the reminder before a day is marked missed.
- `postgres.host`: Optional Postgres host override. Leave blank to try Supervisor auto-discovery.
- `postgres.port`: Postgres port.
- `postgres.database`: Postgres database name.
- `postgres.username`: Postgres user.
- `postgres.password`: Postgres password.
- `postgres.ssl_mode`: SQLAlchemy SSL mode.
- `dashboard.username`: Username for direct LAN dashboard access.
- `dashboard.password`: Password for direct LAN dashboard access.
- `targets`: Weekly and day-by-day goals.

## BlueBubbles Webhook

Configure BlueBubbles to send webhooks to:

`http://YOUR_HOME_ASSISTANT_HOST:8099/webhooks/bluebubbles/YOUR_SECRET`

The dashboard shows the resolved callback URL and current secret.

## Database Tables

- `daily_entries`
- `weekly_goals`
- `weekly_summaries`
- `message_runs`

## Editing Data

Use the dashboard to:

- correct daily drink totals
- mark days as tracked, missed, or manually corrected
- update a week's snapshotted goals
- recalculate weekly summaries after edits

