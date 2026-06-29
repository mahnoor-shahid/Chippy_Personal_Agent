"""Per-user storage for the MCP server's stateful tools (reminders, facts).

Shares the same DATABASE_URL as the agent's conversation memory, but owns its own
tables. The active user is read from the CONVERSATION_ID env var, which the agent
brain injects when it spawns the server — so tools are scoped to the right person
without the LLM ever choosing whose data to touch.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    create_engine,
    select,
    update,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///personal_agent.db")


class Base(DeclarativeBase):
    pass


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    text: Mapped[str] = mapped_column(Text)
    due: Mapped[str | None] = mapped_column(String(128), nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


_engine = create_engine(DATABASE_URL)
Base.metadata.create_all(_engine)


def current_user() -> str:
    """Whose data we're operating on — injected by the agent brain."""
    return os.getenv("CONVERSATION_ID", "default")


# --- reminders ---
def add_reminder(text: str, due: str | None = None) -> int:
    with Session(_engine) as s:
        r = Reminder(conversation_id=current_user(), text=text, due=due)
        s.add(r)
        s.commit()
        return r.id


def list_reminders(include_done: bool = False) -> list[dict]:
    stmt = select(Reminder).where(Reminder.conversation_id == current_user())
    if not include_done:
        stmt = stmt.where(Reminder.done.is_(False))
    with Session(_engine) as s:
        rows = s.execute(stmt.order_by(Reminder.id)).scalars().all()
        return [
            {"id": r.id, "text": r.text, "due": r.due, "done": r.done} for r in rows
        ]


def complete_reminder(reminder_id: int) -> bool:
    with Session(_engine) as s:
        res = s.execute(
            update(Reminder)
            .where(
                Reminder.id == reminder_id,
                Reminder.conversation_id == current_user(),
            )
            .values(done=True)
        )
        s.commit()
        return res.rowcount > 0


# --- facts ---
def add_fact(text: str) -> int:
    with Session(_engine) as s:
        f = Fact(conversation_id=current_user(), text=text)
        s.add(f)
        s.commit()
        return f.id


def list_facts() -> list[dict]:
    with Session(_engine) as s:
        rows = (
            s.execute(
                select(Fact)
                .where(Fact.conversation_id == current_user())
                .order_by(Fact.id)
            )
            .scalars()
            .all()
        )
        return [{"id": f.id, "text": f.text} for f in rows]
