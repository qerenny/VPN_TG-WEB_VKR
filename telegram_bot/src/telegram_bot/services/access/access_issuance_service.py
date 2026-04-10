from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.infrastructure.payment_plan_catalog import get_plan_seed_by_payload
from shared.models.users.telegram_account_model import TelegramAccount
from shared.product_constants import (
    ENTITLEMENT_KIND_TIME,
    ENTITLEMENT_KIND_TRAFFIC,
    PRODUCT_SCOPE_STANDARD,
    PRODUCT_SCOPE_TRAFFIC_LIMITED,
)


@dataclass(frozen=True, slots=True)
class AccessIssuanceResult:
    activation_text: str
    activation_details_text: str


class AccessIssuanceService:
    def __init__(
        self,
        *,
        access_grant_repository,
        subscription_flow_service,
        traffic_limited_service,
        standard_user_subscription_service,
    ) -> None:
        self.access_grant_repository = access_grant_repository
        self.subscription_flow_service = subscription_flow_service
        self.traffic_limited_service = traffic_limited_service
        self.standard_user_subscription_service = standard_user_subscription_service

    async def activate_from_payload(
        self,
        *,
        payload: str,
        source_type: str,
        source_ref: str | None = None,
        tg_id: int | None = None,
        user_id: int | None = None,
        channel_override: str | None = None,
        extra_metadata: dict | None = None,
        duration_days_override: int | None = None,
        quota_bytes_override: int | None = None,
        replace_existing: bool = False,
    ) -> AccessIssuanceResult:
        seed = get_plan_seed_by_payload(payload)
        if seed is None:
            raise ValueError(f"Unsupported access payload: {payload!r}")
        normalized_source_type = str(source_type)
        normalized_source_ref = str(source_ref).strip() if source_ref is not None else None
        if normalized_source_ref:
            existing_grant = await self.access_grant_repository.get_by_source(
                source_type=normalized_source_type,
                source_ref=normalized_source_ref,
            )
            if existing_grant is not None:
                return self._build_existing_grant_result(seed=seed)

        if (
            seed.scope == PRODUCT_SCOPE_TRAFFIC_LIMITED
            and seed.entitlement_kind == ENTITLEMENT_KIND_TRAFFIC
        ):
            return await self._activate_traffic_limited(
                seed=seed,
                payload=str(payload),
                source_type=normalized_source_type,
                source_ref=normalized_source_ref or str(payload),
                tg_id=tg_id,
                user_id=user_id,
                channel_override=channel_override,
                extra_metadata=extra_metadata,
                duration_days_override=duration_days_override,
                quota_bytes_override=quota_bytes_override,
            )

        if (
            seed.scope == PRODUCT_SCOPE_STANDARD
            and seed.entitlement_kind == ENTITLEMENT_KIND_TIME
        ):
            return await self._activate_standard(
                seed=seed,
                payload=str(payload),
                duration_days=int(seed.duration_days),
                source_type=normalized_source_type,
                source_ref=normalized_source_ref,
                tg_id=tg_id,
                user_id=user_id,
                channel_override=channel_override,
                extra_metadata=extra_metadata,
                duration_days_override=duration_days_override,
                replace_existing=replace_existing,
            )

        raise ValueError(
            f"Unsupported access template: scope={seed.scope!r}, "
            f"entitlement_kind={seed.entitlement_kind!r}, payload={payload!r}"
        )

    async def _activate_standard(
        self,
        *,
        seed,
        payload: str,
        duration_days: int,
        source_type: str,
        source_ref: str | None,
        tg_id: int | None,
        user_id: int | None,
        channel_override: str | None,
        extra_metadata: dict | None,
        duration_days_override: int | None,
        replace_existing: bool,
    ) -> AccessIssuanceResult:
        resolved_user_id = await self._resolve_target_user_id(tg_id=tg_id, user_id=user_id)
        if tg_id is not None:
            updated_text, details_text = (
                await self.subscription_flow_service.activate_or_extend_subscription(
                    tg_id=int(tg_id),
                    period=str(payload),
                )
            )
            await self.access_grant_repository.record_grant(
                user_id=int(resolved_user_id),
                template_code=seed.code,
                scope=seed.scope,
                entitlement_kind=seed.entitlement_kind,
                source_type=str(source_type),
                source_ref=source_ref,
                expires_at=None,
                quota_bytes=seed.quota_bytes,
                metadata={
                    "plan_payload": seed.payload,
                    "channel": channel_override or "telegram",
                    **dict(extra_metadata or {}),
                },
            )
            return AccessIssuanceResult(
                activation_text=updated_text,
                activation_details_text=details_text,
            )

        if resolved_user_id is None:
            raise ValueError("user_id is required for standard web access activation")

        if source_type == "payment":
            result = await self.standard_user_subscription_service.activate_payment(
                user_id=int(resolved_user_id),
                product=str(payload),
            )
        else:
            result = await self.standard_user_subscription_service.activate_days(
                user_id=int(resolved_user_id),
                duration_days=int(duration_days_override or duration_days),
                replace_existing=bool(replace_existing),
            )

        await self.access_grant_repository.record_grant(
            user_id=int(result.user_id),
            template_code=seed.code,
            scope=seed.scope,
            entitlement_kind=seed.entitlement_kind,
            source_type=str(source_type),
            source_ref=source_ref,
            expires_at=result.expires_at,
            quota_bytes=seed.quota_bytes,
            metadata={
                "plan_payload": seed.payload,
                "channel": channel_override or "web",
                **dict(extra_metadata or {}),
            },
        )

        expiry_text = result.expires_at.astimezone().strftime("%H:%M:%S %d-%m-%Y")
        status_text = (
            "✅ Базовая конфигурация активирована"
            if result.was_created
            else "✅ Базовая конфигурация продлена"
        )
        return AccessIssuanceResult(
            activation_text=status_text,
            activation_details_text=f"Действует до: {expiry_text}",
        )

    async def _activate_traffic_limited(
        self,
        *,
        seed,
        payload: str,
        source_type: str,
        source_ref: str,
        tg_id: int | None,
        user_id: int | None,
        channel_override: str | None,
        extra_metadata: dict | None,
        duration_days_override: int | None,
        quota_bytes_override: int | None,
    ) -> AccessIssuanceResult:
        if tg_id is not None:
            result = await self.traffic_limited_service.activate_source(
                tg_id=int(tg_id),
                product=str(payload),
                source_type=str(source_type),
                source_ref=str(source_ref),
            )
        else:
            if user_id is None:
                raise ValueError("user_id is required for web traffic-limited access activation")
            result = await self.traffic_limited_service.activate_source_for_user(
                user_id=int(user_id),
                product=str(payload),
                source_type=str(source_type),
                source_ref=str(source_ref),
                duration_days_override=duration_days_override,
                quota_bytes_override=quota_bytes_override,
            )

        await self.access_grant_repository.record_grant(
            user_id=int(result.user_id),
            template_code=seed.code,
            scope=seed.scope,
            entitlement_kind=seed.entitlement_kind,
            source_type=str(source_type),
            source_ref=str(source_ref),
            expires_at=result.expires_at,
            quota_bytes=result.granted_bytes,
            metadata={
                "plan_payload": seed.payload,
                "channel": channel_override or ("telegram" if tg_id is not None else "web"),
                **dict(extra_metadata or {}),
            },
        )

        granted_gb = result.granted_bytes // (1024 * 1024 * 1024)
        remaining_gb = result.remaining_bytes // (1024 * 1024 * 1024)
        expiry_text = (
            result.expires_at.astimezone().strftime("%H:%M:%S %d-%m-%Y")
            if result.expires_at is not None
            else "без ограничения по сроку"
        )
        return AccessIssuanceResult(
            activation_text=f"✅ Конфигурация с лимитом трафика активирована: +{granted_gb} GB",
            activation_details_text=f"Остаток: {remaining_gb} GB\nДействует до: {expiry_text}",
        )

    @staticmethod
    def _build_existing_grant_result(*, seed) -> AccessIssuanceResult:
        if seed.scope == PRODUCT_SCOPE_TRAFFIC_LIMITED:
            return AccessIssuanceResult(
                activation_text="✅ Конфигурация с лимитом трафика уже активирована",
                activation_details_text="Повторное применение не потребовалось.",
            )
        return AccessIssuanceResult(
            activation_text="✅ Базовая конфигурация уже активирована",
            activation_details_text="Повторное применение не потребовалось.",
        )

    @staticmethod
    async def _resolve_target_user_id(*, tg_id: int | None, user_id: int | None) -> int | None:
        if user_id is not None:
            return int(user_id)
        if tg_id is None:
            return None
        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount.user_id).where(
                        TelegramAccount.telegram_id == int(tg_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        if telegram_account is None:
            raise ValueError(f"Telegram account not found for tg_id={tg_id}")
        return int(telegram_account)
