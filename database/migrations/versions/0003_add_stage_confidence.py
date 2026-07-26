"""add stage confidence to site

Revision ID: 8e9fdca6c1c0
Revises: 7d9fdba5b0b9
Create Date: 2026-07-26 12:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e9fdca6c1c0"
down_revision: str | None = "7d9fdba5b0b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sites",
        sa.Column("stage_confidence", sa.Float(), nullable=False, server_default="0.0"),
    )


def downgrade() -> None:
    op.drop_column("sites", "stage_confidence")
