from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import traceback
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import aliased

from backend.admin.types import AdminPrincipal
from shared.config.config import (
    BACKEND_TELEGRAM_SUBSCRIPTION_LINK,
    BACKEND_TELEGRAM_WHITELIST_SUBSCRIPTION_LINK,
    BOT_SUPPORT_TG_LINK,
    PRODUCT_REDIS_PREFIX,
    REDIS_PAYMENT_DEDUPE_PREFIX,
    REDIS_PAYMENT_DEAD_LETTER_QUEUE_KEY,
    REDIS_PAYMENT_READY_QUEUE_KEY,
    REDIS_PAYMENT_RETRY_QUEUE_KEY,
)
from shared.config.database.session import get_db_session
from shared.config.settings import BackendSettings, RolloutFeatureFlags
from shared.constants.payments import (
    ORDER_STATUS_FULFILLED,
    ORDER_STATUS_PAID,
    ORDER_STATUS_PENDING_PAYMENT,
    PROVIDER_STATUS_PAID,
    RUNTIME_PAYMENT_STATUS_PAID,
    RUNTIME_PAYMENT_STATUS_PENDING,
)
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
    PaymentSnapshot,
)
from shared.infrastructure.growth_sync_service import GrowthSyncService
from shared.infrastructure.promos.promo_code_repository import (
    PromoCodeRepository,
)
from shared.infrastructure.referrals.referral_repository import (
    ReferralRepository,
    ReferralSnapshot,
)
from shared.infrastructure.users.telegram_user_repository import (
    TelegramUserRepository,
    TelegramUserSnapshot,
)
from shared.models.admin.admin_audit_log_model import AdminAuditLog
from shared.models.growth.promo_code_model import PromoCode as PromoCodeV2
from shared.models.growth.promo_redemption_model import PromoRedemption
from shared.models.growth.referral_edge_model import ReferralEdge
from shared.models.growth.referral_reward_model import ReferralReward
from shared.models.payments.payment_attempt_model import PaymentAttempt
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.traffic.traffic_state_model import TrafficState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_WHITELIST
from shared.utils.async_redis_client import AsyncRedisClient, RedisClientError
from shared.utils.jwt_encoder import JWTEncoder
from shared.utils.logging_utils import logger, send_telegram_alert
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.infrastructure.api.client_manager import ClientManager
from telegram_bot.services.payments.payment_queue_service import PaymentQueueService
from telegram_bot.services.referrals.referral_bonus_service import ReferralBonusService
from telegram_bot.services.subscriptions.subscription_flow_service import SubscriptionFlowService
from telegram_bot.services.subscriptions.subscription_provisioning_service import (
    SubscriptionProvisioningService,
)
from telegram_bot.services.subscriptions.whitelist_provisioning_service import (
    WhiteListProvisioningService,
)
from telegram_bot.services.subscriptions.whitelist_traffic_service import (
    WhiteListTrafficService,
)
from telegram_bot.services.subscriptions.whitelist_traffic_sync_service import (
    WhiteListTrafficSyncService,
)
from telegram_bot.services.users.user_subscription_info_service import UserSubscriptionInfoService
from telegram_bot.shared.utils.json_builder import JSONBuilder
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator


ALERTED_ADMIN_ACTIONS = {
    "delete_user",
    "block_user",
    "recreate_client",
    "retry_payment_dlq",
}


