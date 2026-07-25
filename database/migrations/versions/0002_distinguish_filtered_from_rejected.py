"""distinguish filtered from rejected records in connector runs

Revision ID: 7d9fdba5b0b9
Revises: 482380a47455
Create Date: 2026-07-25 22:04:34.813644+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "7d9fdba5b0b9"
down_revision: str | None = "482380a47455"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # A server default is required: the column is NOT NULL and existing run rows
    # would otherwise fail the constraint. Historical runs did not distinguish
    # filtering from rejection, so backfilling zero is the honest value.
    op.add_column(
        "connector_runs",
        sa.Column("items_filtered", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("connector_runs", "items_filtered")
