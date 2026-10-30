"""add followup delivery attempts and scheduling state

Revision ID: d71a9e84b2c1
Revises: 012e8b346d5b
Create Date: 2026-10-30 17:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d71a9e84b2c1"
down_revision: Union[str, None] = "012e8b346d5b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add scheduling, approval, and delivery tracking columns to follow_ups
    op.add_column(
        "follow_ups",
        sa.Column(
            "approval_status",
            sa.String(length=50),
            server_default="PENDING_APPROVAL",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_follow_ups_approval_status"),
        "follow_ups",
        ["approval_status"],
        unique=False,
    )

    op.add_column(
        "follow_ups",
        sa.Column(
            "delivery_status",
            sa.String(length=50),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_follow_ups_delivery_status"),
        "follow_ups",
        ["delivery_status"],
        unique=False,
    )

    op.add_column(
        "follow_ups",
        sa.Column("delivery_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_follow_ups_delivery_id"),
        "follow_ups",
        ["delivery_id"],
        unique=False,
    )

    op.add_column(
        "follow_ups",
        sa.Column(
            "schedule_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "follow_ups",
        sa.Column(
            "current_attempt",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "follow_ups",
        sa.Column(
            "max_retries",
            sa.Integer(),
            server_default="3",
            nullable=False,
        ),
    )

    op.add_column(
        "follow_ups",
        sa.Column(
            "n8n_dispatch_status",
            sa.String(length=50),
            server_default="PENDING",
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_follow_ups_n8n_dispatch_status"),
        "follow_ups",
        ["n8n_dispatch_status"],
        unique=False,
    )

    op.add_column(
        "follow_ups",
        sa.Column("n8n_dispatch_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "follow_ups",
        sa.Column(
            "n8n_dispatched_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # 2. Create follow_up_delivery_attempts table with unique constraints
    json_type = (
        postgresql.JSONB(astext_type=sa.Text())
        .with_variant(sa.JSON(), "sqlite")
    )

    op.create_table(
        "follow_up_delivery_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("follow_up_id", sa.String(length=36), nullable=False),
        sa.Column("delivery_id", sa.String(length=64), nullable=False),
        sa.Column(
            "schedule_version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "provider",
            sa.String(length=50),
            server_default="mock",
            nullable=False,
        ),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("recipient", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "retryable",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("response_payload", json_type, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["follow_up_id"],
            ["follow_ups.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "attempt_id",
            name="uq_follow_up_delivery_attempts_attempt_id",
        ),
        sa.UniqueConstraint(
            "delivery_id",
            "attempt",
            name="uq_follow_up_delivery_attempts_deliv_attempt",
        ),
    )
    op.create_index(
        op.f("ix_follow_up_delivery_attempts_follow_up_id"),
        "follow_up_delivery_attempts",
        ["follow_up_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_follow_up_delivery_attempts_delivery_id"),
        "follow_up_delivery_attempts",
        ["delivery_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_follow_up_delivery_attempts_attempt_id"),
        "follow_up_delivery_attempts",
        ["attempt_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_follow_up_delivery_attempts_status"),
        "follow_up_delivery_attempts",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_follow_up_delivery_attempts_status"),
        table_name="follow_up_delivery_attempts",
    )
    op.drop_index(
        op.f("ix_follow_up_delivery_attempts_attempt_id"),
        table_name="follow_up_delivery_attempts",
    )
    op.drop_index(
        op.f("ix_follow_up_delivery_attempts_delivery_id"),
        table_name="follow_up_delivery_attempts",
    )
    op.drop_index(
        op.f("ix_follow_up_delivery_attempts_follow_up_id"),
        table_name="follow_up_delivery_attempts",
    )
    op.drop_table("follow_up_delivery_attempts")

    op.drop_index(
        op.f("ix_follow_ups_n8n_dispatch_status"),
        table_name="follow_ups",
    )
    op.drop_column("follow_ups", "n8n_dispatched_at")
    op.drop_column("follow_ups", "n8n_dispatch_error")
    op.drop_column("follow_ups", "n8n_dispatch_status")
    op.drop_column("follow_ups", "max_retries")
    op.drop_column("follow_ups", "current_attempt")
    op.drop_column("follow_ups", "schedule_version")
    op.drop_index(
        op.f("ix_follow_ups_delivery_id"),
        table_name="follow_ups",
    )
    op.drop_column("follow_ups", "delivery_id")
    op.drop_index(
        op.f("ix_follow_ups_delivery_status"),
        table_name="follow_ups",
    )
    op.drop_column("follow_ups", "delivery_status")
    op.drop_index(
        op.f("ix_follow_ups_approval_status"),
        table_name="follow_ups",
    )
    op.drop_column("follow_ups", "approval_status")
