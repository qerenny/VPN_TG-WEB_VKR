from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List

from sqlmodel import desc, select

from shared.config.database.session import get_db_session
from shared.constants.vpn import VPN_PROVIDER_3X_UI
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.product_constants import PRODUCT_SCOPE_STANDARD
from shared.utils.logging_utils import log_function_call, setup_logger

logger = setup_logger("telegram-user.repository", "database.log")

@dataclass(slots=True)
class TelegramUserSnapshot:
    tg_id: int
    uuid: str
    email: str
    expiration_date: int | None
    login_date: int
    trial_date: int | None
    info_channel_date: int | None
    sub_id: str
    username: str | None = None


@dataclass(frozen=True, slots=True)
class SubscriptionStateSnapshot:
    current_expires_at_ms: int | None
    trial_activated_at_ms: int | None
    info_channel_activated_at_ms: int | None
    blocked_at: datetime | None


class TelegramUserRepository:
    def __init__(self):
        pass

    @log_function_call(logger)
    async def create(
        self,
        obj: TelegramUserSnapshot,
        telegram_username: str | None = None,
    ) -> TelegramUserSnapshot:
        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            seen_at = self._legacy_ts_to_datetime(obj.login_date) or now
            account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.telegram_id == int(obj.tg_id),
                    )
                )
            ).scalar_one_or_none()

            if account is None:
                app_user = AppUser(created_at=seen_at, updated_at=now)
                session.add(app_user)
                await session.flush()
                user_id = int(app_user.id)
                session.add(
                    TelegramAccount(
                        user_id=user_id,
                        telegram_id=int(obj.tg_id),
                        username=telegram_username,
                        linked_at=seen_at,
                        first_seen_at=seen_at,
                        last_seen_at=seen_at,
                        revoked_at=None,
                    )
                )
            else:
                user_id = int(account.user_id)
                app_user = await session.get(AppUser, user_id)
                if app_user is None:
                    app_user = AppUser(created_at=seen_at, updated_at=now)
                    session.add(app_user)
                    await session.flush()
                    user_id = int(app_user.id)
                    account.user_id = user_id
                app_user.updated_at = now
                if telegram_username is not None:
                    account.username = telegram_username
                account.revoked_at = None
                first_seen_at = self._ensure_utc(account.first_seen_at)
                last_seen_at = self._ensure_utc(account.last_seen_at)
                if first_seen_at is None or seen_at < first_seen_at:
                    account.first_seen_at = seen_at
                if last_seen_at is None or seen_at > last_seen_at:
                    account.last_seen_at = seen_at

            await self._upsert_standard_vpn_client(
                session=session,
                user_id=user_id,
                snapshot=obj,
                now=now,
            )
            await self._upsert_subscription_state(
                session=session,
                user_id=user_id,
                snapshot=obj,
                now=now,
            )
            await session.commit()

        created = await self.get(int(obj.tg_id))
        if created is None:
            raise ValueError(f"Failed to create user tg_id={obj.tg_id}")
        return created

    @log_function_call(logger)
    async def delete(self, id: int) -> None:
        async with get_db_session() as session:
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
        async with get_db_session() as session:
            state = await self._get_subscription_state_by_tg_id(session, int(tg_id))
            if state is None:
                return
            state.current_expires_at = self._legacy_ts_to_datetime(expiration_date)
            state.blocked_at = None
            state.updated_at = datetime.now(timezone.utc)
            state.version += 1
            await session.commit()

    @log_function_call(logger)
    async def set_trial_date(self, tg_id: int, trial_date: int) -> None:
        async with get_db_session() as session:
            state = await self._get_subscription_state_by_tg_id(session, int(tg_id))
            if state is None:
                return
            state.trial_activated_at = self._legacy_ts_to_datetime(trial_date)
            state.updated_at = datetime.now(timezone.utc)
            state.version += 1
            await session.commit()

    @log_function_call(logger)
    async def set_info_channel_date(self, tg_id: int, info_channel_date: int) -> None:
        async with get_db_session() as session:
            state = await self._get_subscription_state_by_tg_id(session, int(tg_id))
            if state is None:
                return
            state.info_channel_activated_at = self._legacy_ts_to_datetime(info_channel_date)
            state.updated_at = datetime.now(timezone.utc)
            state.version += 1
            await session.commit()

    @log_function_call(logger)
    async def touch_identity(
        self,
        tg_id: int,
        *,
        telegram_username: str | None,
        seen_at: int,
    ) -> None:
        async with get_db_session() as session:
            account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.telegram_id == int(tg_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if account is None:
                return

            normalized_seen_at = self._legacy_ts_to_datetime(seen_at) or datetime.now(timezone.utc)
            if telegram_username is not None:
                account.username = telegram_username
            first_seen_at = self._ensure_utc(account.first_seen_at)
            last_seen_at = self._ensure_utc(account.last_seen_at)
            if first_seen_at is None or normalized_seen_at < first_seen_at:
                account.first_seen_at = normalized_seen_at
            if last_seen_at is None or normalized_seen_at > last_seen_at:
                account.last_seen_at = normalized_seen_at
            await session.commit()

    @log_function_call(logger)
    async def get(self, id: int) -> TelegramUserSnapshot | None:
        async with get_db_session() as session:
            rows = await self._load_users(session, tg_ids=[int(id)])
            return rows[0] if rows else None

    @log_function_call(logger)
    async def get_app_user_id(self, tg_id: int) -> int | None:
        async with get_db_session() as session:
            account = (
                await session.execute(
                    select(TelegramAccount.user_id).where(
                        TelegramAccount.telegram_id == int(tg_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            return int(account) if account is not None else None

    @log_function_call(logger)
    async def is_blocked(self, tg_id: int) -> bool:
        async with get_db_session() as session:
            account = (
                await session.execute(
                    select(TelegramAccount.user_id).where(
                        TelegramAccount.telegram_id == int(tg_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if account is None:
                return False

            app_user = await session.get(AppUser, int(account))
            return app_user is not None and self._ensure_utc(app_user.blocked_at) is not None

    @log_function_call(logger)
    async def get_standard_vpn_client_id(self, tg_id: int) -> int | None:
        async with get_db_session() as session:
            result = await session.execute(
                select(VpnClient.id)
                .join(
                    TelegramAccount,
                    TelegramAccount.user_id == VpnClient.user_id,
                )
                .where(
                    TelegramAccount.telegram_id == int(tg_id),
                    TelegramAccount.revoked_at.is_(None),
                    VpnClient.scope == PRODUCT_SCOPE_STANDARD,
                    VpnClient.deactivated_at.is_(None),
                )
                .limit(1)
            )
            value = result.scalar_one_or_none()
            return int(value) if value is not None else None

    @log_function_call(logger)
    async def get_all(self) -> List[TelegramUserSnapshot]:
        async with get_db_session() as session:
            return await self._load_users(session)

    @log_function_call(logger)
    async def get_last_users(self, limit: int = 10) -> List[TelegramUserSnapshot]:
        async with get_db_session() as session:
            return await self._load_users(
                session,
                limit=max(1, int(limit)),
                order_desc=True,
            )

    @log_function_call(logger)
    async def get_active_users(self, current_timestamp: int) -> List[TelegramUserSnapshot]:
        async with get_db_session() as session:
            users = await self._load_users(session)
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
    ) -> List[TelegramUserSnapshot]:
        async with get_db_session() as session:
            users = await self._load_users(session)
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
    ) -> list[TelegramUserSnapshot]:
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
                SubscriptionState.info_channel_activated_at,
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
            stmt = stmt.where(
                TelegramAccount.telegram_id.in_([int(tg_id) for tg_id in tg_ids])
            )

        ordering = desc(TelegramAccount.first_seen_at) if order_desc else TelegramAccount.telegram_id
        stmt = stmt.order_by(ordering)
        if limit is not None:
            stmt = stmt.limit(int(limit))

        rows = (await session.execute(stmt)).all()
        return [self._build_snapshot_from_row(row) for row in rows]

    async def _get_subscription_state_by_tg_id(self, session, tg_id: int) -> SubscriptionState | None:
        account = (
            await session.execute(
                select(TelegramAccount).where(
                    TelegramAccount.telegram_id == int(tg_id),
                    TelegramAccount.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if account is None:
            return None

        state = await session.get(SubscriptionState, int(account.user_id))
        if state is None:
            state = SubscriptionState(
                user_id=int(account.user_id),
                current_expires_at=None,
                trial_activated_at=None,
                info_channel_activated_at=None,
                blocked_at=None,
                updated_at=datetime.now(timezone.utc),
                version=0,
            )
            session.add(state)
            await session.flush()
        return state

    async def _upsert_standard_vpn_client(
        self,
        *,
        session,
        user_id: int,
        snapshot: TelegramUserSnapshot,
        now: datetime,
    ) -> None:
        stmt = select(VpnClient).where(
            (VpnClient.user_id == int(user_id))
            & (VpnClient.scope == PRODUCT_SCOPE_STANDARD)
        )
        vpn_client = (await session.execute(stmt)).scalar_one_or_none()
        if vpn_client is None:
            session.add(
                VpnClient(
                    user_id=int(user_id),
                    scope=PRODUCT_SCOPE_STANDARD,
                    provider=VPN_PROVIDER_3X_UI,
                    external_client_uuid=str(snapshot.uuid),
                    external_email=str(snapshot.email),
                    subscription_external_id=str(snapshot.sub_id),
                    metadata_json={},
                    created_at=now,
                    updated_at=now,
                    deactivated_at=None,
                )
            )
            return

        vpn_client.user_id = int(user_id)
        vpn_client.scope = PRODUCT_SCOPE_STANDARD
        vpn_client.provider = VPN_PROVIDER_3X_UI
        vpn_client.external_client_uuid = str(snapshot.uuid)
        vpn_client.external_email = str(snapshot.email)
        vpn_client.subscription_external_id = str(snapshot.sub_id)
        vpn_client.updated_at = now
        vpn_client.deactivated_at = None

    async def _upsert_subscription_state(
        self,
        *,
        session,
        user_id: int,
        snapshot: TelegramUserSnapshot,
        now: datetime,
    ) -> None:
        state = await session.get(SubscriptionState, int(user_id))
        if state is None:
            session.add(
                SubscriptionState(
                    user_id=int(user_id),
                    current_expires_at=self._legacy_ts_to_datetime(snapshot.expiration_date),
                    trial_activated_at=self._legacy_ts_to_datetime(snapshot.trial_date),
                    info_channel_activated_at=self._legacy_ts_to_datetime(snapshot.info_channel_date),
                    blocked_at=None,
                    updated_at=now,
                    version=0,
                )
            )
            return

        state.current_expires_at = self._legacy_ts_to_datetime(snapshot.expiration_date)
        state.trial_activated_at = self._legacy_ts_to_datetime(snapshot.trial_date)
        state.info_channel_activated_at = self._legacy_ts_to_datetime(snapshot.info_channel_date)
        state.blocked_at = None
        state.updated_at = now
        state.version += 1

    def _build_snapshot_from_row(self, row) -> TelegramUserSnapshot:
        snapshot = SubscriptionStateSnapshot(
            current_expires_at_ms=self._datetime_to_legacy_ms(row.current_expires_at),
            trial_activated_at_ms=self._datetime_to_legacy_ms(row.trial_activated_at),
            info_channel_activated_at_ms=self._datetime_to_legacy_ms(row.info_channel_activated_at),
            blocked_at=self._ensure_utc(row.blocked_at),
        )
        login_date = self._datetime_to_legacy_ms(
            row.first_seen_at or row.linked_at or row.last_seen_at
        ) or 0

        return TelegramUserSnapshot(
            tg_id=int(row.telegram_id),
            uuid=str(row.external_client_uuid or ""),
            email=str(row.external_email or ""),
            expiration_date=None
            if snapshot.blocked_at is not None
            else snapshot.current_expires_at_ms,
            login_date=login_date,
            trial_date=snapshot.trial_activated_at_ms,
            info_channel_date=snapshot.info_channel_activated_at_ms,
            sub_id=str(row.subscription_external_id or ""),
            username=row.username,
        )

    @staticmethod
    def _legacy_ts_to_datetime(timestamp_ms: int | None) -> datetime | None:
        if timestamp_ms is None:
            return None
        return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)

    @staticmethod
    def _datetime_to_legacy_ms(value: datetime | None) -> int | None:
        normalized = TelegramUserRepository._ensure_utc(value)
        if normalized is None:
            return None
        return int(normalized.timestamp() * 1000)

    @staticmethod
    def _ensure_utc(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
