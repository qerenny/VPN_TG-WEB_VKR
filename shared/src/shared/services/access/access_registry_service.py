from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import re
from typing import Any

from fastapi import HTTPException

from shared.config.settings import get_effective_product_feature_settings
from shared.infrastructure.access.access_registry_repository import (
    ACCESS_REGISTRY_DEFAULT_TEMPLATE_CODE,
    AccessRegistryRepository,
)
from shared.infrastructure.access.access_grant_repository import AccessGrantRepository
from shared.models.access.access_registry_entry_model import AccessRegistryEntry
from shared.product_constants import PRODUCT_SCOPE_STANDARD
from shared.services.access.service_utils import (
    format_template_label_or_none,
    resolve_actor,
)


@dataclass(frozen=True, slots=True)
class AccessRegistryEntrySnapshot:
    id: int
    identity_type: str
    identity_value: str
    template_code: str
    template_label: str
    priority: int
    auto_approve: bool
    allow_auto_renew: bool
    is_active: bool
    note: str | None
    created_by_actor: str | None
    updated_by_actor: str | None
    created_at: str
    updated_at: str
    valid_from: str | None
    valid_until: str | None
    matched_users_count: int
    issued_users_count: int
    access_issued: bool
    issuance_status_label: str
    metadata: dict[str, Any]