class AdminService:
    def __init__(
        self,
        settings: BackendSettings,
        user_repository: TelegramUserRepository,
        payment_repository: PaymentRepository,
        referral_repository: ReferralRepository,
        promo_code_repository: PromoCodeRepository,
        jwt_encoder: JWTEncoder,
        timestamp: TimestampUtils,
    ):
        self.settings = settings
        self.user_repository = user_repository
        self.payment_repository = payment_repository
        self.referral_repository = referral_repository
        self.promo_code_repository = promo_code_repository
        self.jwt_encoder = jwt_encoder
        self.timestamp = timestamp
        self.uuid_generator = UUIDGenerator()

        self.client_manager = ClientManager(
            repo=user_repository,
            timestamp=timestamp,
            jsonutils=JSONBuilder(),
            uuidgen=self.uuid_generator,
        )
        self.subscription_provisioning_service = SubscriptionProvisioningService(
            repo=user_repository,
            timestamputils=timestamp,
            client=self.client_manager,
            jwt_encoder=jwt_encoder,
            uuidgen=self.uuid_generator,
        )
        self.user_subscription_info_service = UserSubscriptionInfoService(
            repo=user_repository,
            timestamp=timestamp,
        )
        self.subscription_flow_service = SubscriptionFlowService(
            repo=user_repository,
            subscription_service=self.subscription_provisioning_service,
            instruction=None,
            user_subscription_info_service=self.user_subscription_info_service,
            timestamp=timestamp,
        )
        self.whitelist_provisioning_service = WhiteListProvisioningService(
            repo=user_repository,
            timestamp=timestamp,
            client_manager=self.client_manager,
            uuidgen=self.uuid_generator,
        )
        self.whitelist_traffic_service = WhiteListTrafficService(
            provisioning_service=self.whitelist_provisioning_service,
            timestamp=timestamp,
            client_manager=self.client_manager,
        )
        self.whitelist_traffic_sync_service = WhiteListTrafficSyncService(
            client_manager=self.client_manager,
        )
        self.referral_bonus_service = ReferralBonusService(
            repo_referrals=referral_repository,
            repo_user=user_repository,
            timestamp=timestamp,
            client=self.client_manager,
            sync_service=GrowthSyncService(
                RolloutFeatureFlags(db_dual_write_growth=True)
            ),
        )

    async def get_overview(self, redis_client: AsyncRedisClient | None) -> dict[str, Any]:
        now = datetime.now(timezone.utc)

        async with get_db_session() as session:
            total_users = (
                await session.execute(
                    select(func.count(AppUser.id)).where(
                        AppUser.deleted_at.is_(None)
                    )
                )
            ).scalar_one()
            active_users = (
                await session.execute(
                    select(func.count(SubscriptionState.user_id)).where(
                        SubscriptionState.current_expires_at.is_not(None),
                        SubscriptionState.current_expires_at > now,
                        SubscriptionState.blocked_at.is_(None),
                    )
                )
            ).scalar_one()
            blocked_users = (
                await session.execute(
                    select(func.count(AppUser.id)).where(
                        AppUser.deleted_at.is_(None),
                        AppUser.blocked_at.is_not(None),
                    )
                )
            ).scalar_one()
            pending_payments = (
                await session.execute(
                    select(func.count(PaymentOrder.id)).where(
                        PaymentOrder.status.in_((ORDER_STATUS_PENDING_PAYMENT, ORDER_STATUS_PAID))
                    )
                )
            ).scalar_one()
            last_day_threshold = datetime.now(timezone.utc).replace(microsecond=0)
            last_day_threshold = last_day_threshold.replace(hour=0, minute=0, second=0)
            audit_last_day = (
                await session.execute(
                    select(func.count(AdminAuditLog.id)).where(
                        AdminAuditLog.created_at >= last_day_threshold
                    )
                )
            ).scalar_one()

        queue_stats = await self._get_queue_stats(redis_client)
        return {
            "role": self.settings.admin.default_role,
            "stats": {
                "total_users": int(total_users or 0),
                "active_users": int(active_users or 0),
                "blocked_users": int(blocked_users or 0),
                "pending_payments": int(pending_payments or 0),
                "audit_records": int(audit_last_day or 0),
            },
            "queues": queue_stats,
            "cache": {
                "subscription_build_local": len(self._subscription_routes().subscription_cache.cache),
                "subscription_info_local": len(self._subscription_routes().subscription_info_cache.cache),
                "subscription_inflight": len(self._subscription_routes().subscription_inflight),
            },
            "features": {
                "subscription_source": "current",
                "payments_source": "current",
                "growth_source": "current",
                "vpn_topology_source": "current",
            },
        }

    async def search_users(self, query: str | None, limit: int = 25) -> list[dict[str, Any]]:
        normalized_query = str(query or "").strip()
        standard_client = aliased(VpnClient)
        whitelist_client = aliased(VpnClient)
        whitelist_state = aliased(TrafficState)

        async with get_db_session() as session:
            stmt = (
                select(
                    AppUser.id,
                    AppUser.created_at,
                    TelegramAccount.username,
                    TelegramAccount.telegram_id,
                    WebAccount.email,
                    AppUser.blocked_at,
                    SubscriptionState.current_expires_at,
                    standard_client.external_client_uuid,
                    standard_client.subscription_external_id,
                    standard_client.external_email,
                    whitelist_client.external_email,
                    whitelist_state.remaining_bytes,
                    whitelist_state.expires_at,
                    whitelist_state.is_blocked,
                )
                .select_from(AppUser)
                .outerjoin(
                    TelegramAccount,
                    (TelegramAccount.user_id == AppUser.id)
                    & TelegramAccount.revoked_at.is_(None),
                )
                .outerjoin(
                    WebAccount,
                    (WebAccount.user_id == AppUser.id)
                    & WebAccount.revoked_at.is_(None),
                )
                .outerjoin(SubscriptionState, SubscriptionState.user_id == AppUser.id)
                .outerjoin(
                    standard_client,
                    (standard_client.user_id == AppUser.id)
                    & standard_client.deactivated_at.is_(None)
                    & (standard_client.scope == PRODUCT_SCOPE_STANDARD),
                )
                .outerjoin(
                    whitelist_client,
                    (whitelist_client.user_id == AppUser.id)
                    & whitelist_client.deactivated_at.is_(None)
                    & (whitelist_client.scope == PRODUCT_SCOPE_WHITELIST),
                )
                .outerjoin(
                    whitelist_state,
                    whitelist_state.vpn_client_id == whitelist_client.id,
                )
                .where(AppUser.deleted_at.is_(None))
                .order_by(desc(AppUser.created_at))
                .limit(max(1, min(limit, 100)))
            )

            if normalized_query:
                filters = [
                    WebAccount.email.ilike(f"%{normalized_query}%"),
                    TelegramAccount.username.ilike(f"%{normalized_query}%"),
                    standard_client.external_email.ilike(f"%{normalized_query}%"),
                    standard_client.external_client_uuid.ilike(f"%{normalized_query}%"),
                    standard_client.subscription_external_id.ilike(f"%{normalized_query}%"),
                    whitelist_client.external_email.ilike(f"%{normalized_query}%"),
                ]
                if normalized_query.isdigit():
                    filters.append(TelegramAccount.telegram_id == int(normalized_query))
                    filters.append(AppUser.id == int(normalized_query))
                stmt = stmt.where(or_(*filters))

            rows = (await session.execute(stmt)).all()

        items: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for (
            user_id,
            created_at,
            username,
            tg_id,
            web_email,
            blocked_at,
            standard_expires_at,
            standard_uuid,
            standard_sub_id,
            standard_email,
            whitelist_email,
            whitelist_remaining_bytes,
            whitelist_expires_at,
            whitelist_is_blocked,
        ) in rows:
            items.append(
                self._serialize_user_summary(
                    user_id=int(user_id),
                    email=(
                        str(web_email or "").strip()
                        or str(standard_email or "").strip()
                        or str(whitelist_email or "").strip()
                        or f"user-{int(user_id)}"
                    ),
                    username=username,
                    tg_id=int(tg_id) if tg_id is not None else None,
                    uuid=str(standard_uuid or "") or None,
                    sub_id=str(standard_sub_id or "") or None,
                    created_at=created_at,
                    expiration_date=standard_expires_at,
                    has_web_account=bool(web_email),
                    has_telegram=tg_id is not None,
                    active_whitelist=self._is_whitelist_active_from_primitives(
                        remaining_bytes=whitelist_remaining_bytes,
                        expires_at=whitelist_expires_at,
                        is_blocked=whitelist_is_blocked,
                        now=now,
                    ),
                    blocked_at=blocked_at,
                )
            )
        return items

    async def get_user_360(self, user_id: int, redis_client: AsyncRedisClient | None) -> dict[str, Any]:
        normalized_user_id = int(user_id)

        async with get_db_session() as session:
            app_user = await session.get(AppUser, normalized_user_id)
            if app_user is None or app_user.deleted_at is not None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            telegram_account = await self._load_telegram_account(session, user_id=normalized_user_id)
            web_account = await self._load_web_account(session, user_id=normalized_user_id)
            user_profile = await session.get(UserProfile, normalized_user_id)
            subscription_state = await session.get(SubscriptionState, normalized_user_id)
            standard_client = (
                await session.execute(
                    select(VpnClient)
                    .where(
                        VpnClient.user_id == normalized_user_id,
                        VpnClient.scope == PRODUCT_SCOPE_STANDARD,
                        VpnClient.deactivated_at.is_(None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            whitelist_client = (
                await session.execute(
                    select(VpnClient)
                    .where(
                        VpnClient.user_id == normalized_user_id,
                        VpnClient.scope == PRODUCT_SCOPE_WHITELIST,
                        VpnClient.deactivated_at.is_(None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            whitelist_state = (
                await session.get(TrafficState, whitelist_client.id)
                if whitelist_client is not None
                else None
            )
            payment_orders = (
                await session.execute(
                    select(PaymentOrder, PaymentAttempt)
                    .outerjoin(PaymentAttempt, PaymentAttempt.order_id == PaymentOrder.id)
                    .where(PaymentOrder.user_id == normalized_user_id)
                    .order_by(desc(PaymentOrder.created_at))
                    .limit(20)
                )
            ).all()
            promo_redemptions = (
                await session.execute(
                    select(PromoRedemption, PromoCodeV2.code)
                    .join(PromoCodeV2, PromoCodeV2.id == PromoRedemption.promo_code_id)
                    .where(PromoRedemption.user_id == normalized_user_id)
                    .order_by(desc(PromoRedemption.redeemed_at))
                )
            ).all()
            referral_rewards = (
                await session.execute(
                    select(ReferralReward)
                    .where(ReferralReward.beneficiary_user_id == normalized_user_id)
                    .order_by(desc(ReferralReward.created_at))
                    .limit(20)
                )
            ).scalars().all()

        tg_id = int(telegram_account.telegram_id) if telegram_account is not None else None
        referral = await self.referral_repository.get(int(tg_id)) if tg_id is not None else None
        legacy_payments = [
            self._build_legacy_payment_from_v2(order, attempt, tg_id=int(tg_id or 0))
            for order, attempt in payment_orders
        ]
        subscription_link = await self._safe_subscription_link(int(tg_id)) if tg_id is not None else ""
        whitelist_subscription_link = (
            await self._safe_subscription_link(int(tg_id), scope=PRODUCT_SCOPE_WHITELIST)
            if tg_id is not None
            else ""
        )
        diagnostics = await self.get_user_diagnostics(normalized_user_id, redis_client)
        playbooks = await self.get_user_playbooks(normalized_user_id, redis_client, diagnostics=diagnostics)
        profile_email = (
            str(getattr(user_profile, "preferred_contact_email", "") or "").strip()
            or str(getattr(web_account, "email", "") or "").strip()
            or str(getattr(standard_client, "external_email", "") or "").strip()
            or str(getattr(whitelist_client, "external_email", "") or "").strip()
            or f"user-{normalized_user_id}"
        )
        standard_sub_id = getattr(standard_client, "subscription_external_id", None)

        return {
            "summary": self._serialize_user_summary(
                user_id=normalized_user_id,
                email=profile_email,
                username=getattr(telegram_account, "username", None),
                tg_id=tg_id,
                uuid=getattr(standard_client, "external_client_uuid", None),
                sub_id=standard_sub_id,
                created_at=app_user.created_at,
                expiration_date=getattr(subscription_state, "current_expires_at", None),
                has_web_account=web_account is not None,
                has_telegram=telegram_account is not None,
                active_whitelist=self._is_whitelist_active(whitelist_state),
                blocked_at=getattr(app_user, "blocked_at", None) or getattr(subscription_state, "blocked_at", None),
            ),
            "profile": {
                "user_id": normalized_user_id,
                "tg_id": tg_id,
                "email": profile_email,
                "auth_email": getattr(web_account, "email", None),
                "preferred_contact_email": getattr(user_profile, "preferred_contact_email", None),
                "uuid": str(getattr(standard_client, "external_client_uuid", "") or ""),
                "sub_id": str(standard_sub_id or ""),
                "login_date": self._datetime_to_iso(
                    getattr(telegram_account, "first_seen_at", None)
                    or getattr(web_account, "created_at", None)
                    or getattr(app_user, "created_at", None)
                ),
                "expiration_date": self._datetime_to_iso(getattr(subscription_state, "current_expires_at", None)),
                "trial_date": self._datetime_to_iso(getattr(subscription_state, "trial_activated_at", None)),
                "news_channel_date": self._datetime_to_iso(getattr(subscription_state, "news_bonus_activated_at", None)),
                "subscription_link": subscription_link,
                "raw_build_link": (
                    f"{BACKEND_TELEGRAM_SUBSCRIPTION_LINK}?uuid={standard_sub_id}"
                    if standard_sub_id
                    else ""
                ),
                "support_link": BOT_SUPPORT_TG_LINK,
                "whitelist": self._serialize_whitelist_profile(
                    whitelist_client=whitelist_client,
                    whitelist_state=whitelist_state,
                    whitelist_subscription_link=whitelist_subscription_link,
                ),
            },
            "telegram_account": self._serialize_telegram_account(telegram_account),
            "web_account": self._serialize_web_account(web_account),
            "state": self._serialize_state(app_user, subscription_state),
            "payments": {
                "legacy": [self._serialize_legacy_payment(payment) for payment in legacy_payments],
                "current": [
                    self._serialize_v2_payment_order(order, attempt)
                    for order, attempt in payment_orders
                ],
            },
            "referral": self._serialize_referral(referral),
            "referral_rewards": [
                {
                    "trigger_type": reward.trigger_type,
                    "trigger_ref": reward.trigger_ref,
                    "reward_days": reward.reward_days,
                    "created_at": self._datetime_to_iso(reward.created_at),
                    "applied_at": self._datetime_to_iso(reward.applied_at),
                    "canceled_at": self._datetime_to_iso(reward.canceled_at),
                    "metadata": dict(reward.metadata_json or {}),
                }
                for reward in referral_rewards
            ],
            "promo": {
                "legacy": [
                    {"code": code, "id": redemption.id}
                    for redemption, code in promo_redemptions
                ],
                "current": [
                    {
                        "code": code,
                        "redeemed_at": self._datetime_to_iso(redemption.redeemed_at),
                        "subscription_grant_id": redemption.subscription_grant_id,
                    }
                    for redemption, code in promo_redemptions
                ],
            },
            "diagnostics": diagnostics,
            "playbooks": playbooks,
        }

    async def get_user_diagnostics(
        self,
        user_id: int,
        redis_client: AsyncRedisClient | None,
    ) -> dict[str, Any]:
        normalized_user_id = int(user_id)

        async with get_db_session() as session:
            app_user = await session.get(AppUser, normalized_user_id)
            if app_user is None or app_user.deleted_at is not None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
            telegram_account = await self._load_telegram_account(session, user_id=normalized_user_id)
            subscription_state = await session.get(SubscriptionState, normalized_user_id)
            standard_client = (
                await session.execute(
                    select(VpnClient)
                    .where(
                        VpnClient.user_id == normalized_user_id,
                        VpnClient.scope == PRODUCT_SCOPE_STANDARD,
                        VpnClient.deactivated_at.is_(None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            whitelist_client = (
                await session.execute(
                    select(VpnClient)
                    .where(
                        VpnClient.user_id == normalized_user_id,
                        VpnClient.scope == PRODUCT_SCOPE_WHITELIST,
                        VpnClient.deactivated_at.is_(None),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            whitelist_state = (
                await session.get(TrafficState, whitelist_client.id)
                if whitelist_client is not None
                else None
            )
            payment_orders = (
                await session.execute(
                    select(PaymentOrder, PaymentAttempt)
                    .outerjoin(PaymentAttempt, PaymentAttempt.order_id == PaymentOrder.id)
                    .where(PaymentOrder.user_id == normalized_user_id)
                    .order_by(desc(PaymentOrder.created_at))
                    .limit(25)
                )
            ).all()

        recent_payments = [
            self._build_legacy_payment_from_v2(
                order,
                attempt,
                tg_id=int(getattr(telegram_account, "telegram_id", 0) or 0),
            )
            for order, attempt in payment_orders
        ]

        standard_tg_id = int(getattr(telegram_account, "telegram_id", 0) or 0)
        standard_email = str(getattr(standard_client, "external_email", "") or "")
        standard_sub_id = str(getattr(standard_client, "subscription_external_id", "") or "")
        cache_key = None
        redis_build_key = None
        redis_info_key = None
        if standard_tg_id and standard_email:
            token = self.jwt_encoder.encode({"tg_id": standard_tg_id, "email": standard_email})
            cache_key = f"current:{token}"
            redis_build_key = self._subscription_build_redis_key(standard_sub_id)
            redis_info_key = self._subscription_info_redis_key(cache_key)

        client_status = {"status": "unknown", "details": None}
        try:
            if standard_client is None:
                client_status = {"status": "missing", "details": None}
            else:
                client_exists = await self.client_manager.client_exists(
                    str(standard_client.external_client_uuid)
                )
                client_status = {
                    "status": "present" if client_exists else "missing",
                    "details": f"uuid={standard_client.external_client_uuid}",
                }
        except Exception as err:
            client_status = {"status": "error", "details": str(err)}

        redis_cache = {
            "build": False,
            "info": False,
        }
        if redis_client is not None and redis_build_key and redis_info_key:
            try:
                redis_cache = {
                    "build": await redis_client.exists(redis_build_key),
                    "info": await redis_client.exists(redis_info_key),
                }
            except RedisClientError as err:
                redis_cache["error"] = str(err)

        parity = {
            "legacy_expiration_date": self._datetime_to_iso(getattr(subscription_state, "current_expires_at", None)),
            "v2_expiration_date": self._datetime_to_iso(getattr(subscription_state, "current_expires_at", None)),
            "legacy_trial_date": self._datetime_to_iso(getattr(subscription_state, "trial_activated_at", None)),
            "v2_trial_date": self._datetime_to_iso(getattr(subscription_state, "trial_activated_at", None)),
            "legacy_news_channel_date": self._datetime_to_iso(getattr(subscription_state, "news_bonus_activated_at", None)),
            "v2_news_channel_date": self._datetime_to_iso(getattr(subscription_state, "news_bonus_activated_at", None)),
            "blocked_at": self._datetime_to_iso(
                getattr(subscription_state, "blocked_at", None) or getattr(app_user, "blocked_at", None)
            ),
        }
        parity["has_mismatch"] = any(
            [
                parity["legacy_expiration_date"] != parity["v2_expiration_date"],
                bool(parity["legacy_trial_date"]) != bool(parity["v2_trial_date"]),
                bool(parity["legacy_news_channel_date"]) != bool(parity["v2_news_channel_date"]),
            ]
        )

        recent_dead_letters = await self._load_recent_dead_letters(
            redis_client,
            tg_id=standard_tg_id or None,
            limit=10,
        )
        payment_statuses = Counter(str(payment.status or "").lower() for payment in recent_payments)
        paid_unconfirmed = [
            payment.payment_id
            for payment in recent_payments
            if str(payment.status or "").lower() in PROVIDER_STATUS_PAID and not bool(payment.confirmed)
        ]

        return {
            "subscription": {
                "is_active": self._is_future_datetime(
                    getattr(subscription_state, "current_expires_at", None)
                ),
                "expiration_date": self._datetime_to_iso(getattr(subscription_state, "current_expires_at", None)),
                "token_cache_key": cache_key,
                "build_cache_key": standard_sub_id or None,
            },
            "client": client_status,
            "whitelist": self._serialize_whitelist_diagnostics(
                whitelist_client=whitelist_client,
                whitelist_state=whitelist_state,
            ),
            "cache": {
                "local": {
                    "build": bool(standard_sub_id) and (
                        str(standard_sub_id) in self._subscription_routes().subscription_cache.cache
                    ),
                    "info": bool(cache_key) and (
                        cache_key in self._subscription_routes().subscription_info_cache.cache
                    ),
                },
                "redis": redis_cache,
            },
            "payments": {
                "recent_status_counts": dict(payment_statuses),
                "has_paid_unconfirmed": bool(paid_unconfirmed),
                "paid_unconfirmed_payment_ids": paid_unconfirmed,
            },
            "queues": {
                "recent_dead_letters": recent_dead_letters,
            },
            "parity": parity,
            "timeline": [
                {"label": "registered", "value": self._datetime_to_iso(getattr(app_user, "created_at", None))},
                {"label": "trial", "value": self._datetime_to_iso(getattr(subscription_state, "trial_activated_at", None))},
                {"label": "news_bonus", "value": self._datetime_to_iso(getattr(subscription_state, "news_bonus_activated_at", None))},
                {"label": "expires", "value": self._datetime_to_iso(getattr(subscription_state, "current_expires_at", None))},
                {
                    "label": "blocked",
                    "value": self._datetime_to_iso(
                        getattr(subscription_state, "blocked_at", None) or getattr(app_user, "blocked_at", None)
                    ),
                },
            ],
        }

    async def get_user_playbooks(
        self,
        user_id: int,
        redis_client: AsyncRedisClient | None,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        async with get_db_session() as session:
            app_user = await session.get(AppUser, int(user_id))
            if app_user is None or app_user.deleted_at is not None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        info = diagnostics or await self.get_user_diagnostics(int(user_id), redis_client)
        playbooks: list[dict[str, Any]] = []

        if info["payments"]["has_paid_unconfirmed"] and not info["subscription"]["is_active"]:
            playbooks.append(
                {
                    "id": "payment_paid_but_not_activated",
                    "severity": "high",
                    "title": "Оплата прошла, подписка не активировалась",
                    "summary": "Есть платёж в paid/succeeded без подтверждения и у пользователя неактивная подписка.",
                    "checks": [
                        "Проверить последние payment events и provider status.",
                        "Проверить DLQ и retry queue.",
                        "Проверить наличие клиента и текущую expiration_date.",
                    ],
                    "suggested_actions": ["retry_payment_dlq", "grant_compensation_days", "recreate_client"],
                }
            )

        if info["client"]["status"] == "missing" and info["subscription"]["is_active"]:
            playbooks.append(
                {
                    "id": "missing_client",
                    "severity": "high",
                    "title": "Пользователь есть в БД, но нет в 3x-ui",
                    "summary": "Подписка активна, но клиент на сервере не найден.",
                    "checks": [
                        "Проверить uuid и sub_id в user profile.",
                        "Проверить недавние ошибки provision/update.",
                    ],
                    "suggested_actions": ["recreate_client", "clear_cache"],
                }
            )

        if info["parity"]["has_mismatch"]:
            playbooks.append(
                {
                    "id": "profile_state_mismatch",
                    "severity": "medium",
                    "title": "Данные профиля и subscription state расходятся",
                    "summary": "Часть полей пользовательского профиля и subscription state не совпадает.",
                    "checks": [
                        "Сравнить expiration/trial/news bonus между profile и subscription state.",
                        "Проверить, не остался ли пользователь заблокирован в текущем состоянии.",
                    ],
                    "suggested_actions": ["clear_cache", "rebuild_subscription_link"],
                }
            )

        if info["queues"]["recent_dead_letters"]:
            playbooks.append(
                {
                    "id": "queue_errors",
                    "severity": "medium",
                    "title": "Есть ошибки в очередях по пользователю",
                    "summary": "В dead letter queue найдены записи, связанные с пользователем.",
                    "checks": [
                        "Проверить payload и причину последней ошибки.",
                        "Перед retry убедиться, что первопричина устранена.",
                    ],
                    "suggested_actions": ["retry_payment_dlq"],
                }
            )

        if info["parity"]["legacy_trial_date"]:
            playbooks.append(
                {
                    "id": "trial_edge_case",
                    "severity": "low",
                    "title": "Trial уже использован или спорный кейс",
                    "summary": "У пользователя уже есть отметка trial_date.",
                    "checks": [
                        "Проверить, не нужен ли ручной override.",
                        "Проверить причину обращения и историю платежей.",
                    ],
                    "suggested_actions": ["grant_compensation_days"],
                }
            )

        playbooks.append(
            {
                "id": "telegram_proxy_help",
                "severity": "low",
                "title": "Проблема входа в Telegram",
                "summary": "Если пользователь не может открыть бота, можно быстро перевести его на proxy flow.",
                "checks": [
                    "Уточнить, открывается ли Telegram без VPN.",
                    "Отправить proxy-flow и проверить, может ли пользователь снова зайти в бота.",
                ],
                "suggested_actions": ["rebuild_subscription_link"],
            }
        )

        return playbooks

    async def list_audit_logs(self, limit: int = 50, target_tg_id: int | None = None) -> list[dict[str, Any]]:
        async with get_db_session() as session:
            stmt = select(AdminAuditLog).order_by(desc(AdminAuditLog.created_at)).limit(max(1, min(limit, 200)))
            if target_tg_id is not None:
                stmt = stmt.where(AdminAuditLog.target_tg_id == int(target_tg_id))
            rows = (await session.execute(stmt)).scalars().all()

        return [
            {
                "id": row.id,
                "actor": row.actor,
                "actor_role": row.actor_role,
                "action_type": row.action_type,
                "target_tg_id": row.target_tg_id,
                "status": row.status,
                "reason": row.reason,
                "dry_run": row.dry_run,
                "summary": row.summary,
                "created_at": self._datetime_to_iso(row.created_at),
                "metadata": dict(row.metadata_json or {}),
            }
            for row in rows
        ]

    async def execute_action(
        self,
        principal: AdminPrincipal,
        action_type: str,
        target_user_id: int | None,
        target_tg_id: int | None,
        reason: str | None,
        dry_run: bool,
        params: dict[str, Any],
        redis_client: AsyncRedisClient | None,
    ) -> dict[str, Any]:
        action = str(action_type or "").strip()
        if not action:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Action type is required")

        metadata = dict(params or {})
        if target_user_id is not None:
            metadata.setdefault("target_user_id", int(target_user_id))
        status_name = "success"
        summary = ""
        alert_error: Exception | None = None
        try:
            result = await self._execute_action_inner(
                action=action,
                target_user_id=target_user_id,
                target_tg_id=target_tg_id,
                dry_run=dry_run,
                params=metadata,
                redis_client=redis_client,
            )
            summary = str(result.get("summary", "")).strip()
            return_payload = {
                "status": "dry_run" if dry_run else "success",
                "action_type": action,
                "target_user_id": target_user_id,
                "target_tg_id": target_tg_id,
                **result,
            }
            return return_payload
        except HTTPException as err:
            status_name = "failed"
            summary = str(err.detail)
            raise
        except Exception as err:
            status_name = "failed"
            summary = str(err)
            alert_error = err
            logger.opt(exception=err).error(
                f"Admin action {action} failed for user_id={target_user_id}, tg_id={target_tg_id}: {err}"
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=str(err),
            ) from err
        finally:
            audit_id = await self._append_audit_log(
                principal=principal,
                action_type=action,
                target_tg_id=target_tg_id,
                status_name=status_name if not dry_run else "dry_run",
                reason=reason,
                dry_run=dry_run,
                summary=summary,
                metadata=metadata,
            )
            if action in ALERTED_ADMIN_ACTIONS:
                self._send_admin_action_alert(
                    principal=principal,
                    action=action,
                    target_tg_id=target_tg_id,
                    dry_run=dry_run,
                    reason=reason,
                    status_name=status_name if not dry_run else "dry_run",
                    summary=summary,
                    metadata=metadata,
                    audit_id=audit_id,
                    error=alert_error,
                )

    async def _execute_action_inner(
        self,
        *,
        action: str,
        target_user_id: int | None,
        target_tg_id: int | None,
        dry_run: bool,
        params: dict[str, Any],
        redis_client: AsyncRedisClient | None,
    ) -> dict[str, Any]:
        if action == "extend_subscription":
            tg_id = await self._require_telegram_target(target_user_id, target_tg_id)
            period = str(params.get("period") or "").strip()
            if not period:
                raise HTTPException(status_code=400, detail="period is required")
            if dry_run:
                return {"summary": f"Will extend subscription for {tg_id} by {period}."}
            await self.subscription_provisioning_service.create_or_update_user(tg_id, period)
            link = await self._safe_subscription_link(tg_id)
            return {"summary": f"Subscription extended by {period}.", "subscription_link": link}

        if action == "grant_trial":
            tg_id = await self._require_telegram_target(target_user_id, target_tg_id)
            if dry_run:
                return {"summary": f"Will try to activate trial for {tg_id}."}
            activated = await self.subscription_flow_service.activate_trial(tg_id)
            return {"summary": "Trial activated." if activated else "Trial was already used or user is active."}

        if action == "recreate_client":
            tg_id = await self._require_telegram_target(target_user_id, target_tg_id)
            user = await self._load_user(tg_id)
            if not user.expiration_date:
                raise HTTPException(status_code=400, detail="User has no expiration_date to recreate client from")
            if dry_run:
                return {"summary": f"Will recreate 3x-ui client for {tg_id} with preserved expiry."}
            try:
                if await self.client_manager.client_exists(str(user.uuid)):
                    await self.client_manager.delete_client(str(user.uuid))
            except Exception:
                logger.warning(f"Proceeding with recreate_client for tg_id={tg_id} after failed existence/delete check")
            await self.client_manager.add_client(
                tg_id,
                "day0",
                user=user,
                target_expiration_date=int(user.expiration_date),
            )
            return {"summary": "Client recreated in 3x-ui."}

        if action == "delete_user":
            user_id = await self._require_user_target(target_user_id, target_tg_id)
            tg_id = await self._resolve_tg_id(target_user_id=target_user_id, target_tg_id=target_tg_id)
            if dry_run:
                return {
                    "summary": (
                        f"Will hard-delete user {user_id}"
                        + (f" (tg_id={tg_id})" if tg_id is not None else "")
                        + " from current datastores and 3x-ui if present."
                    )
                }
            if tg_id is not None:
                deleted = await self.subscription_provisioning_service.delete_user(tg_id)
            else:
                deleted = await self._delete_app_user(user_id)
            return {"summary": "User deleted." if deleted else "User not found."}

        if action == "block_user":
            user_id = await self._require_user_target(target_user_id, target_tg_id)
            if dry_run:
                return {"summary": f"Will block user {user_id} in current state."}
            await self._set_block_state(user_id, blocked=True)
            return {"summary": "User blocked."}

        if action == "unblock_user":
            user_id = await self._require_user_target(target_user_id, target_tg_id)
            if dry_run:
                return {"summary": f"Will unblock user {user_id} in current state."}
            await self._set_block_state(user_id, blocked=False)
            return {"summary": "User unblocked."}

        if action == "rebuild_subscription_link":
            tg_id = await self._require_telegram_target(target_user_id, target_tg_id)
            if not dry_run:
                await self._clear_user_cache(tg_id, redis_client)
            link = await self._safe_subscription_link(tg_id)
            return {"summary": "Subscription link rebuilt.", "subscription_link": link}

        if action == "retry_payment_dlq":
            limit = int(params.get("limit") or 100)
            delay_seconds = int(params.get("delay_seconds") or 0)
            if dry_run:
                return {"summary": f"Will retry payment DLQ with limit={limit}, delay={delay_seconds}s."}
            if redis_client is None:
                raise HTTPException(status_code=503, detail="Redis is unavailable")
            queue = self._build_payment_queue_service(redis_client)
            requeued, skipped = await queue.requeue_dead_letters(limit=limit, delay_seconds=delay_seconds)
            return {
                "summary": f"Payment DLQ retried. Requeued={requeued}, skipped={skipped}.",
                "requeued": requeued,
                "skipped": skipped,
            }

        if action == "grant_referral_bonus":
            tg_id = await self._require_telegram_target(target_user_id, target_tg_id)
            days = int(params.get("days") or 0)
            if days <= 0:
                raise HTTPException(status_code=400, detail="days must be > 0")
            if dry_run:
                return {"summary": f"Will grant referral bonus of {days} days to {tg_id}."}
            await self.referral_bonus_service.grant_bonus_to_user(tg_id, days)
            return {"summary": f"Referral bonus of {days} days granted."}

        if action == "grant_compensation_days":
            tg_id = await self._require_telegram_target(target_user_id, target_tg_id)
            days = int(params.get("days") or 0)
            if days <= 0:
                raise HTTPException(status_code=400, detail="days must be > 0")
            if dry_run:
                return {"summary": f"Will grant compensation of {days} days to {tg_id}."}
            user = await self._load_user(tg_id)
            if user.expiration_date and int(user.expiration_date) > self.timestamp.current_timestamp():
                await self.client_manager.update_client(tg_id, f"day{days}", user=user)
            else:
                await self.subscription_provisioning_service.create_or_update_user(tg_id, f"day{days}", user=user)
            return {"summary": f"Compensation of {days} days granted."}

        if action == "unlink_problem_entity":
            user_id = await self._require_user_target(target_user_id, target_tg_id)
            entity_type = str(params.get("entity_type") or "").strip().lower()
            if not entity_type:
                raise HTTPException(status_code=400, detail="entity_type is required")
            if dry_run:
                return {"summary": f"Will unlink entity '{entity_type}' for user {user_id}."}
            await self._unlink_problem_entity(user_id, entity_type)
            return {"summary": f"Entity '{entity_type}' unlinked."}

        if action == "grant_whitelist_package":
            user_id = await self._require_user_target(target_user_id, target_tg_id)
            plan_code = str(params.get("plan_code") or "").strip()
            if not plan_code:
                raise HTTPException(status_code=400, detail="plan_code is required")
            if dry_run:
                return {"summary": f"Will grant traffic-limited package {plan_code} to user {user_id}."}
            result = await self.whitelist_traffic_service.grant_admin_package_for_user(
                user_id=user_id,
                plan_code=plan_code,
                source_ref=f"admin:{user_id}:{self.timestamp.current_timestamp()}",
            )
            return {
                "summary": (
                    f"Traffic-limited package granted. Remaining={result.remaining_bytes}, "
                    f"expires_at={self._datetime_to_iso(result.expires_at)}."
                ),
                "allocated_bytes": result.allocated_bytes,
                "remaining_bytes": result.remaining_bytes,
                "expires_at": self._datetime_to_iso(result.expires_at),
            }

        if action == "sync_whitelist_traffic":
            user_id = await self._require_user_target(target_user_id, target_tg_id)
            if dry_run:
                return {"summary": f"Will sync traffic-limited configuration for user {user_id}."}
            synced = await self.whitelist_traffic_sync_service.sync_user_once(user_id=user_id)
            if not synced:
                raise HTTPException(status_code=404, detail="Traffic-limited configuration not found")
            return {"summary": "Traffic-limited configuration synced."}

        if action == "clear_cache":
            if dry_run:
                return {"summary": "Will clear local and targeted Redis subscription caches."}
            tg_id = await self._resolve_tg_id(target_user_id=target_user_id, target_tg_id=target_tg_id)
            if tg_id is not None:
                await self._clear_user_cache(tg_id, redis_client)
                return {"summary": f"Caches cleared for user {tg_id}."}
            routes = self._subscription_routes()
            routes.subscription_cache.clear()
            routes.subscription_info_cache.clear()
            return {"summary": "Local subscription caches cleared."}

        raise HTTPException(status_code=400, detail=f"Unsupported action: {action}")

    async def _append_audit_log(
        self,
        *,
        principal: AdminPrincipal,
        action_type: str,
        target_tg_id: int | None,
        status_name: str,
        reason: str | None,
        dry_run: bool,
        summary: str,
        metadata: dict[str, Any],
    ) -> int:
        async with get_db_session() as session:
            row = AdminAuditLog(
                actor=principal.actor,
                actor_role=principal.role,
                action_type=action_type,
                target_tg_id=target_tg_id,
                status=status_name,
                reason=reason,
                dry_run=dry_run,
                summary=summary or None,
                created_at=datetime.now(timezone.utc),
                metadata_json=metadata,
            )
            session.add(row)
            await session.flush()
            await session.commit()
            return int(row.id)

    def _send_admin_action_alert(
        self,
        *,
        principal: AdminPrincipal,
        action: str,
        target_tg_id: int | None,
        dry_run: bool,
        reason: str | None,
        status_name: str,
        summary: str,
        metadata: dict[str, Any],
        audit_id: int,
        error: Exception | None,
    ) -> None:
        send_telegram_alert(
            title="Admin action alert",
            level="WARNING" if status_name in {"success", "dry_run"} else "ERROR",
            summary=summary or f"Admin action {action} completed with status={status_name}",
            details={
                "audit_id": audit_id,
                "action": action,
                "status": status_name,
                "dry_run": dry_run,
                "actor": principal.actor,
                "role": principal.role,
                "target_tg_id": target_tg_id if target_tg_id is not None else "global",
                "reason": reason or "not provided",
                "params": json.dumps(metadata, ensure_ascii=False) if metadata else "{}",
            },
            source="backend.admin",
            traceback_text=(
                "".join(traceback.format_exception(type(error), error, error.__traceback__)).strip()
                if error
                else None
            ),
        )

    async def _set_block_state(self, user_id: int, *, blocked: bool) -> None:
        now = datetime.now(timezone.utc)
        async with get_db_session() as session:
            app_user = await session.get(AppUser, int(user_id))
            if app_user is None or app_user.deleted_at is not None:
                raise HTTPException(status_code=404, detail="User not found")
            subscription_state = await session.get(SubscriptionState, int(user_id))
            if app_user is not None:
                app_user.blocked_at = now if blocked else None
                app_user.updated_at = now
            if subscription_state is not None:
                subscription_state.blocked_at = now if blocked else None
                subscription_state.updated_at = now
                subscription_state.version = int(subscription_state.version or 0) + 1
            await session.commit()

    async def _unlink_problem_entity(self, user_id: int, entity_type: str) -> None:
        now = datetime.now(timezone.utc)
        async with get_db_session() as session:
            if entity_type == "referrer":
                account = (
                    await session.execute(
                        select(TelegramAccount).where(
                            TelegramAccount.user_id == int(user_id),
                            TelegramAccount.revoked_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
                if account is None:
                    raise HTTPException(status_code=404, detail="Telegram account not found")
                edge = (
                    await session.execute(
                        select(ReferralEdge).where(
                            ReferralEdge.referred_user_id == account.user_id
                        )
                    )
                ).scalar_one_or_none()
                if edge is None:
                    raise HTTPException(status_code=404, detail="Referral edge not found")
                await session.delete(edge)
                await session.commit()
                return

            if entity_type == "telegram_account":
                account = (
                    await session.execute(
                        select(TelegramAccount).where(TelegramAccount.user_id == int(user_id))
                    )
                ).scalar_one_or_none()
                if account is None:
                    raise HTTPException(status_code=404, detail="Telegram account not found")
                account.revoked_at = now
                account.last_seen_at = now
                await session.commit()
                return

            if entity_type == "web_account":
                account = (
                    await session.execute(
                        select(WebAccount).where(
                            WebAccount.user_id == int(user_id),
                            WebAccount.revoked_at.is_(None),
                        )
                    )
                ).scalar_one_or_none()
                if account is None:
                    raise HTTPException(status_code=404, detail="Web account not found")
                account.revoked_at = now
                account.updated_at = now
                await session.commit()
                return

            raise HTTPException(status_code=400, detail=f"Unsupported entity_type: {entity_type}")

    async def _clear_user_cache(self, tg_id: int, redis_client: AsyncRedisClient | None) -> None:
        user = await self._load_user(tg_id)
        token = self.jwt_encoder.encode({"tg_id": int(user.tg_id), "email": user.email})
        source_tag = "current"
        cache_key = f"{source_tag}:{token}"

        routes = self._subscription_routes()
        routes.subscription_cache.cache.pop(str(user.sub_id), None)
        routes.subscription_info_cache.cache.pop(cache_key, None)

        if redis_client is None:
            return

        for key in (
            self._subscription_build_redis_key(str(user.sub_id)),
            self._subscription_info_redis_key(cache_key),
        ):
            try:
                await redis_client.delete(key)
            except RedisClientError as err:
                logger.warning(f"Failed to delete Redis cache key {key}: {err}")

    @staticmethod
    def _subscription_build_redis_key(sub_id: str) -> str:
        return f"{PRODUCT_REDIS_PREFIX}:subscription:build:{sub_id}"

    @staticmethod
    def _subscription_info_redis_key(cache_key: str) -> str:
        return f"{PRODUCT_REDIS_PREFIX}:subscription:info:{cache_key}"

    async def _load_recent_dead_letters(
        self,
        redis_client: AsyncRedisClient | None,
        *,
        tg_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if redis_client is None:
            return []

        try:
            rows = await redis_client.lrange(REDIS_PAYMENT_DEAD_LETTER_QUEUE_KEY, -max(1, limit), -1)
        except RedisClientError as err:
            return [{"error": str(err)}]

        result: list[dict[str, Any]] = []
        for raw_row in reversed(rows):
            try:
                dead_task = json.loads(raw_row)
            except json.JSONDecodeError:
                continue
            payload = dead_task.get("payload") or {}
            if tg_id is not None and int(payload.get("tg_id") or -1) != int(tg_id):
                continue
            result.append(
                {
                    "payment_id": payload.get("payment_id"),
                    "error": dead_task.get("error"),
                    "failed_at": self._legacy_ms_to_iso(int(dead_task.get("failed_at", 0)) * 1000)
                    if dead_task.get("failed_at")
                    else None,
                    "payload": payload,
                }
            )
        return result[:limit]

    def _build_payment_queue_service(self, redis_client: AsyncRedisClient) -> PaymentQueueService:
        return PaymentQueueService(
            redis_client=redis_client,
            ready_queue_key=REDIS_PAYMENT_READY_QUEUE_KEY,
            retry_queue_key=REDIS_PAYMENT_RETRY_QUEUE_KEY,
            dead_letter_queue_key=REDIS_PAYMENT_DEAD_LETTER_QUEUE_KEY,
            dedupe_prefix=REDIS_PAYMENT_DEDUPE_PREFIX,
        )

    async def _get_queue_stats(self, redis_client: AsyncRedisClient | None) -> dict[str, Any]:
        if redis_client is None:
            return {"redis_available": False}

        try:
            return {
                "redis_available": True,
                "payment_ready": await redis_client.llen(REDIS_PAYMENT_READY_QUEUE_KEY),
                "payment_retry": await redis_client.llen(REDIS_PAYMENT_RETRY_QUEUE_KEY),
                "payment_dead_letter": await redis_client.llen(REDIS_PAYMENT_DEAD_LETTER_QUEUE_KEY),
            }
        except RedisClientError as err:
            return {"redis_available": False, "error": str(err)}

    async def _safe_subscription_link(
        self,
        tg_id: int,
        *,
        scope: str = PRODUCT_SCOPE_STANDARD,
    ) -> str:
        try:
            return await self.subscription_provisioning_service.get_subscription_link(
                tg_id,
                scope=scope,
            )
        except Exception as err:
            logger.warning(f"Failed to build subscription link for {tg_id}, scope={scope}: {err}")
            return ""

    def _serialize_whitelist_profile(
        self,
        *,
        whitelist_client: VpnClient | None,
        whitelist_state: TrafficState | None,
        whitelist_subscription_link: str,
    ) -> dict[str, Any]:
        if whitelist_client is None:
            return {
                "is_enabled": False,
                "email": None,
                "uuid": None,
                "sub_id": None,
                "subscription_link": "",
                "raw_build_link": "",
                "allocated_bytes": 0,
                "used_bytes": 0,
                "remaining_bytes": 0,
                "expires_at": None,
                "last_provider_sync_at": None,
                "is_active": False,
                "is_blocked": False,
            }

        return {
            "is_enabled": True,
            "email": str(whitelist_client.external_email),
            "uuid": str(whitelist_client.external_client_uuid),
            "sub_id": str(whitelist_client.subscription_external_id),
            "subscription_link": whitelist_subscription_link,
            "raw_build_link": (
                f"{BACKEND_TELEGRAM_WHITELIST_SUBSCRIPTION_LINK}"
                f"?uuid={whitelist_client.subscription_external_id}"
            ),
            "allocated_bytes": int(getattr(whitelist_state, "allocated_bytes", 0) or 0),
            "used_bytes": int(getattr(whitelist_state, "used_bytes", 0) or 0),
            "remaining_bytes": int(getattr(whitelist_state, "remaining_bytes", 0) or 0),
            "expires_at": self._datetime_to_iso(getattr(whitelist_state, "expires_at", None)),
            "last_provider_sync_at": self._datetime_to_iso(
                getattr(whitelist_state, "last_provider_sync_at", None)
            ),
            "is_active": self._is_whitelist_active(whitelist_state),
            "is_blocked": bool(getattr(whitelist_state, "is_blocked", False)),
        }

    def _serialize_whitelist_diagnostics(
        self,
        *,
        whitelist_client: VpnClient | None,
        whitelist_state: TrafficState | None,
    ) -> dict[str, Any]:
        if whitelist_client is None:
            return {
                "status": "missing",
                "details": None,
                "allocated_bytes": 0,
                "used_bytes": 0,
                "remaining_bytes": 0,
                "expires_at": None,
                "last_provider_sync_at": None,
                "is_active": False,
                "is_blocked": False,
            }

        return {
            "status": "present",
            "details": (
                f"uuid={whitelist_client.external_client_uuid}, "
                f"email={whitelist_client.external_email}"
            ),
            "allocated_bytes": int(getattr(whitelist_state, "allocated_bytes", 0) or 0),
            "used_bytes": int(getattr(whitelist_state, "used_bytes", 0) or 0),
            "remaining_bytes": int(getattr(whitelist_state, "remaining_bytes", 0) or 0),
            "expires_at": self._datetime_to_iso(getattr(whitelist_state, "expires_at", None)),
            "last_provider_sync_at": self._datetime_to_iso(
                getattr(whitelist_state, "last_provider_sync_at", None)
            ),
            "is_active": self._is_whitelist_active(whitelist_state),
            "is_blocked": bool(getattr(whitelist_state, "is_blocked", False)),
        }

    def _is_whitelist_active(self, whitelist_state: TrafficState | None) -> bool:
        if whitelist_state is None:
            return False
        return self._is_whitelist_active_from_primitives(
            remaining_bytes=getattr(whitelist_state, "remaining_bytes", 0),
            expires_at=getattr(whitelist_state, "expires_at", None),
            is_blocked=getattr(whitelist_state, "is_blocked", False),
        )

    @staticmethod
    def _is_whitelist_active_from_primitives(
        *,
        remaining_bytes: int | None,
        expires_at: datetime | None,
        is_blocked: bool | None,
        now: datetime | None = None,
    ) -> bool:
        current_time = now or datetime.now(timezone.utc)
        if expires_at is not None:
            normalized = (
                expires_at
                if expires_at.tzinfo is not None
                else expires_at.replace(tzinfo=timezone.utc)
            )
            if normalized.astimezone(timezone.utc) <= current_time:
                return False
        return int(remaining_bytes or 0) > 0 and not bool(is_blocked)

    @staticmethod
    def _is_future_datetime(
        value: datetime | None,
        *,
        now: datetime | None = None,
    ) -> bool:
        if value is None:
            return False
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        current_time = now or datetime.now(timezone.utc)
        return normalized.astimezone(timezone.utc) > current_time

    async def _load_user(self, tg_id: int) -> TelegramUserSnapshot:
        user = await self.user_repository.get(tg_id)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    async def _delete_app_user(self, user_id: int) -> bool:
        async with get_db_session() as session:
            app_user = await session.get(AppUser, int(user_id))
            if app_user is None or app_user.deleted_at is not None:
                return False
            await session.delete(app_user)
            await session.commit()
            return True

    async def _require_user_target(
        self,
        target_user_id: int | None,
        target_tg_id: int | None,
    ) -> int:
        if target_user_id is not None:
            return int(target_user_id)
        if target_tg_id is None:
            raise HTTPException(status_code=400, detail="target_user_id is required")
        async with get_db_session() as session:
            account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.telegram_id == int(target_tg_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if account is None:
                raise HTTPException(status_code=404, detail="Telegram account not found")
            return int(account.user_id)

    async def _resolve_tg_id(
        self,
        *,
        target_user_id: int | None,
        target_tg_id: int | None,
    ) -> int | None:
        if target_tg_id is not None:
            return int(target_tg_id)
        if target_user_id is None:
            return None
        async with get_db_session() as session:
            account = await self._load_telegram_account(session, user_id=int(target_user_id))
            return int(account.telegram_id) if account is not None else None

    async def _require_telegram_target(
        self,
        target_user_id: int | None,
        target_tg_id: int | None,
    ) -> int:
        tg_id = await self._resolve_tg_id(
            target_user_id=target_user_id,
            target_tg_id=target_tg_id,
        )
        if tg_id is None:
            raise HTTPException(status_code=400, detail="This action requires linked Telegram account")
        return int(tg_id)

    @staticmethod
    async def _load_telegram_account(session, *, user_id: int) -> TelegramAccount | None:
        return (
            await session.execute(
                select(TelegramAccount)
                .where(
                    TelegramAccount.user_id == int(user_id),
                    TelegramAccount.revoked_at.is_(None),
                )
                .order_by(desc(TelegramAccount.last_seen_at))
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def _load_web_account(session, *, user_id: int) -> WebAccount | None:
        return (
            await session.execute(
                select(WebAccount)
                .where(
                    WebAccount.user_id == int(user_id),
                    WebAccount.revoked_at.is_(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    def _serialize_user_summary(
        self,
        *,
        user_id: int,
        email: str,
        username: str | None,
        tg_id: int | None,
        uuid: str | None,
        sub_id: str | None,
        created_at: datetime | None,
        expiration_date: datetime | None,
        has_web_account: bool,
        has_telegram: bool,
        active_whitelist: bool,
        blocked_at: datetime | None,
        is_active: bool | None = None,
    ) -> dict[str, Any]:
        resolved_is_active = (
            bool(is_active)
            if is_active is not None
            else (self._is_future_datetime(expiration_date) or bool(active_whitelist))
        )
        return {
            "user_id": int(user_id),
            "tg_id": int(tg_id) if tg_id is not None else None,
            "email": email,
            "username": username,
            "uuid": str(uuid or ""),
            "sub_id": str(sub_id or ""),
            "created_at": self._datetime_to_iso(created_at),
            "expiration_date": self._datetime_to_iso(expiration_date),
            "has_web_account": bool(has_web_account),
            "has_telegram": bool(has_telegram),
            "identity_kind": (
                "linked"
                if has_web_account and has_telegram
                else "web"
                if has_web_account
                else "telegram"
                if has_telegram
                else "internal"
            ),
            "has_whitelist": bool(active_whitelist),
            "is_active": resolved_is_active,
            "is_blocked": blocked_at is not None,
            "blocked_at": self._datetime_to_iso(blocked_at),
        }

    @staticmethod
    def _serialize_telegram_account(account: TelegramAccount | None) -> dict[str, Any] | None:
        if account is None:
            return None
        return {
            "user_id": account.user_id,
            "telegram_id": int(account.telegram_id),
            "username": account.username,
            "linked_at": AdminService._datetime_to_iso(account.linked_at),
            "first_seen_at": AdminService._datetime_to_iso(account.first_seen_at),
            "last_seen_at": AdminService._datetime_to_iso(account.last_seen_at),
            "revoked_at": AdminService._datetime_to_iso(account.revoked_at),
        }

    @staticmethod
    def _serialize_web_account(account: WebAccount | None) -> dict[str, Any] | None:
        if account is None:
            return None
        return {
            "user_id": account.user_id,
            "email": account.email,
            "email_verified_at": AdminService._datetime_to_iso(account.email_verified_at),
            "linked_at": AdminService._datetime_to_iso(account.linked_at),
            "last_login_at": AdminService._datetime_to_iso(account.last_login_at),
            "revoked_at": AdminService._datetime_to_iso(account.revoked_at),
        }

    @staticmethod
    def _serialize_state(app_user: AppUser | None, subscription_state: SubscriptionState | None) -> dict[str, Any] | None:
        if app_user is None and subscription_state is None:
            return None
        return {
            "app_user": {
                "id": getattr(app_user, "id", None),
                "created_at": AdminService._datetime_to_iso(getattr(app_user, "created_at", None)),
                "updated_at": AdminService._datetime_to_iso(getattr(app_user, "updated_at", None)),
                "blocked_at": AdminService._datetime_to_iso(getattr(app_user, "blocked_at", None)),
                "deleted_at": AdminService._datetime_to_iso(getattr(app_user, "deleted_at", None)),
            }
            if app_user is not None
            else None,
            "subscription_state": {
                "current_expires_at": AdminService._datetime_to_iso(getattr(subscription_state, "current_expires_at", None)),
                "trial_activated_at": AdminService._datetime_to_iso(getattr(subscription_state, "trial_activated_at", None)),
                "news_bonus_activated_at": AdminService._datetime_to_iso(getattr(subscription_state, "news_bonus_activated_at", None)),
                "blocked_at": AdminService._datetime_to_iso(getattr(subscription_state, "blocked_at", None)),
                "updated_at": AdminService._datetime_to_iso(getattr(subscription_state, "updated_at", None)),
                "version": getattr(subscription_state, "version", None),
            }
            if subscription_state is not None
            else None,
        }

    @staticmethod
    def _serialize_referral(referral: ReferralSnapshot | None) -> dict[str, Any] | None:
        if referral is None:
            return None
        return {
            "referrer_tg_id": referral.referrer_tg_id,
            "days_pending": referral.days_pending,
            "invited_count": referral.invited_count,
            "paid_count": referral.paid_count,
            "bonus_is_received": referral.bonus_is_received,
        }

    @staticmethod
    def _serialize_legacy_payment(payment: PaymentSnapshot) -> dict[str, Any]:
        return {
            "payment_id": payment.payment_id,
            "status": payment.status,
            "created_at": AdminService._legacy_ms_to_iso(payment.created_at),
            "confirmed": bool(payment.confirmed),
            "method": payment.method,
            "payload": payment.payload,
        }

    @staticmethod
    def _serialize_v2_payment_order(order: PaymentOrder, attempt: PaymentAttempt | None) -> dict[str, Any]:
        return {
            "id": order.id,
            "status": order.status,
            "amount": str(order.amount),
            "currency": order.currency,
            "created_at": AdminService._datetime_to_iso(order.created_at),
            "paid_at": AdminService._datetime_to_iso(order.paid_at),
            "fulfilled_at": AdminService._datetime_to_iso(order.fulfilled_at),
            "subscription_grant_id": order.subscription_grant_id,
            "provider": getattr(attempt, "provider", None),
            "provider_payment_id": getattr(attempt, "provider_payment_id", None),
            "provider_status": getattr(attempt, "provider_status", None),
        }

    @staticmethod
    def _build_legacy_payment_from_v2(
        order: PaymentOrder,
        attempt: PaymentAttempt | None,
        *,
        tg_id: int,
    ) -> PaymentSnapshot:
        order_metadata = dict(order.metadata_json or {})
        plan_payload = str(order_metadata.get("legacy_payload") or "").strip()
        provider_status = str(getattr(attempt, "provider_status", "") or "").strip().lower()
        order_status = str(order.status or "").strip().lower()

        if order_status == ORDER_STATUS_FULFILLED:
            legacy_status = provider_status or RUNTIME_PAYMENT_STATUS_PAID
        elif provider_status:
            legacy_status = provider_status
        elif order_status == ORDER_STATUS_PENDING_PAYMENT:
            legacy_status = RUNTIME_PAYMENT_STATUS_PENDING
        else:
            legacy_status = order_status or RUNTIME_PAYMENT_STATUS_PENDING

        created_at = order.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        return PaymentSnapshot(
            payment_id=str(getattr(attempt, "provider_payment_id", "") or ""),
            user_id=int(order.user_id),
            tg_id=int(tg_id),
            status=legacy_status,
            payload=plan_payload,
            created_at=int(created_at.timestamp() * 1000),
            confirmed=bool(
                order.fulfilled_at is not None
                or order.subscription_grant_id is not None
                or order_status == ORDER_STATUS_FULFILLED
            ),
            method=str(getattr(attempt, "provider", "") or "").strip().lower() or None,
        )

    @staticmethod
    def _datetime_to_iso(value: datetime | None) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _datetime_to_legacy_ms(value: datetime | None) -> int | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)

    @staticmethod
    def _legacy_ms_to_iso(value: int | None) -> str | None:
        if value is None:
            return None
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat()

    async def list_promo_codes(self, *, limit: int = 100) -> list[dict[str, Any]]:
        async with get_db_session() as session:
            promos = (
                await session.execute(
                    select(PromoCodeV2)
                    .order_by(desc(PromoCodeV2.created_at))
                    .limit(limit)
                )
            ).scalars().all()

            result = []
            for promo in promos:
                redemptions_count = (
                    await session.execute(
                        select(func.count(PromoRedemption.id)).where(
                            PromoRedemption.promo_code_id == promo.id
                        )
                    )
                ).scalar_one()

                plan_name = None
                if promo.plan_id is not None:
                    from shared.models.payments.plan_model import Plan
                    plan = await session.get(Plan, promo.plan_id)
                    if plan:
                        plan_name = plan.name

                result.append({
                    "id": promo.id,
                    "code": promo.code,
                    "plan_id": promo.plan_id,
                    "plan_name": plan_name,
                    "duration_days_override": promo.duration_days_override,
                    "max_redemptions": promo.max_redemptions,
                    "per_user_limit": promo.per_user_limit,
                    "redemptions_count": int(redemptions_count or 0),
                    "valid_from": self._datetime_to_iso(promo.valid_from),
                    "valid_until": self._datetime_to_iso(promo.valid_until),
                    "is_active": promo.is_active,
                    "created_at": self._datetime_to_iso(promo.created_at),
                })
            return result

    async def create_promo_code(
        self,
        *,
        code: str,
        plan_id: int | None = None,
        duration_days_override: int | None = None,
        max_redemptions: int | None = None,
        per_user_limit: int = 1,
        valid_from: str | None = None,
        valid_until: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        parsed_valid_from = datetime.fromisoformat(valid_from) if valid_from else None
        parsed_valid_until = datetime.fromisoformat(valid_until) if valid_until else None

        async with get_db_session() as session:
            existing = (
                await session.execute(
                    select(PromoCodeV2).where(PromoCodeV2.code == code)
                )
            ).scalar_one_or_none()
            if existing:
                raise HTTPException(status_code=400, detail=f"Promo code '{code}' already exists")

            promo = PromoCodeV2(
                code=code,
                plan_id=plan_id,
                duration_days_override=duration_days_override,
                max_redemptions=max_redemptions,
                per_user_limit=per_user_limit,
                valid_from=parsed_valid_from,
                valid_until=parsed_valid_until,
                is_active=True,
                metadata_json={},
                created_at=now,
            )
            session.add(promo)
            await session.flush()
            await session.commit()
            await session.refresh(promo)

            return {
                "id": promo.id,
                "code": promo.code,
                "plan_id": promo.plan_id,
                "duration_days_override": promo.duration_days_override,
                "max_redemptions": promo.max_redemptions,
                "per_user_limit": promo.per_user_limit,
                "valid_from": self._datetime_to_iso(promo.valid_from),
                "valid_until": self._datetime_to_iso(promo.valid_until),
                "is_active": promo.is_active,
                "created_at": self._datetime_to_iso(promo.created_at),
            }

    async def toggle_promo_code(self, *, promo_id: int, is_active: bool) -> dict[str, Any]:
        async with get_db_session() as session:
            promo = await session.get(PromoCodeV2, promo_id)
            if not promo:
                raise HTTPException(status_code=404, detail="Promo code not found")

            promo.is_active = is_active
            session.add(promo)
            await session.commit()
            await session.refresh(promo)

            return {
                "id": promo.id,
                "code": promo.code,
                "is_active": promo.is_active,
            }

    @staticmethod
    def _subscription_routes():
        from backend.routers.subscription import subscription_routes

        return subscription_routes
