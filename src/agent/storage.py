"""Conversation storage + memory.

SQLite by default (zero setup), but the DB URL is configurable, so switching to
Postgres on the VPS later is a one-line `.env` change — no code changes.

Conversations are keyed by `conversation_id`, a channel-scoped identity like
"whatsapp:+9233..." or "telegram:12345". That keeps memory per-user and lets us
grow into real multi-tenant accounts in Phase 2 without reshaping the schema.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import DateTime, Integer, String, Text, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///personal_agent.db")


class Base(DeclarativeBase):
    pass


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(128), index=True)
    role: Mapped[str] = mapped_column(String(16))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


_engine = create_engine(DATABASE_URL)
Base.metadata.create_all(_engine)  # idempotent; fine until we add migrations


def save_message(conversation_id: str, role: str, content: str) -> None:
    with Session(_engine) as session:
        session.add(Message(conversation_id=conversation_id, role=role, content=content))
        session.commit()


def count_user_messages_since(conversation_id: str, since: datetime) -> int:
    """How many messages this user has sent since `since` (for rate limiting)."""
    with Session(_engine) as session:
        return session.execute(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
                Message.created_at >= since,
            )
        ).scalar_one()


def recent_messages(conversation_id: str, limit: int = 8) -> list[dict]:
    """Return the last `limit` turns in chronological order (oldest first)."""
    with Session(_engine) as session:
        rows = (
            session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.id.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]
