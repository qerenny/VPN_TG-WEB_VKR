from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.infrastructure.payment_plan_catalog import (
    get_plan_seed_by_code,
    get_plan_seed_by_legacy_payload,
)
from shared.models.payments.plan_model import Plan
from shared.models.traffic.traffic_grant_model import TrafficGrant
from shared.models.traffic.traffic_state_model import TrafficState
from shared.product_constants import (
    ENTITLEMENT_KIND_TRAFFIC,
    PRODUCT_SCOPE_WHITELIST,
)
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.services.subscriptions.whitelist_provisioning_service import (
    WhiteListProvisioningService,
)


@dataclass(frozen=True, slots=True)
class WhiteListActivationResult:
    user_id: int
    vpn_client_id: int
    granted_bytes: int
    allocated_bytes: int
    remaining_bytes: int
    expires_at: datetime | None
    was_created: bool


class WhiteListTrafficService:
    def __init__(
        self,
        provisioning_service: WhiteListProvisioningService,
        timestamp: TimestampUtils,
        client_manager,
    ):
        self.provisioning_service = provisioning_service
        self.timestamp = timestamp
        self.client_manager = client_manager

    async def activate_payment(
        self,
        *,
        tg_id: int,
        product: str,
        payment_id: str,
    ) -> WhiteListActivationResult:
        seed = get_plan_seed_by_legacy_payload(product)
        if seed is None:
            raise ValueError(f"Unsupported product: {product}")
        return await self._activate_seed(
            tg_id=tg_id,
            seed=seed,
            source_type="payment",
            source_ref=str(payment_id),
        )

    async def activate_payment_for_user(
        self,
        *,
        user_id: int,
        product: str,
        payment_id: str,
    ) -> WhiteListActivationResult:
        seed = get_plan_seed_by_legacy_payload(product)
        if seed is None:
            raise ValueError(f"Unsupported product: {product}")
        return await self._activate_seed_for_user(
            user_id=int(user_id),
            seed=seed,
            source_type="payment",
            source_ref=str(payment_id),
        )

    async def activate_trial(self, *, tg_id: int) -> WhiteListActivationResult:
        seed = get_plan_seed_by_code("whitelist_trial_2gb")
        if seed is None:
            raise ValueError("Whitelist trial plan is not configured")
        return await self._activate_seed(
            tg_id=tg_id,
            seed=seed,
            source_type="trial",
            source_ref=f"whitelist_trial:{int(tg_id)}",
        )

    async def has_used_trial(self, *, tg_id: int) -> bool:
        async with get_db_session() as session:
            existing_grant = (
                await session.execute(
                    select(TrafficGrant.id).where(
                        TrafficGrant.scope == PRODUCT_SCOPE_WHITELIST,
                        TrafficGrant.source_type == "trial",
                        TrafficGrant.source_ref == f"whitelist_trial:{int(tg_id)}",
                    )
                )
            ).first()
        return existing_grant is not None

    async def grant_admin_package_for_user(
        self,
        *,
        user_id: int,
        plan_code: str,
        source_ref: str,
    ) -> WhiteListActivationResult:
        seed = get_plan_seed_by_code(str(plan_code))
        if seed is None:
            raise ValueError(f"Unsupported whitelist plan code: {plan_code}")
        return await self._activate_seed_for_user(
            user_id=int(user_id),
            seed=seed,
            source_type="admin",
            source_ref=str(source_ref),
        )

    async def _activate_seed(
        self,
        *,
        tg_id: int,
        seed,
        source_type: str,
        source_ref: str,
    ) -> WhiteListActivationResult:
        if seed.scope != PRODUCT_SCOPE_WHITELIST:
            raise ValueError(f"Plan {seed.code} is not a whitelist product")
        if seed.entitlement_kind != ENTITLEMENT_KIND_TRAFFIC:
            raise ValueError(f"Plan {seed.code} is not traffic-based")
        if seed.quota_bytes is None or seed.quota_bytes <= 0:
            raise ValueError(f"Plan {seed.code} has no positive traffic quota")

        client_info = await self.provisioning_service.ensure_whitelist_client(
            tg_id,
            traffic_bytes=int(seed.quota_bytes),
            duration_days=int(seed.duration_days),
        )

        async with get_db_session() as session:
            existing_grant = (
                await session.execute(
                    select(TrafficGrant).where(
                        TrafficGrant.scope == PRODUCT_SCOPE_WHITELIST,
                        TrafficGrant.source_type == str(source_type),
                        TrafficGrant.source_ref == str(source_ref),
                    )
                )
            ).scalar_one_or_none()
            if existing_grant is not None:
                state = await session.get(TrafficState, int(client_info.vpn_client_id))
                return WhiteListActivationResult(
                    user_id=int(client_info.user_id),
                    vpn_client_id=int(client_info.vpn_client_id),
                    granted_bytes=int(existing_grant.granted_bytes),
                    allocated_bytes=int(getattr(state, "allocated_bytes", 0) or 0),
                    remaining_bytes=int(getattr(state, "remaining_bytes", 0) or 0),
                    expires_at=getattr(state, "expires_at", None),
                    was_created=False,
                )

            plan = (
                await session.execute(select(Plan).where(Plan.code == seed.code))
            ).scalar_one_or_none()
            if plan is None:
                raise ValueError(f"Plan {seed.code} not found")

            state = await session.get(TrafficState, int(client_info.vpn_client_id))
            current_expires_at = getattr(state, "expires_at", None)
            current_used_bytes = int(getattr(state, "used_bytes", 0) or 0)
            current_allocated_bytes = int(getattr(state, "allocated_bytes", 0) or 0)

            new_expires_at = self._extend_expiry(
                current_expires_at,
                duration_days=int(seed.duration_days),
            )
            new_allocated_bytes = current_allocated_bytes + int(seed.quota_bytes)
            new_remaining_bytes = max(0, new_allocated_bytes - current_used_bytes)

            grant = TrafficGrant(
                user_id=int(client_info.user_id),
                vpn_client_id=int(client_info.vpn_client_id),
                plan_id=int(plan.id),
                scope=PRODUCT_SCOPE_WHITELIST,
                source_type=str(source_type),
                source_ref=str(source_ref),
                status="applied",
                granted_bytes=int(seed.quota_bytes),
                expires_at=new_expires_at,
                is_trial=(seed.kind == "trial"),
                created_at=datetime.now(timezone.utc),
                applied_at=datetime.now(timezone.utc),
                metadata_json={
                    "legacy_payload": seed.legacy_payload,
                    "plan_code": seed.code,
                    "source_type": str(source_type),
                },
            )
            session.add(grant)

            if state is None:
                state = TrafficState(
                    vpn_client_id=int(client_info.vpn_client_id),
                    scope=PRODUCT_SCOPE_WHITELIST,
                    allocated_bytes=new_allocated_bytes,
                    used_bytes=current_used_bytes,
                    remaining_bytes=new_remaining_bytes,
                    expires_at=new_expires_at,
                    is_blocked=new_remaining_bytes <= 0,
                    block_reason="quota_depleted" if new_remaining_bytes <= 0 else None,
                    last_provider_sync_at=None,
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(state)
            else:
                state.scope = PRODUCT_SCOPE_WHITELIST
                state.allocated_bytes = new_allocated_bytes
                state.remaining_bytes = new_remaining_bytes
                state.expires_at = new_expires_at
                state.is_blocked = new_remaining_bytes <= 0
                state.block_reason = (
                    "quota_depleted" if new_remaining_bytes <= 0 else None
                )
                state.updated_at = datetime.now(timezone.utc)

            await session.commit()

        await self.client_manager.update_scoped_client(
            server_pool=self.provisioning_service._get_server_pool(),
            cache_namespace=PRODUCT_SCOPE_WHITELIST,
            tg_id=int(tg_id),
            client_uuid=str(client_info.client_uuid),
            email=str(client_info.email),
            sub_id=str(client_info.subscription_id),
            expires_at=self._datetime_to_legacy_ms(new_expires_at),
            total_bytes=new_allocated_bytes,
        )

        logger.info(
            f"Activated whitelist package for tg_id={tg_id}, source_type={source_type}, "
            f"source_ref={source_ref}, allocated_bytes={new_allocated_bytes}, "
            f"remaining_bytes={new_remaining_bytes}"
        )
        return WhiteListActivationResult(
            user_id=int(client_info.user_id),
            vpn_client_id=int(client_info.vpn_client_id),
            granted_bytes=int(seed.quota_bytes),
            allocated_bytes=new_allocated_bytes,
            remaining_bytes=new_remaining_bytes,
            expires_at=new_expires_at,
            was_created=True,
        )

    async def _activate_seed_for_user(
        self,
        *,
        user_id: int,
        seed,
        source_type: str,
        source_ref: str,
    ) -> WhiteListActivationResult:
        if seed.scope != PRODUCT_SCOPE_WHITELIST:
            raise ValueError(f"Plan {seed.code} is not a whitelist product")
        if seed.entitlement_kind != ENTITLEMENT_KIND_TRAFFIC:
            raise ValueError(f"Plan {seed.code} is not traffic-based")
        if seed.quota_bytes is None or seed.quota_bytes <= 0:
            raise ValueError(f"Plan {seed.code} has no positive traffic quota")

        client_info = await self.provisioning_service.ensure_whitelist_client_for_user(
            user_id=int(user_id),
            traffic_bytes=int(seed.quota_bytes),
            duration_days=int(seed.duration_days),
        )

        async with get_db_session() as session:
            existing_grant = (
                await session.execute(
                    select(TrafficGrant).where(
                        TrafficGrant.scope == PRODUCT_SCOPE_WHITELIST,
                        TrafficGrant.source_type == str(source_type),
                        TrafficGrant.source_ref == str(source_ref),
                    )
                )
            ).scalar_one_or_none()
            if existing_grant is not None:
                state = await session.get(TrafficState, int(client_info.vpn_client_id))
                return WhiteListActivationResult(
                    user_id=int(client_info.user_id),
                    vpn_client_id=int(client_info.vpn_client_id),
                    granted_bytes=int(existing_grant.granted_bytes),
                    allocated_bytes=int(getattr(state, "allocated_bytes", 0) or 0),
                    remaining_bytes=int(getattr(state, "remaining_bytes", 0) or 0),
                    expires_at=getattr(state, "expires_at", None),
                    was_created=False,
                )

            plan = (
                await session.execute(select(Plan).where(Plan.code == seed.code))
            ).scalar_one_or_none()
            if plan is None:
                raise ValueError(f"Plan {seed.code} not found")

            state = await session.get(TrafficState, int(client_info.vpn_client_id))
            current_expires_at = getattr(state, "expires_at", None)
            current_used_bytes = int(getattr(state, "used_bytes", 0) or 0)
            current_allocated_bytes = int(getattr(state, "allocated_bytes", 0) or 0)

            new_expires_at = self._extend_expiry(
                current_expires_at,
                duration_days=int(seed.duration_days),
            )
            new_allocated_bytes = current_allocated_bytes + int(seed.quota_bytes)
            new_remaining_bytes = max(0, new_allocated_bytes - current_used_bytes)

            grant = TrafficGrant(
                user_id=int(client_info.user_id),
                vpn_client_id=int(client_info.vpn_client_id),
                plan_id=int(plan.id),
                scope=PRODUCT_SCOPE_WHITELIST,
                source_type=str(source_type),
                source_ref=str(source_ref),
                status="applied",
                granted_bytes=int(seed.quota_bytes),
                expires_at=new_expires_at,
                is_trial=(seed.kind == "trial"),
                created_at=datetime.now(timezone.utc),
                applied_at=datetime.now(timezone.utc),
                metadata_json={
                    "legacy_payload": seed.legacy_payload,
                    "plan_code": seed.code,
                    "source_type": str(source_type),
                    "channel": "web",
                },
            )
            session.add(grant)

            if state is None:
                state = TrafficState(
                    vpn_client_id=int(client_info.vpn_client_id),
                    scope=PRODUCT_SCOPE_WHITELIST,
                    allocated_bytes=new_allocated_bytes,
                    used_bytes=current_used_bytes,
                    remaining_bytes=new_remaining_bytes,
                    expires_at=new_expires_at,
                    is_blocked=new_remaining_bytes <= 0,
                    block_reason="quota_depleted" if new_remaining_bytes <= 0 else None,
                    last_provider_sync_at=None,
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(state)
            else:
                state.scope = PRODUCT_SCOPE_WHITELIST
                state.allocated_bytes = new_allocated_bytes
                state.remaining_bytes = new_remaining_bytes
                state.expires_at = new_expires_at
                state.is_blocked = new_remaining_bytes <= 0
                state.block_reason = (
                    "quota_depleted" if new_remaining_bytes <= 0 else None
                )
                state.updated_at = datetime.now(timezone.utc)

            await session.commit()

        await self.client_manager.update_scoped_client(
            server_pool=self.provisioning_service._get_server_pool(),
            cache_namespace=PRODUCT_SCOPE_WHITELIST,
            tg_id=0,
            client_uuid=str(client_info.client_uuid),
            email=str(client_info.email),
            sub_id=str(client_info.subscription_id),
            expires_at=self._datetime_to_legacy_ms(new_expires_at),
            total_bytes=new_allocated_bytes,
        )

        logger.info(
            f"Activated whitelist package for user_id={user_id}, source_type={source_type}, "
            f"source_ref={source_ref}, allocated_bytes={new_allocated_bytes}, "
            f"remaining_bytes={new_remaining_bytes}"
        )
        return WhiteListActivationResult(
            user_id=int(client_info.user_id),
            vpn_client_id=int(client_info.vpn_client_id),
            granted_bytes=int(seed.quota_bytes),
            allocated_bytes=new_allocated_bytes,
            remaining_bytes=new_remaining_bytes,
            expires_at=new_expires_at,
            was_created=True,
        )

    @staticmethod
    def _extend_expiry(
        current_expires_at: datetime | None,
        *,
        duration_days: int,
    ) -> datetime:
        now = datetime.now(timezone.utc)
        base = now
        if current_expires_at is not None:
            normalized = (
                current_expires_at
                if current_expires_at.tzinfo is not None
                else current_expires_at.replace(tzinfo=timezone.utc)
            )
            if normalized > now:
                base = normalized
        return base + timedelta(days=int(duration_days))

    @staticmethod
    def _datetime_to_legacy_ms(value: datetime | None) -> int:
        if value is None:
            return 0
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return int(normalized.timestamp() * 1000)
