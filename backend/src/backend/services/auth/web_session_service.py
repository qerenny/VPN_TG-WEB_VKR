from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

from shared.config.database.engine import async_session_factory
from shared.models.users.web_session_model import WebSession


@dataclass(slots=True)
class WebSessionSnapshot:
    session_id: int
    user_id: int
    raw_token: str
    expires_at: datetime


class WebSessionService:
    def __init__(self, *, ttl_minutes: int):
        self.ttl_minutes = max(5, int(ttl_minutes))

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    async def create_session(
        self,
        *,
        user_id: int,
        ip_address: str | None,
        user_agent: str | None,
        device_name: str | None,
    ) -> WebSessionSnapshot:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.ttl_minutes)
        raw_token = secrets.token_urlsafe(48)

        session_row = WebSession(
            user_id=user_id,
            session_token_hash=self._hash_token(raw_token),
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name,
            created_at=now,
            last_seen_at=now,
            expires_at=expires_at,
            revoked_at=None,
            metadata_json={},
        )

        async with async_session_factory() as session:
            session.add(session_row)
            await session.commit()
            await session.refresh(session_row)

        return WebSessionSnapshot(
            session_id=int(session_row.id),
            user_id=int(user_id),
            raw_token=raw_token,
            expires_at=expires_at,
        )

    async def resolve_session(self, raw_token: str | None) -> WebSession | None:
        if not raw_token:
            return None

        now = datetime.now(timezone.utc)
        token_hash = self._hash_token(raw_token)
        async with async_session_factory() as session:
            result = await session.execute(
                select(WebSession).where(
                    and_(
                        WebSession.session_token_hash == token_hash,
                        WebSession.revoked_at.is_(None),
                        WebSession.expires_at > now,
                    )
                )
            )
            web_session = result.scalar_one_or_none()
            if web_session is None:
                return None

            web_session.last_seen_at = now
            session.add(web_session)
            await session.commit()
            await session.refresh(web_session)
            return web_session

    async def revoke_session(self, raw_token: str | None) -> None:
        if not raw_token:
            return

        token_hash = self._hash_token(raw_token)
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            result = await session.execute(
                select(WebSession).where(WebSession.session_token_hash == token_hash)
            )
            web_session = result.scalar_one_or_none()
            if web_session is None or web_session.revoked_at is not None:
                return
            web_session.revoked_at = now
            session.add(web_session)
            await session.commit()

    async def revoke_all_sessions_for_user(self, user_id: int) -> None:
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            result = await session.execute(
                select(WebSession).where(
                    and_(
                        WebSession.user_id == int(user_id),
                        WebSession.revoked_at.is_(None),
                    )
                )
            )
            sessions = result.scalars().all()
            for web_session in sessions:
                web_session.revoked_at = now
                session.add(web_session)
            await session.commit()
