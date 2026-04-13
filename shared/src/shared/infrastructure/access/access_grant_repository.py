from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.infrastructure.access.repository_utils import clamp_limit, merge_metadata, normalize_string_list, normalize_optional_text, utc_now
from shared.models.access.access_grant_model import AccessGrant
from shared.models.payments.plan_model import Plan
from shared.product_constants import ACCESS_GRANT_STATUS_ACTIVE, ACCESS_GRANT_STATUS_EXPIRED, ACCESS_GRANT_STATUS_REVOKED


class AccessGrantRepository:
    @staticmethod
    def _ordered_grants_stmt():
        return select(AccessGrant).order_by(AccessGrant.created_at.desc(), AccessGrant.id.desc())

    @staticmethod
    def _apply_revocation(
        row: AccessGrant,
        *,
        now: datetime,
        actor: str,
        reason: str | None = None,
    ) -> None:
        row.status = ACCESS_GRANT_STATUS_REVOKED
        row.revoked_at = now
        row.metadata_json = merge_metadata(
            row.metadata_json,
            {
                "revoked_by_actor": normalize_optional_text(actor),
                "revoke_reason": normalize_optional_text(reason),
            },
        )

    async def list_active_grants_by_source_types(
        self,
        *,
        source_types: list[str],
        limit: int = 500,
    ) -> list[AccessGrant]:
        normalized = normalize_string_list(source_types)
        if not normalized:
            return []
        await self.reconcile_expired_grants()
        async with get_db_session() as session:
            rows = await session.execute(
                self._ordered_grants_stmt()
                .where(
                    AccessGrant.status == ACCESS_GRANT_STATUS_ACTIVE,
                    or_(*[AccessGrant.source_type == item for item in normalized]),
                )
                .limit(clamp_limit(limit, maximum=1000))
            )
            return list(rows.scalars().all())

    async def list_expiring_active_grants(
        self,
        *,
        within_hours: int,
        limit: int = 200,
    ) -> list[AccessGrant]:
        now = datetime.now(timezone.utc)
        boundary = now + timedelta(hours=max(1, int(within_hours)))
        async with get_db_session() as session:
            rows = await session.execute(
                select(AccessGrant)
                .where(
                    AccessGrant.status == ACCESS_GRANT_STATUS_ACTIVE,
                    AccessGrant.expires_at.is_not(None),
                    AccessGrant.expires_at > now,
                    AccessGrant.expires_at <= boundary,
                )
                .order_by(AccessGrant.expires_at.asc(), AccessGrant.id.asc())
                .limit(clamp_limit(limit, maximum=500))
            )
            return list(rows.scalars().all())

    async def list_user_grants(
        self,
        *,
        user_id: int,
        limit: int = 20,
    ) -> list[AccessGrant]:
        async with get_db_session() as session:
            rows = await session.execute(
                self._ordered_grants_stmt()
                .where(AccessGrant.user_id == int(user_id))
                .limit(clamp_limit(limit, maximum=200))
            )
            return list(rows.scalars().all())

    async def get_by_source(
        self,
        *,
        source_type: str,
        source_ref: str,
    ) -> AccessGrant | None:
        async with get_db_session() as session:
            return (
                await session.execute(
                    select(AccessGrant).where(
                        AccessGrant.source_type == str(source_type).strip().lower(),
                        AccessGrant.source_ref == str(source_ref).strip(),
                    )
                )
            ).scalar_one_or_none()

    async def list_active_user_grants(
        self,
        *,
        user_id: int,
        limit: int = 20,
    ) -> list[AccessGrant]:
        await self.reconcile_expired_grants(user_id=int(user_id))
        async with get_db_session() as session:
            rows = await session.execute(
                self._ordered_grants_stmt()
                .where(
                    AccessGrant.user_id == int(user_id),
                    AccessGrant.status == ACCESS_GRANT_STATUS_ACTIVE,
                )
                .limit(clamp_limit(limit, maximum=200))
            )
            return list(rows.scalars().all())

    async def reconcile_expired_grants(self, *, user_id: int | None = None) -> list[AccessGrant]:
        now = utc_now()
        async with get_db_session() as session:
            stmt = select(AccessGrant).where(
                AccessGrant.status == ACCESS_GRANT_STATUS_ACTIVE,
                AccessGrant.expires_at.is_not(None),
                AccessGrant.expires_at < now,
            )
            if user_id is not None:
                stmt = stmt.where(AccessGrant.user_id == int(user_id))
            rows = (await session.execute(stmt)).scalars().all()
            if not rows:
                return []
            for row in rows:
                row.status = ACCESS_GRANT_STATUS_EXPIRED
                row.metadata_json = merge_metadata(row.metadata_json, {"expired_at": now.isoformat()})
                session.add(row)
            await session.commit()
            for row in rows:
                await session.refresh(row)
            return list(rows)

    async def revoke_user_scope_grants(
        self,
        *,
        user_id: int,
        scope: str,
        actor: str,
        reason: str | None = None,
    ) -> list[AccessGrant]:
        await self.reconcile_expired_grants(user_id=int(user_id))
        now = utc_now()
        async with get_db_session() as session:
            rows = (
                await session.execute(
                    select(AccessGrant).where(
                        AccessGrant.user_id == int(user_id),
                        AccessGrant.scope == str(scope).strip().lower(),
                        AccessGrant.status == ACCESS_GRANT_STATUS_ACTIVE,
                    )
                )
            ).scalars().all()
            if not rows:
                return []
            for row in rows:
                self._apply_revocation(row, now=now, actor=actor, reason=reason)
                session.add(row)
            await session.commit()
            for row in rows:
                await session.refresh(row)
            return list(rows)

    async def revoke_scope_grants_by_source_types(
        self,
        *,
        user_id: int,
        scope: str,
        source_types: list[str],
        actor: str,
        reason: str | None = None,
    ) -> list[AccessGrant]:
        await self.reconcile_expired_grants(user_id=int(user_id))
        normalized = normalize_string_list(source_types)
        if not normalized:
            return []
        now = utc_now()
        async with get_db_session() as session:
            rows = (
                await session.execute(
                    select(AccessGrant).where(
                        AccessGrant.user_id == int(user_id),
                        AccessGrant.scope == str(scope).strip().lower(),
                        AccessGrant.status == ACCESS_GRANT_STATUS_ACTIVE,
                        or_(*[AccessGrant.source_type == item for item in normalized]),
                    )
                )
            ).scalars().all()
            if not rows:
                return []
            for row in rows:
                self._apply_revocation(row, now=now, actor=actor, reason=reason)
                session.add(row)
            await session.commit()
            for row in rows:
                await session.refresh(row)
            return list(rows)

    async def has_active_scope_grant(
        self,
        *,
        user_id: int,
        scope: str,
        exclude_grant_id: int | None = None,
    ) -> bool:
        await self.reconcile_expired_grants(user_id=int(user_id))
        async with get_db_session() as session:
            stmt = select(AccessGrant.id).where(
                AccessGrant.user_id == int(user_id),
                AccessGrant.scope == str(scope).strip().lower(),
                AccessGrant.status == ACCESS_GRANT_STATUS_ACTIVE,
            )
            if exclude_grant_id is not None:
                stmt = stmt.where(AccessGrant.id != int(exclude_grant_id))
            row = (await session.execute(stmt.limit(1))).first()
            return row is not None

    async def record_grant(
        self,
        *,
        user_id: int,
        template_code: str,
        scope: str,
        entitlement_kind: str,
        source_type: str,
        source_ref: str | None,
        expires_at: datetime | None,
        quota_bytes: int | None,
        granted_by_user_id: int | None = None,
        status: str = "active",
        metadata: dict | None = None,
    ) -> AccessGrant:
        async with get_db_session() as session:
            if source_ref:
                existing = (
                    await session.execute(
                        select(AccessGrant).where(
                            AccessGrant.source_type == str(source_type),
                            AccessGrant.source_ref == str(source_ref),
                        )
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    return existing

            plan = (
                await session.execute(
                    select(Plan).where(Plan.code == str(template_code).strip().lower())
                )
            ).scalar_one_or_none()

            now = datetime.now(timezone.utc)
            grant = AccessGrant(
                user_id=int(user_id),
                granted_by_user_id=(
                    int(granted_by_user_id) if granted_by_user_id is not None else None
                ),
                plan_id=int(plan.id) if plan is not None else None,
                template_code=str(template_code).strip().lower(),
                scope=str(scope).strip().lower(),
                entitlement_kind=str(entitlement_kind).strip().lower(),
                source_type=str(source_type).strip().lower(),
                source_ref=str(source_ref).strip() if source_ref else None,
                status=str(status).strip().lower(),
                expires_at=expires_at,
                quota_bytes=quota_bytes,
                created_at=now,
                activated_at=now,
                revoked_at=None,
                metadata_json=dict(metadata or {}),
            )
            session.add(grant)
            await session.commit()
            await session.refresh(grant)
            return grant