class AccessRegistryService:
    BATCH_SPLIT_PATTERN = re.compile(r"[\s,;|]+")

    def __init__(
        self,
        *,
        access_registry_repository: AccessRegistryRepository,
        access_grant_repository: AccessGrantRepository | None = None,
    ) -> None:
        self.access_registry_repository = access_registry_repository
        self.access_grant_repository = access_grant_repository

    async def upsert_entry(
        self,
        *,
        identity_type: str,
        identity_value: str,
        template_code: str,
        priority: int,
        auto_approve: bool,
        allow_auto_renew: bool,
        is_active: bool,
        note: str | None,
        valid_from: str | None,
        valid_until: str | None,
        principal: Any,
    ) -> AccessRegistryEntrySnapshot:
        self._ensure_registry_enabled()
        try:
            row = await self.access_registry_repository.upsert_entry(
                **self._build_entry_write_payload(
                    identity_type=identity_type,
                    identity_value=identity_value,
                    priority=priority,
                    auto_approve=auto_approve,
                    allow_auto_renew=allow_auto_renew,
                    is_active=is_active,
                    note=note,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    principal=principal,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return self._serialize(row)

    async def update_entry(
        self,
        *,
        entry_id: int,
        identity_type: str,
        identity_value: str,
        priority: int,
        auto_approve: bool,
        allow_auto_renew: bool,
        is_active: bool,
        note: str | None,
        valid_from: str | None,
        valid_until: str | None,
        principal: Any,
    ) -> AccessRegistryEntrySnapshot:
        self._ensure_registry_enabled()
        try:
            row = await self.access_registry_repository.update_entry(
                entry_id=int(entry_id),
                **self._build_entry_write_payload(
                    identity_type=identity_type,
                    identity_value=identity_value,
                    priority=priority,
                    auto_approve=auto_approve,
                    allow_auto_renew=allow_auto_renew,
                    is_active=is_active,
                    note=note,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    principal=principal,
                ),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        self._raise_if_missing(row)
        return self._serialize(row)

    async def batch_upsert_entries(
        self,
        *,
        identities_text: str,
        priority: int,
        auto_approve: bool,
        allow_auto_renew: bool,
        is_active: bool,
        note: str | None,
        valid_from: str | None,
        valid_until: str | None,
        principal: Any,
    ) -> list[AccessRegistryEntrySnapshot]:
        self._ensure_registry_enabled()
        tokens = [token for token in self.BATCH_SPLIT_PATTERN.split(str(identities_text or "").strip()) if token]
        if not tokens:
            raise HTTPException(status_code=400, detail="No identities provided")
        invalid_tokens: list[str] = []
        rows: list[AccessRegistryEntrySnapshot] = []
        for token in tokens:
            try:
                identity_type = self._detect_identity_type(token)
            except ValueError:
                invalid_tokens.append(token)
                continue
            rows.append(
                await self.upsert_entry(
                    identity_type=identity_type,
                    identity_value=token,
                    template_code=ACCESS_REGISTRY_DEFAULT_TEMPLATE_CODE,
                    priority=priority,
                    auto_approve=auto_approve,
                    allow_auto_renew=allow_auto_renew,
                    is_active=is_active,
                    note=note,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    principal=principal,
                )
            )
        if invalid_tokens:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported identities: {', '.join(invalid_tokens[:20])}",
            )
        return rows

    async def list_entries(self, *, limit: int = 200) -> list[AccessRegistryEntrySnapshot]:
        self._ensure_registry_enabled()
        rows = await self.access_registry_repository.list_entries(limit=limit)
        return [await self._serialize_with_runtime_status(row) for row in rows]

    async def set_entry_active(
        self,
        *,
        entry_id: int,
        is_active: bool,
        principal: Any,
    ) -> AccessRegistryEntrySnapshot:
        self._ensure_registry_enabled()
        row = await self.access_registry_repository.set_active(
            entry_id=entry_id,
            is_active=is_active,
            actor=resolve_actor(principal),
        )
        self._raise_if_missing(row)
        return await self._serialize_with_runtime_status(row)

    async def delete_entry(
        self,
        *,
        entry_id: int,
    ) -> None:
        self._ensure_registry_enabled()
        target = await self._get_entry_or_404(entry_id=entry_id)
        if bool(getattr(target, "is_active", False)):
            raise HTTPException(
                status_code=409,
                detail="Deactivate the registry entry before deleting it",
            )
        deleted = await self.access_registry_repository.delete_entry(entry_id=int(entry_id))
        if not deleted:
            raise HTTPException(status_code=404, detail="Access registry entry not found")

    async def find_auto_approve_match(
        self,
        *,
        user_id: int,
        requested_template_code: str | None = None,
        request_kind: str | None = None,
    ) -> AccessRegistryEntrySnapshot | None:
        if not get_effective_product_feature_settings().access_registry_enabled:
            return None
        row = await self.access_registry_repository.find_auto_approve_match(
            user_id=user_id,
            requested_template_code=requested_template_code,
            request_kind=request_kind,
        )
        return self._serialize(row) if row is not None else None

    async def find_managed_entry(self, *, user_id: int) -> AccessRegistryEntrySnapshot | None:
        if not get_effective_product_feature_settings().access_registry_enabled:
            return None
        row = await self.access_registry_repository.find_matching_entry_for_user(user_id=int(user_id))
        return self._serialize(row) if row is not None else None

    async def _serialize_with_runtime_status(self, row: AccessRegistryEntry) -> AccessRegistryEntrySnapshot:
        matched_users_count, issued_users_count = await self._compute_runtime_status_counts(row)
        issuance_status_label = self._issuance_status_label(
            matched_users_count=matched_users_count,
            issued_users_count=issued_users_count,
        )
        base = self._serialize(row)
        return AccessRegistryEntrySnapshot(
            **{**asdict(base),
               "matched_users_count": matched_users_count,
               "issued_users_count": issued_users_count,
               "access_issued": issued_users_count > 0,
               "issuance_status_label": issuance_status_label}
        )

    @staticmethod
    def _build_entry_write_payload(
        *,
        identity_type: str,
        identity_value: str,
        priority: int,
        auto_approve: bool,
        allow_auto_renew: bool,
        is_active: bool,
        note: str | None,
        valid_from: str | None,
        valid_until: str | None,
        principal: Any,
    ) -> dict[str, Any]:
        return {
            "identity_type": identity_type,
            "identity_value": identity_value,
            "template_code": ACCESS_REGISTRY_DEFAULT_TEMPLATE_CODE,
            "priority": int(priority),
            "auto_approve": auto_approve,
            "allow_auto_renew": allow_auto_renew,
            "is_active": is_active,
            "note": note,
            "valid_from": AccessRegistryService._parse_optional_datetime(valid_from, field_name="valid_from"),
            "valid_until": AccessRegistryService._parse_optional_datetime(valid_until, field_name="valid_until"),
            "actor": resolve_actor(principal),
        }

    async def _compute_runtime_status_counts(self, row: AccessRegistryEntry) -> tuple[int, int]:
        if self.access_grant_repository is None:
            return 0, 0

        user_ids = await self.access_registry_repository.resolve_user_ids_for_entry(entry=row)
        matched_users_count = len(user_ids)
        issued_users_count = 0
        for user_id in user_ids:
            issued = await self.access_grant_repository.has_active_scope_grant(
                user_id=int(user_id),
                scope=PRODUCT_SCOPE_STANDARD,
            )
            issued_users_count += int(bool(issued))
        return matched_users_count, issued_users_count

    async def _get_entry_or_404(self, *, entry_id: int) -> AccessRegistryEntry:
        rows = await self.access_registry_repository.list_entries(limit=500)
        target = next((row for row in rows if int(row.id) == int(entry_id)), None)
        self._raise_if_missing(target)
        return target

    @staticmethod
    def _raise_if_missing(row: AccessRegistryEntry | None) -> None:
        if row is None:
            raise HTTPException(status_code=404, detail="Access registry entry not found")

    @staticmethod
    def _serialize(row: AccessRegistryEntry) -> AccessRegistryEntrySnapshot:
        return AccessRegistryEntrySnapshot(
            id=int(row.id),
            identity_type=str(row.identity_type),
            identity_value=str(row.identity_value),
            template_code=str(row.template_code),
            template_label=format_template_label_or_none(str(row.template_code)) or "Не указан",
            priority=int(row.priority),
            auto_approve=bool(row.auto_approve),
            allow_auto_renew=bool(getattr(row, "allow_auto_renew", False)),
            is_active=bool(row.is_active),
            note=row.note,
            created_by_actor=row.created_by_actor,
            updated_by_actor=row.updated_by_actor,
            created_at=row.created_at.isoformat(),
            updated_at=row.updated_at.isoformat(),
            valid_from=row.valid_from.isoformat() if getattr(row, "valid_from", None) is not None else None,
            valid_until=row.valid_until.isoformat() if getattr(row, "valid_until", None) is not None else None,
            matched_users_count=0,
            issued_users_count=0,
            access_issued=False,
            issuance_status_label="Статус не рассчитан",
            metadata=dict(row.metadata_json or {}),
        )

    @staticmethod
    def _issuance_status_label(*, matched_users_count: int, issued_users_count: int) -> str:
        if matched_users_count <= 0:
            return "Пользователь не найден"
        if issued_users_count <= 0:
            return "Доступ пока не выдан"
        if issued_users_count >= matched_users_count:
            return "Доступ выдан"
        return f"Выдан частично ({issued_users_count}/{matched_users_count})"

    @staticmethod
    def _ensure_registry_enabled() -> None:
        if not get_effective_product_feature_settings().access_registry_enabled:
            raise HTTPException(status_code=404, detail="Access registry module is disabled")

    @staticmethod
    def _parse_optional_datetime(value: str | None, *, field_name: str) -> datetime | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"{field_name} must be a valid ISO datetime",
            ) from exc
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)

    @staticmethod
    def _detect_identity_type(token: str) -> str:
        normalized = str(token or "").strip()
        if "@" in normalized:
            return "email"
        if normalized.lstrip("-").isdigit():
            return "telegram_id"
        raise ValueError("Unsupported identity")
