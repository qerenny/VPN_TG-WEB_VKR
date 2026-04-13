from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import and_, desc, func as sa_func, select

from shared.config.database.session import get_db_session
from shared.config.settings import get_effective_product_feature_settings
from shared.config.config import (
    BACKEND_TELEGRAM_SUBSCRIPTION_LINK,
    BACKEND_TELEGRAM_TRAFFIC_LIMITED_SUBSCRIPTION_LINK,
    BOT_REFERRAL_LINK,
)
from shared.constants.payments import (
    ORDER_STATUS_FULFILLED,
    PLAN_KIND_PAID,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING_PAYMENT,
    RUNTIME_PAYMENT_STATUS_PAID,
    RUNTIME_PAYMENT_STATUS_PENDING,
)
from shared.models.growth.referral_edge_model import ReferralEdge
from shared.models.growth.referral_reward_model import ReferralReward
from shared.models.access.access_grant_model import AccessGrant
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.payments.plan_model import Plan
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.traffic.traffic_state_model import TrafficState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.infrastructure.access.access_registry_repository import AccessRegistryRepository
from shared.utils.access_template_labels import format_access_template_label
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_TRAFFIC_LIMITED
from shared.utils.timestamp_utils import TimestampUtils


@dataclass(frozen=True, slots=True)
class AccountProfileSnapshot:
    display_name: str | None
    timezone: str | None
    locale: str | None
    marketing_opt_in: bool
    preferred_contact_email: str | None
    auth_email: str | None
    email_verified: bool


