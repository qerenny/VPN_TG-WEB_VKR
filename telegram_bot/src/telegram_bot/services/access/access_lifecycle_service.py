from __future__ import annotations

import asyncio
from dataclasses import dataclass

from shared.config.settings import get_product_feature_settings
from shared.infrastructure.access.access_grant_repository import AccessGrantRepository
from shared.infrastructure.access.access_registry_repository import AccessRegistryRepository
from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_code
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_TRAFFIC_LIMITED
from shared.utils.logging_utils import logger


@dataclass(frozen=True, slots=True)
class AccessLifecycleRunResult:
    expired_grants: int
    runtime_revocations: int
    registry_issued_grants: int
    registry_revoked_grants: int
    auto_renewed_grants: int


class AccessLifecycleService:
    def __init__(
        self,
        *,
        access_grant_repository: AccessGrantRepository,
        access_registry_repository: AccessRegistryRepository,
        access_issuance_service,
        standard_user_subscription_service,
        traffic_limited_service,
    ) -> None:
        self.access_grant_repository = access_grant_repository
        self.access_registry_repository = access_registry_repository
        self.access_issuance_service = access_issuance_service
        self.standard_user_subscription_service = standard_user_subscription_service
        self.traffic_limited_service = traffic_limited_service
        self._stop_event = asyncio.Event()

    async def run_scheduler(self) -> None:
        logger.info("Access lifecycle scheduler started")
        while not self._stop_event.is_set():
            try:
                result = await self.run_once()
                if result.expired_grants or result.runtime_revocations or result.auto_renewed_grants:
                    logger.info(
                        "Access lifecycle tick: "
                        f"expired={result.expired_grants}, "
                        f"runtime_revocations={result.runtime_revocations}, "
                        f"registry_issued={result.registry_issued_grants}, "
                        f"registry_revoked={result.registry_revoked_grants}, "
                        f"auto_renewed={result.auto_renewed_grants}"
                    )
            except asyncio.CancelledError:
                raise
            except Exception as err:
                logger.error(
                    "Access lifecycle scheduler error: "
                    f"{type(err).__name__}: {err}"
                )

            interval_seconds = max(
                30,
                int(getattr(get_product_feature_settings(), "access_lifecycle_scan_interval_seconds", 300)),
            )
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                continue

    async def shutdown(self) -> None:
        self._stop_event.set()

    async def run_once(self) -> AccessLifecycleRunResult:
        expired_rows = await self.access_grant_repository.reconcile_expired_grants()
        runtime_revocations = await self._reconcile_runtime_for_expired(expired_rows)
        registry_issued = await self._ensure_registry_managed_access()
        registry_revoked = await self._reconcile_registry_managed_grants()
        auto_renewed = await self._auto_renew_expiring_grants()
        return AccessLifecycleRunResult(
            expired_grants=len(expired_rows),
            runtime_revocations=runtime_revocations,
            registry_issued_grants=registry_issued,
            registry_revoked_grants=registry_revoked,
            auto_renewed_grants=auto_renewed,
        )

    async def _ensure_registry_managed_access(self) -> int:
        features = get_product_feature_settings()
        if not getattr(features, "access_registry_enabled", False):
            return 0

        seed = get_plan_seed_by_code("month_1")
        if seed is None:
            logger.warning("Skip access registry bootstrap: month_1 plan seed is missing")
            return 0

        issued_count = 0
        entries = await self.access_registry_repository.list_active_entries(limit=500)
        for entry in entries:
            if not bool(getattr(entry, "auto_approve", False)):
                continue
            user_ids = await self.access_registry_repository.resolve_user_ids_for_entry(entry=entry)
            for user_id in user_ids:
                has_active_standard = await self.access_grant_repository.has_active_scope_grant(
                    user_id=int(user_id),
                    scope=PRODUCT_SCOPE_STANDARD,
                )
                if has_active_standard:
                    continue
                await self.access_issuance_service.activate_from_payload(
                    payload=str(seed.payload),
                    source_type="access_registry",
                    source_ref=None,
                    user_id=int(user_id),
                    channel_override="system",
                    extra_metadata={
                        "access_registry_entry_id": int(entry.id),
                        "registry_bootstrap": True,
                    },
                )
                issued_count += 1
        return issued_count

    async def _reconcile_registry_managed_grants(self) -> int:
        features = get_product_feature_settings()
        if not getattr(features, "access_registry_enabled", False):
            return 0

        rows = await self.access_grant_repository.list_active_grants_by_source_types(
            source_types=["access_registry", "access_registry_auto_renew"],
            limit=500,
        )
        processed_pairs: set[tuple[int, str]] = set()
        revoked_count = 0
        for row in rows:
            key = (int(row.user_id), str(row.scope))
            if key in processed_pairs:
                continue
            processed_pairs.add(key)
            match = await self.access_registry_repository.find_matching_entry_for_user(user_id=int(row.user_id))
            if match is not None:
                continue
            revoked = await self.access_grant_repository.revoke_scope_grants_by_source_types(
                user_id=int(row.user_id),
                scope=str(row.scope),
                source_types=["access_registry", "access_registry_auto_renew"],
                actor="system:access_registry",
                reason="Registry entry missing or inactive",
            )
            if not revoked:
                continue
            revoked_count += len(revoked)
            has_replacement = await self.access_grant_repository.has_active_scope_grant(
                user_id=int(row.user_id),
                scope=str(row.scope),
            )
            if not has_replacement:
                await self._revoke_runtime_access(user_id=int(row.user_id), scope=str(row.scope))
        return revoked_count

    async def _reconcile_runtime_for_expired(self, rows) -> int:
        processed_pairs: set[tuple[int, str]] = set()
        revocations = 0
        for row in rows:
            if row.id is None:
                continue
            key = (int(row.user_id), str(row.scope))
            if key in processed_pairs:
                continue
            processed_pairs.add(key)
            has_replacement = await self.access_grant_repository.has_active_scope_grant(
                user_id=int(row.user_id),
                scope=str(row.scope),
            )
            if has_replacement:
                continue
            revoked = await self._revoke_runtime_access(
                user_id=int(row.user_id),
                scope=str(row.scope),
            )
            if revoked:
                revocations += 1
        return revocations

    async def _auto_renew_expiring_grants(self) -> int:
        features = get_product_feature_settings()
        if not getattr(features, "access_registry_enabled", False):
            return 0

        window_hours = max(1, int(getattr(features, "access_auto_renew_window_hours", 24)))
        rows = await self.access_grant_repository.list_expiring_active_grants(within_hours=window_hours)
        renewed_count = 0
        for row in rows:
            if row.id is None:
                continue
            source_ref = f"access_auto_renew:{int(row.id)}"
            existing = await self.access_grant_repository.get_by_source(
                source_type="access_registry_auto_renew",
                source_ref=source_ref,
            )
            if existing is not None:
                continue
            registry_match = await self.access_registry_repository.find_auto_approve_match(
                user_id=int(row.user_id),
                requested_template_code=str(row.template_code),
                request_kind="renewal",
            )
            if registry_match is None:
                continue
            payload = self._resolve_payload(row)
            if payload is None:
                logger.warning(
                    f"Skip access auto-renew for grant_id={row.id}: cannot resolve payload "
                    f"for template={row.template_code!r}"
                )
                continue
            await self.access_issuance_service.activate_from_payload(
                payload=payload,
                source_type="access_registry_auto_renew",
                source_ref=source_ref,
                user_id=int(row.user_id),
                channel_override="system",
                extra_metadata={
                    "auto_renew": True,
                    "renewed_from_grant_id": int(row.id),
                    "access_registry_entry_id": int(registry_match.id),
                },
            )
            renewed_count += 1
        return renewed_count

    async def _revoke_runtime_access(self, *, user_id: int, scope: str) -> bool:
        normalized_scope = str(scope or "").strip().lower()
        if normalized_scope == PRODUCT_SCOPE_STANDARD:
            return bool(
                await self.standard_user_subscription_service.revoke_access(user_id=int(user_id))
            )
        if normalized_scope == PRODUCT_SCOPE_TRAFFIC_LIMITED:
            return bool(
                await self.traffic_limited_service.revoke_access_for_user(user_id=int(user_id))
            )
        return False

    @staticmethod
    def _resolve_payload(row) -> str | None:
        metadata = dict(getattr(row, "metadata_json", {}) or {})
        payload = str(metadata.get("plan_payload") or "").strip().lower()
        if payload:
            return payload
        seed = get_plan_seed_by_code(str(getattr(row, "template_code", "")).strip().lower())
        return seed.payload if seed is not None else None
