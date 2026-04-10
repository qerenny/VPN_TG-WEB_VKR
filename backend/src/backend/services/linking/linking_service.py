from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy import and_, select

from shared.config.config import BOT_REFERRAL_LINK, FRONTEND_LINK
from shared.constants.linking import LINK_TELEGRAM_PURPOSE, LINK_WEB_PURPOSE
from shared.config.database.engine import async_session_factory
from shared.infrastructure.identity_link_service import IdentityLinkService
from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount
from shared.models.users.web_session_model import WebSession
from shared.models.vpn.vpn_client_model import VpnClient

@dataclass(frozen=True, slots=True)
class TelegramLinkStartResult:
    status: str
    deep_link: str | None
    expires_at: str | None
    telegram_id: int | None
    telegram_username: str | None


@dataclass(frozen=True, slots=True)
class WebLinkStartResult:
    status: str
    link_url: str | None
    expires_at: str | None


@dataclass(frozen=True, slots=True)
class PublicLinkPreviewResult:
    status: str
    purpose: str | None
    expires_at: str | None


@dataclass(frozen=True, slots=True)
class PublicLinkConsumeResult:
    status: str
    linked_user_id: int | None


class LinkingService:
    def __init__(self, *, identity_link_service: IdentityLinkService) -> None:
        self.identity_link_service = identity_link_service

    async def start_telegram_link(self, *, user_id: int) -> TelegramLinkStartResult:
        async with async_session_factory() as session:
            web_account = (
                await session.execute(
                    select(WebAccount).where(
                        and_(
                            WebAccount.user_id == int(user_id),
                            WebAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if web_account is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Web account not found",
                )

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
            if telegram_account is not None:
                return TelegramLinkStartResult(
                    status="already_linked",
                    deep_link=None,
                    expires_at=None,
                    telegram_id=int(telegram_account.telegram_id),
                    telegram_username=getattr(telegram_account, "username", None),
                )

            issued = await self.identity_link_service.issue_token(
                session,
                user_id=int(user_id),
                purpose=LINK_TELEGRAM_PURPOSE,
                issued_by_channel="web",
                metadata={"flow": "web_to_telegram"},
            )
            await session.commit()

        deep_link = f"{BOT_REFERRAL_LINK}link_{issued.raw_token}"
        return TelegramLinkStartResult(
            status="pending",
            deep_link=deep_link,
            expires_at=issued.expires_at.isoformat(),
            telegram_id=None,
            telegram_username=None,
        )

    async def start_web_link(self, *, telegram_id: int) -> WebLinkStartResult:
        async with async_session_factory() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        and_(
                            TelegramAccount.telegram_id == int(telegram_id),
                            TelegramAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if telegram_account is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Telegram account not found",
                )

            existing_web = (
                await session.execute(
                    select(WebAccount).where(
                        and_(
                            WebAccount.user_id == int(telegram_account.user_id),
                            WebAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing_web is not None:
                return WebLinkStartResult(
                    status="already_linked",
                    link_url=None,
                    expires_at=None,
                )

            issued = await self.identity_link_service.issue_token(
                session,
                user_id=int(telegram_account.user_id),
                purpose=LINK_WEB_PURPOSE,
                issued_by_channel="telegram",
                metadata={"flow": "telegram_to_web"},
            )
            await session.commit()

        return WebLinkStartResult(
            status="pending",
            link_url=f"{FRONTEND_LINK.rstrip('/')}/auth/login?link_token={issued.raw_token}",
            expires_at=issued.expires_at.isoformat(),
        )

    async def preview_web_link(self, *, raw_token: str) -> PublicLinkPreviewResult:
        async with async_session_factory() as session:
            token = await self.identity_link_service.get_active_token(
                session,
                raw_token=raw_token,
                purpose=LINK_WEB_PURPOSE,
            )
        if token is None:
            return PublicLinkPreviewResult(
                status="invalid",
                purpose=None,
                expires_at=None,
            )
        return PublicLinkPreviewResult(
            status="pending",
            purpose=str(token.purpose),
            expires_at=token.expires_at.isoformat(),
        )

    async def consume_web_link(
        self,
        *,
        raw_token: str,
        current_user_id: int,
    ) -> PublicLinkConsumeResult:
        async with async_session_factory() as session:
            token = await self.identity_link_service.get_active_token(
                session,
                raw_token=raw_token,
                purpose=LINK_WEB_PURPOSE,
            )
            if token is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Link token is invalid or expired",
                )

            target_user = await session.get(AppUser, int(token.user_id))
            current_user = await session.get(AppUser, int(current_user_id))
            if target_user is None or current_user is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Link target not found",
                )

            if int(token.user_id) == int(current_user_id):
                await session.commit()
                return PublicLinkConsumeResult(
                    status="already_linked",
                    linked_user_id=int(token.user_id),
                )

            target_web = (
                await session.execute(
                    select(WebAccount).where(
                        and_(
                            WebAccount.user_id == int(token.user_id),
                            WebAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if target_web is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Target account already has a web profile",
                )

            current_web = (
                await session.execute(
                    select(WebAccount).where(
                        and_(
                            WebAccount.user_id == int(current_user_id),
                            WebAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if current_web is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Current web account not found",
                )

            if not await self._is_empty_web_shell(session, int(current_user_id)):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This web account already has data and cannot be auto-linked",
                )

            current_profile = await session.get(UserProfile, int(current_user_id))
            target_profile = await session.get(UserProfile, int(token.user_id))
            if current_profile is not None and target_profile is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Both accounts already have profile data; auto-merge is запрещен",
                )

            current_web.user_id = int(token.user_id)
            current_web.updated_at = target_user.updated_at
            session.add(current_web)

            if current_profile is not None:
                current_profile.user_id = int(token.user_id)
                session.add(current_profile)

            current_sessions = (
                await session.execute(
                    select(WebSession).where(
                        WebSession.user_id == int(current_user_id),
                        WebSession.revoked_at.is_(None),
                    )
                )
            ).scalars().all()
            for web_session in current_sessions:
                web_session.user_id = int(token.user_id)
                session.add(web_session)

            current_user.deleted_at = current_user.deleted_at or target_user.updated_at
            current_user.updated_at = target_user.updated_at
            target_user.updated_at = target_user.updated_at
            session.add(current_user)
            session.add(target_user)
            await session.commit()

        return PublicLinkConsumeResult(
            status="linked",
            linked_user_id=int(token.user_id),
        )

    async def _is_empty_web_shell(self, session, user_id: int) -> bool:
        has_telegram = (
            await session.execute(
                select(TelegramAccount.id).where(
                    and_(
                        TelegramAccount.user_id == int(user_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            )
        ).scalar_one_or_none()
        if has_telegram is not None:
            return False

        has_payments = (
            await session.execute(
                select(PaymentOrder.id).where(PaymentOrder.user_id == int(user_id)).limit(1)
            )
        ).scalar_one_or_none()
        if has_payments is not None:
            return False

        has_vpn_clients = (
            await session.execute(
                select(VpnClient.id).where(
                    VpnClient.user_id == int(user_id),
                    VpnClient.deactivated_at.is_(None),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if has_vpn_clients is not None:
            return False

        subscription_state = await session.get(SubscriptionState, int(user_id))
        if subscription_state is not None and any(
            [
                subscription_state.current_expires_at is not None,
                subscription_state.trial_activated_at is not None,
                subscription_state.info_channel_activated_at is not None,
            ]
        ):
            return False

        return True
