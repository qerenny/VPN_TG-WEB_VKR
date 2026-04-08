from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from shared.models.users.identity_link_token_model import IdentityLinkToken


@dataclass(frozen=True, slots=True)
class IssuedIdentityLinkToken:
    raw_token: str
    expires_at: datetime


class IdentityLinkService:
    def __init__(self, *, ttl_minutes: int) -> None:
        self.ttl_minutes = max(1, int(ttl_minutes))

    async def issue_token(
        self,
        session,
        *,
        user_id: int,
        purpose: str,
        issued_by_channel: str,
        metadata: dict | None = None,
    ) -> IssuedIdentityLinkToken:
        raw_token = secrets.token_urlsafe(24)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.ttl_minutes)
        session.add(
            IdentityLinkToken(
                user_id=int(user_id),
                purpose=str(purpose),
                token_hash=self.hash_token(raw_token),
                issued_by_channel=str(issued_by_channel),
                expires_at=expires_at,
                used_at=None,
                created_at=now,
                metadata_json=dict(metadata or {}),
            )
        )
        await session.flush()
        return IssuedIdentityLinkToken(raw_token=raw_token, expires_at=expires_at)

    async def get_active_token(
        self,
        session,
        *,
        raw_token: str,
        purpose: str,
    ) -> IdentityLinkToken | None:
        from sqlmodel import select

        token_hash = self.hash_token(raw_token)
        result = await session.execute(
            select(IdentityLinkToken).where(
                IdentityLinkToken.token_hash == token_hash,
                IdentityLinkToken.purpose == str(purpose),
            )
        )
        token = result.scalar_one_or_none()
        if token is None:
            return None
        expires_at = token.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return None
        return token

    @staticmethod
    def mark_used(token: IdentityLinkToken) -> None:
        token.used_at = datetime.now(timezone.utc)

    @staticmethod
    def hash_token(raw_token: str) -> str:
        return hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()
