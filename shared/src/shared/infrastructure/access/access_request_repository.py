from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, or_
from sqlmodel import select

from shared.config.database.session import get_db_session
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
                    str(requested_template_code).strip().lower()
                    if requested_template_code
                    else None
                ),
                channel=str(channel).strip().lower(),
                request_kind=str(request_kind or ACCESS_REQUEST_KIND_NEW_ACCESS).strip().lower(),
                status="pending",
                comment=(str(comment).strip() or None) if comment is not None else None,
                review_note=None,
                reviewed_by_actor=None,
                requested_at=datetime.now(timezone.utc),
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
                or_(AccessRequest.expires_at.is_(None), AccessRequest.expires_at >= datetime.now(timezone.utc)),
            )
            normalized_request_kind = str(request_kind or "").strip().lower()
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
                        AccessRequest.expires_at < datetime.now(timezone.utc),
                    )
                )
            ).scalars().all()
            if not rows:
                return []
            now = datetime.now(timezone.utc)
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
                .limit(max(1, min(int(limit), 100)))
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
                max(1, min(int(limit), 500))
            )
            if status_name:
                stmt = stmt.where(AccessRequest.status == str(status_name).strip().lower())
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
            row.status = str(status_name).strip().lower()
            row.reviewed_by_actor = str(reviewed_by_actor).strip() or None
            row.review_note = (str(review_note).strip() or None) if review_note is not None else None
            row.reviewed_at = datetime.now(timezone.utc)
            row.access_grant_id = int(access_grant_id) if access_grant_id is not None else None
            if metadata:
                row.metadata_json = {
                    **dict(row.metadata_json or {}),
                    **dict(metadata),
                }
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
                row.metadata_json = {
                    **dict(row.metadata_json or {}),
                    **dict(metadata),
                }
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row
