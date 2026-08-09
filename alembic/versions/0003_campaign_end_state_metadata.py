"""Add campaign run-name and end-state metadata columns (issues #14/#25).

Revision: 0003
Branch label: None
Parent: 0002

Altered tables:
  campaign — adds three nullable columns so the DB-backed CampaignRegistry
             (ADR-025, spec-006 T037) can be the source of truth for what the
             in-memory registry used to hold:
    name         TEXT         — optional run name (POST /me/game body.name)
    ended_reason TEXT         — "death" | "victory" (graveyard display)
    ended_at     TIMESTAMPTZ  — when the run ended

All nullable: existing rows (and rows created lazily by the engine's
``_ensure_campaign``) need no backfill.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("campaign", sa.Column("name", sa.Text, nullable=True))
    op.add_column("campaign", sa.Column("ended_reason", sa.Text, nullable=True))
    op.add_column("campaign", sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("campaign", "ended_at")
    op.drop_column("campaign", "ended_reason")
    op.drop_column("campaign", "name")
