# Drink Tracker Home Assistant Add-on

Track daily drinks over iMessage or SMS through BlueBubbles, store results in PostgreSQL, and review or correct everything from a built-in dashboard.

[![Open your Home Assistant instance and show the add-on repository dialog with this repo pre-filled.](https://my.home-assistant.io/badges/supervisor_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fdannymace%2Fha-drink-tracker)

## What It Does

- Sends a daily BlueBubbles message asking for yesterday's drink total.
- Accepts numeric-only replies, confirms receipt, and sends a week-so-far summary.
- Sends one reminder after 1 hour if there is no reply, then stops tracking that prompt after another hour.
- Stores daily tracking, weekly goal snapshots, prompt runs, and weekly summaries in PostgreSQL.
- Exposes an editable dashboard over Home Assistant ingress and a direct LAN URL.
- Auto-discovers the Postgres add-on hostname from the Home Assistant Supervisor when possible.

## Repository Layout

- `repository.yaml`: Home Assistant add-on repository metadata.
- `drink_tracker/`: The actual add-on.

## Add-on Setup

1. Add this repository to Home Assistant.
2. Install the `Drink Tracker` add-on.
3. Configure:
   - BlueBubbles host and password
   - recipient address
   - PostgreSQL password and, if needed, host override
   - dashboard password for direct LAN access
   - daily and weekly schedules
   - weekly and per-day goals
4. Start the add-on.
5. Point BlueBubbles webhooks at the callback URL shown in the dashboard or add-on logs.

## Runtime Notes

- Weeks start on Monday.
- Historical goals are snapshotted per week, so editing future goals does not rewrite past targets.
- Direct LAN dashboard access uses the configured dashboard username and password.
- The same web app serves both the dashboard and the BlueBubbles webhook endpoint.

## Development

The add-on is a Python app packaged for Home Assistant.

```bash
cd drink_tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
```

