from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import or_
from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.config.settings import RolloutFeatureFlags
from shared.constants.vpn import VPN_PROVIDER_3X_UI
from shared.migration_support.models.users.user_model import User as LegacyUser
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.product_constants import PRODUCT_SCOPE_STANDARD
from shared.utils.logging_utils import setup_logger

logger = setup_logger("rollout.phase1.sync", "database.log")

class IdentitySubscriptionSyncService:
    def __init__(self, features: RolloutFeatureFlags):
        self.features = features

    async def sync_legacy_user(
        self,
        user: LegacyUser,
        *,
        telegram_username: str | None = None,
    ) -> int | None:
        if not (
            self.features.db_dual_write_identity
            or self.features.db_dual_write_subscription
        ):
            return None

        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            app_user = await self._get_or_create_app_user(session, user, now)
            await self._upsert_telegram_account(
                session=session,
                user_id=int(app_user.id),
                telegram_id=int(user.tg_id),
                telegram_username=telegram_username,
                seen_at=self._legacy_ts_to_datetime(user.login_date) or now,
            )
            await self._upsert_vpn_client(
                session=session,
                user_id=int(app_user.id),
                legacy_user=user,
                now=now,
            )

            if self.features.db_dual_write_subscription:
                await self._upsert_subscription_state(
                    session=session,
                    user_id=int(app_user.id),
                    legacy_user=user,
                    now=now,
                )

            await session.commit()
            return int(app_user.id)

    async def _get_or_create_app_user(
        self,
        session,
        legacy_user: LegacyUser,
        now: datetime,
    ) -> AppUser:
        account_stmt = select(TelegramAccount).where(
            TelegramAccount.telegram_id == int(legacy_user.tg_id),
        )
        account = (await session.execute(account_stmt)).scalar_one_or_none()
        if account:
            user = await session.get(AppUser, account.user_id)
            if user is not None:
                user.updated_at = now
                return user

        client_stmt = select(VpnClient).where(
            VpnClient.scope == PRODUCT_SCOPE_STANDARD,
            VpnClient.deactivated_at.is_(None),
            or_(
                VpnClient.external_client_uuid == str(legacy_user.uuid),
                VpnClient.subscription_external_id == str(legacy_user.sub_id),
                VpnClient.external_email == str(legacy_user.email),
            ),
        )
        vpn_client = (await session.execute(client_stmt)).scalar_one_or_none()
        if vpn_client:
            user = await session.get(AppUser, vpn_client.user_id)
            if user is not None:
                user.updated_at = now
                return user

        created_at = self._legacy_ts_to_datetime(legacy_user.login_date) or now
        user = AppUser(created_at=created_at, updated_at=now)
        session.add(user)
        await session.flush()
        return user

    async def _upsert_telegram_account(
        self,
        *,
        session,
        user_id: int,
        telegram_id: int,
        telegram_username: str | None,
        seen_at: datetime,
    ) -> None:
        stmt = select(TelegramAccount).where(TelegramAccount.telegram_id == telegram_id)
        account = (await session.execute(stmt)).scalar_one_or_none()
        if account is None:
            account = (
                await session.execute(
                    select(TelegramAccount).where(TelegramAccount.user_id == user_id)
                )
            ).scalar_one_or_none()

        if account is None:
            session.add(
                TelegramAccount(
                    user_id=user_id,
                    telegram_id=telegram_id,
                    username=telegram_username,
                    linked_at=seen_at,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    revoked_at=None,
                )
            )
            return

        account.user_id = user_id
        account.telegram_id = telegram_id
        if telegram_username is not None:
            account.username = telegram_username
        first_seen_at = self._ensure_utc(account.first_seen_at)
        last_seen_at = self._ensure_utc(account.last_seen_at)
        if first_seen_at is None or seen_at < first_seen_at:
            account.first_seen_at = seen_at
        if last_seen_at is None or seen_at > last_seen_at:
            account.last_seen_at = seen_at
        account.revoked_at = None

    async def _upsert_vpn_client(
        self,
        *,
        session,
        user_id: int,
        legacy_user: LegacyUser,
        now: datetime,
    ) -> None:
        identifiers = [
            str(legacy_user.uuid or "").strip(),
            str(legacy_user.sub_id or "").strip(),
            str(legacy_user.email or "").strip(),
        ]
        if not all(identifiers):
            logger.warning(
                f"Skipping vpn_client sync for tg_id={getattr(legacy_user, 'tg_id', None)} "
                "due to incomplete legacy identifiers"
            )
            return

        stmt = select(VpnClient).where(
            or_(
                (VpnClient.user_id == user_id) & (VpnClient.scope == PRODUCT_SCOPE_STANDARD),
                VpnClient.external_client_uuid == identifiers[0],
                VpnClient.subscription_external_id == identifiers[1],
                VpnClient.external_email == identifiers[2],
            )
        )
        vpn_client = (await session.execute(stmt)).scalar_one_or_none()
        if vpn_client is None:
            session.add(
                VpnClient(
                    user_id=user_id,
                    scope=PRODUCT_SCOPE_STANDARD,
                    provider=VPN_PROVIDER_3X_UI,
                    external_client_uuid=identifiers[0],
                    external_email=identifiers[2],
                    subscription_external_id=identifiers[1],
                    metadata_json={},
                    created_at=now,
                    updated_at=now,
                    deactivated_at=None,
                )
            )
            return

        vpn_client.user_id = user_id
        vpn_client.scope = PRODUCT_SCOPE_STANDARD
        vpn_client.provider = VPN_PROVIDER_3X_UI
        vpn_client.external_client_uuid = identifiers[0]
        vpn_client.external_email = identifiers[2]
        vpn_client.subscription_external_id = identifiers[1]
        vpn_client.updated_at = now
        vpn_client.deactivated_at = None

    async def _upsert_subscription_state(
        self,
        *,
        session,
        user_id: int,
        legacy_user: LegacyUser,
        now: datetime,
    ) -> None:
        state = await session.get(SubscriptionState, user_id)
        if state is None:
            session.add(
                SubscriptionState(
                    user_id=user_id,
                    current_expires_at=self._legacy_ts_to_datetime(
                        legacy_user.expiration_date
                    ),
                    trial_activated_at=self._legacy_ts_to_datetime(
                        legacy_user.trial_date
                    ),
                    news_bonus_activated_at=self._legacy_ts_to_datetime(
                        legacy_user.news_channel_date
                    ),
                    blocked_at=None,
                    updated_at=now,
                    version=0,
                )
            )
            return

        state.current_expires_at = self._legacy_ts_to_datetime(
            legacy_user.expiration_date
        )
        state.trial_activated_at = self._legacy_ts_to_datetime(legacy_user.trial_date)
        state.news_bonus_activated_at = self._legacy_ts_to_datetime(
            legacy_user.news_channel_date
        )
        state.updated_at = now
        state.version += 1

    @staticmethod
    def _legacy_ts_to_datetime(timestamp_ms: int | None) -> datetime | None:
        if timestamp_ms is None:
            return None
        return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)

    @staticmethod
    def _ensure_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
