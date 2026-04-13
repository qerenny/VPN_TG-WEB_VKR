from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, or_
from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.infrastructure.access.repository_utils import (
    clamp_limit,
    merge_metadata,
    normalize_optional_text,
    normalize_text,
    utc_now,
)
from shared.models.access.access_request_model import AccessRequest
from shared.product_constants import ACCESS_REQUEST_KIND_NEW_ACCESS


class AccessRequestRepository:
    async def create_request(
        self,
        *,
        user_id: int,
        requested_template_code: str | None,
        channel: str,
        request_kind: str = ACCESS_REQUEST_KIND_NEW_ACCESS,
        comment: str | None,
        expires_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> AccessRequest:
        existing = await self.find_pending_duplicate(
            user_id=user_id,
            request_kind=request_kind,
        )
        if existing is not None:
            return existing

        async with get_db_session() as session:
            row = AccessRequest(
                user_id=int(user_id),
                requested_template_code=(
                    normalize_optional_text(requested_template_code, lowercase=True)
                ),
                channel=normalize_text(channel, lowercase=True),
                request_kind=normalize_text(request_kind or ACCESS_REQUEST_KIND_NEW_ACCESS, lowercase=True),
                status="pending",
                comment=normalize_optional_text(comment),
                review_note=None,
                reviewed_by_actor=None,
                requested_at=utc_now(),
                reviewed_at=None,
                expires_at=expires_at,
                metadata_json=dict(metadata or {}),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def find_pending_duplicate(
        self,
        *,
        user_id: int,
        request_kind: str | None = None,
    ) -> AccessRequest | None:
        async with get_db_session() as session:
            stmt = select(AccessRequest).where(
                AccessRequest.user_id == int(user_id),
                AccessRequest.status == "pending",
                or_(AccessRequest.expires_at.is_(None), AccessRequest.expires_at >= utc_now()),
            )
            normalized_request_kind = normalize_text(request_kind, lowercase=True)
            if normalized_request_kind:
                stmt = stmt.where(AccessRequest.request_kind == normalized_request_kind)
            return (await session.execute(stmt)).scalar_one_or_none()

    async def expire_stale_pending(self) -> list[AccessRequest]:
        async with get_db_session() as session:
            rows = (
                await session.execute(
                    select(AccessRequest).where(
                        AccessRequest.status == "pending",
                        AccessRequest.expires_at.is_not(None),
                        AccessRequest.expires_at < utc_now(),
                    )
                )
            ).scalars().all()
            if not rows:
                return []
            now = utc_now()
            for row in rows:
                row.status = "expired"
                row.reviewed_by_actor = "system:auto_expire"
                row.review_note = "Request expired before review"
                row.reviewed_at = now
                session.add(row)
            await session.commit()
            for row in rows:
                await session.refresh(row)
            return list(rows)

    async def get_request(self, request_id: int) -> AccessRequest | None:
        async with get_db_session() as session:
            return await session.get(AccessRequest, int(request_id))

    async def list_user_requests(self, *, user_id: int, limit: int = 20) -> list[AccessRequest]:
        async with get_db_session() as session:
            rows = await session.execute(
                select(AccessRequest)
                .where(AccessRequest.user_id == int(user_id))
                .order_by(desc(AccessRequest.requested_at))
                .limit(clamp_limit(limit, maximum=100))
            )
            return list(rows.scalars().all())

    async def list_requests(
        self,
        *,
        status_name: str | None = None,
        limit: int = 100,
    ) -> list[AccessRequest]:
        async with get_db_session() as session:
            stmt = select(AccessRequest).order_by(desc(AccessRequest.requested_at)).limit(
                clamp_limit(limit, maximum=500)
            )
            if status_name:
                stmt = stmt.where(AccessRequest.status == normalize_text(status_name, lowercase=True))
            rows = await session.execute(stmt)
            return list(rows.scalars().all())

    async def mark_reviewed(
        self,
        *,
        request_id: int,
        status_name: str,
        reviewed_by_actor: str,
        review_note: str | None = None,
        access_grant_id: int | None = None,
        metadata: dict | None = None,
    ) -> AccessRequest:
        async with get_db_session() as session:
            row = await session.get(AccessRequest, int(request_id))
            if row is None:
                raise ValueError(f"Access request {request_id} not found")
            row.status = normalize_text(status_name, lowercase=True)
            row.reviewed_by_actor = normalize_optional_text(reviewed_by_actor)
            row.review_note = normalize_optional_text(review_note)
            row.reviewed_at = utc_now()
            row.access_grant_id = int(access_grant_id) if access_grant_id is not None else None
            if metadata:
                row.metadata_json = merge_metadata(row.metadata_json, metadata)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def touch_pending_request(
        self,
        *,
        request_id: int,
        requested_at: datetime,
        metadata: dict | None = None,
    ) -> AccessRequest:
        async with get_db_session() as session:
            row = await session.get(AccessRequest, int(request_id))
            if row is None:
                raise ValueError(f"Access request {request_id} not found")
            row.requested_at = requested_at
            if metadata:
                row.metadata_json = merge_metadata(row.metadata_json, metadata)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row
