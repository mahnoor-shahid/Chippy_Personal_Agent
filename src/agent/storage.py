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


class KV(Base):
    """Tiny key-value store (e.g. the last video id we posted per channel)."""

    __tablename__ = "kv"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class Post(Base):
    """A generated opinion piece we keep so the owner can RESEND it later."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # "tldr" | "stockify"
    date_key: Mapped[str] = mapped_column(String(10), index=True)  # local YYYY-MM-DD
    prompt: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


_engine = create_engine(DATABASE_URL)
Base.metadata.create_all(_engine)  # idempotent; fine until we add migrations


def save_post(kind: str, date_key: str, prompt: str, content: str) -> None:
    with Session(_engine) as session:
        session.add(Post(kind=kind, date_key=date_key, prompt=prompt, content=content))
        session.commit()


def get_post(kind: str, date_key: str | None = None) -> dict | None:
    """Latest post of `kind` (optionally on a specific local date YYYY-MM-DD)."""
    stmt = select(Post).where(Post.kind == kind)
    if date_key:
        stmt = stmt.where(Post.date_key == date_key)
    with Session(_engine) as session:
        row = session.execute(stmt.order_by(Post.id.desc()).limit(1)).scalar_one_or_none()
        if row is None:
            return None
        return {"kind": row.kind, "date_key": row.date_key, "prompt": row.prompt, "content": row.content}


def list_posts(limit: int = 15) -> list[dict]:
    with Session(_engine) as session:
        rows = (
            session.execute(select(Post).order_by(Post.id.desc()).limit(limit))
            .scalars()
            .all()
        )
    return [{"kind": r.kind, "date_key": r.date_key} for r in rows]


def kv_get(key: str) -> str | None:
    with Session(_engine) as session:
        row = session.get(KV, key)
        return row.value if row else None


def kv_set(key: str, value: str) -> None:
    with Session(_engine) as session:
        row = session.get(KV, key)
        if row:
            row.value = value
        else:
            session.add(KV(key=key, value=value))
        session.commit()


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


def last_user_message_time(conversation_id: str) -> datetime | None:
    """When this user last messaged (for keep-alive nudges + welcome-back).

    Always returned as a timezone-aware UTC datetime (SQLite hands back naive)."""
    with Session(_engine) as session:
        ts = session.execute(
            select(Message.created_at)
            .where(Message.conversation_id == conversation_id, Message.role == "user")
            .order_by(Message.id.desc())
            .limit(1)
        ).scalar_one_or_none()
    if ts is not None and ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


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
