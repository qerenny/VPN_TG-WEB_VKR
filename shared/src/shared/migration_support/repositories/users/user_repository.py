from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from sqlmodel import desc, select

from shared.config.settings import RolloutFeatureFlags
from shared.infrastructure.base_repository import BaseRepository
from shared.infrastructure.identity_subscription_sync_service import (
    IdentitySubscriptionSyncService,
)
from shared.migration_support.models.users.user_model import User
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.product_constants import PRODUCT_SCOPE_STANDARD
from shared.utils.logging_utils import log_function_call, setup_logger

logger = setup_logger("migration_support.user.repository", "database.log")


@dataclass(frozen=True, slots=True)
class SubscriptionStateSnapshot:
    current_expires_at_ms: int | None
    trial_activated_at_ms: int | None
    news_bonus_activated_at_ms: int | None
    blocked_at: datetime | None


class UserRepository(BaseRepository[User]):
    def __init__(self, features: RolloutFeatureFlags | None = None):
        super().__init__(User)
        self.features = features or RolloutFeatureFlags()
        self.identity_sync_service = IdentitySubscriptionSyncService(
            RolloutFeatureFlags(
                db_dual_write_identity=True,
                db_dual_write_subscription=True,
            )
        )

    @log_function_call(logger)
    async def create(
        self,
        obj: User,
        telegram_username: str | None = None,
    ) -> User:
        await self.identity_sync_service.sync_legacy_user(
            obj,
            telegram_username=telegram_username,
        )
        created = await self.get(int(obj.tg_id))
        if created is None:
            raise ValueError(f"Failed to create user tg_id={obj.tg_id}")
        return created

    @log_function_call(logger)
    async def delete(self, id: int) -> None:
        async with self.get_session() as session:
            account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.telegram_id == int(id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if account is None:
                return

            app_user = await session.get(AppUser, account.user_id)
            if app_user is None:
                return

            await session.delete(app_user)
            await session.commit()

    @log_function_call(logger)
    async def update_expiration(self, tg_id: int, expiration_date: int) -> None:
        user = await self.get(int(tg_id))
        if user is None:
            return

        user.expiration_date = expiration_date
        await self.identity_sync_service.sync_legacy_user(user)

    @log_function_call(logger)
    async def set_trial_date(self, tg_id: int, trial_date: int) -> None:
        user = await self.get(int(tg_id))
        if user is None:
            return

        user.trial_date = trial_date
        await self.identity_sync_service.sync_legacy_user(user)

    @log_function_call(logger)
    async def set_news_channel_date(self, tg_id: int, news_channel_date: int) -> None:
        user = await self.get(int(tg_id))
        if user is None:
            return

        user.news_channel_date = news_channel_date
        await self.identity_sync_service.sync_legacy_user(user)

    @log_function_call(logger)
    async def touch_identity(
        self,
        tg_id: int,
        *,
        telegram_username: str | None,
        seen_at: int,
    ) -> None:
        user = await self.get(int(tg_id))
        if user is None:
            return

        user.login_date = int(seen_at)
        await self.identity_sync_service.sync_legacy_user(
            user,
            telegram_username=telegram_username,
        )

    @log_function_call(logger)
    async def get(self, id: int) -> User | None:
        async with self.get_session() as session:
            rows = await self._load_users(session, tg_ids=[int(id)])
            return rows[0] if rows else None

    @log_function_call(logger)
    async def get_all(self) -> List[User]:
        async with self.get_session() as session:
            return await self._load_users(session)

    @log_function_call(logger)
    async def get_last_users(self, limit: int = 10) -> List[User]:
        async with self.get_session() as session:
            return await self._load_users(
                session,
                limit=max(1, int(limit)),
                order_desc=True,
            )

    @log_function_call(logger)
    async def get_active_users(self, current_timestamp: int) -> List[User]:
        async with self.get_session() as session:
            rows = await self._load_user_rows(session)
            users = [
                self._build_legacy_user_from_row(row)
                for row in rows
                if row.blocked_at is None
            ]
            return [
                user
                for user in users
                if user.expiration_date is not None
                and int(user.expiration_date) > int(current_timestamp)
            ]

    @log_function_call(logger)
    async def get_users_expiring_between(
        self,
        start_timestamp: int,
        end_timestamp: int,
    ) -> List[User]:
        async with self.get_session() as session:
            rows = await self._load_user_rows(session)
            users = [
                self._build_legacy_user_from_row(row)
                for row in rows
                if row.blocked_at is None
            ]
            return [
                user
                for user in users
                if user.expiration_date is not None
                and int(user.expiration_date) > int(start_timestamp)
                and int(user.expiration_date) <= int(end_timestamp)
            ]

    async def _load_users(
        self,
        session,
        *,
        tg_ids: list[int] | None = None,
        limit: int | None = None,
        order_desc: bool = False,
    ) -> list[User]:
        rows = await self._load_user_rows(
            session,
            tg_ids=tg_ids,
            limit=limit,
            order_desc=order_desc,
        )
        return [self._build_legacy_user_from_row(row) for row in rows]

    async def _load_user_rows(
        self,
        session,
        *,
        tg_ids: list[int] | None = None,
        limit: int | None = None,
        order_desc: bool = False,
    ):
        stmt = (
            select(
                TelegramAccount.telegram_id,
                TelegramAccount.username,
                TelegramAccount.linked_at,
                TelegramAccount.first_seen_at,
                TelegramAccount.last_seen_at,
                VpnClient.external_client_uuid,
                VpnClient.external_email,
                VpnClient.subscription_external_id,
                SubscriptionState.current_expires_at,
                SubscriptionState.trial_activated_at,
                SubscriptionState.news_bonus_activated_at,
                SubscriptionState.blocked_at,
            )
            .join(AppUser, AppUser.id == TelegramAccount.user_id)
            .outerjoin(
                VpnClient,
                (VpnClient.user_id == TelegramAccount.user_id)
                & VpnClient.deactivated_at.is_(None)
                & (VpnClient.scope == PRODUCT_SCOPE_STANDARD),
            )
            .outerjoin(
                SubscriptionState,
                SubscriptionState.user_id == TelegramAccount.user_id,
            )
            .where(TelegramAccount.revoked_at.is_(None))
        )

        if tg_ids:
            stmt = stmt.where(TelegramAccount.telegram_id.in_([int(tg_id) for tg_id in tg_ids]))

        ordering = desc(TelegramAccount.first_seen_at) if order_desc else TelegramAccount.telegram_id
        stmt = stmt.order_by(ordering)
        if limit is not None:
            stmt = stmt.limit(int(limit))

        return (await session.execute(stmt)).all()

    def _build_legacy_user_from_row(self, row) -> User:
        return User(
            tg_id=int(row.telegram_id),
            uuid=str(row.external_client_uuid or ""),
            email=str(row.external_email or ""),
            expiration_date=self._dt_to_legacy_ms(row.current_expires_at),
            login_date=self._dt_to_legacy_ms(row.last_seen_at or row.first_seen_at or row.linked_at)
            or 0,
            trial_date=self._dt_to_legacy_ms(row.trial_activated_at),
            news_channel_date=self._dt_to_legacy_ms(row.news_bonus_activated_at),
            sub_id=str(row.subscription_external_id or ""),
        )

    @staticmethod
    def _dt_to_legacy_ms(value: datetime | None) -> int | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)
        return int(value.timestamp() * 1000)
