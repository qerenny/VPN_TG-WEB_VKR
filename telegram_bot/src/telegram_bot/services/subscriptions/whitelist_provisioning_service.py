from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import select

from shared.config.config import WHITELIST_API_SERVERS
from shared.config.database.session import get_db_session
from shared.constants.vpn import VPN_PROVIDER_3X_UI
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.web_account_model import WebAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.product_constants import PRODUCT_SCOPE_WHITELIST
from shared.utils.client_identity import build_vpn_client_email
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.infrastructure.api.client_manager import ClientManager
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator


@dataclass(frozen=True, slots=True)
class WhiteListClientInfo:
    user_id: int
    vpn_client_id: int
    client_uuid: str
    email: str
    subscription_id: str
    scope: str


class WhiteListProvisioningService:
    def __init__(
        self,
        repo,
        timestamp: TimestampUtils,
        client_manager: ClientManager,
        uuidgen: UUIDGenerator,
    ):
        self.repo = repo
        self.timestamp = timestamp
        self.client_manager = client_manager
        self.uuidgen = uuidgen

    @staticmethod
    def _get_server_pool() -> dict[str, dict]:
        return WHITELIST_API_SERVERS

    async def ensure_whitelist_client(
        self,
        tg_id: int,
        *,
        traffic_bytes: int,
        duration_days: int,
    ) -> WhiteListClientInfo:
        if traffic_bytes <= 0:
            raise ValueError("traffic_bytes must be positive")
        if duration_days <= 0:
            raise ValueError("duration_days must be positive")

        legacy_user = await self.repo.get(tg_id)
        if not legacy_user:
            raise AttributeError("User not found")

        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.telegram_id == int(tg_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if telegram_account is None:
                raise AttributeError("Telegram account not found")

            existing_client = (
                await session.execute(
                    select(VpnClient).where(
                        VpnClient.user_id == int(telegram_account.user_id),
                        VpnClient.scope == PRODUCT_SCOPE_WHITELIST,
                        VpnClient.deactivated_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if existing_client is not None:
                await self.client_manager.sync_v2_scoped_topology(
                    vpn_client_id=int(existing_client.id),
                    scope=PRODUCT_SCOPE_WHITELIST,
                )
                return self._to_info(existing_client)

            server_pool = self._get_server_pool()
            if not server_pool:
                raise ValueError("WhiteList servers are not configured")

            client_uuid = self.uuidgen.generate_id()
            subscription_id = self.uuidgen.generate_id()
            external_email = build_vpn_client_email(
                seed=str(legacy_user.email or ""),
                client_uuid=client_uuid,
                scope=PRODUCT_SCOPE_WHITELIST,
            )
            expires_at = self.timestamp.set_client_date(f"day{duration_days}")

            await self.client_manager.add_scoped_client(
                server_pool=server_pool,
                cache_namespace=PRODUCT_SCOPE_WHITELIST,
                tg_id=int(tg_id),
                client_uuid=client_uuid,
                email=external_email,
                sub_id=subscription_id,
                expires_at=expires_at,
                total_bytes=int(traffic_bytes),
            )

            vpn_client = VpnClient(
                user_id=int(telegram_account.user_id),
                scope=PRODUCT_SCOPE_WHITELIST,
                provider=VPN_PROVIDER_3X_UI,
                external_client_uuid=client_uuid,
                external_email=external_email,
                subscription_external_id=subscription_id,
                metadata_json={"bootstrap_traffic_bytes": int(traffic_bytes)},
                created_at=self.timestamp.current_time(),
                updated_at=self.timestamp.current_time(),
                deactivated_at=None,
            )
            session.add(vpn_client)
            await session.commit()
            await session.refresh(vpn_client)
            await self.client_manager.sync_v2_scoped_topology(
                vpn_client_id=int(vpn_client.id),
                scope=PRODUCT_SCOPE_WHITELIST,
            )
            logger.info(
                f"Provisioned whitelist client for tg_id={tg_id}, vpn_client_id={vpn_client.id}"
            )
            return self._to_info(vpn_client)

    async def ensure_whitelist_client_for_user(
        self,
        *,
        user_id: int,
        traffic_bytes: int,
        duration_days: int,
    ) -> WhiteListClientInfo:
        if traffic_bytes <= 0:
            raise ValueError("traffic_bytes must be positive")
        if duration_days <= 0:
            raise ValueError("duration_days must be positive")

        async with get_db_session() as session:
            existing_client = (
                await session.execute(
                    select(VpnClient).where(
                        VpnClient.user_id == int(user_id),
                        VpnClient.scope == PRODUCT_SCOPE_WHITELIST,
                        VpnClient.deactivated_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if existing_client is not None:
                await self.client_manager.sync_v2_scoped_topology(
                    vpn_client_id=int(existing_client.id),
                    scope=PRODUCT_SCOPE_WHITELIST,
                )
                return self._to_info(existing_client)

            web_account = (
                await session.execute(
                    select(WebAccount).where(
                        WebAccount.user_id == int(user_id),
                        WebAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if web_account is None:
                raise ValueError(f"Web account not found for user_id={user_id}")

            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.user_id == int(user_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

            server_pool = self._get_server_pool()
            if not server_pool:
                raise ValueError("WhiteList servers are not configured")

            client_uuid = self.uuidgen.generate_id()
            subscription_id = self.uuidgen.generate_id()
            external_email = build_vpn_client_email(
                seed=str(web_account.email or ""),
                client_uuid=client_uuid,
                scope=PRODUCT_SCOPE_WHITELIST,
            )
            expires_at = self.timestamp.set_client_date(f"day{duration_days}")
            tg_id = int(telegram_account.telegram_id) if telegram_account is not None else 0

            await self.client_manager.add_scoped_client(
                server_pool=server_pool,
                cache_namespace=PRODUCT_SCOPE_WHITELIST,
                tg_id=tg_id,
                client_uuid=client_uuid,
                email=external_email,
                sub_id=subscription_id,
                expires_at=expires_at,
                total_bytes=int(traffic_bytes),
            )

            now = self.timestamp.current_time()
            vpn_client = VpnClient(
                user_id=int(user_id),
                scope=PRODUCT_SCOPE_WHITELIST,
                provider=VPN_PROVIDER_3X_UI,
                external_client_uuid=client_uuid,
                external_email=external_email,
                subscription_external_id=subscription_id,
                metadata_json={"bootstrap_traffic_bytes": int(traffic_bytes), "bootstrap_channel": "web"},
                created_at=now,
                updated_at=now,
                deactivated_at=None,
            )
            session.add(vpn_client)
            await session.commit()
            await session.refresh(vpn_client)
            await self.client_manager.sync_v2_scoped_topology(
                vpn_client_id=int(vpn_client.id),
                scope=PRODUCT_SCOPE_WHITELIST,
            )
            logger.info(
                f"Provisioned whitelist client for user_id={user_id}, vpn_client_id={vpn_client.id}"
            )
            return self._to_info(vpn_client)

    @staticmethod
    def _to_info(vpn_client: VpnClient) -> WhiteListClientInfo:
        return WhiteListClientInfo(
            user_id=int(vpn_client.user_id),
            vpn_client_id=int(vpn_client.id),
            client_uuid=str(vpn_client.external_client_uuid),
            email=str(vpn_client.external_email),
            subscription_id=str(vpn_client.subscription_external_id),
            scope=str(vpn_client.scope),
        )
