"""Phase 3 growth v2 tables

Revision ID: 9b3a4e7f6c11
Revises: 7c9d5a1b4f22
Create Date: 2026-03-14 23:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9b3a4e7f6c11"
down_revision: Union[str, None] = "7c9d5a1b4f22"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "promo_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.BigInteger(), nullable=True),
        sa.Column("duration_days_override", sa.Integer(), nullable=True),
        sa.Column("max_redemptions", sa.Integer(), nullable=True),
        sa.Column("per_user_limit", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "duration_days_override IS NULL OR duration_days_override > 0",
            name="ck_promo_codes_duration_days_override_positive",
        ),
        sa.CheckConstraint(
            "max_redemptions IS NULL OR max_redemptions >= 0",
            name="ck_promo_codes_max_redemptions_non_negative",
        ),
        sa.CheckConstraint(
            "per_user_limit > 0",
            name="ck_promo_codes_per_user_limit_positive",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "promo_redemptions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("promo_code_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subscription_grant_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["promo_code_id"], ["promo_codes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["subscription_grant_id"],
            ["subscription_grants.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("promo_code_id", "user_id", name="uq_promo_redemptions_code_user"),
        sa.UniqueConstraint("subscription_grant_id", name="uq_promo_redemptions_grant"),
    )

    op.create_table(
        "referral_edges",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("referrer_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referred_user_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "referrer_user_id <> referred_user_id",
            name="ck_referral_edges_distinct_users",
        ),
        sa.ForeignKeyConstraint(["referrer_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["referred_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("referred_user_id", name="uq_referral_edges_referred_user"),
        sa.UniqueConstraint(
            "referrer_user_id",
            "referred_user_id",
            name="uq_referral_edges_pair",
        ),
    )

    op.create_table(
        "referral_reward_rules",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("paid_referrals_threshold", sa.Integer(), nullable=False),
        sa.Column("reward_days", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.CheckConstraint(
            "paid_referrals_threshold > 0",
            name="ck_referral_reward_rules_threshold_positive",
        ),
        sa.CheckConstraint(
            "reward_days > 0",
            name="ck_referral_reward_rules_reward_days_positive",
        ),
        sa.UniqueConstraint("paid_referrals_threshold"),
    )

    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("referral_edge_id", sa.BigInteger(), nullable=True),
        sa.Column("beneficiary_user_id", sa.BigInteger(), nullable=False),
        sa.Column("referral_reward_rule_id", sa.BigInteger(), nullable=True),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("trigger_ref", sa.Text(), nullable=False),
        sa.Column("reward_days", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("subscription_grant_id", sa.BigInteger(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.CheckConstraint(
            "reward_days > 0",
            name="ck_referral_rewards_reward_days_positive",
        ),
        sa.ForeignKeyConstraint(["referral_edge_id"], ["referral_edges.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["beneficiary_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["referral_reward_rule_id"],
            ["referral_reward_rules.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["subscription_grant_id"],
            ["subscription_grants.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "beneficiary_user_id",
            "trigger_type",
            "trigger_ref",
            name="uq_referral_rewards_trigger",
        ),
        sa.UniqueConstraint("subscription_grant_id", name="uq_referral_rewards_grant"),
    )


def downgrade() -> None:
    op.drop_table("referral_rewards")
    op.drop_table("referral_reward_rules")
    op.drop_table("referral_edges")
    op.drop_table("promo_redemptions")
    op.drop_table("promo_codes")
