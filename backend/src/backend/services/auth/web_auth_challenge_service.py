from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select, update

from shared.config.database.engine import async_session_factory
from shared.models.users.web_auth_challenge_model import WebAuthChallenge


REGISTER_EMAIL_VERIFICATION_PURPOSE = "register_email_verification"
PASSWORD_RESET_PURPOSE = "password_reset"
LINKING_CONFIRMATION_PURPOSE = "linking_confirmation"


@dataclass(frozen=True, slots=True)
class IssuedWebAuthChallenge:
    email: str
    purpose: str
    code: str
    expires_at: datetime


class WebAuthChallengeService:
    def __init__(
        self,
        *,
        code_ttl_minutes: int,
        resend_cooldown_seconds: int,
        request_window_seconds: int,
        max_requests_per_window_per_email: int,
        max_requests_per_window_per_ip: int,
        max_failed_attempts: int,
    ) -> None:
        self.code_ttl_minutes = max(1, int(code_ttl_minutes))
        self.resend_cooldown_seconds = max(0, int(resend_cooldown_seconds))
        self.request_window_seconds = max(60, int(request_window_seconds))
        self.max_requests_per_window_per_email = max(
            1, int(max_requests_per_window_per_email)
        )
        self.max_requests_per_window_per_ip = max(1, int(max_requests_per_window_per_ip))
        self.max_failed_attempts = max(1, int(max_failed_attempts))

    @staticmethod
    def normalize_email(email: str) -> str:
        return str(email or "").strip().lower()

    @staticmethod
    def _hash_code(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    @staticmethod
    def _generate_code() -> str:
        return f"{secrets.randbelow(900000) + 100000:06d}"

    @staticmethod
    def _coerce_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def issue_challenge(
        self,
        *,
        email: str,
        purpose: str,
        request_ip: str | None,
        request_user_agent: str | None,
    ) -> IssuedWebAuthChallenge:
        normalized_email = self.normalize_email(email)
        now = datetime.now(timezone.utc)
        window_started_at = now - timedelta(seconds=self.request_window_seconds)

        async with async_session_factory() as session:
            await self._assert_request_limits(
                session=session,
                purpose=purpose,
                email=normalized_email,
                request_ip=request_ip,
                now=now,
                window_started_at=window_started_at,
            )
            await self._revoke_active_challenges(
                session=session,
                purpose=purpose,
                email=normalized_email,
                now=now,
            )

            code = self._generate_code()
            challenge = WebAuthChallenge(
                email=normalized_email,
                purpose=purpose,
                code_hash=self._hash_code(code),
                request_ip=request_ip,
                request_user_agent=request_user_agent,
                failed_attempts=0,
                last_sent_at=now,
                expires_at=now + timedelta(minutes=self.code_ttl_minutes),
                consumed_at=None,
                revoked_at=None,
                created_at=now,
                updated_at=now,
                metadata_json={},
            )
            session.add(challenge)
            await session.commit()

        return IssuedWebAuthChallenge(
            email=normalized_email,
            purpose=purpose,
            code=code,
            expires_at=now + timedelta(minutes=self.code_ttl_minutes),
        )

    async def consume_challenge(
        self,
        *,
        email: str,
        purpose: str,
        code: str,
    ) -> None:
        normalized_email = self.normalize_email(email)
        now = datetime.now(timezone.utc)

        async with async_session_factory() as session:
            result = await session.execute(
                select(WebAuthChallenge)
                .where(
                    and_(
                        WebAuthChallenge.email == normalized_email,
                        WebAuthChallenge.purpose == purpose,
                        WebAuthChallenge.revoked_at.is_(None),
                        WebAuthChallenge.consumed_at.is_(None),
                    )
                )
                .order_by(WebAuthChallenge.id.desc())
                .limit(1)
            )
            challenge = result.scalar_one_or_none()
            if challenge is None or self._coerce_utc(challenge.expires_at) <= now:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Code is invalid or expired",
                )

            if not hmac.compare_digest(challenge.code_hash, self._hash_code(str(code or "").strip())):
                challenge.failed_attempts = int(challenge.failed_attempts or 0) + 1
                challenge.updated_at = now
                if challenge.failed_attempts >= self.max_failed_attempts:
                    challenge.revoked_at = now
                session.add(challenge)
                await session.commit()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Code is invalid or expired",
                )

            challenge.consumed_at = now
            challenge.updated_at = now
            session.add(challenge)
            await session.commit()

    async def _assert_request_limits(
        self,
        *,
        session,
        purpose: str,
        email: str,
        request_ip: str | None,
        now: datetime,
        window_started_at: datetime,
    ) -> None:
        recent_email_count = (
            await session.execute(
                select(func.count())
                .select_from(WebAuthChallenge)
                .where(
                    and_(
                        WebAuthChallenge.email == email,
                        WebAuthChallenge.purpose == purpose,
                        WebAuthChallenge.created_at >= window_started_at,
                    )
                )
            )
        ).scalar_one()
        if int(recent_email_count or 0) >= self.max_requests_per_window_per_email:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many code requests for this email",
            )

        if request_ip:
            recent_ip_count = (
                await session.execute(
                    select(func.count())
                    .select_from(WebAuthChallenge)
                    .where(
                        and_(
                            WebAuthChallenge.request_ip == request_ip,
                            WebAuthChallenge.created_at >= window_started_at,
                        )
                    )
                )
            ).scalar_one()
            if int(recent_ip_count or 0) >= self.max_requests_per_window_per_ip:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many code requests from this IP",
                )

        if self.resend_cooldown_seconds <= 0:
            return

        recent_active = (
            await session.execute(
                select(WebAuthChallenge)
                .where(
                    and_(
                        WebAuthChallenge.email == email,
                        WebAuthChallenge.purpose == purpose,
                        WebAuthChallenge.revoked_at.is_(None),
                        WebAuthChallenge.consumed_at.is_(None),
                        WebAuthChallenge.expires_at > now,
                    )
                )
                .order_by(WebAuthChallenge.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if recent_active is None:
            return

        cooldown_deadline = recent_active.last_sent_at + timedelta(
            seconds=self.resend_cooldown_seconds
        )
        if cooldown_deadline > now:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait before requesting another code",
            )

    async def _revoke_active_challenges(
        self,
        *,
        session,
        purpose: str,
        email: str,
        now: datetime,
    ) -> None:
        await session.execute(
            update(WebAuthChallenge)
            .where(
                and_(
                    WebAuthChallenge.email == email,
                    WebAuthChallenge.purpose == purpose,
                    WebAuthChallenge.revoked_at.is_(None),
                    WebAuthChallenge.consumed_at.is_(None),
                    or_(WebAuthChallenge.expires_at > now, WebAuthChallenge.expires_at.is_(None)),
                )
            )
            .values(revoked_at=now, updated_at=now)
        )
