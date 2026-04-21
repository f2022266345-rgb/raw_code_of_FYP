from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from pgvector.sqlalchemy import Vector


EMBEDDING_DIM = 256


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_database_url(raw_url: str) -> str:
    if raw_url.startswith("postgresql://") and "+" not in raw_url.split("://", 1)[0]:
        return raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw_url


DATABASE_URL = _normalize_database_url(
    os.getenv("DATABASE_URL", "postgresql://postgres:admin@localhost:5432/fyp_db")
)


class Base(DeclarativeBase):
    pass


class SessionORM(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)

    is_authenticated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_crisis_modal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    major: Mapped[str | None] = mapped_column(String(120), nullable=True)
    university: Mapped[str | None] = mapped_column(String(180), nullable=True)
    stress_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_phase: Mapped[str | None] = mapped_column(String(80), nullable=True)
    academic_confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    social_battery: Mapped[str | None] = mapped_column(String(24), nullable=True)
    current_mood: Mapped[str | None] = mapped_column(String(60), nullable=True)

    is_analyzing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    academic_status: Mapped[str] = mapped_column(String(24), default="idle", nullable=False)
    social_status: Mapped[str] = mapped_column(String(24), default="idle", nullable=False)
    wellness_status: Mapped[str] = mapped_column(String(24), default="idle", nullable=False)

    academic_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    social_result: Mapped[str | None] = mapped_column(Text, nullable=True)
    wellness_result: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    notifications = relationship("NotificationORM", back_populates="session", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessageORM", back_populates="session", cascade="all, delete-orphan")


class NotificationORM(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    type: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    session = relationship("SessionORM", back_populates="notifications")


class ChatMessageORM(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )

    agent_type: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)

    session = relationship("SessionORM", back_populates="chat_messages")


class KnowledgeChunkORM(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_type: Mapped[str | None] = mapped_column(String(24), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now_utc, nullable=False)


engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

