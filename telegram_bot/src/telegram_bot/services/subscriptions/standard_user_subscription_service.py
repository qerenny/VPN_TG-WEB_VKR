from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from shared.config.config import API_SERVERS
from shared.config.database.session import get_db_session
from shared.constants.vpn import VPN_PROVIDER_3X_UI
from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_payload
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.web_account_model import WebAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.product_constants import ENTITLEMENT_KIND_TIME, PRODUCT_SCOPE_STANDARD
from shared.utils.client_identity import build_vpn_client_email, resolve_user_identity_seed
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import datetime_to_legacy_ms
from telegram_bot.infrastructure.api.client_manager import ClientManager
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator


@dataclass(frozen=True, slots=True)
class StandardUserActivationResult:
    user_id: int
    vpn_client_id: int
    expires_at: datetime
    was_created: bool


class StandardUserSubscriptionService:
    def __init__(
        self,
        *,
        client_manager: ClientManager,
        uuidgen: UUIDGenerator,
    ) -> None:
        self.client_manager = client_manager
        self.uuidgen = uuidgen

    async def activate_payment(
        self,
        *,
        user_id: int,
        product: str,
    ) -> StandardUserActivationResult:
        seed = get_plan_seed_by_payload(product)
        if seed is None:
            raise ValueError(f"Unsupported product: {product!r}")
        if seed.scope != PRODUCT_SCOPE_STANDARD or seed.entitlement_kind != ENTITLEMENT_KIND_TIME:
            raise ValueError(f"Product {product!r} is not a standard time-based plan")

        return await self._activate_duration(
            user_id=user_id,
            duration_days=int(seed.duration_days),
        )

    async def activate_days(
        self,
        *,
        user_id: int,
        duration_days: int,
        replace_existing: bool = False,
    ) -> StandardUserActivationResult:
        if int(duration_days) <= 0:
            raise ValueError(f"duration_days must be positive, got {duration_days}")
        return await self._activate_duration(
            user_id=user_id,
            duration_days=int(duration_days),
            replace_existing=bool(replace_existing),
        )

    async def _activate_duration(
        self,
        *,
        user_id: int,
        duration_days: int,
        replace_existing: bool = False,
    ) -> StandardUserActivationResult:
        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.user_id == int(user_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            web_account = (
                await session.execute(
                    select(WebAccount).where(
                        WebAccount.user_id == int(user_id),
                        WebAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            vpn_client = (
                await session.execute(
                    select(VpnClient).where(
                        VpnClient.user_id == int(user_id),
                        VpnClient.scope == PRODUCT_SCOPE_STANDARD,
                        VpnClient.deactivated_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            state = await session.get(SubscriptionState, int(user_id))

            current_expires_at = getattr(state, "current_expires_at", None)
            new_expires_at = self._extend_expiry(
                current_expires_at=current_expires_at,
                duration_days=int(duration_days),
                replace_existing=bool(replace_existing),
            )
            tg_id = int(telegram_account.telegram_id) if telegram_account is not None else 0

            if vpn_client is None:
                client_uuid = self.uuidgen.generate_id()
                subscription_id = self.uuidgen.generate_id()
                identity_seed = resolve_user_identity_seed(
                    web_email=str(web_account.email) if web_account is not None else None,
                    telegram_username=getattr(telegram_account, "username", None),
                    telegram_id=int(telegram_account.telegram_id) if telegram_account is not None else None,
                    user_id=int(user_id),
                )
                external_email = build_vpn_client_email(
                    seed=identity_seed,
                    client_uuid=client_uuid,
                    scope=PRODUCT_SCOPE_STANDARD,
                )
                await self.client_manager.add_scoped_client(
                    server_pool=API_SERVERS,
                    cache_namespace=PRODUCT_SCOPE_STANDARD,
                    tg_id=tg_id,
                    client_uuid=client_uuid,
                    email=external_email,
                    sub_id=subscription_id,
                    expires_at=datetime_to_legacy_ms(new_expires_at),
                    total_bytes=0,
                )
                now = datetime.now(timezone.utc)
                vpn_client = VpnClient(
                    user_id=int(user_id),
                    scope=PRODUCT_SCOPE_STANDARD,
                    provider=VPN_PROVIDER_3X_UI,
                    external_client_uuid=client_uuid,
                    external_email=external_email,
                    subscription_external_id=subscription_id,
                    metadata_json={"bootstrap_channel": "web"},
                    created_at=now,
                    updated_at=now,
                    deactivated_at=None,
                )
                session.add(vpn_client)
                await session.flush()
                was_created = True
            else:
                client_uuid = str(vpn_client.external_client_uuid)
                external_email = str(vpn_client.external_email)
                subscription_id = str(vpn_client.subscription_external_id)
                client_exists = await self.client_manager.client_exists(client_uuid)
                if client_exists:
                    await self.client_manager.update_scoped_client(
                        server_pool=API_SERVERS,
                        cache_namespace=PRODUCT_SCOPE_STANDARD,
                        tg_id=tg_id,
                        client_uuid=client_uuid,
                        email=external_email,
                        sub_id=subscription_id,
                        expires_at=datetime_to_legacy_ms(new_expires_at),
                        total_bytes=0,
                    )
                else:
                    logger.warning(
                        f"Standard vpn_client missing in remote panel for user_id={user_id}, "
                        f"vpn_client_id={vpn_client.id}; re-provisioning with existing identifiers"
                    )
                    await self.client_manager.add_scoped_client(
                        server_pool=API_SERVERS,
                        cache_namespace=PRODUCT_SCOPE_STANDARD,
                        tg_id=tg_id,
                        client_uuid=client_uuid,
                        email=external_email,
                        sub_id=subscription_id,
                        expires_at=datetime_to_legacy_ms(new_expires_at),
                        total_bytes=0,
                    )
                vpn_client.updated_at = datetime.now(timezone.utc)
                was_created = False

            if state is None:
                state = SubscriptionState(
                    user_id=int(user_id),
                    current_expires_at=new_expires_at,
                    trial_activated_at=None,
                    info_channel_activated_at=None,
                    blocked_at=None,
                    updated_at=datetime.now(timezone.utc),
                    version=0,
                )
                session.add(state)
            else:
                state.current_expires_at = new_expires_at
                state.blocked_at = None
                state.updated_at = datetime.now(timezone.utc)
                state.version += 1

            await session.commit()
            vpn_client_id = int(vpn_client.id)

        await self.client_manager.sync_v2_scoped_topology(
            vpn_client_id=vpn_client_id,
            scope=PRODUCT_SCOPE_STANDARD,
        )
        logger.info(
            f"Activated standard subscription for user_id={user_id}, "
            f"vpn_client_id={vpn_client_id}, created={was_created}"
        )
        return StandardUserActivationResult(
            user_id=int(user_id),
            vpn_client_id=vpn_client_id,
            expires_at=new_expires_at,
            was_created=was_created,
        )

    @staticmethod
    def _extend_expiry(*, current_expires_at: datetime | None, duration_days: int, replace_existing: bool = False) -> datetime:
        now = datetime.now(timezone.utc)
        base = now
        if not replace_existing and current_expires_at is not None:
            normalized = (
                current_expires_at
                if current_expires_at.tzinfo is not None
                else current_expires_at.replace(tzinfo=timezone.utc)
            )
            if normalized > now:
                base = normalized
        return base + timedelta(days=int(duration_days))

    async def revoke_access(self, *, user_id: int) -> bool:
        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.user_id == int(user_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            vpn_client = (
                await session.execute(
                    select(VpnClient).where(
                        VpnClient.user_id == int(user_id),
                        VpnClient.scope == PRODUCT_SCOPE_STANDARD,
                        VpnClient.deactivated_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            state = await session.get(SubscriptionState, int(user_id))
            if state is None:
                return False
            now = datetime.now(timezone.utc)
            state.current_expires_at = now
            state.blocked_at = None
            state.updated_at = now
            state.version += 1
            session.add(state)
            await session.commit()

        if vpn_client is not None:
            tg_id = int(telegram_account.telegram_id) if telegram_account is not None else 0
            await self.client_manager.update_scoped_client(
                server_pool=API_SERVERS,
                cache_namespace=PRODUCT_SCOPE_STANDARD,
                tg_id=tg_id,
                client_uuid=str(vpn_client.external_client_uuid),
                email=str(vpn_client.external_email),
                sub_id=str(vpn_client.subscription_external_id),
                expires_at=datetime_to_legacy_ms(now),
                total_bytes=0,
            )
        return True
