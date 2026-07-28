"""rename area_consumption to area_totals

The table was named for the first thing that went into it. It already holds
county population, which is not a consumption, and it is about to hold
generation capacity, which is the opposite of one. What it actually holds is a
measured total for an area, whatever the quantity, so it is named for that.

Everything moves with the table: the unique constraint, both foreign keys, the
primary key and all seven indexes. Postgres leaves those names alone on a plain
ALTER TABLE RENAME, which would have left the schema describing a table that no
longer exists and made the next autogenerate noisy.

Revision ID: 4c1d90fb7a35
Revises: 9f0aedb7d2e1
Create Date: 2026-07-28 06:30:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "4c1d90fb7a35"
down_revision: str | None = "9f0aedb7d2e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "area_consumption"
NEW = "area_totals"

# Every index on the table, by its unqualified suffix.
INDEX_SUFFIXES = (
    "area_kind",
    "area_code",
    "metric",
    "reference_year",
    "source_id",
    "document_version_id",
    "lookup",
)

CONSTRAINTS = (
    ("uq_{}_measure", "uq_{}_measure"),
    ("pk_{}", "pk_{}"),
    ("fk_{}_source_id_sources", "fk_{}_source_id_sources"),
    (
        "fk_{}_document_version_id_document_versions",
        "fk_{}_document_version_id_document_versions",
    ),
)


def _rename(old_table: str, new_table: str) -> None:
    op.rename_table(old_table, new_table)
    for suffix in INDEX_SUFFIXES:
        op.execute(f"ALTER INDEX ix_{old_table}_{suffix} RENAME TO ix_{new_table}_{suffix}")
    for old_pattern, new_pattern in CONSTRAINTS:
        old_name = old_pattern.format(old_table)
        new_name = new_pattern.format(new_table)
        op.execute(f"ALTER TABLE {new_table} RENAME CONSTRAINT {old_name} TO {new_name}")


def upgrade() -> None:
    _rename(OLD, NEW)


def downgrade() -> None:
    _rename(NEW, OLD)
