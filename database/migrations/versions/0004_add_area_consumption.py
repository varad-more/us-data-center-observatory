"""add area consumption totals

Reported resource totals for a whole county or state, kept in their own table
rather than as a nullable site on ``site_estimates``. A site estimate is an
inference from acreage; these are figures an agency measured. Sharing a table
would invite summing across that line.

Revision ID: 9f0aedb7d2e1
Revises: 8e9fdca6c1c0
Create Date: 2026-07-28 03:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PgUUID

revision: str = "9f0aedb7d2e1"
down_revision: str | None = "8e9fdca6c1c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "area_consumption",
        sa.Column("id", PgUUID(as_uuid=True), primary_key=True),
        sa.Column("area_kind", sa.String(length=20), nullable=False),
        sa.Column("area_code", sa.String(length=10), nullable=False),
        sa.Column("area_name", sa.String(length=120), nullable=False),
        sa.Column("metric", sa.String(length=60), nullable=False),
        sa.Column("sector", sa.String(length=60), nullable=False, server_default="all"),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(length=40), nullable=False),
        sa.Column("reference_year", sa.SmallInteger(), nullable=False),
        sa.Column(
            "assertion_class", sa.String(length=20), nullable=False, server_default="reported"
        ),
        sa.Column("source_id", PgUUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", PgUUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_area_consumption_source_id_sources",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            name="fk_area_consumption_document_version_id_document_versions",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "area_kind",
            "area_code",
            "metric",
            "sector",
            "reference_year",
            name="uq_area_consumption_measure",
        ),
    )
    op.create_index(
        op.f("ix_area_consumption_area_kind"), "area_consumption", ["area_kind"], unique=False
    )
    op.create_index(
        op.f("ix_area_consumption_area_code"), "area_consumption", ["area_code"], unique=False
    )
    op.create_index(
        op.f("ix_area_consumption_metric"), "area_consumption", ["metric"], unique=False
    )
    op.create_index(
        op.f("ix_area_consumption_reference_year"),
        "area_consumption",
        ["reference_year"],
        unique=False,
    )
    op.create_index(
        op.f("ix_area_consumption_source_id"), "area_consumption", ["source_id"], unique=False
    )
    op.create_index(
        op.f("ix_area_consumption_document_version_id"),
        "area_consumption",
        ["document_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_area_consumption_lookup",
        "area_consumption",
        ["area_kind", "area_code", "metric"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_area_consumption_lookup", table_name="area_consumption")
    op.drop_index(op.f("ix_area_consumption_document_version_id"), table_name="area_consumption")
    op.drop_index(op.f("ix_area_consumption_source_id"), table_name="area_consumption")
    op.drop_index(op.f("ix_area_consumption_reference_year"), table_name="area_consumption")
    op.drop_index(op.f("ix_area_consumption_metric"), table_name="area_consumption")
    op.drop_index(op.f("ix_area_consumption_area_code"), table_name="area_consumption")
    op.drop_index(op.f("ix_area_consumption_area_kind"), table_name="area_consumption")
    op.drop_table("area_consumption")
