from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import and_, select

from backend.services.auth.password_hasher import PasswordHasher
from backend.services.auth.web_auth_challenge_service import (
    PASSWORD_RESET_PURPOSE,
    REGISTER_EMAIL_VERIFICATION_PURPOSE,
    WebAuthChallengeService,
)
from backend.services.auth.web_session_service import WebSessionService, WebSessionSnapshot
from backend.services.email.transactional_email_service import TransactionalEmailService
from shared.constants.linking import LINK_WEB_PURPOSE
from shared.config.database.engine import async_session_factory
from shared.infrastructure.identity_link_service import IdentityLinkService
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount
from shared.utils.telegram_web_login_token import verify_telegram_web_login_token


@dataclass(slots=True)
class AuthenticatedWebUser:
    user_id: int
    email: str | None
    email_verified: bool
    telegram_linked: bool
    telegram_id: int | None
    telegram_username: str | None
    created_at: datetime
    last_login_at: datetime | None


class AuthService:
    def __init__(
        self,
        *,
        password_hasher: PasswordHasher,
        session_service: WebSessionService,
        challenge_service: WebAuthChallengeService,
        transactional_email_service: TransactionalEmailService,
        identity_link_service: IdentityLinkService,
        email_code_ttl_minutes: int,
        password_min_length: int,
        telegram_web_login_secret: str,
    ):
        self.password_hasher = password_hasher
        self.session_service = session_service
        self.challenge_service = challenge_service
        self.transactional_email_service = transactional_email_service
        self.identity_link_service = identity_link_service
        self.email_code_ttl_minutes = max(1, int(email_code_ttl_minutes))
        self.password_min_length = max(1, int(password_min_length))
        self.telegram_web_login_secret = str(telegram_web_login_secret)
        self.email_verification_required = bool(
            getattr(getattr(transactional_email_service, "delivery_service", None), "settings", None)
            and getattr(transactional_email_service.delivery_service.settings, "enabled", False)
            and str(transactional_email_service.delivery_service.settings.provider).strip().lower() != "noop"
        )

    async def login(
        self,
        *,
        email: str,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
        device_name: str | None,
    ) -> WebSessionSnapshot:
        normalized_email = str(email or "").strip().lower()
        async with async_session_factory() as session:
            result = await session.execute(
                select(WebAccount).where(
                    and_(
                        WebAccount.email == normalized_email,
                        WebAccount.revoked_at.is_(None),
                    )
                )
            )
            web_account = result.scalar_one_or_none()
            if web_account is None or not self.password_hasher.verify_password(
                password,
                web_account.password_hash,
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password",
                )

            if web_account.email_verified_at is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Email is not verified",
                )

            web_account.last_login_at = datetime.now(timezone.utc)
            session.add(web_account)
            await session.commit()

            return await self.session_service.create_session(
                user_id=int(web_account.user_id),
                ip_address=ip_address,
                user_agent=user_agent,
                device_name=device_name,
            )

    async def logout(self, raw_session_token: str | None) -> None:
        await self.session_service.revoke_session(raw_session_token)

    async def start_registration(
        self,
        *,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> bool:
        normalized_email = self.challenge_service.normalize_email(email)
        if not normalized_email:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required")

        async with async_session_factory() as session:
            existing = await session.execute(
                select(WebAccount).where(
                    and_(
                        WebAccount.email == normalized_email,
                        WebAccount.revoked_at.is_(None),
                    )
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                )

        if not self.email_verification_required:
            return False

        challenge = await self.challenge_service.issue_challenge(
            email=normalized_email,
            purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
            request_ip=ip_address,
            request_user_agent=user_agent,
        )
        await self.transactional_email_service.send_verification_code(
            to_email=normalized_email,
            code=challenge.code,
            expires_minutes=self.email_code_ttl_minutes,
        )
        return True

    async def resend_registration(
        self,
        *,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> bool:
        return await self.start_registration(
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def verify_registration(
        self,
        *,
        email: str,
        code: str,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
        device_name: str | None,
    ) -> WebSessionSnapshot:
        normalized_email = self.challenge_service.normalize_email(email)
        self._validate_new_password(password)
        if self.email_verification_required:
            await self.challenge_service.consume_challenge(
                email=normalized_email,
                purpose=REGISTER_EMAIL_VERIFICATION_PURPOSE,
                code=code,
            )

        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            existing = await session.execute(
                select(WebAccount).where(
                    and_(
                        WebAccount.email == normalized_email,
                        WebAccount.revoked_at.is_(None),
                    )
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                )

            claimed_user_id = await self._find_claimed_user_id(session, normalized_email)
            if claimed_user_id is not None:
                app_user = await session.get(AppUser, int(claimed_user_id))
                if app_user is None or app_user.deleted_at is not None:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Email claim is not available",
                    )
                app_user.updated_at = now
                session.add(app_user)
            else:
                app_user = AppUser(
                    created_at=now,
                    updated_at=now,
                    blocked_at=None,
                    deleted_at=None,
                )
                session.add(app_user)
                await session.flush()
            session.add(
                WebAccount(
                    user_id=int(app_user.id),
                    email=normalized_email,
                    password_hash=self.password_hasher.hash_password(password),
                    email_verified_at=now,
                    linked_at=now,
                    last_login_at=now,
                    revoked_at=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                ) from None

        return await self.session_service.create_session(
            user_id=int(app_user.id),
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name,
        )

    async def login_via_telegram_link(
        self,
        *,
        raw_token: str,
        ip_address: str | None,
        user_agent: str | None,
        device_name: str | None,
    ) -> WebSessionSnapshot:
        async with async_session_factory() as session:
            token = await self.identity_link_service.get_active_token(
                session,
                raw_token=raw_token,
                purpose=LINK_WEB_PURPOSE,
            )
            app_user: AppUser | None = None
            if token is not None:
                app_user = await session.get(AppUser, int(token.user_id))
            else:
                claims = verify_telegram_web_login_token(
                    raw_token,
                    secret=self.telegram_web_login_secret,
                )
                if claims is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Link token is invalid or expired",
                    )
                telegram_account = (
                    await session.execute(
                        select(TelegramAccount).where(
                            and_(
                                TelegramAccount.telegram_id == int(claims.tg_id),
                                TelegramAccount.user_id == int(claims.user_id),
                                TelegramAccount.revoked_at.is_(None),
                            )
                        )
                    )
                ).scalar_one_or_none()
                if telegram_account is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Telegram link is invalid",
                    )
                app_user = await session.get(AppUser, int(claims.user_id))

            if app_user is None or app_user.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Link target not found",
                )

            web_account = (
                await session.execute(
                    select(WebAccount).where(
                        and_(
                            WebAccount.user_id == int(app_user.id),
                            WebAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()

            now = datetime.now(timezone.utc)
            app_user.updated_at = now
            session.add(app_user)
            if web_account is not None:
                web_account.last_login_at = now
                web_account.updated_at = now
                session.add(web_account)

            await session.commit()

        return await self.session_service.create_session(
            user_id=int(app_user.id),
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name,
        )

    async def start_password_reset(
        self,
        *,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        normalized_email = self.challenge_service.normalize_email(email)
        if not normalized_email:
            return

        async with async_session_factory() as session:
            existing = await session.execute(
                select(WebAccount).where(
                    and_(
                        WebAccount.email == normalized_email,
                        WebAccount.revoked_at.is_(None),
                        WebAccount.email_verified_at.is_not(None),
                    )
                )
            )
            web_account = existing.scalar_one_or_none()
        if web_account is None:
            return

        challenge = await self.challenge_service.issue_challenge(
            email=normalized_email,
            purpose=PASSWORD_RESET_PURPOSE,
            request_ip=ip_address,
            request_user_agent=user_agent,
        )
        await self.transactional_email_service.send_password_reset_code(
            to_email=normalized_email,
            code=challenge.code,
            expires_minutes=self.email_code_ttl_minutes,
        )

    async def reset_password(
        self,
        *,
        email: str,
        code: str,
        new_password: str,
    ) -> None:
        normalized_email = self.challenge_service.normalize_email(email)
        self._validate_new_password(new_password)
        await self.challenge_service.consume_challenge(
            email=normalized_email,
            purpose=PASSWORD_RESET_PURPOSE,
            code=code,
        )

        async with async_session_factory() as session:
            existing = await session.execute(
                select(WebAccount).where(
                    and_(
                        WebAccount.email == normalized_email,
                        WebAccount.revoked_at.is_(None),
                    )
                )
            )
            web_account = existing.scalar_one_or_none()
            if web_account is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reset request is invalid",
                )
            web_account.password_hash = self.password_hasher.hash_password(new_password)
            web_account.updated_at = datetime.now(timezone.utc)
            session.add(web_account)
            await session.commit()

        await self.session_service.revoke_all_sessions_for_user(int(web_account.user_id))

    async def get_current_user(self, raw_session_token: str | None) -> AuthenticatedWebUser:
        web_session = await self.session_service.resolve_session(raw_session_token)
        if web_session is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )

        async with async_session_factory() as session:
            app_user = await session.get(AppUser, int(web_session.user_id))
            if app_user is None or app_user.deleted_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            web_account_result = await session.execute(
                select(WebAccount).where(
                    and_(
                        WebAccount.user_id == web_session.user_id,
                        WebAccount.revoked_at.is_(None),
                    )
                )
            )
            web_account = web_account_result.scalar_one_or_none()

            telegram_result = await session.execute(
                select(TelegramAccount).where(
                    and_(
                        TelegramAccount.user_id == web_session.user_id,
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            )
            telegram_account = telegram_result.scalar_one_or_none()

        return AuthenticatedWebUser(
            user_id=int(app_user.id),
            email=str(web_account.email) if web_account is not None else None,
            email_verified=bool(web_account and web_account.email_verified_at is not None),
            telegram_linked=telegram_account is not None,
            telegram_id=int(telegram_account.telegram_id) if telegram_account else None,
            telegram_username=getattr(telegram_account, "username", None),
            created_at=app_user.created_at,
            last_login_at=getattr(web_account, "last_login_at", None),
        )

    async def _find_claimed_user_id(self, session, normalized_email: str) -> int | None:
        profiles = (
            await session.execute(
                select(UserProfile).where(UserProfile.preferred_contact_email == normalized_email)
            )
        ).scalars().all()
        if not profiles:
            return None

        candidate_user_ids: list[int] = []
        for profile in profiles:
            app_user = await session.get(AppUser, int(profile.user_id))
            if app_user is None or app_user.deleted_at is not None:
                continue

            existing_web = (
                await session.execute(
                    select(WebAccount).where(
                        and_(
                            WebAccount.user_id == int(profile.user_id),
                            WebAccount.revoked_at.is_(None),
                        )
                    )
                )
            ).scalar_one_or_none()
            if existing_web is None:
                candidate_user_ids.append(int(profile.user_id))

        unique_ids = sorted(set(candidate_user_ids))
        if len(unique_ids) > 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already reserved by another account",
            )
        if not unique_ids:
            return None
        return int(unique_ids[0])

    def _validate_new_password(self, password: str) -> None:
        normalized = str(password or "")
        if len(normalized) < self.password_min_length:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password must be at least {self.password_min_length} characters",
            )
