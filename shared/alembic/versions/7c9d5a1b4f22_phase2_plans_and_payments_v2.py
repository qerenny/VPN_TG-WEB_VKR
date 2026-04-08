"""Phase 2 plans and payments v2 tables

Revision ID: 7c9d5a1b4f22
Revises: 3f8c3b9a2d41
Create Date: 2026-03-14 20:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c9d5a1b4f22"
down_revision: Union[str, None] = "3f8c3b9a2d41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("price_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.CheckConstraint("duration_days > 0", name="ck_plans_duration_days_positive"),
        sa.CheckConstraint(
            "(price_amount IS NULL AND currency IS NULL) "
            "OR (price_amount IS NOT NULL AND currency IS NOT NULL)",
            name="ck_plans_price_currency_pair",
        ),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "subscription_grants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("duration_days", sa.Integer(), nullable=False),
        sa.Column("expires_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.CheckConstraint(
            "duration_days > 0",
            name="ck_subscription_grants_duration_days_positive",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "uq_subscription_grants_source",
        "subscription_grants",
        ["source_type", "source_ref"],
        unique=True,
    )
    op.create_index(
        "uq_subscription_grants_trial_active",
        "subscription_grants",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("source_type = 'trial' AND status <> 'canceled'"),
    )
    op.create_index(
        "uq_subscription_grants_news_bonus_active",
        "subscription_grants",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("source_type = 'news_bonus' AND status <> 'canceled'"),
    )

    op.create_table(
        "payment_orders",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fulfilled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("subscription_grant_id", sa.BigInteger(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["subscription_grant_id"],
            ["subscription_grants.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("subscription_grant_id"),
    )

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_payment_id", sa.Text(), nullable=False),
        sa.Column("provider_status", sa.Text(), nullable=False),
        sa.Column(
            "provider_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["payment_orders.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider", "provider_payment_id"),
    )

    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("attempt_id", sa.BigInteger(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_payment_id", sa.Text(), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=True),
        sa.Column("payload_hash", sa.Text(), nullable=False),
        sa.Column("provider_status", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["attempt_id"], ["payment_attempts.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "uq_payment_webhook_events_provider_payload_hash",
        "payment_webhook_events",
        ["provider", "payload_hash"],
        unique=True,
    )
    op.create_index(
        "uq_payment_webhook_events_provider_event_id",
        "payment_webhook_events",
        ["provider", "provider_event_id"],
        unique=True,
        postgresql_where=sa.text("provider_event_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_payment_webhook_events_provider_event_id",
        table_name="payment_webhook_events",
    )
    op.drop_index(
        "uq_payment_webhook_events_provider_payload_hash",
        table_name="payment_webhook_events",
    )
    op.drop_table("payment_webhook_events")

    op.drop_table("payment_attempts")
    op.drop_table("payment_orders")

    op.drop_index(
        "uq_subscription_grants_news_bonus_active",
        table_name="subscription_grants",
    )
    op.drop_index(
        "uq_subscription_grants_trial_active",
        table_name="subscription_grants",
    )
    op.drop_index("uq_subscription_grants_source", table_name="subscription_grants")
    op.drop_table("subscription_grants")

    op.drop_table("plans")
