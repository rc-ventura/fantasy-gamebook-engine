"""Add account, campaign.account_id FK, and session_lease (slice 004).

Revision: 0002
Branch label: None
Parent: 0001

New tables:
  account       (id UUID PK, sub TEXT UNIQUE, created_at TIMESTAMPTZ)
  session_lease (campaign_id PK/FK→campaign, lease_token, acquired_at,
                 expires_at, holder_account_id FK→account)

Altered tables:
  campaign — adds nullable ``account_id`` FK→account (nullable for backward
             compat with existing dev rows; new rows require it via app logic).

Index:
  ix_session_lease_expires_at — for TTL cleanup queries.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # account — the player identity (PII-minimal: sub + created_at only)
    # ------------------------------------------------------------------
    op.create_table(
        "account",
        sa.Column("id", sa.Text, primary_key=True),
        # OIDC subject claim — the only external identifier stored
        sa.Column("sub", sa.Text, nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index("ix_account_sub", "account", ["sub"], unique=True)

    # ------------------------------------------------------------------
    # campaign — add account_id FK (nullable for backward compat)
    # ------------------------------------------------------------------
    op.add_column(
        "campaign",
        sa.Column(
            "account_id",
            sa.Text,
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=True,  # nullable: existing dev rows have no account
        ),
    )
    op.create_index("ix_campaign_account_id", "campaign", ["account_id"])

    # ------------------------------------------------------------------
    # session_lease — single active session per campaign
    # ------------------------------------------------------------------
    op.create_table(
        "session_lease",
        sa.Column(
            "campaign_id",
            sa.Text,
            sa.ForeignKey("campaign.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("lease_token", sa.Text, nullable=False),
        sa.Column(
            "acquired_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "holder_account_id",
            sa.Text,
            sa.ForeignKey("account.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_session_lease_expires_at", "session_lease", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_session_lease_expires_at", table_name="session_lease")
    op.drop_table("session_lease")
    op.drop_index("ix_campaign_account_id", table_name="campaign")
    op.drop_column("campaign", "account_id")
    op.drop_index("ix_account_sub", table_name="account")
    op.drop_table("account")
