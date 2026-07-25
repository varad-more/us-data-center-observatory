"""Declarative base and shared column mixins."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
"""Deterministic constraint names so Alembic migrations are stable and reversible."""


class Base(DeclarativeBase):
    """Base class for all Helios ORM models."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    type_annotation_map = {
        dict[str, Any]: JSONB,
        list[str]: JSONB,
        datetime: DateTime(timezone=True),
    }

    def __repr__(self) -> str:
        pk = getattr(self, "id", None)
        return f"<{type(self).__name__} {pk}>"


class UUIDPrimaryKeyMixin:
    """Adds a client-generatable UUID primary key.

    UUIDs are generated in Python rather than the database so that a connector
    can build an entire object graph - document, versions, evidence records -
    and wire up the foreign keys before issuing a single INSERT.
    """

    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    """Adds transaction-time bookkeeping columns.

    These record when *Helios* learned or changed something and must never be
    used as a proxy for when a fact became true in the world.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class EffectiveDatingMixin:
    """Adds valid-time bounds to a row.

    An open-ended row (``effective_end IS NULL``) is currently believed true. A
    closed row describes something that *was* true, which is what makes
    ownership history and stage history reconstructable.
    """

    effective_start: Mapped[date | None] = mapped_column(index=True)
    effective_end: Mapped[date | None] = mapped_column(index=True)


__all__ = [
    "Base",
    "EffectiveDatingMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
]
