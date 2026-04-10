from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import desc, or_
from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.models.access.access_registry_entry_model import AccessRegistryEntry
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount

ALLOWED_REGISTRY_IDENTITY_TYPES = {"telegram_id", "email"}
ACCESS_REGISTRY_DEFAULT_TEMPLATE_CODE = "month_1"


class AccessRegistryRepository:
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
        actor: str,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        metadata: dict | None = None,
    ) -> AccessRegistryEntry:
        normalized_type, normalized_value = self.normalize_identity(identity_type, identity_value)
        normalized_template_code = (
            str(template_code or ACCESS_REGISTRY_DEFAULT_TEMPLATE_CODE).strip().lower()
            or ACCESS_REGISTRY_DEFAULT_TEMPLATE_CODE
        )
        if not normalized_template_code:
            raise ValueError("template_code is required")
        normalized_priority = int(priority)

        async with get_db_session() as session:
            row = (
                await session.execute(
                    select(AccessRegistryEntry).where(
                        AccessRegistryEntry.identity_type == normalized_type,
                        AccessRegistryEntry.identity_value == normalized_value,
                    )
                )
            ).scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if row is None:
                row = AccessRegistryEntry(
                    identity_type=normalized_type,
                    identity_value=normalized_value,
                    template_code=normalized_template_code,
                    priority=normalized_priority,
                    auto_approve=bool(auto_approve),
                    allow_auto_renew=bool(allow_auto_renew),
                    is_active=bool(is_active),
                    note=(str(note).strip() or None) if note is not None else None,
                    created_by_actor=str(actor or "").strip() or None,
                    updated_by_actor=str(actor or "").strip() or None,
                    created_at=now,
                    updated_at=now,
                    valid_from=valid_from,
                    valid_until=valid_until,
                    metadata_json=dict(metadata or {}),
                )
            else:
                row.template_code = normalized_template_code
                row.priority = normalized_priority
                row.auto_approve = bool(auto_approve)
                row.allow_auto_renew = bool(allow_auto_renew)
                row.is_active = bool(is_active)
                row.note = (str(note).strip() or None) if note is not None else None
                row.updated_by_actor = str(actor or "").strip() or None
                row.updated_at = now
                row.valid_from = valid_from
                row.valid_until = valid_until
                row.metadata_json = {**dict(row.metadata_json or {}), **dict(metadata or {})}
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def list_entries(self, *, limit: int = 200) -> list[AccessRegistryEntry]:
        async with get_db_session() as session:
            rows = await session.execute(
                select(AccessRegistryEntry)
                .order_by(
                    desc(AccessRegistryEntry.priority),
                    desc(AccessRegistryEntry.updated_at),
                    desc(AccessRegistryEntry.id),
                )
                .limit(max(1, min(int(limit), 500)))
            )
            return list(rows.scalars().all())

    async def list_active_entries(self, *, limit: int = 500) -> list[AccessRegistryEntry]:
        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            rows = await session.execute(
                select(AccessRegistryEntry)
                .where(
                    AccessRegistryEntry.is_active.is_(True),
                    or_(AccessRegistryEntry.valid_from.is_(None), AccessRegistryEntry.valid_from <= now),
                    or_(AccessRegistryEntry.valid_until.is_(None), AccessRegistryEntry.valid_until >= now),
                )
                .order_by(
                    desc(AccessRegistryEntry.priority),
                    desc(AccessRegistryEntry.updated_at),
                    desc(AccessRegistryEntry.id),
                )
                .limit(max(1, min(int(limit), 1000)))
            )
            return list(rows.scalars().all())

    async def set_active(self, *, entry_id: int, is_active: bool, actor: str) -> AccessRegistryEntry | None:
        async with get_db_session() as session:
            row = await session.get(AccessRegistryEntry, int(entry_id))
            if row is None:
                return None
            row.is_active = bool(is_active)
            row.updated_by_actor = str(actor or "").strip() or None
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

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
        actor: str,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        metadata: dict | None = None,
    ) -> AccessRegistryEntry | None:
        normalized_type, normalized_value = self.normalize_identity(identity_type, identity_value)
        async with get_db_session() as session:
            row = await session.get(AccessRegistryEntry, int(entry_id))
            if row is None:
                return None
            duplicate = (
                await session.execute(
                    select(AccessRegistryEntry).where(
                        AccessRegistryEntry.id != int(entry_id),
                        AccessRegistryEntry.identity_type == normalized_type,
                        AccessRegistryEntry.identity_value == normalized_value,
                    )
                )
            ).scalar_one_or_none()
            if duplicate is not None:
                raise ValueError("Access registry entry with this identity already exists")
            row.identity_type = normalized_type
            row.identity_value = normalized_value
            row.template_code = ACCESS_REGISTRY_DEFAULT_TEMPLATE_CODE
            row.priority = int(priority)
            row.auto_approve = bool(auto_approve)
            row.allow_auto_renew = bool(allow_auto_renew)
            row.is_active = bool(is_active)
            row.note = (str(note).strip() or None) if note is not None else None
            row.valid_from = valid_from
            row.valid_until = valid_until
            row.updated_by_actor = str(actor or "").strip() or None
            row.updated_at = datetime.now(timezone.utc)
            if metadata:
                row.metadata_json = {**dict(row.metadata_json or {}), **dict(metadata)}
            session.add(row)
            await session.commit()
            await session.refresh(row)
            return row

    async def delete_entry(self, *, entry_id: int) -> bool:
        async with get_db_session() as session:
            row = await session.get(AccessRegistryEntry, int(entry_id))
            if row is None:
                return False
            await session.delete(row)
            await session.commit()
            return True

    async def find_auto_approve_match(
        self,
        *,
        user_id: int,
        requested_template_code: str | None = None,
        request_kind: str | None = None,
    ) -> AccessRegistryEntry | None:
        return await self.find_matching_entry_for_user(
            user_id=int(user_id),
            require_auto_approve=True,
            require_auto_renew=str(request_kind or "").strip().lower() == "renewal",
        )

    async def find_matching_entry_for_user(
        self,
        *,
        user_id: int,
        require_auto_approve: bool = False,
        require_auto_renew: bool = False,
    ) -> AccessRegistryEntry | None:
        async with get_db_session() as session:
            candidates = await self._load_user_identities(session, int(user_id))
            if not candidates:
                return None
            now = datetime.now(timezone.utc)
            rows: list[AccessRegistryEntry] = []
            for identity_type, identity_value in candidates:
                stmt = (
                    select(AccessRegistryEntry)
                    .where(
                        AccessRegistryEntry.identity_type == identity_type,
                        AccessRegistryEntry.identity_value == identity_value,
                        AccessRegistryEntry.is_active.is_(True),
                        or_(AccessRegistryEntry.valid_from.is_(None), AccessRegistryEntry.valid_from <= now),
                        or_(AccessRegistryEntry.valid_until.is_(None), AccessRegistryEntry.valid_until >= now),
                    )
                    .order_by(
                        desc(AccessRegistryEntry.priority),
                        desc(AccessRegistryEntry.updated_at),
                        desc(AccessRegistryEntry.id),
                    )
                )
                if require_auto_approve:
                    stmt = stmt.where(AccessRegistryEntry.auto_approve.is_(True))
                if require_auto_renew:
                    stmt = stmt.where(AccessRegistryEntry.allow_auto_renew.is_(True))
                rows.extend(list((await session.execute(stmt)).scalars().all()))
            if rows:
                rows.sort(key=lambda row: (int(row.priority or 0), row.updated_at, int(row.id or 0)), reverse=True)
                return rows[0]
        return None

    async def resolve_user_ids_for_entry(self, *, entry: AccessRegistryEntry) -> list[int]:
        return await self.resolve_user_ids_for_identity(
            identity_type=str(entry.identity_type),
            identity_value=str(entry.identity_value),
        )

    async def resolve_user_ids_for_identity(
        self,
        *,
        identity_type: str,
        identity_value: str,
    ) -> list[int]:
        normalized_type, normalized_value = self.normalize_identity(identity_type, identity_value)
        async with get_db_session() as session:
            if normalized_type == "telegram_id":
                rows = await session.execute(
                    select(TelegramAccount.user_id).where(
                        TelegramAccount.telegram_id == int(normalized_value),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
                return sorted({int(row[0]) for row in rows.all()})

            if normalized_type == "email":
                normalized_email = self._normalize_optional_email(normalized_value) or ""
                web_rows = await session.execute(
                    select(WebAccount.user_id).where(
                        WebAccount.email == normalized_email,
                        WebAccount.revoked_at.is_(None),
                    )
                )
                profile_rows = await session.execute(
                    select(UserProfile.user_id).where(
                        UserProfile.preferred_contact_email == normalized_email,
                    )
                )
                return sorted(
                    {
                        *[int(row[0]) for row in web_rows.all()],
                        *[int(row[0]) for row in profile_rows.all()],
                    }
                )
        return []

    @staticmethod
    async def _load_user_identities(session, user_id: int) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []

        telegram = (
            await session.execute(
                select(TelegramAccount.telegram_id).where(
                    TelegramAccount.user_id == int(user_id),
                    TelegramAccount.revoked_at.is_(None),
                )
            )
        ).first()
        if telegram is not None:
            telegram_id = telegram[0]
            candidates.append(("telegram_id", str(int(telegram_id))))

        web_email = (
            await session.execute(
                select(WebAccount.email).where(
                    WebAccount.user_id == int(user_id),
                    WebAccount.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        normalized_web_email = AccessRegistryRepository._normalize_optional_email(web_email)
        if normalized_web_email:
            candidates.append(("email", normalized_web_email))

        preferred_email = (
            await session.execute(
                select(UserProfile.preferred_contact_email).where(UserProfile.user_id == int(user_id))
            )
        ).scalar_one_or_none()
        normalized_preferred_email = AccessRegistryRepository._normalize_optional_email(preferred_email)
        if normalized_preferred_email and ("email", normalized_preferred_email) not in candidates:
            candidates.append(("email", normalized_preferred_email))

        return candidates

    @staticmethod
    def normalize_identity(identity_type: str, identity_value: str) -> tuple[str, str]:
        normalized_type = str(identity_type or "").strip().lower()
        if normalized_type not in ALLOWED_REGISTRY_IDENTITY_TYPES:
            raise ValueError(f"Unsupported access registry identity type: {identity_type}")
        normalized_value = str(identity_value or "").strip()
        if normalized_type == "telegram_id":
            if not normalized_value.lstrip("-").isdigit():
                raise ValueError("telegram_id must be numeric")
            return normalized_type, str(int(normalized_value))
        if normalized_type == "email":
            normalized_value = AccessRegistryRepository._normalize_optional_email(normalized_value) or ""
        if not normalized_value:
            raise ValueError("identity_value is required")
        return normalized_type, normalized_value

    @staticmethod
    def _normalize_optional_email(value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        return normalized or None
