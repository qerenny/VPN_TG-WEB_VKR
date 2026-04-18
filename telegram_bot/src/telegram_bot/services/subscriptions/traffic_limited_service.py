from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.infrastructure.payment_plan_catalog import (
    get_plan_seed_by_code,
    get_plan_seed_by_payload,
)
from shared.models.payments.plan_model import Plan
from shared.models.traffic.traffic_grant_model import TrafficGrant
from shared.models.traffic.traffic_state_model import TrafficState
from shared.product_constants import (
    ENTITLEMENT_KIND_TRAFFIC,
    PRODUCT_SCOPE_TRAFFIC_LIMITED,
)
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils, datetime_to_legacy_ms
from telegram_bot.services.subscriptions.traffic_limited_provisioning_service import (
    TrafficLimitedProvisioningService,
)


@dataclass(frozen=True, slots=True)
class TrafficLimitedActivationResult:
    user_id: int
    vpn_client_id: int
    granted_bytes: int
    allocated_bytes: int
    remaining_bytes: int
    expires_at: datetime | None
    was_created: bool


class TrafficLimitedService:
    def __init__(
        self,
        provisioning_service: TrafficLimitedProvisioningService,
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
    ) -> TrafficLimitedActivationResult:
        return await self.activate_source(
            tg_id=int(tg_id),
            product=str(product),
            source_type="payment",
            source_ref=str(payment_id),
        )

    async def activate_source(
        self,
        *,
        tg_id: int,
        product: str,
        source_type: str,
        source_ref: str,
    ) -> TrafficLimitedActivationResult:
        seed = get_plan_seed_by_payload(product)
        if seed is None:
            raise ValueError(f"Unsupported product: {product}")
        return await self._activate_seed(
            tg_id=tg_id,
            seed=seed,
            source_type=str(source_type),
            source_ref=str(source_ref),
        )

    async def activate_source_for_user(
        self,
        *,
        user_id: int,
        product: str,
        source_type: str,
        source_ref: str,
        duration_days_override: int | None = None,
        quota_bytes_override: int | None = None,
    ) -> TrafficLimitedActivationResult:
        seed = get_plan_seed_by_payload(product)
        if seed is None:
            raise ValueError(f"Unsupported product: {product}")
        return await self._activate_seed_for_user(
            user_id=int(user_id),
            seed=seed,
            source_type=str(source_type),
            source_ref=str(source_ref),
            duration_days_override=duration_days_override,
            quota_bytes_override=quota_bytes_override,
        )

    async def activate_trial(self, *, tg_id: int) -> TrafficLimitedActivationResult:
        seed = get_plan_seed_by_code("traffic_limited_trial_2gb")
        if seed is None:
            raise ValueError("TrafficLimited trial plan is not configured")
        return await self._activate_seed(
            tg_id=tg_id,
            seed=seed,
            source_type="trial",
            source_ref=f"traffic_limited_trial:{int(tg_id)}",
        )

    async def has_used_trial(self, *, tg_id: int) -> bool:
        async with get_db_session() as session:
            existing_grant = (
                await session.execute(
                    select(TrafficGrant.id).where(
                        TrafficGrant.scope == PRODUCT_SCOPE_TRAFFIC_LIMITED,
                        TrafficGrant.source_type == "trial",
                        TrafficGrant.source_ref == f"traffic_limited_trial:{int(tg_id)}",
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
        duration_days_override: int | None = None,
        quota_bytes_override: int | None = None,
    ) -> TrafficLimitedActivationResult:
        seed = get_plan_seed_by_code(str(plan_code))
        if seed is None:
            raise ValueError(f"Unsupported traffic_limited plan code: {plan_code}")
        return await self._activate_seed_for_user(
            user_id=int(user_id),
            seed=seed,
            source_type="admin",
            source_ref=str(source_ref),
            duration_days_override=duration_days_override,
            quota_bytes_override=quota_bytes_override,
        )

    async def _activate_seed(
        self,
        *,
        tg_id: int,
        seed,
        source_type: str,
        source_ref: str,
    ) -> TrafficLimitedActivationResult:
        if seed.scope != PRODUCT_SCOPE_TRAFFIC_LIMITED:
            raise ValueError(f"Plan {seed.code} is not a traffic_limited product")
        if seed.entitlement_kind != ENTITLEMENT_KIND_TRAFFIC:
            raise ValueError(f"Plan {seed.code} is not traffic-based")
        if seed.quota_bytes is None or seed.quota_bytes <= 0:
            raise ValueError(f"Plan {seed.code} has no positive traffic quota")

        client_info = await self.provisioning_service.ensure_traffic_limited_client(
            tg_id,
            traffic_bytes=int(seed.quota_bytes),
            duration_days=int(seed.duration_days),
        )

        async with get_db_session() as session:
            existing_grant = (
                await session.execute(
                    select(TrafficGrant).where(
                        TrafficGrant.scope == PRODUCT_SCOPE_TRAFFIC_LIMITED,
                        TrafficGrant.source_type == str(source_type),
                        TrafficGrant.source_ref == str(source_ref),
                    )
                )
            ).scalar_one_or_none()
            if existing_grant is not None:
                state = await session.get(TrafficState, int(client_info.vpn_client_id))
                return TrafficLimitedActivationResult(
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
                scope=PRODUCT_SCOPE_TRAFFIC_LIMITED,
                source_type=str(source_type),
                source_ref=str(source_ref),
                status="applied",
                granted_bytes=int(seed.quota_bytes),
                expires_at=new_expires_at,
                is_trial=(seed.kind == "trial"),
                created_at=datetime.now(timezone.utc),
                applied_at=datetime.now(timezone.utc),
                metadata_json={
                    "plan_payload": seed.payload,
                    "plan_code": seed.code,
                    "source_type": str(source_type),
                },
            )
            session.add(grant)

            if state is None:
                state = TrafficState(
                    vpn_client_id=int(client_info.vpn_client_id),
                    scope=PRODUCT_SCOPE_TRAFFIC_LIMITED,
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
                state.scope = PRODUCT_SCOPE_TRAFFIC_LIMITED
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
            cache_namespace=PRODUCT_SCOPE_TRAFFIC_LIMITED,
            tg_id=int(tg_id),
            client_uuid=str(client_info.client_uuid),
            email=str(client_info.email),
            sub_id=str(client_info.subscription_id),
            expires_at=datetime_to_legacy_ms(new_expires_at, none_value=0),
            total_bytes=new_allocated_bytes,
        )

        logger.info(
            f"Activated traffic_limited package for tg_id={tg_id}, source_type={source_type}, "
            f"source_ref={source_ref}, allocated_bytes={new_allocated_bytes}, "
            f"remaining_bytes={new_remaining_bytes}"
        )
        return TrafficLimitedActivationResult(
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
        duration_days_override: int | None = None,
        quota_bytes_override: int | None = None,
    ) -> TrafficLimitedActivationResult:
        if seed.scope != PRODUCT_SCOPE_TRAFFIC_LIMITED:
            raise ValueError(f"Plan {seed.code} is not a traffic_limited product")
        if seed.entitlement_kind != ENTITLEMENT_KIND_TRAFFIC:
            raise ValueError(f"Plan {seed.code} is not traffic-based")
        resolved_quota_bytes = int(quota_bytes_override) if quota_bytes_override is not None else int(seed.quota_bytes or 0)
        resolved_duration_days = int(duration_days_override) if duration_days_override is not None else int(seed.duration_days)
        if resolved_quota_bytes <= 0:
            raise ValueError(f"Plan {seed.code} has no positive traffic quota")

        client_info = await self.provisioning_service.ensure_traffic_limited_client_for_user(
            user_id=int(user_id),
            traffic_bytes=resolved_quota_bytes,
            duration_days=resolved_duration_days,
        )

        async with get_db_session() as session:
            existing_grant = (
                await session.execute(
                    select(TrafficGrant).where(
                        TrafficGrant.scope == PRODUCT_SCOPE_TRAFFIC_LIMITED,
                        TrafficGrant.source_type == str(source_type),
                        TrafficGrant.source_ref == str(source_ref),
                    )
                )
            ).scalar_one_or_none()
            if existing_grant is not None:
                state = await session.get(TrafficState, int(client_info.vpn_client_id))
                return TrafficLimitedActivationResult(
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
                duration_days=resolved_duration_days,
            )
            new_allocated_bytes = current_allocated_bytes + resolved_quota_bytes
            new_remaining_bytes = max(0, new_allocated_bytes - current_used_bytes)

            grant = TrafficGrant(
                user_id=int(client_info.user_id),
                vpn_client_id=int(client_info.vpn_client_id),
                plan_id=int(plan.id),
                scope=PRODUCT_SCOPE_TRAFFIC_LIMITED,
                source_type=str(source_type),
                source_ref=str(source_ref),
                status="applied",
                granted_bytes=resolved_quota_bytes,
                expires_at=new_expires_at,
                is_trial=(seed.kind == "trial"),
                created_at=datetime.now(timezone.utc),
                applied_at=datetime.now(timezone.utc),
                metadata_json={
                    "plan_payload": seed.payload,
                    "plan_code": seed.code,
                    "source_type": str(source_type),
                    "channel": "web",
                    "duration_days_override": duration_days_override,
                    "quota_bytes_override": quota_bytes_override,
                },
            )
            session.add(grant)

            if state is None:
                state = TrafficState(
                    vpn_client_id=int(client_info.vpn_client_id),
                    scope=PRODUCT_SCOPE_TRAFFIC_LIMITED,
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
                state.scope = PRODUCT_SCOPE_TRAFFIC_LIMITED
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
            cache_namespace=PRODUCT_SCOPE_TRAFFIC_LIMITED,
            tg_id=0,
            client_uuid=str(client_info.client_uuid),
            email=str(client_info.email),
            sub_id=str(client_info.subscription_id),
            expires_at=datetime_to_legacy_ms(new_expires_at, none_value=0),
            total_bytes=new_allocated_bytes,
        )

        logger.info(
            f"Activated traffic_limited package for user_id={user_id}, source_type={source_type}, "
            f"source_ref={source_ref}, allocated_bytes={new_allocated_bytes}, "
            f"remaining_bytes={new_remaining_bytes}"
        )
        return TrafficLimitedActivationResult(
            user_id=int(client_info.user_id),
            vpn_client_id=int(client_info.vpn_client_id),
            granted_bytes=resolved_quota_bytes,
            allocated_bytes=new_allocated_bytes,
            remaining_bytes=new_remaining_bytes,
            expires_at=new_expires_at,
            was_created=True,
        )

    async def revoke_access_for_user(self, *, user_id: int) -> bool:
        async with get_db_session() as session:
            latest_grant = (
                await session.execute(
                    select(TrafficGrant).where(TrafficGrant.user_id == int(user_id)).order_by(
                        TrafficGrant.created_at.desc(),
                        TrafficGrant.id.desc(),
                    ).limit(1)
                )
            ).scalar_one_or_none()
            if latest_grant is None:
                return False
            state = await session.get(TrafficState, int(latest_grant.vpn_client_id))
            if state is None:
                return False
            now = datetime.now(timezone.utc)
            state.remaining_bytes = 0
            state.expires_at = now
            state.is_blocked = True
            state.block_reason = "admin_revoked"
            state.updated_at = now
            session.add(state)
            await session.commit()
        return True

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
