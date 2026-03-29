"""Core drink tracking service."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from .bluebubbles import BlueBubblesClient
from .database import create_session_factory
from .models import DailyEntry, MessageRun, WeeklyGoal, WeeklySummary
from .settings import Settings, TargetSettings
from .supervisor import SupervisorClient

LOGGER = logging.getLogger(__name__)

DAY_LABELS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
KEYCAPS = {str(i): f"{i}\N{variation selector-16}\N{combining enclosing keycap}" for i in range(10)}
NUMBER_PATTERN = re.compile(r"^\s*(\d+)\s*$")
FIGURE_SPACE = "\u2007"
MESSAGE_DATA_HINT_KEYS = {
    "address",
    "body",
    "chatGuid",
    "chat_guid",
    "chats",
    "guid",
    "handle",
    "isFromMe",
    "message",
    "participants",
    "sender",
    "subject",
    "text",
}


@dataclass
class DayView:
    entry_date: date
    drinks: int | None
    status: str
    target: int


class DrinkTrackerService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.zone = ZoneInfo(settings.time_zone)
        self.scheduler = BackgroundScheduler(timezone=self.zone)
        self.supervisor = SupervisorClient(settings.supervisor_url)
        self.db_engine = None
        self.session_factory: sessionmaker[Session] | None = None
        self.client: BlueBubblesClient | None = None
        self.config_errors: list[str] = []
        self.started = False
        self.database_url = ""
        self._allowed_reply_sources_cache: tuple[set[str], set[str]] | None = None

    def start(self) -> None:
        self.settings.ensure_webhook_secret()
        self._configure_runtime()
        if self.config_errors:
            LOGGER.warning("Drink Tracker started with configuration errors: %s", self.config_errors)
            return

        self._schedule_jobs()
        self.started = True

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _configure_runtime(self) -> None:
        self.config_errors = []
        self.db_engine = None
        self.session_factory = None
        self.client = None
        self.database_url = ""
        self._allowed_reply_sources_cache = None

        if not self.settings.recipient_address:
            self.config_errors.append("Recipient address is required.")
        if not self.settings.bluebubbles.host:
            self.config_errors.append("BlueBubbles host is required.")
        if not self.settings.bluebubbles.password:
            self.config_errors.append("BlueBubbles password is required.")
        if not self.settings.postgres.password and not self.settings.database_url_override:
            self.config_errors.append("PostgreSQL password is required.")

        if not self.settings.postgres.host and not self.settings.database_url_override:
            discovered_host = self.supervisor.discover_postgres_host()
            if discovered_host:
                self.settings.postgres.host = discovered_host
            else:
                self.config_errors.append(
                    "PostgreSQL host could not be auto-discovered. Set postgres.host in the add-on options."
                )

        if self.config_errors:
            return

        self.client = BlueBubblesClient(
            host=self.settings.bluebubbles.host,
            password=self.settings.bluebubbles.password,
            verify_ssl=self.settings.bluebubbles.ssl,
            method=self.settings.bluebubbles.send_method,
        )
        self.database_url = self.settings.database_url_override or self.settings.postgres.build_url()

        try:
            self.db_engine, self.session_factory = create_session_factory(self.database_url)
        except (SQLAlchemyError, ValueError) as exc:
            LOGGER.exception("Unable to initialize the Drink Tracker database connection.")
            self.config_errors.append(self._render_database_connection_error(exc))

    def _render_database_connection_error(self, exc: Exception) -> str:
        host, port = self.settings.postgres.normalized_endpoint()
        message = f"Unable to connect to PostgreSQL at {host}:{port}."
        if host in {"homeassistant.local", "localhost", "127.0.0.1"} or host.endswith(".local"):
            message += " Use the Postgres add-on hostname, for example `db21ed7f-postgres-latest`, instead of the Home Assistant host."
        return f"{message} {exc}"

    def _schedule_jobs(self) -> None:
        daily_hour, daily_minute = self._parse_clock(self.settings.schedules.daily_prompt_time)
        weekly_hour, weekly_minute = self._parse_clock(self.settings.schedules.weekly_summary_time)

        self.scheduler.add_job(
            self.send_daily_prompt,
            trigger="cron",
            hour=daily_hour,
            minute=daily_minute,
            id="daily_prompt",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.send_weekly_summary,
            trigger="cron",
            day_of_week=self.settings.schedules.weekly_summary_day,
            hour=weekly_hour,
            minute=weekly_minute,
            id="weekly_summary",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.run_housekeeping,
            trigger="interval",
            minutes=1,
            id="housekeeping",
            replace_existing=True,
        )
        if not self.scheduler.running:
            self.scheduler.start()

    def _parse_clock(self, value: str) -> tuple[int, int]:
        hour, minute = value.split(":")
        return int(hour), int(minute)

    def now(self) -> datetime:
        return datetime.now(self.zone)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok" if not self.config_errors else "error",
            "config_errors": self.config_errors,
            "database_url": self.database_url if self.database_url else "",
            "webhook_secret": self.settings.ensure_webhook_secret(),
            "recipient_address": self.settings.recipient_address,
            "postgres_host": self.settings.postgres.host,
        }

    def _session(self) -> Session:
        if not self.session_factory:
            raise RuntimeError("Database is not configured.")
        return self.session_factory()

    def _require_client(self) -> BlueBubblesClient:
        if not self.client:
            raise RuntimeError("BlueBubbles client is not configured.")
        return self.client

    def send_daily_prompt(self, now: datetime | None = None) -> dict[str, Any]:
        if self.config_errors:
            return {"status": "skipped", "reason": "configuration incomplete"}

        client = self._require_client()
        now = now or self.now()
        tracked_date = (now - timedelta(days=1)).date()
        prompt_text = "Danny, how did you do yesterday? Reply with your total drinks from yesterday."

        with self._session() as session:
            existing_run = session.scalar(select(MessageRun).where(MessageRun.tracked_date == tracked_date))
            if existing_run and existing_run.state == "awaiting_reply":
                return {
                    "status": "skipped",
                    "reason": "already awaiting reply",
                    "tracked_date": tracked_date.isoformat(),
                }
            if existing_run and existing_run.state == "answered":
                entry = session.scalar(select(DailyEntry).where(DailyEntry.entry_date == tracked_date))
                return {
                    "status": "skipped",
                    "reason": "already answered",
                    "tracked_date": tracked_date.isoformat(),
                    "drinks": entry.drinks if entry else None,
                }

            self._ensure_weekly_goal_snapshot(session, self.week_start_for(tracked_date))
            entry = session.scalar(select(DailyEntry).where(DailyEntry.entry_date == tracked_date))
            if not entry:
                entry = DailyEntry(entry_date=tracked_date, status="pending", source="sms")
                session.add(entry)
            entry.prompt_sent_at = now
            entry.status = "pending"

            run = existing_run or MessageRun(
                tracked_date=tracked_date,
                recipient=self.settings.recipient_address,
                sent_at=now,
                remind_at=now + timedelta(minutes=self.settings.schedules.reminder_delay_minutes),
                expires_at=now
                + timedelta(minutes=self.settings.schedules.reminder_delay_minutes)
                + timedelta(minutes=self.settings.schedules.reminder_window_minutes),
            )
            run.prompt_message = prompt_text
            run.state = "awaiting_reply"
            session.add(run)
            session.commit()

        client.send_to_addresses([self.settings.recipient_address], prompt_text)
        return {"status": "sent", "tracked_date": tracked_date.isoformat()}

    def send_weekly_summary(self, now: datetime | None = None) -> dict[str, Any]:
        if self.config_errors:
            return {"status": "skipped", "reason": "configuration incomplete"}

        now = now or self.now()
        current_week_start = self.week_start_for(now.date())
        previous_week_start = current_week_start - timedelta(days=7)

        with self._session() as session:
            self._ensure_weekly_goal_snapshot(session, previous_week_start)
            summary = self._recalculate_weekly_summary(session, previous_week_start, previous_week_start + timedelta(days=6))
            snapshot = self._build_week_snapshot(session, summary.week_start, summary.week_end)
            message = self._render_weekly_summary_message(summary, snapshot=snapshot)
            summary.summary_text = message
            summary.summary_sent_at = now
            session.commit()

        self._require_client().send_to_addresses([self.settings.recipient_address], message)
        return {
            "status": "sent",
            "week_start": summary.week_start.isoformat(),
            "week_end": summary.week_end.isoformat(),
        }

    def run_housekeeping(self, now: datetime | None = None) -> None:
        if self.config_errors:
            return

        now = now or self.now()
        client = self._require_client()

        with self._session() as session:
            runs = session.scalars(
                select(MessageRun).where(MessageRun.state == "awaiting_reply").order_by(MessageRun.tracked_date)
            ).all()
            for run in runs:
                if not run.reminder_sent_at and now >= run.remind_at:
                    reminder = (
                        "Reminder: reply with just the number of drinks you had yesterday. "
                        "I will stop waiting after one more hour."
                    )
                    client.send_to_addresses([self.settings.recipient_address], reminder)
                    run.reminder_sent_at = now
                    continue

                if now >= run.expires_at:
                    run.state = "missed"
                    entry = session.scalar(select(DailyEntry).where(DailyEntry.entry_date == run.tracked_date))
                    if not entry:
                        entry = DailyEntry(entry_date=run.tracked_date)
                        session.add(entry)
                    entry.status = "missed"
                    entry.reminder_sent_at = run.reminder_sent_at
                    entry.note = "No numeric reply received before the reminder window expired."
            session.commit()

    def process_bluebubbles_webhook(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.config_errors:
            return {"status": "ignored", "reason": "configuration incomplete"}

        raw_event_type = payload.get("type") or payload.get("event") or payload.get("eventType")
        event_type = self._normalize_event_type(raw_event_type)
        if "message" not in event_type:
            return self._ignored_webhook_result(
                "unsupported event",
                raw_event_type=raw_event_type,
                event_type=event_type,
            )

        message_data = self._extract_message_data(payload)

        body = self._extract_message_body(message_data)
        match = NUMBER_PATTERN.match(body or "")
        if not match:
            return self._ignored_webhook_result(
                "message is not numeric",
                raw_event_type=raw_event_type,
                event_type=event_type,
                message_data=message_data,
            )

        drinks = int(match.group(1))
        chat_guid = self._extract_chat_guid(message_data)
        source_address = self._extract_source_address(message_data)
        allowed_addresses, allowed_chat_guids = self._allowed_reply_sources()
        matches_allowed_source = self._matches_allowed_reply_source(
            source_address,
            chat_guid,
            allowed_addresses,
            allowed_chat_guids,
        )
        now = self.now()

        with self._session() as session:
            run = session.scalar(
                select(MessageRun)
                .where(MessageRun.state == "awaiting_reply")
                .order_by(MessageRun.tracked_date.desc())
            )
            if not run:
                return self._ignored_webhook_result(
                    "no open prompt",
                    raw_event_type=raw_event_type,
                    event_type=event_type,
                    message_data=message_data,
                )

            if message_data.get("isFromMe") and not matches_allowed_source:
                return self._ignored_webhook_result(
                    "outbound message",
                    raw_event_type=raw_event_type,
                    event_type=event_type,
                    message_data=message_data,
                )

            if source_address and not matches_allowed_source and run.source_address:
                return self._ignored_webhook_result(
                    "source address mismatch",
                    raw_event_type=raw_event_type,
                    event_type=event_type,
                    message_data=message_data,
                )

            run.state = "answered"
            run.reply_message = body.strip()
            run.reply_received_at = now
            if chat_guid:
                run.chat_guid = chat_guid
            if source_address:
                run.source_address = source_address

            entry = session.scalar(select(DailyEntry).where(DailyEntry.entry_date == run.tracked_date))
            if not entry:
                entry = DailyEntry(entry_date=run.tracked_date)
                session.add(entry)
            entry.drinks = drinks
            entry.status = "tracked"
            entry.source = "sms"
            entry.chat_guid = chat_guid or entry.chat_guid
            entry.confirmed_at = now
            entry.prompt_sent_at = run.sent_at
            entry.reminder_sent_at = run.reminder_sent_at

            week_start = self.week_start_for(run.tracked_date)
            self._ensure_weekly_goal_snapshot(session, week_start)
            summary = self._recalculate_weekly_summary(session, week_start, run.tracked_date)
            session.commit()

        confirmation = self._render_confirmation_message(summary, run.tracked_date)
        client = self._require_client()
        confirmation_delivery = "address"
        try:
            if chat_guid:
                client.send_to_chat_guid(chat_guid, confirmation)
                confirmation_delivery = "chat"
            else:
                client.send_to_addresses([self.settings.recipient_address], confirmation)
        except Exception:
            if chat_guid:
                LOGGER.warning(
                    "Unable to send confirmation to BlueBubbles chat %s, falling back to recipient address.",
                    chat_guid,
                    exc_info=True,
                )
                try:
                    client.send_to_addresses([self.settings.recipient_address], confirmation)
                except Exception:
                    LOGGER.exception("Unable to send confirmation to recipient address after chat fallback.")
                    confirmation_delivery = "failed"
                else:
                    confirmation_delivery = "address-fallback"
            else:
                LOGGER.exception("Unable to send confirmation to recipient address.")
                confirmation_delivery = "failed"
        LOGGER.info(
            "Stored BlueBubbles reply for %s: drinks=%s source=%s event=%s delivery=%s",
            run.tracked_date.isoformat(),
            drinks,
            source_address or self._extract_source_address(message_data) or "unknown",
            event_type or raw_event_type or "unknown",
            confirmation_delivery,
        )
        return {
            "status": "stored",
            "tracked_date": run.tracked_date.isoformat(),
            "drinks": drinks,
            "confirmation_delivery": confirmation_delivery,
        }

    def dashboard_context(self, request_base: str) -> dict[str, Any]:
        context: dict[str, Any] = {
            "config_errors": self.config_errors,
            "health": self.health(),
            "recipient_address": self.settings.recipient_address,
            "direct_url": request_base,
            "webhook_path": f"/webhooks/bluebubbles/{self.settings.ensure_webhook_secret()}",
            "weekly_summary_day": self.settings.schedules.weekly_summary_day,
            "weekly_summary_time": self.settings.schedules.weekly_summary_time,
            "daily_prompt_time": self.settings.schedules.daily_prompt_time,
        }
        if self.config_errors or not self.session_factory:
            context.update({"daily_rows": [], "weekly_goals": [], "weekly_summaries": [], "message_runs": []})
            return context

        with self._session() as session:
            daily_rows = session.scalars(select(DailyEntry).order_by(DailyEntry.entry_date.desc())).all()
            goals = session.scalars(select(WeeklyGoal).order_by(WeeklyGoal.week_start.desc())).all()
            summaries = session.scalars(select(WeeklySummary).order_by(WeeklySummary.week_start.desc())).all()
            message_runs = session.scalars(select(MessageRun).order_by(MessageRun.tracked_date.desc())).all()
            context["daily_rows"] = [
                {
                    "id": row.id,
                    "entry_date": row.entry_date.isoformat(),
                    "drinks": "" if row.drinks is None else row.drinks,
                    "status": row.status,
                    "note": row.note,
                    "target": self._target_for_date(session, row.entry_date),
                }
                for row in daily_rows
            ]
            context["weekly_goals"] = [
                {
                    "week_start": row.week_start.isoformat(),
                    "weekly_drinks": row.weekly_drinks,
                    "weekly_dry_days": row.weekly_dry_days,
                    "monday": row.monday,
                    "tuesday": row.tuesday,
                    "wednesday": row.wednesday,
                    "thursday": row.thursday,
                    "friday": row.friday,
                    "saturday": row.saturday,
                    "sunday": row.sunday,
                }
                for row in goals
            ]
            context["weekly_summaries"] = [
                {
                    "week_start": row.week_start.isoformat(),
                    "week_end": row.week_end.isoformat(),
                    "total_drinks": row.total_drinks,
                    "dry_days": row.dry_days,
                    "tracked_days": row.tracked_days,
                    "average_drinks_per_day": round(row.average_drinks_per_day, 2),
                    "average_drinks_per_tracked_day": round(row.average_drinks_per_tracked_day, 2),
                    "weekly_drink_target": row.weekly_drink_target,
                    "weekly_dry_day_target": row.weekly_dry_day_target,
                    "delta_from_last_week": row.delta_from_last_week,
                    "tracking_streak_days": row.tracking_streak_days,
                    "full_week_streak": row.full_week_streak,
                    "is_complete": row.is_complete,
                    "summary_sent_at": row.summary_sent_at.isoformat() if row.summary_sent_at else "",
                }
                for row in summaries
            ]
            context["message_runs"] = [
                {
                    "tracked_date": row.tracked_date.isoformat(),
                    "state": row.state,
                    "sent_at": row.sent_at.isoformat(),
                    "reply_received_at": row.reply_received_at.isoformat() if row.reply_received_at else "",
                    "source_address": row.source_address,
                }
                for row in message_runs
            ]
            return context

    def upsert_daily_entry(self, entry_date: date, drinks: int | None, status: str, note: str) -> None:
        with self._session() as session:
            entry = session.scalar(select(DailyEntry).where(DailyEntry.entry_date == entry_date))
            if not entry:
                entry = DailyEntry(entry_date=entry_date)
                session.add(entry)
            entry.drinks = drinks
            entry.status = status
            entry.note = note
            if status in {"tracked", "manual"} and drinks is not None:
                entry.confirmed_at = self.now()
            week_start = self.week_start_for(entry_date)
            self._ensure_weekly_goal_snapshot(session, week_start)
            self._recalculate_weekly_summary(session, week_start, min(self.week_end_for(week_start), self.now().date()))
            session.commit()

    def upsert_weekly_goal(self, week_start: date, values: dict[str, int]) -> None:
        with self._session() as session:
            goal = session.scalar(select(WeeklyGoal).where(WeeklyGoal.week_start == week_start))
            if not goal:
                goal = WeeklyGoal(week_start=week_start, **values)
                session.add(goal)
            else:
                for key, value in values.items():
                    setattr(goal, key, value)
            self._recalculate_weekly_summary(session, week_start, min(self.week_end_for(week_start), self.now().date()))
            session.commit()

    def recalculate_all(self) -> None:
        if self.config_errors:
            return
        with self._session() as session:
            week_starts = {self.week_start_for(row.entry_date) for row in session.scalars(select(DailyEntry)).all()}
            week_starts.update({row.week_start for row in session.scalars(select(WeeklyGoal)).all()})
            for week_start in sorted(week_starts):
                self._ensure_weekly_goal_snapshot(session, week_start)
                self._recalculate_weekly_summary(
                    session,
                    week_start,
                    min(self.week_end_for(week_start), self.now().date()),
                )
            session.commit()

    @staticmethod
    def week_start_for(value: date) -> date:
        return value - timedelta(days=value.weekday())

    @staticmethod
    def week_end_for(week_start: date) -> date:
        return week_start + timedelta(days=6)

    def _ensure_weekly_goal_snapshot(self, session: Session, week_start: date) -> WeeklyGoal:
        existing = session.scalar(select(WeeklyGoal).where(WeeklyGoal.week_start == week_start))
        if existing:
            return existing
        defaults = self._targets_as_dict(self.settings.targets)
        goal = WeeklyGoal(week_start=week_start, **defaults)
        session.add(goal)
        session.flush()
        return goal

    def _target_for_date(self, session: Session, entry_date: date) -> int:
        week_start = self.week_start_for(entry_date)
        goal = session.scalar(select(WeeklyGoal).where(WeeklyGoal.week_start == week_start))
        if not goal:
            return self.settings.targets.by_weekday()[entry_date.weekday()]
        return self._goal_day_target(goal, entry_date.weekday())

    def _goal_day_target(self, goal: WeeklyGoal, weekday: int) -> int:
        return {
            0: goal.monday,
            1: goal.tuesday,
            2: goal.wednesday,
            3: goal.thursday,
            4: goal.friday,
            5: goal.saturday,
            6: goal.sunday,
        }[weekday]

    def _targets_as_dict(self, target_settings: TargetSettings) -> dict[str, int]:
        return {
            "weekly_drinks": target_settings.weekly_drinks,
            "weekly_dry_days": target_settings.weekly_dry_days,
            "monday": target_settings.monday,
            "tuesday": target_settings.tuesday,
            "wednesday": target_settings.wednesday,
            "thursday": target_settings.thursday,
            "friday": target_settings.friday,
            "saturday": target_settings.saturday,
            "sunday": target_settings.sunday,
        }

    def _build_week_snapshot(self, session: Session, week_start: date, through_date: date) -> dict[str, Any]:
        week_end = self.week_end_for(week_start)
        goal = self._ensure_weekly_goal_snapshot(session, week_start)
        due_date = min(through_date, week_end)
        entries = session.scalars(
            select(DailyEntry)
            .where(DailyEntry.entry_date >= week_start, DailyEntry.entry_date <= week_end)
            .order_by(DailyEntry.entry_date.asc())
        ).all()
        entries_by_date = {entry.entry_date: entry for entry in entries}

        day_views: list[DayView] = []
        total_drinks = 0
        dry_days = 0
        tracked_days = 0

        for offset in range(7):
            current_date = week_start + timedelta(days=offset)
            entry = entries_by_date.get(current_date)
            drinks = entry.drinks if entry else None
            status = entry.status if entry else "missing"
            target = self._goal_day_target(goal, current_date.weekday())
            if entry and entry.drinks is not None:
                total_drinks += entry.drinks
            if entry and entry.status in {"tracked", "manual"} and entry.drinks is not None:
                tracked_days += 1
                if entry.drinks == 0:
                    dry_days += 1
            day_views.append(DayView(current_date, drinks, status, target))

        due_days = max(0, (due_date - week_start).days + 1)
        calendar_day_count = 7
        previous_week_start = week_start - timedelta(days=7)
        previous_total = self._week_total_drinks(session, previous_week_start)
        delta = total_drinks - previous_total if previous_total is not None else None

        return {
            "week_start": week_start,
            "week_end": week_end,
            "daily": day_views,
            "goal": goal,
            "total_drinks": total_drinks,
            "dry_days": dry_days,
            "tracked_days": tracked_days,
            "due_days": due_days,
            "average_drinks_per_day": total_drinks / calendar_day_count,
            "average_drinks_per_tracked_day": (total_drinks / tracked_days) if tracked_days else 0.0,
            "previous_week_total": previous_total,
            "delta_from_last_week": delta,
            "tracking_streak_days": self._tracking_streak_days(session, due_date),
            "full_week_streak": self._full_week_streak(session, week_start),
            "is_complete": due_date >= week_end,
        }

    def _recalculate_weekly_summary(
        self,
        session: Session,
        week_start: date,
        through_date: date,
        *,
        commit: bool = False,
    ) -> WeeklySummary:
        snapshot = self._build_week_snapshot(session, week_start, through_date)
        summary = session.scalar(select(WeeklySummary).where(WeeklySummary.week_start == week_start))
        if not summary:
            summary = WeeklySummary(week_start=week_start, week_end=snapshot["week_end"])
            session.add(summary)

        summary.week_end = snapshot["week_end"]
        summary.total_drinks = snapshot["total_drinks"]
        summary.dry_days = snapshot["dry_days"]
        summary.tracked_days = snapshot["tracked_days"]
        summary.average_drinks_per_day = snapshot["average_drinks_per_day"]
        summary.average_drinks_per_tracked_day = snapshot["average_drinks_per_tracked_day"]
        summary.weekly_drink_target = snapshot["goal"].weekly_drinks
        summary.weekly_dry_day_target = snapshot["goal"].weekly_dry_days
        summary.previous_week_total = snapshot["previous_week_total"]
        summary.delta_from_last_week = snapshot["delta_from_last_week"]
        summary.tracking_streak_days = snapshot["tracking_streak_days"]
        summary.full_week_streak = snapshot["full_week_streak"]
        summary.is_complete = snapshot["is_complete"]
        summary.summary_text = summary.summary_text or ""
        if commit:
            session.commit()
        return summary

    def _tracking_streak_days(self, session: Session, through_date: date) -> int:
        tracked_dates = {
            row.entry_date
            for row in session.scalars(
                select(DailyEntry).where(
                    DailyEntry.status.in_(["tracked", "manual"]),
                    DailyEntry.drinks.is_not(None),
                    DailyEntry.entry_date <= through_date,
                )
            ).all()
        }
        streak = 0
        pointer = through_date
        while pointer in tracked_dates:
            streak += 1
            pointer -= timedelta(days=1)
        return streak

    def _full_week_streak(self, session: Session, through_week_start: date) -> int:
        streak = 0
        pointer = through_week_start
        while True:
            if self._tracked_days_for_week(session, pointer) == 7:
                streak += 1
                pointer -= timedelta(days=7)
                continue
            break
        return streak

    def _week_total_drinks(self, session: Session, week_start: date) -> int | None:
        week_end = self.week_end_for(week_start)
        entries = session.scalars(
            select(DailyEntry).where(
                DailyEntry.entry_date >= week_start,
                DailyEntry.entry_date <= week_end,
                DailyEntry.drinks.is_not(None),
            )
        ).all()
        if not entries:
            return None
        return sum(entry.drinks or 0 for entry in entries)

    def _tracked_days_for_week(self, session: Session, week_start: date) -> int:
        week_end = self.week_end_for(week_start)
        entries = session.scalars(
            select(DailyEntry).where(
                DailyEntry.entry_date >= week_start,
                DailyEntry.entry_date <= week_end,
                DailyEntry.status.in_(["tracked", "manual"]),
                DailyEntry.drinks.is_not(None),
            )
        ).all()
        return len(entries)

    def _extract_message_body(self, message_data: dict[str, Any]) -> str:
        for key in ("text", "message", "body", "subject"):
            value = message_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, dict):
                nested_value = self._extract_message_body(value)
                if nested_value:
                    return nested_value
        for key in ("data", "payload"):
            value = message_data.get(key)
            if isinstance(value, dict):
                nested_value = self._extract_message_body(value)
                if nested_value:
                    return nested_value
        return ""

    def _extract_chat_guid(self, message_data: dict[str, Any]) -> str:
        for key in ("chatGuid", "chat_guid", "guid"):
            value = message_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        chats = message_data.get("chats", [])
        if isinstance(chats, list) and chats:
            first_chat = chats[0]
            if isinstance(first_chat, dict):
                guid = first_chat.get("guid")
                if isinstance(guid, str) and guid.strip():
                    return guid.strip()
        for key in ("chat", "message", "data", "payload"):
            value = message_data.get(key)
            if isinstance(value, dict):
                nested_guid = self._extract_chat_guid(value)
                if nested_guid:
                    return nested_guid
        return ""

    def _extract_source_address(self, message_data: dict[str, Any]) -> str:
        for key in ("address",):
            value = message_data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        handle = message_data.get("handle")
        if isinstance(handle, dict) and handle.get("address"):
            return str(handle["address"])
        sender = message_data.get("sender")
        if isinstance(sender, dict) and sender.get("address"):
            return str(sender["address"])
        participants = message_data.get("participants")
        if isinstance(participants, list):
            for participant in participants:
                if isinstance(participant, dict) and participant.get("address"):
                    return str(participant["address"])
        for key in ("message", "data", "payload"):
            value = message_data.get(key)
            if isinstance(value, dict):
                nested_address = self._extract_source_address(value)
                if nested_address:
                    return nested_address
        return ""

    def _extract_message_data(self, payload: dict[str, Any]) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        for key in ("data", "message", "payload"):
            value = payload.get(key)
            if isinstance(value, dict):
                candidates.append(value)
        for candidate in candidates:
            if self._looks_like_message_data(candidate):
                return candidate
            for key in ("data", "message", "payload"):
                nested = candidate.get(key)
                if isinstance(nested, dict) and self._looks_like_message_data(nested):
                    return nested
        return candidates[0] if candidates else {}

    def _looks_like_message_data(self, candidate: dict[str, Any]) -> bool:
        return bool(MESSAGE_DATA_HINT_KEYS.intersection(candidate.keys()))

    def _normalize_event_type(self, value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip().lower().replace("_", "-")

    def _allowed_reply_sources(self) -> tuple[set[str], set[str]]:
        if self._allowed_reply_sources_cache is not None:
            addresses, chat_guids = self._allowed_reply_sources_cache
            return set(addresses), set(chat_guids)

        addresses = {self.settings.recipient_address}
        chat_guids: set[str] = set()
        client = self.client
        if not client or not self.settings.recipient_address:
            self._allowed_reply_sources_cache = (set(addresses), set(chat_guids))
            return addresses, chat_guids

        try:
            primary_chat = client.get_chat(f"iMessage;-;{self.settings.recipient_address}")
            self._merge_allowed_reply_sources(primary_chat, addresses, chat_guids)
            alternate_handle = primary_chat.get("lastAddressedHandle")
            if isinstance(alternate_handle, str) and alternate_handle.strip():
                alternate_chat = client.get_chat(f"iMessage;-;{alternate_handle.strip()}")
                self._merge_allowed_reply_sources(alternate_chat, addresses, chat_guids)
        except Exception:
            LOGGER.warning("Unable to resolve BlueBubbles self-chat aliases for reply matching.", exc_info=True)

        self._allowed_reply_sources_cache = (set(addresses), set(chat_guids))
        return addresses, chat_guids

    def _merge_allowed_reply_sources(
        self,
        chat_data: dict[str, Any],
        addresses: set[str],
        chat_guids: set[str],
    ) -> None:
        for key in ("chatIdentifier", "lastAddressedHandle"):
            value = chat_data.get(key)
            if isinstance(value, str) and value.strip():
                addresses.add(value.strip())
        guid = chat_data.get("guid")
        if isinstance(guid, str) and guid.strip():
            chat_guids.add(guid.strip())

    def _matches_allowed_reply_source(
        self,
        source_address: str,
        chat_guid: str,
        allowed_addresses: set[str],
        allowed_chat_guids: set[str],
    ) -> bool:
        if source_address and source_address in allowed_addresses:
            return True
        if chat_guid and chat_guid in allowed_chat_guids:
            return True
        return False

    def _ignored_webhook_result(
        self,
        reason: str,
        *,
        raw_event_type: Any,
        event_type: str,
        message_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if message_data:
            body = self._preview_message_body(self._extract_message_body(message_data))
            source_address = self._extract_source_address(message_data) or "-"
            data_keys = ",".join(sorted(message_data.keys())) or "-"
            LOGGER.info(
                "Ignored BlueBubbles webhook: reason=%s event=%s raw_type=%r body=%r source=%s keys=%s",
                reason,
                event_type or "unknown",
                raw_event_type,
                body,
                source_address,
                data_keys,
            )
        return {"status": "ignored", "reason": reason}

    def _preview_message_body(self, body: str) -> str:
        if not body:
            return ""
        body = body.strip()
        if len(body) <= 32:
            return body
        return f"{body[:29]}..."

    def _render_confirmation_message(self, summary: WeeklySummary, tracked_date: date) -> str:
        lines = [
            "☑️ Tracking confirmed.",
            "Your Week So Far",
        ]
        with self._session() as session:
            snapshot = self._build_week_snapshot(session, summary.week_start, tracked_date)
            lines.extend(self._render_week_snapshot_lines(snapshot, highlight_date=tracked_date))
        return "\n".join(lines)

    def _render_weekly_summary_message(
        self,
        summary: WeeklySummary,
        *,
        snapshot: dict[str, Any] | None = None,
    ) -> str:
        if snapshot is None:
            with self._session() as session:
                snapshot = self._build_week_snapshot(session, summary.week_start, summary.week_end)
        lines = [
            "📊 Weekly Drink Summary",
            f"Week of {summary.week_start.strftime('%b %d')} to {summary.week_end.strftime('%b %d')}",
        ]
        lines.extend(self._render_week_snapshot_lines(snapshot))
        if summary.delta_from_last_week is not None:
            if summary.delta_from_last_week < 0:
                lines.append(f"You had {abs(summary.delta_from_last_week)} fewer drinks than last week.")
            elif summary.delta_from_last_week > 0:
                lines.append(f"You had {summary.delta_from_last_week} more drinks than last week.")
            else:
                lines.append("You matched last week's total exactly.")
        return "\n".join(lines)

    def _render_week_snapshot_lines(
        self,
        snapshot: dict[str, Any],
        *,
        highlight_date: date | None = None,
    ) -> list[str]:
        label_width = 12
        lines = [
            f"{self._status_icon(snapshot['total_drinks'] <= snapshot['goal'].weekly_drinks)} {self._pad_label('Drinks', label_width)} → {self._align_number(snapshot['total_drinks'])} │ {self._align_number(snapshot['goal'].weekly_drinks)} target",
            f"{self._status_icon(snapshot['dry_days'] >= snapshot['goal'].weekly_dry_days)} {self._pad_label('Dry Days', label_width)} → {self._align_number(snapshot['dry_days'])} │ {self._align_number(snapshot['goal'].weekly_dry_days)} target",
            f"{self._tracked_days_icon(snapshot['tracked_days'], snapshot['due_days'])} {self._pad_label('Tracked Days', label_width)} → {self._align_number(snapshot['tracked_days'])} │ {self._align_number(snapshot['due_days'])} due",
            f"⚪️ {self._pad_label('Average', label_width)} → {self._align_decimal(snapshot['average_drinks_per_day'])} │ {self._align_decimal(snapshot['average_drinks_per_tracked_day'])} tracked",
            "Daily Drinks vs. Target",
        ]
        for day in snapshot["daily"]:
            drinks = self._align_number(day.drinks) if day.drinks is not None else self._align_missing()
            marker = "  👈" if highlight_date and day.entry_date == highlight_date else ""
            lines.append(
                f"{self._daily_icon(day.drinks, day.target)} {DAY_LABELS[day.entry_date.weekday()]} → {drinks} │ {self._align_number(day.target)}{marker}"
            )
        if snapshot["tracking_streak_days"] > 1:
            lines.append(f"🔥 {snapshot['tracking_streak_days']} day tracking streak!")
        if snapshot["full_week_streak"] > 1:
            lines.append(f"You tracked {snapshot['full_week_streak']} full weeks in a row.")
        return lines

    def _stylize_number(self, value: int) -> str:
        if value == 0:
            return KEYCAPS["0"]
        return "".join(KEYCAPS[digit] for digit in str(value))

    def _align_number(self, value: int, width: int = 2) -> str:
        text = str(value)
        return f"{FIGURE_SPACE * max(0, width - len(text))}{text}"

    def _align_decimal(self, value: float, width: int = 4) -> str:
        text = f"{value:.1f}"
        return f"{FIGURE_SPACE * max(0, width - len(text))}{text}"

    def _align_missing(self, width: int = 2) -> str:
        return f"{FIGURE_SPACE * max(0, width - 1)}-"

    def _pad_label(self, value: str, width: int) -> str:
        return value.ljust(width)

    def _status_icon(self, condition: bool) -> str:
        return "🟢" if condition else "🔴"

    def _tracked_days_icon(self, tracked_days: int, due_days: int) -> str:
        return "🟢" if tracked_days == due_days else "🟡"

    def _daily_icon(self, drinks: int | None, target: int) -> str:
        if drinks is None:
            return "⚪️"
        if drinks == 0 and target == 0:
            return "🟢"
        if drinks <= target:
            return "🟢"
        if target == 0:
            return "🔴"
        if drinks <= target + 2:
            return "🟡"
        return "🔴"