class AccountService:
    def __init__(
        self,
        *,
        timestamp: TimestampUtils,
        access_registry_repository: AccessRegistryRepository | None = None,
    ) -> None:
        self.timestamp = timestamp
        self.access_registry_repository = access_registry_repository

    async def get_profile(self, *, user_id: int) -> AccountProfileSnapshot:
        async with get_db_session() as session:
            web_account = await self._get_web_account(session, user_id)
            profile = await session.get(UserProfile, int(user_id))

        return AccountProfileSnapshot(
            display_name=getattr(profile, "display_name", None),
            timezone=getattr(profile, "timezone", None),
            locale=getattr(profile, "locale", None),
            marketing_opt_in=bool(getattr(profile, "marketing_opt_in", False)),
            preferred_contact_email=(
                None if web_account is not None else getattr(profile, "preferred_contact_email", None)
            ),
            auth_email=str(web_account.email) if web_account is not None else None,
            email_verified=bool(web_account and web_account.email_verified_at is not None),
        )

    async def update_profile(
        self,
        *,
        user_id: int,
        display_name: str | None,
        timezone_name: str | None,
        locale: str | None,
        marketing_opt_in: bool | None,
        preferred_contact_email: str | None,
    ) -> AccountProfileSnapshot:
        now = datetime.now(timezone.utc)
        async with get_db_session() as session:
            web_account = await self._get_web_account(session, user_id)
            profile = await session.get(UserProfile, int(user_id))
            if profile is None:
                profile = UserProfile(
                    user_id=int(user_id),
                    created_at=now,
                    updated_at=now,
                    display_name=None,
                    timezone=None,
                    locale=None,
                    marketing_opt_in=False,
                    preferred_contact_email=None,
                )

            profile.display_name = self._normalize_optional_text(display_name)
            profile.timezone = self._normalize_optional_text(timezone_name)
            profile.locale = self._normalize_optional_text(locale)
            if marketing_opt_in is not None:
                profile.marketing_opt_in = bool(marketing_opt_in)
            normalized_contact_email = (
                None
                if web_account is not None
                else self._normalize_optional_email(preferred_contact_email)
            )
            if normalized_contact_email is not None:
                await self._ensure_preferred_contact_email_available(
                    session=session,
                    user_id=int(user_id),
                    normalized_email=normalized_contact_email,
                )
            profile.preferred_contact_email = normalized_contact_email
            profile.updated_at = now
            session.add(profile)
            await session.commit()

        return await self.get_profile(user_id=user_id)

    async def get_referral_stats(self, *, user_id: int) -> dict:
        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        and_(
                            TelegramAccount.user_id == int(user_id),
                            TelegramAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()

            invited_count = (
                await session.execute(
                    select(sa_func.count(ReferralEdge.id)).where(
                        ReferralEdge.referrer_user_id == int(user_id)
                    )
                )
            ).scalar_one()

            paid_count = (
                await session.execute(
                    select(sa_func.count(ReferralReward.id)).where(
                        ReferralReward.beneficiary_user_id == int(user_id),
                        ReferralReward.trigger_type == "first_paid_order",
                        ReferralReward.canceled_at.is_(None),
                    )
                )
            ).scalar_one()

            pending_days = (
                await session.execute(
                    select(sa_func.coalesce(sa_func.sum(ReferralReward.reward_days), 0)).where(
                        ReferralReward.beneficiary_user_id == int(user_id),
                        ReferralReward.applied_at.is_(None),
                        ReferralReward.canceled_at.is_(None),
                    )
                )
            ).scalar_one()

        tg_id = int(telegram_account.telegram_id) if telegram_account else None
        referral_link = f"{BOT_REFERRAL_LINK}{tg_id}" if tg_id else None

        return {
            "invited_count": int(invited_count or 0),
            "paid_count": int(paid_count or 0),
            "pending_days": int(pending_days or 0),
            "referral_link": referral_link,
            "telegram_linked": telegram_account is not None,
        }

    async def get_links(self, *, user_id: int) -> dict:
        async with get_db_session() as session:
            web_account = await self._get_web_account(session, user_id)
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        and_(
                            TelegramAccount.user_id == int(user_id),
                            TelegramAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()

        return {
            "web": {
                "linked": web_account is not None,
                "email": str(web_account.email) if web_account is not None else None,
                "email_verified": bool(web_account and web_account.email_verified_at is not None),
                "linked_at": self._isoformat(getattr(web_account, "linked_at", None)),
                "last_login_at": self._isoformat(getattr(web_account, "last_login_at", None)),
            },
            "telegram": {
                "linked": telegram_account is not None,
                "telegram_id": int(telegram_account.telegram_id) if telegram_account else None,
                "username": getattr(telegram_account, "username", None),
                "linked_at": self._isoformat(getattr(telegram_account, "linked_at", None)),
                "first_seen_at": self._isoformat(getattr(telegram_account, "first_seen_at", None)),
                "last_seen_at": self._isoformat(getattr(telegram_account, "last_seen_at", None)),
            },
        }

    async def get_access_grants(self, *, user_id: int, limit: int = 20) -> list[dict]:
        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            expired_rows = (
                await session.execute(
                    select(AccessGrant).where(
                        AccessGrant.user_id == int(user_id),
                        AccessGrant.status == "active",
                        AccessGrant.expires_at.is_not(None),
                        AccessGrant.expires_at < now,
                    )
                )
            ).scalars().all()
            for row in expired_rows:
                row.status = "expired"
                row.metadata_json = {**dict(row.metadata_json or {}), "expired_at": now.isoformat()}
                session.add(row)
            if expired_rows:
                await session.commit()
            rows = (
                await session.execute(
                    select(AccessGrant)
                    .where(AccessGrant.user_id == int(user_id))
                    .order_by(desc(AccessGrant.created_at), desc(AccessGrant.id))
                    .limit(max(1, min(int(limit), 100)))
                )
            ).scalars().all()

        return [self._serialize_access_grant(row) for row in rows]

    async def get_subscriptions(self, *, user_id: int) -> dict:
        async with get_db_session() as session:
            standard_client = (
                await session.execute(
                    select(VpnClient).where(
                        VpnClient.user_id == int(user_id),
                        VpnClient.scope == PRODUCT_SCOPE_STANDARD,
                        VpnClient.deactivated_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            traffic_limited_client = (
                await session.execute(
                    select(VpnClient).where(
                        VpnClient.user_id == int(user_id),
                        VpnClient.scope == PRODUCT_SCOPE_TRAFFIC_LIMITED,
                        VpnClient.deactivated_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            standard_state = await session.get(SubscriptionState, int(user_id))
            traffic_limited_state = (
                await session.get(TrafficState, int(traffic_limited_client.id))
                if traffic_limited_client is not None
                else None
            )

        standard_expires_at = getattr(standard_state, "current_expires_at", None)
        standard_expires_at_ms = self._datetime_to_legacy_ms(standard_expires_at)
        traffic_limited_expires_at = getattr(traffic_limited_state, "expires_at", None)
        traffic_limited_expires_at_ms = self._datetime_to_legacy_ms(traffic_limited_expires_at)
        traffic_limited_remaining = int(getattr(traffic_limited_state, "remaining_bytes", 0) or 0)
        traffic_limited_blocked = bool(getattr(traffic_limited_state, "is_blocked", False))
        standard_is_active = bool(
            standard_expires_at_ms and int(standard_expires_at_ms) > self.timestamp.current_timestamp()
        )
        traffic_limited_is_active = bool(
            traffic_limited_client is not None
            and not traffic_limited_blocked
            and traffic_limited_remaining > 0
            and (
                traffic_limited_expires_at_ms is None
                or int(traffic_limited_expires_at_ms) > self.timestamp.current_timestamp()
            )
        )

        registry_managed = False
        registry_entry = None
        if self.access_registry_repository is not None:
            registry_entry = await self.access_registry_repository.find_matching_entry_for_user(user_id=int(user_id))
            registry_managed = registry_entry is not None

        return {
            "standard": {
                "scope": PRODUCT_SCOPE_STANDARD,
                "is_active": standard_is_active,
                "expires_at": self._isoformat(standard_expires_at),
                "human_view_expiration_remaining": (
                    self.timestamp.calculate_time_difference(int(standard_expires_at_ms))
                    if standard_expires_at_ms
                    else None
                ),
                "subscription_import_url": (
                    f"{BACKEND_TELEGRAM_SUBSCRIPTION_LINK}?uuid={standard_client.subscription_external_id}"
                    if standard_client is not None and standard_is_active
                    else None
                ),
                "external_email": getattr(standard_client, "external_email", None),
                "subscription_external_id": getattr(
                    standard_client, "subscription_external_id", None
                ),
            },
            "traffic_limited": {
                "scope": PRODUCT_SCOPE_TRAFFIC_LIMITED,
                "is_active": traffic_limited_is_active,
                "expires_at": self._isoformat(traffic_limited_expires_at),
                "human_view_expiration_remaining": (
                    self.timestamp.calculate_time_difference(int(traffic_limited_expires_at_ms))
                    if traffic_limited_expires_at_ms
                    else None
                ),
                "subscription_import_url": (
                    f"{BACKEND_TELEGRAM_TRAFFIC_LIMITED_SUBSCRIPTION_LINK}?uuid={traffic_limited_client.subscription_external_id}"
                    if traffic_limited_client is not None and traffic_limited_is_active
                    else None
                ),
                "external_email": getattr(traffic_limited_client, "external_email", None),
                "subscription_external_id": getattr(
                    traffic_limited_client, "subscription_external_id", None
                ),
                "traffic_allocated_bytes": int(
                    getattr(traffic_limited_state, "allocated_bytes", 0) or 0
                )
                if traffic_limited_state is not None
                else None,
                "traffic_used_bytes": int(getattr(traffic_limited_state, "used_bytes", 0) or 0)
                if traffic_limited_state is not None
                else None,
                "traffic_remaining_bytes": traffic_limited_remaining if traffic_limited_state is not None else None,
                "human_view_traffic_allocated": self._human_view_traffic_bytes(
                    getattr(traffic_limited_state, "allocated_bytes", None)
                ),
                "human_view_traffic_used": self._human_view_traffic_bytes(
                    getattr(traffic_limited_state, "used_bytes", None)
                ),
                "human_view_traffic_remaining": self._human_view_traffic_bytes(
                    getattr(traffic_limited_state, "remaining_bytes", None)
                ),
            },
            "access_policy": {
                "registry_managed": registry_managed,
                "registry_template_code": getattr(registry_entry, "template_code", None),
                "registry_template_label": (
                    format_access_template_label(str(registry_entry.template_code))
                    if registry_entry is not None
                    else None
                ),
            },
        }

    @staticmethod
    def _serialize_access_grant(row: AccessGrant) -> dict:
        return {
            "id": int(row.id),
            "template_code": str(row.template_code),
            "template_label": format_access_template_label(str(row.template_code)),
            "scope": str(row.scope),
            "entitlement_kind": str(row.entitlement_kind),
            "source_type": str(row.source_type),
            "source_ref": row.source_ref,
            "status": str(row.status),
            "expires_at": row.expires_at.isoformat() if row.expires_at is not None else None,
            "quota_bytes": int(row.quota_bytes) if row.quota_bytes is not None else None,
            "granted_by_user_id": int(row.granted_by_user_id) if row.granted_by_user_id is not None else None,
            "created_at": row.created_at.isoformat(),
            "activated_at": row.activated_at.isoformat() if row.activated_at is not None else None,
            "revoked_at": row.revoked_at.isoformat() if getattr(row, "revoked_at", None) is not None else None,
            "metadata": dict(row.metadata_json or {}),
        }

    async def get_payments(self, *, user_id: int, limit: int = 20) -> list[dict]:
        async with get_db_session() as session:
            rows = (
                await session.execute(
                    select(PaymentOrder, Plan, PaymentAttempt)
                    .join(Plan, Plan.id == PaymentOrder.plan_id)
                    .outerjoin(PaymentAttempt, PaymentAttempt.order_id == PaymentOrder.id)
                    .where(PaymentOrder.user_id == int(user_id))
                    .order_by(desc(PaymentOrder.created_at), desc(PaymentAttempt.created_at))
                    .limit(max(1, min(int(limit), 100)))
                )
            ).all()

        payments: list[dict] = []
        seen_order_ids: set[int] = set()
        for order, plan, attempt in rows:
            if int(order.id) in seen_order_ids:
                continue
            seen_order_ids.add(int(order.id))
            payments.append(
                {
                    "order_id": int(order.id),
                    "plan_code": str(plan.code),
                    "plan_name": str(plan.name),
                    "scope": str(plan.scope),
                    "entitlement_kind": str(plan.entitlement_kind),
                    "status": str(order.status),
                    "runtime_status": self._runtime_order_status(order.status),
                    "amount": str(order.amount),
                    "currency": str(order.currency),
                    "provider": getattr(attempt, "provider", None),
                    "provider_payment_id": getattr(attempt, "provider_payment_id", None),
                    "provider_status": getattr(attempt, "provider_status", None),
                    "created_at": self._isoformat(order.created_at),
                    "paid_at": self._isoformat(order.paid_at),
                    "fulfilled_at": self._isoformat(order.fulfilled_at),
                }
            )
        return payments

    async def get_plan_catalog(self) -> dict:
        features = get_effective_product_feature_settings()
        async with get_db_session() as session:
            plans = (
                await session.execute(
                    select(Plan)
                    .where(
                        Plan.is_active.is_(True),
                        Plan.kind == PLAN_KIND_PAID,
                        Plan.price_amount.is_not(None),
                    )
                    .order_by(Plan.scope.asc(), Plan.duration_days.asc(), Plan.price_amount.asc())
                )
            ).scalars().all()

        standard: list[dict] = []
        traffic_limited: list[dict] = []

        for plan in plans:
            item = {
                "code": str(plan.code),
                "name": str(plan.name),
                "scope": str(plan.scope),
                "entitlement_kind": str(plan.entitlement_kind),
                "duration_days": int(plan.duration_days),
                "quota_bytes": int(plan.quota_bytes) if plan.quota_bytes is not None else None,
                "price_amount": str(plan.price_amount),
                "currency": str(plan.currency or ""),
                "human_view_traffic_quota": self._human_view_traffic_bytes(plan.quota_bytes),
            }
            if str(plan.scope) == PRODUCT_SCOPE_TRAFFIC_LIMITED:
                if features.traffic_limited_config_enabled:
                    traffic_limited.append(item)
            else:
                if features.standard_config_enabled:
                    standard.append(item)

        return {
            "standard": standard,
            "traffic_limited": traffic_limited,
        }

    async def _get_web_account(self, session, user_id: int) -> WebAccount | None:
        result = await session.execute(
            select(WebAccount).where(
                and_(
                    WebAccount.user_id == int(user_id),
                    WebAccount.revoked_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()

    async def _ensure_preferred_contact_email_available(
        self,
        *,
        session,
        user_id: int,
        normalized_email: str,
    ) -> None:
        existing_web_account = (
            await session.execute(
                select(WebAccount).where(
                    and_(
                        WebAccount.email == normalized_email,
                        WebAccount.user_id != int(user_id),
                        WebAccount.revoked_at.is_(None),
                    )
                )
            )
        ).scalar_one_or_none()
        if existing_web_account is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already attached to another account",
            )

        claimed_profiles = (
            await session.execute(
                select(UserProfile).where(
                    and_(
                        UserProfile.preferred_contact_email == normalized_email,
                        UserProfile.user_id != int(user_id),
                    )
                )
            )
        ).scalars().all()
        for claimed_profile in claimed_profiles:
            app_user = await session.get(AppUser, int(claimed_profile.user_id))
            if app_user is None or app_user.deleted_at is not None:
                continue
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already attached to another account",
            )

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        normalized = str(value or "").strip()
        return normalized or None

    @staticmethod
    def _normalize_optional_email(value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        return normalized or None

    @staticmethod
    def _isoformat(value: datetime | None) -> str | None:
        if value is None:
            return None
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _datetime_to_legacy_ms(value: datetime | None) -> int | None:
        if value is None:
            return None
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return int(normalized.astimezone(timezone.utc).timestamp() * 1000)

    @staticmethod
    def _human_view_traffic_bytes(value: int | None) -> str | None:
        if value is None:
            return None
        bytes_value = int(value)
        gib = 1024 * 1024 * 1024
        mib = 1024 * 1024
        kib = 1024
        if bytes_value >= gib:
            gb_value = bytes_value / gib
            return f"{int(gb_value)} GB" if bytes_value % gib == 0 else f"{gb_value:.1f} GB"
        if bytes_value >= mib:
            mb_value = bytes_value / mib
            return f"{int(mb_value)} MB" if bytes_value % mib == 0 else f"{mb_value:.1f} MB"
        if bytes_value >= kib:
            kb_value = bytes_value / kib
            return f"{int(kb_value)} KB" if bytes_value % kib == 0 else f"{kb_value:.1f} KB"
        return f"{bytes_value} B"

    @staticmethod
    def _runtime_order_status(order_status: str | None) -> str:
        normalized = str(order_status or "").strip().lower()
        if normalized in {ORDER_STATUS_PAID, ORDER_STATUS_FULFILLED}:
            return RUNTIME_PAYMENT_STATUS_PAID
        if normalized == ORDER_STATUS_PENDING_PAYMENT:
            return RUNTIME_PAYMENT_STATUS_PENDING
        return normalized or RUNTIME_PAYMENT_STATUS_PENDING
