"""SQLAlchemy models."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for ORM models."""


class DailyEntry(Base):
    __tablename__ = "daily_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    drinks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    source: Mapped[str] = mapped_column(String(32), default="sms")
    note: Mapped[str] = mapped_column(Text, default="")
    chat_guid: Mapped[str] = mapped_column(String(255), default="")
    prompt_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WeeklyGoal(Base):
    __tablename__ = "weekly_goals"
    __table_args__ = (UniqueConstraint("week_start", name="uq_weekly_goals_week_start"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    weekly_drinks: Mapped[int] = mapped_column(Integer)
    weekly_dry_days: Mapped[int] = mapped_column(Integer)
    monday: Mapped[int] = mapped_column(Integer)
    tuesday: Mapped[int] = mapped_column(Integer)
    wednesday: Mapped[int] = mapped_column(Integer)
    thursday: Mapped[int] = mapped_column(Integer)
    friday: Mapped[int] = mapped_column(Integer)
    saturday: Mapped[int] = mapped_column(Integer)
    sunday: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class WeeklySummary(Base):
    __tablename__ = "weekly_summaries"
    __table_args__ = (UniqueConstraint("week_start", name="uq_weekly_summaries_week_start"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    week_start: Mapped[date] = mapped_column(Date, index=True)
    week_end: Mapped[date] = mapped_column(Date)
    total_drinks: Mapped[int] = mapped_column(Integer, default=0)
    dry_days: Mapped[int] = mapped_column(Integer, default=0)
    tracked_days: Mapped[int] = mapped_column(Integer, default=0)
    average_drinks_per_day: Mapped[float] = mapped_column(default=0.0)
    average_drinks_per_tracked_day: Mapped[float] = mapped_column(default=0.0)
    weekly_drink_target: Mapped[int] = mapped_column(Integer, default=0)
    weekly_dry_day_target: Mapped[int] = mapped_column(Integer, default=0)
    previous_week_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delta_from_last_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tracking_streak_days: Mapped[int] = mapped_column(Integer, default=0)
    full_week_streak: Mapped[int] = mapped_column(Integer, default=0)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    summary_text: Mapped[str] = mapped_column(Text, default="")
    summary_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MessageRun(Base):
    __tablename__ = "message_runs"
    __table_args__ = (UniqueConstraint("tracked_date", name="uq_message_runs_tracked_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracked_date: Mapped[date] = mapped_column(Date, index=True)
    recipient: Mapped[str] = mapped_column(String(255))
    prompt_message: Mapped[str] = mapped_column(Text, default="")
    reply_message: Mapped[str] = mapped_column(Text, default="")
    state: Mapped[str] = mapped_column(String(32), default="awaiting_reply")
    chat_guid: Mapped[str] = mapped_column(String(255), default="")
    source_address: Mapped[str] = mapped_column(String(255), default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reminder_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reply_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

