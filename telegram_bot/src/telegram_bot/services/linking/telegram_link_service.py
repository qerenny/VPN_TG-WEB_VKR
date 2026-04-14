from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, select

from shared.config.config import FRONTEND_TELEGRAM_LINK
from shared.constants.linking import LINK_TELEGRAM_PURPOSE
from shared.config.database.session import get_db_session
from shared.infrastructure.identity_link_service import IdentityLinkService
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount
from shared.models.users.web_session_model import WebSession
from shared.services.linking.account_state import is_empty_web_shell
from shared.utils.telegram_web_login_token import issue_telegram_web_login_token


@dataclass(frozen=True, slots=True)
class TelegramLinkConsumeResult:
    status: str
    message: str


class TelegramLinkService:
    def __init__(self, *, identity_link_service: IdentityLinkService, secret: str) -> None:
        self.identity_link_service = identity_link_service
        self.secret = str(secret)

    async def consume_start_token(
        self,
        *,
        tg_id: int,
        telegram_username: str | None,
        raw_token: str,
    ) -> TelegramLinkConsumeResult:
        async with get_db_session() as session:
            token = await self.identity_link_service.get_active_token(
                session,
                raw_token=raw_token,
                purpose=LINK_TELEGRAM_PURPOSE,
            )
            if token is None:
                return TelegramLinkConsumeResult(
                    status="invalid",
                    message="Ссылка привязки недействительна или уже использована.",
                )

            target_user = await session.get(AppUser, int(token.user_id))
            if target_user is None or target_user.deleted_at is not None:
                return TelegramLinkConsumeResult(
                    status="invalid",
                    message="Аккаунт для привязки не найден.",
                )

            existing_by_telegram = (
                await session.execute(
                    select(TelegramAccount).where(
                        and_(
                            TelegramAccount.telegram_id == int(tg_id),
                            TelegramAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing_by_telegram is not None and int(existing_by_telegram.user_id) != int(token.user_id):
                merged = await self._merge_web_shell_into_existing_telegram_user(
                    session=session,
                    web_user_id=int(token.user_id),
                    telegram_user_id=int(existing_by_telegram.user_id),
                    telegram_account=existing_by_telegram,
                    telegram_username=telegram_username,
                )
                if not merged:
                    return TelegramLinkConsumeResult(
                        status="conflict",
                        message="Этот Telegram уже привязан к другому аккаунту. Автоматическая привязка запрещена.",
                    )
                return TelegramLinkConsumeResult(
                    status="linked",
                    message="Telegram уже был связан с отдельным аккаунтом. Мы безопасно объединили web-профиль и Telegram в один аккаунт.",
                )

            existing_target = (
                await session.execute(
                    select(TelegramAccount).where(
                        and_(
                            TelegramAccount.user_id == int(token.user_id),
                            TelegramAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing_target is not None and int(existing_target.telegram_id) != int(tg_id):
                return TelegramLinkConsumeResult(
                    status="conflict",
                    message="К этому аккаунту уже привязан другой Telegram. Автоматическая перепривязка запрещена.",
                )

            now = datetime.now(timezone.utc)
            if existing_by_telegram is not None:
                existing_by_telegram.username = telegram_username
                existing_by_telegram.last_seen_at = now
                existing_by_telegram.revoked_at = None
            elif existing_target is not None:
                existing_target.telegram_id = int(tg_id)
                existing_target.username = telegram_username
                existing_target.last_seen_at = now
                existing_target.revoked_at = None
            else:
                session.add(
                    TelegramAccount(
                        user_id=int(token.user_id),
                        telegram_id=int(tg_id),
                        username=telegram_username,
                        linked_at=now,
                        first_seen_at=now,
                        last_seen_at=now,
                        revoked_at=None,
                    )
                )

            target_user.updated_at = now
            session.add(target_user)
            await session.commit()

        return TelegramLinkConsumeResult(
            status="linked",
            message="Telegram успешно привязан к аккаунту сайта.",
        )

    async def create_web_link(self, *, tg_id: int) -> str | None:
        if not FRONTEND_TELEGRAM_LINK:
            return None

        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        and_(
                            TelegramAccount.telegram_id == int(tg_id),
                            TelegramAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if telegram_account is None:
                return None

            raw_token = issue_telegram_web_login_token(
                tg_id=int(telegram_account.telegram_id),
                user_id=int(telegram_account.user_id),
                secret=self.secret,
            )
            await session.commit()

        return f"{FRONTEND_TELEGRAM_LINK.rstrip('/')}/auth/login?link_token={raw_token}"

    async def _merge_web_shell_into_existing_telegram_user(
        self,
        *,
        session,
        web_user_id: int,
        telegram_user_id: int,
        telegram_account: TelegramAccount,
        telegram_username: str | None,
    ) -> bool:
        if int(web_user_id) == int(telegram_user_id):
            return True

        web_user = await session.get(AppUser, int(web_user_id))
        telegram_user = await session.get(AppUser, int(telegram_user_id))
        if web_user is None or telegram_user is None:
            return False
        if web_user.deleted_at is not None or telegram_user.deleted_at is not None:
            return False

        web_account = (
            await session.execute(
                select(WebAccount).where(
                    and_(
                        WebAccount.user_id == int(web_user_id),
                        WebAccount.revoked_at.is_(None),
                    )
                )
            )
        ).scalar_one_or_none()
        if web_account is None:
            return False

        existing_target_web = (
            await session.execute(
                select(WebAccount).where(
                    and_(
                        WebAccount.user_id == int(telegram_user_id),
                        WebAccount.revoked_at.is_(None),
                    )
                )
            )
        ).scalar_one_or_none()
        if existing_target_web is not None:
            return False

        if not await is_empty_web_shell(session, int(web_user_id)):
            return False

        source_profile = await session.get(UserProfile, int(web_user_id))
        target_profile = await session.get(UserProfile, int(telegram_user_id))
        if source_profile is not None and target_profile is not None:
            return False

        now = datetime.now(timezone.utc)
        web_account.user_id = int(telegram_user_id)
        web_account.updated_at = now
        session.add(web_account)

        if source_profile is not None:
            source_profile.user_id = int(telegram_user_id)
            source_profile.updated_at = now
            session.add(source_profile)

        current_sessions = (
            await session.execute(
                select(WebSession).where(
                    WebSession.user_id == int(web_user_id),
                    WebSession.revoked_at.is_(None),
                )
            )
        ).scalars().all()
        for web_session in current_sessions:
            web_session.user_id = int(telegram_user_id)
            session.add(web_session)

        telegram_account.username = telegram_username
        telegram_account.last_seen_at = now
        telegram_account.revoked_at = None
        session.add(telegram_account)

        web_user.deleted_at = now
        web_user.updated_at = now
        telegram_user.updated_at = now
        session.add(web_user)
        session.add(telegram_user)
        await session.commit()
        return True
