from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.config.settings import get_effective_product_feature_settings
from shared.infrastructure.access.access_grant_repository import AccessGrantRepository
from shared.infrastructure.access.access_request_repository import AccessRequestRepository
from shared.models.access.access_request_model import AccessRequest
from shared.models.payments.plan_model import Plan
from shared.product_constants import (
    ACCESS_REQUEST_KIND_NEW_ACCESS,
    ACCESS_REQUEST_KIND_RENEWAL,
    PRODUCT_SCOPE_STANDARD,
    PRODUCT_SCOPE_TRAFFIC_LIMITED,
)
from shared.services.access.access_registry_service import AccessRegistryService
from shared.utils.access_template_labels import format_access_template_label, is_requestable_access_template_code
from telegram_bot.services.access.access_issuance_service import AccessIssuanceService


@dataclass(frozen=True, slots=True)
class AccessRequestSnapshot:
    id: int
    user_id: int
    requested_template_code: str | None
    requested_template_label: str | None
    approved_template_label: str | None
    access_grant_id: int | None
    channel: str
    request_kind: str
    status: str
    comment: str | None
    review_note: str | None
    reviewed_by_actor: str | None
    requested_at: str
    reviewed_at: str | None
    expires_at: str | None
    metadata: dict[str, Any]


class AccessRequestService:
    REPEAT_COOLDOWN_SECONDS = 600

    def __init__(
        self,
        *,
        access_request_repository: AccessRequestRepository,
        access_grant_repository: AccessGrantRepository,
        access_issuance_service: AccessIssuanceService,
        access_registry_service: AccessRegistryService | None = None,
        notification_service: Any | None = None,
    ) -> None:
        self.access_request_repository = access_request_repository
        self.access_grant_repository = access_grant_repository
        self.access_issuance_service = access_issuance_service
        self.access_registry_service = access_registry_service
        self.notification_service = notification_service

    async def create_request(
        self,
        *,
        user_id: int,
        template_code: str | None,
        comment: str | None,
        channel: str,
        request_kind: str = ACCESS_REQUEST_KIND_NEW_ACCESS,
    ) -> AccessRequestSnapshot:
        self._ensure_requests_enabled()
        await self._expire_stale_pending_requests()
        if await self.is_registry_managed_user(user_id=int(user_id)):
            raise HTTPException(
                status_code=409,
                detail="Access is managed automatically by the access registry",
            )

        normalized_request_kind = self._normalize_request_kind(request_kind)
        normalized_template_code = str(template_code).strip().lower() if template_code is not None else None
        if normalized_template_code:
            plan = await self._load_plan_or_404(normalized_template_code)
            if not is_requestable_access_template_code(normalized_template_code):
                raise HTTPException(
                    status_code=400,
                    detail="This access template is not available for self-service requests",
                )
            self._ensure_plan_scope_enabled(str(plan.scope))
        elif normalized_request_kind == ACCESS_REQUEST_KIND_RENEWAL:
            normalized_template_code = await self._resolve_default_renewal_template_code(int(user_id))
            if normalized_template_code is None:
                raise HTTPException(
                    status_code=400,
                    detail="No active access found for renewal request",
                )

        row = await self.access_request_repository.create_request(
            user_id=int(user_id),
            requested_template_code=normalized_template_code,
            channel=str(channel).strip().lower(),
            request_kind=normalized_request_kind,
            comment=comment,
            expires_at=self._build_pending_expiry(),
            metadata={},
        )
        result = await self._maybe_auto_approve(
            row,
            requested_template_code=normalized_template_code,
            request_kind=normalized_request_kind,
        )
        if result.status == "pending" and self.notification_service is not None:
            await self.notification_service.notify_admins_request_created(
                request_id=int(result.id),
                user_id=int(result.user_id),
                request_kind=result.request_kind,
                requested_template_code=result.requested_template_code,
                channel=result.channel,
                comment=result.comment,
            )
        return result

    async def is_registry_managed_user(self, *, user_id: int) -> bool:
        if self.access_registry_service is None:
            return False
        return await self.access_registry_service.find_managed_entry(user_id=int(user_id)) is not None

    async def list_user_requests(self, *, user_id: int, limit: int = 20) -> list[AccessRequestSnapshot]:
        self._ensure_requests_enabled()
        await self._expire_stale_pending_requests()
        rows = await self.access_request_repository.list_user_requests(user_id=int(user_id), limit=limit)
        return [self._serialize_request(row) for row in rows]

    async def list_requests(
        self,
        *,
        status_name: str | None = None,
        limit: int = 100,
    ) -> list[AccessRequestSnapshot]:
        self._ensure_requests_enabled()
        await self._expire_stale_pending_requests()
        rows = await self.access_request_repository.list_requests(status_name=status_name, limit=limit)
        return [self._serialize_request(row) for row in rows]

    async def review_request(
        self,
        *,
        request_id: int,
        decision: str,
        principal: Any,
        review_note: str | None = None,
        template_code: str | None = None,
    ) -> AccessRequestSnapshot:
        self._ensure_requests_enabled()
        await self._expire_stale_pending_requests()
        row = await self.access_request_repository.get_request(int(request_id))
        if row is None:
            raise HTTPException(status_code=404, detail="Access request not found")
        if str(row.status).strip().lower() != "pending":
            raise HTTPException(status_code=409, detail="Access request is already reviewed")

        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"approve", "reject"}:
            raise HTTPException(status_code=400, detail="Unsupported review decision")

        actor = str(getattr(principal, "actor", "") or "").strip() or "system"
        if normalized_decision == "reject":
            updated = await self.access_request_repository.mark_reviewed(
                request_id=int(request_id),
                status_name="rejected",
                reviewed_by_actor=actor,
                review_note=review_note,
            )
            await self._notify_reviewed(updated)
            return self._serialize_request(updated)

        resolved_template_code = (
            str(template_code).strip().lower()
            if template_code is not None and str(template_code).strip()
            else str(row.requested_template_code or "").strip().lower() or None
        )
        if not resolved_template_code:
            raise HTTPException(
                status_code=400,
                detail="template_code is required to approve access request",
            )
        plan = await self._load_plan_or_404(resolved_template_code)
        self._ensure_plan_scope_enabled(str(plan.scope))

        source_ref = f"access_request:{int(row.id)}"
        await self.access_issuance_service.activate_from_payload(
            payload=str(plan.payload),
            source_type="request_approval",
            source_ref=source_ref,
            user_id=int(row.user_id),
            extra_metadata={
                "request_kind": str(getattr(row, "request_kind", ACCESS_REQUEST_KIND_NEW_ACCESS)),
            },
        )
        grant = await self.access_grant_repository.get_by_source(
            source_type="request_approval",
            source_ref=source_ref,
        )
        updated = await self.access_request_repository.mark_reviewed(
            request_id=int(request_id),
            status_name="approved",
            reviewed_by_actor=actor,
            review_note=review_note,
            access_grant_id=int(grant.id) if grant is not None and grant.id is not None else None,
            metadata={"approved_template_code": resolved_template_code},
        )
        await self._notify_reviewed(updated)
        return self._serialize_request(updated)

    async def repeat_request(
        self,
        *,
        user_id: int,
        request_id: int,
    ) -> AccessRequestSnapshot:
        self._ensure_requests_enabled()
        await self._expire_stale_pending_requests()
        row = await self.access_request_repository.get_request(int(request_id))
        if row is None or int(row.user_id) != int(user_id):
            raise HTTPException(status_code=404, detail="Access request not found")
        if str(row.status).strip().lower() != "pending":
            raise HTTPException(status_code=409, detail="Only pending access requests can be repeated")

        now = datetime.now(timezone.utc)
        requested_at = row.requested_at
        if requested_at.tzinfo is None:
            requested_at = requested_at.replace(tzinfo=timezone.utc)
        remaining_seconds = max(
            0,
            self.REPEAT_COOLDOWN_SECONDS - int((now - requested_at).total_seconds()),
        )
        if remaining_seconds > 0:
            raise HTTPException(
                status_code=429,
                detail=f"Repeat request will be available in {remaining_seconds} seconds",
            )

        metadata = dict(row.metadata_json or {})
        updated = await self.access_request_repository.touch_pending_request(
            request_id=int(request_id),
            requested_at=now,
            metadata={
                "repeat_count": int(metadata.get("repeat_count") or 0) + 1,
                "last_repeated_at": now.isoformat(),
            },
        )
        if self.notification_service is not None:
            await self.notification_service.notify_admins_request_created(
                request_id=int(updated.id),
                user_id=int(updated.user_id),
                request_kind=str(getattr(updated, "request_kind", ACCESS_REQUEST_KIND_NEW_ACCESS)),
                requested_template_code=updated.requested_template_code,
                channel=updated.channel,
                comment=updated.comment,
            )
        return self._serialize_request(updated)

    @staticmethod
    def _serialize_request(row: AccessRequest) -> AccessRequestSnapshot:
        metadata = dict(row.metadata_json or {})
        requested_template_code = row.requested_template_code
        approved_template_code = str(metadata.get("approved_template_code") or "").strip() or None
        return AccessRequestSnapshot(
            id=int(row.id),
            user_id=int(row.user_id),
            requested_template_code=requested_template_code,
            requested_template_label=(
                format_access_template_label(requested_template_code)
                if requested_template_code is not None
                else None
            ),
            approved_template_label=(
                format_access_template_label(approved_template_code)
                if approved_template_code is not None
                else None
            ),
            access_grant_id=row.access_grant_id,
            channel=str(row.channel),
            request_kind=str(getattr(row, "request_kind", ACCESS_REQUEST_KIND_NEW_ACCESS)),
            status=str(row.status),
            comment=row.comment,
            review_note=row.review_note,
            reviewed_by_actor=row.reviewed_by_actor,
            requested_at=row.requested_at.isoformat(),
            reviewed_at=row.reviewed_at.isoformat() if row.reviewed_at is not None else None,
            expires_at=row.expires_at.isoformat() if getattr(row, "expires_at", None) is not None else None,
            metadata=metadata,
        )

    @staticmethod
    def _ensure_requests_enabled() -> None:
        if not get_effective_product_feature_settings().access_requests_enabled:
            raise HTTPException(status_code=404, detail="Access requests module is disabled")

    @staticmethod
    def _normalize_request_kind(value: str | None) -> str:
        normalized = str(value or ACCESS_REQUEST_KIND_NEW_ACCESS).strip().lower()
        if normalized not in {ACCESS_REQUEST_KIND_NEW_ACCESS, ACCESS_REQUEST_KIND_RENEWAL}:
            raise HTTPException(status_code=400, detail="Unsupported request kind")
        return normalized

    @staticmethod
    def _build_pending_expiry() -> datetime:
        features = get_effective_product_feature_settings()
        ttl_hours = max(1, int(getattr(features, "access_request_pending_ttl_hours", 72)))
        return datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

    @staticmethod
    async def _load_plan_or_404(template_code: str) -> Plan:
        async with get_db_session() as session:
            plan = (
                await session.execute(
                    select(Plan).where(
                        Plan.code == str(template_code).strip().lower(),
                        Plan.is_active.is_(True),
                    )
                )
            ).scalar_one_or_none()
        if plan is None:
            raise HTTPException(status_code=404, detail="Access template not found")
        return plan

    @staticmethod
    def _ensure_plan_scope_enabled(scope: str) -> None:
        features = get_effective_product_feature_settings()
        normalized_scope = str(scope or "").strip().lower()
        if normalized_scope == PRODUCT_SCOPE_STANDARD and not features.standard_config_enabled:
            raise HTTPException(status_code=404, detail="Standard configuration module is disabled")
        if normalized_scope == PRODUCT_SCOPE_TRAFFIC_LIMITED and not features.traffic_limited_config_enabled:
            raise HTTPException(
                status_code=404,
                detail="Traffic-limited configuration module is disabled",
            )

    async def _maybe_auto_approve(
        self,
        row: AccessRequest,
        *,
        requested_template_code: str | None,
        request_kind: str,
    ) -> AccessRequestSnapshot:
        if self.access_registry_service is None:
            return self._serialize_request(row)

        match = await self.access_registry_service.find_auto_approve_match(
            user_id=int(row.user_id),
            requested_template_code=requested_template_code,
            request_kind=request_kind,
        )
        if match is None:
            return self._serialize_request(row)

        resolved_template_code = requested_template_code or str(match.template_code).strip().lower()
        plan = await self._load_plan_or_404(resolved_template_code)
        self._ensure_plan_scope_enabled(str(plan.scope))

        source_ref = f"access_request:{int(row.id)}"
        await self.access_issuance_service.activate_from_payload(
            payload=str(plan.payload),
            source_type="access_registry",
            source_ref=source_ref,
            user_id=int(row.user_id),
            extra_metadata={
                "request_kind": request_kind,
                "access_registry_entry_id": int(match.id),
            },
        )
        grant = await self.access_grant_repository.get_by_source(
            source_type="access_registry",
            source_ref=source_ref,
        )
        updated = await self.access_request_repository.mark_reviewed(
            request_id=int(row.id),
            status_name="approved",
            reviewed_by_actor="access_registry",
            review_note="Auto-approved by access registry",
            access_grant_id=int(grant.id) if grant is not None and grant.id is not None else None,
            metadata={
                "approved_template_code": resolved_template_code,
                "access_registry_entry_id": int(match.id),
                "auto_approved": True,
            },
        )
        await self._notify_reviewed(updated)
        return self._serialize_request(updated)

    async def _notify_reviewed(self, row: AccessRequest) -> None:
        if self.notification_service is None:
            return
        metadata = dict(row.metadata_json or {})
        template_code = str(metadata.get("approved_template_code") or row.requested_template_code or "").strip() or None
        await self.notification_service.notify_user_request_reviewed(
            user_id=int(row.user_id),
            request_id=int(row.id),
            status=str(row.status),
            request_kind=str(getattr(row, "request_kind", ACCESS_REQUEST_KIND_NEW_ACCESS)),
            template_code=template_code,
            review_note=row.review_note,
            reviewed_by_actor=row.reviewed_by_actor,
            auto_approved=bool(metadata.get("auto_approved")),
        )

    async def _expire_stale_pending_requests(self) -> None:
        expired_rows = await self.access_request_repository.expire_stale_pending()
        if not expired_rows or self.notification_service is None:
            return
        for row in expired_rows:
            await self.notification_service.notify_user_request_reviewed(
                user_id=int(row.user_id),
                request_id=int(row.id),
                status=str(row.status),
                request_kind=str(getattr(row, "request_kind", ACCESS_REQUEST_KIND_NEW_ACCESS)),
                template_code=str(row.requested_template_code or "").strip() or None,
                review_note=row.review_note,
                reviewed_by_actor=row.reviewed_by_actor,
                auto_approved=False,
            )

    async def _resolve_default_renewal_template_code(self, user_id: int) -> str | None:
        active_grants = await self.access_grant_repository.list_active_user_grants(user_id=int(user_id), limit=20)
        if not active_grants:
            return None
        latest = active_grants[0]
        return str(getattr(latest, "template_code", "") or "").strip().lower() or None
