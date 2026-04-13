from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.product_constants import ACCESS_REQUEST_KIND_NEW_ACCESS


@dataclass(frozen=True, slots=True)
class TelegramAccessRequestSnapshot:
    id: int
    user_id: int
    requested_template_code: str | None
    status: str
    channel: str
    request_kind: str
    comment: str | None
    review_note: str | None
    reviewed_by_actor: str | None
    requested_at: str
    reviewed_at: str | None
    expires_at: str | None
    metadata: dict


class TelegramAccessRequestService:
    def __init__(
        self,
        *,
        user_repository: TelegramUserRepository,
        access_request_service: Any,
        access_grant_repository: Any,
    ) -> None:
        self.user_repository = user_repository
        self.access_request_service = access_request_service
        self.access_grant_repository = access_grant_repository

    async def create_or_get_pending_request(
        self,
        *,
        tg_id: int,
        template_code: str | None = None,
        request_kind: str = ACCESS_REQUEST_KIND_NEW_ACCESS,
        comment: str | None = None,
    ) -> tuple[TelegramAccessRequestSnapshot, bool]:
        user_id = await self.user_repository.get_app_user_id(int(tg_id))
        if user_id is None:
            raise ValueError(f"Telegram user {tg_id} is not registered")

        before = await self.access_request_service.list_user_requests(user_id=int(user_id), limit=1)
        created = await self.access_request_service.create_request(
            user_id=int(user_id),
            template_code=template_code,
            request_kind=request_kind,
            comment=comment,
            channel="telegram",
        )
        existing_first_id = before[0].id if before else None
        return self._serialize(created), created.id != existing_first_id

    async def list_requests(self, *, tg_id: int, limit: int = 5) -> list[TelegramAccessRequestSnapshot]:
        user_id = await self.user_repository.get_app_user_id(int(tg_id))
        if user_id is None:
            return []
        rows = await self.access_request_service.list_user_requests(user_id=int(user_id), limit=limit)
        return [self._serialize(row) for row in rows]

    async def has_active_access(self, *, tg_id: int) -> bool:
        user_id = await self.user_repository.get_app_user_id(int(tg_id))
        if user_id is None:
            return False
        rows = await self.access_grant_repository.list_active_user_grants(user_id=int(user_id), limit=1)
        return bool(rows)

    async def is_registry_managed(self, *, tg_id: int) -> bool:
        user_id = await self.user_repository.get_app_user_id(int(tg_id))
        if user_id is None:
            return False
        checker = getattr(self.access_request_service, "is_registry_managed_user", None)
        if checker is None:
            return False
        return bool(await checker(user_id=int(user_id)))

    async def get_active_template_codes_by_scope(self, *, tg_id: int) -> dict[str, str]:
        user_id = await self.user_repository.get_app_user_id(int(tg_id))
        if user_id is None:
            return {}
        rows = await self.access_grant_repository.list_active_user_grants(user_id=int(user_id), limit=20)
        result: dict[str, str] = {}
        for row in rows:
            scope = str(getattr(row, "scope", "") or "").strip().lower()
            template_code = str(getattr(row, "template_code", "") or "").strip().lower()
            if scope and template_code and scope not in result:
                result[scope] = template_code
        return result

    @staticmethod
    def _serialize(row) -> TelegramAccessRequestSnapshot:
        return TelegramAccessRequestSnapshot(
            id=int(row.id),
            user_id=int(row.user_id),
            requested_template_code=getattr(row, "requested_template_code", None),
            status=str(row.status),
            channel=str(row.channel),
            request_kind=str(getattr(row, "request_kind", ACCESS_REQUEST_KIND_NEW_ACCESS)),
            comment=row.comment,
            review_note=row.review_note,
            reviewed_by_actor=getattr(row, "reviewed_by_actor", None),
            requested_at=row.requested_at,
            reviewed_at=row.reviewed_at,
            expires_at=getattr(row, "expires_at", None),
            metadata=dict(getattr(row, "metadata", {}) or {}),
        )
