from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class ReferralReward(SQLModel, table=True):
    __tablename__ = "referral_rewards"
    __table_args__ = (
        UniqueConstraint(
            "beneficiary_user_id",
            "trigger_type",
            "trigger_ref",
            name="uq_referral_rewards_trigger",
        ),
        UniqueConstraint(
            "subscription_grant_id",
            name="uq_referral_rewards_grant",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    referral_edge_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("referral_edges.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    beneficiary_user_id: int = Field(
        sa_column=Column(
            BigInteger,
            ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    referral_reward_rule_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("referral_reward_rules.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    trigger_type: str = Field(sa_column=Column(Text, nullable=False))
    trigger_ref: str = Field(sa_column=Column(Text, nullable=False))
    reward_days: int = Field(sa_column=Column(Integer, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    applied_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    canceled_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    subscription_grant_id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            ForeignKey("subscription_grants.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    metadata_json: dict = Field(
        default_factory=dict,
        sa_column=Column("metadata", JSON, nullable=False),
    )
