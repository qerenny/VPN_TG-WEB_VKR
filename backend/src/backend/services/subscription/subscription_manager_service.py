from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from jwt import PyJWTError
from sqlmodel import select

from shared.config.config import (
    BACKEND_TELEGRAM_SUBSCRIPTION_LINK,
    BACKEND_TELEGRAM_WHITELIST_SUBSCRIPTION_LINK,
    BOT_SUPPORT_TG_LINK,
)
from shared.config.database.session import get_db_session
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.models.traffic.traffic_state_model import TrafficState
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_WHITELIST
from shared.utils.jwt_encoder import JWTEncoder
from shared.utils.timestamp_utils import TimestampUtils


@dataclass(frozen=True, slots=True)
class WhiteListSubscriptionSnapshot:
    external_email: str
    subscription_external_id: str
    expires_at_ms: int | None
    allocated_bytes: int
    used_bytes: int
    remaining_bytes: int
    is_blocked: bool


class SubscriptionManagerService:
    def __init__(
        self,
        repo: TelegramUserRepository,
        jwt_encoder: JWTEncoder,
        timestamp: TimestampUtils,
    ):
        self.jwt_encoder = jwt_encoder
        self.repo = repo
        self.timestamp = timestamp

    async def get_subscription_formatted_info(
        self,
        token: str,
        *,
        scope: str = PRODUCT_SCOPE_STANDARD,
    ) -> dict:
        try:
            data = self.jwt_encoder.decode(token)
            resolved_scope = self._resolve_scope(data, requested_scope=scope)
            tg_id = int(data.get("tg_id"))
            email = data.get("email")

            if not tg_id or not email:
                raise ValueError("Missing required fields")

            if resolved_scope == PRODUCT_SCOPE_STANDARD:
                return await self._get_standard_subscription_formatted_info(
                    tg_id=tg_id,
                    email=str(email),
                )
            if resolved_scope == PRODUCT_SCOPE_WHITELIST:
                return await self._get_whitelist_subscription_formatted_info(
                    tg_id=tg_id,
                    email=str(email),
                )

            raise HTTPException(status_code=400, detail="Unsupported subscription scope")

        except PyJWTError:
            raise HTTPException(status_code=400, detail="Invalid token signature or expired")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid token format")

    async def _get_standard_subscription_formatted_info(
        self,
        *,
        tg_id: int,
        email: str,
    ) -> dict:
        user = await self.repo.get(tg_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user.email != email:
            raise HTTPException(status_code=404, detail="Email mismatch")

        return {
            "scope": PRODUCT_SCOPE_STANDARD,
            "human_view_expiration_remaining": await self._human_view_expiration_remaining(
                user.expiration_date
            ),
            "human_view_expiration_date": await self._human_view_expiration_date(
                user.expiration_date
            ),
            "sub_link": await self._create_sub_link(
                user.sub_id,
                scope=PRODUCT_SCOPE_STANDARD,
            ),
            "sub_is_active": await self._sub_is_active(user.expiration_date),
            "support_link": BOT_SUPPORT_TG_LINK,
            "traffic_allocated_bytes": None,
            "traffic_used_bytes": None,
            "traffic_remaining_bytes": None,
            "human_view_traffic_allocated": None,
            "human_view_traffic_used": None,
            "human_view_traffic_remaining": None,
        }

    async def _get_whitelist_subscription_formatted_info(
        self,
        *,
        tg_id: int,
        email: str,
    ) -> dict:
        snapshot = await self._get_whitelist_snapshot(tg_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="WhiteList subscription not found")

        if snapshot.external_email != email:
            raise HTTPException(status_code=404, detail="Email mismatch")

        return {
            "scope": PRODUCT_SCOPE_WHITELIST,
            "human_view_expiration_remaining": await self._human_view_expiration_remaining(
                snapshot.expires_at_ms
            ),
            "human_view_expiration_date": await self._human_view_expiration_date(
                snapshot.expires_at_ms
            ),
            "sub_link": await self._create_sub_link(
                snapshot.subscription_external_id,
                scope=PRODUCT_SCOPE_WHITELIST,
            ),
            "sub_is_active": self._whitelist_sub_is_active(snapshot),
            "support_link": BOT_SUPPORT_TG_LINK,
            "traffic_allocated_bytes": snapshot.allocated_bytes,
            "traffic_used_bytes": snapshot.used_bytes,
            "traffic_remaining_bytes": snapshot.remaining_bytes,
            "human_view_traffic_allocated": self._human_view_traffic_bytes(snapshot.allocated_bytes),
            "human_view_traffic_used": self._human_view_traffic_bytes(snapshot.used_bytes),
            "human_view_traffic_remaining": self._human_view_traffic_bytes(snapshot.remaining_bytes),
        }

    async def _get_whitelist_snapshot(
        self,
        tg_id: int,
    ) -> WhiteListSubscriptionSnapshot | None:
        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.telegram_id == int(tg_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if telegram_account is None:
                return None

            vpn_client = (
                await session.execute(
                    select(VpnClient).where(
                        VpnClient.user_id == int(telegram_account.user_id),
                        VpnClient.scope == PRODUCT_SCOPE_WHITELIST,
                        VpnClient.deactivated_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if vpn_client is None:
                return None

            state = await session.get(TrafficState, int(vpn_client.id))

        return WhiteListSubscriptionSnapshot(
            external_email=str(vpn_client.external_email),
            subscription_external_id=str(vpn_client.subscription_external_id),
            expires_at_ms=self._datetime_to_legacy_ms(getattr(state, "expires_at", None)),
            allocated_bytes=int(getattr(state, "allocated_bytes", 0) or 0),
            used_bytes=int(getattr(state, "used_bytes", 0) or 0),
            remaining_bytes=int(getattr(state, "remaining_bytes", 0) or 0),
            is_blocked=bool(getattr(state, "is_blocked", False)),
        )

    def _resolve_scope(self, token_data: dict, *, requested_scope: str) -> str:
        token_scope = str(token_data.get("scope") or PRODUCT_SCOPE_STANDARD)
        scope = str(requested_scope or token_scope or PRODUCT_SCOPE_STANDARD)
        if token_scope != scope:
            raise HTTPException(status_code=404, detail="Token scope mismatch")
        return scope

    async def _create_app_link(self, sub_id: int) -> str:
        return f"v2raytun://import/{BACKEND_TELEGRAM_SUBSCRIPTION_LINK}?uuid={sub_id}"

    async def _create_sub_link(self, sub_id: str, *, scope: str) -> str:
        base_url = BACKEND_TELEGRAM_SUBSCRIPTION_LINK
        if scope == PRODUCT_SCOPE_WHITELIST:
            base_url = BACKEND_TELEGRAM_WHITELIST_SUBSCRIPTION_LINK
        return f"{base_url}?uuid={sub_id}"

    async def _sub_is_active(self, expiration_date: int | None) -> bool | None:
        if not expiration_date:
            return None
        return int(expiration_date) > self.timestamp.current_timestamp()

    def _whitelist_sub_is_active(self, snapshot: WhiteListSubscriptionSnapshot) -> bool:
        if snapshot.is_blocked or snapshot.remaining_bytes <= 0:
            return False
        if not snapshot.expires_at_ms:
            return True
        return int(snapshot.expires_at_ms) > self.timestamp.current_timestamp()

    async def _human_view_expiration_remaining(self, expiration_date: int | None) -> str | None:
        if not expiration_date:
            return None
        return self.timestamp.calculate_time_difference(int(expiration_date))

    async def _human_view_expiration_date(self, expiration_date: int | None) -> str | None:
        if not expiration_date:
            return None
        return (
            self.timestamp.timestamp_to_date(int(expiration_date))
            .replace(microsecond=0, tzinfo=None)
            .strftime("%H:%M:%S %d-%m-%Y")
        )

    @staticmethod
    def _datetime_to_legacy_ms(value: datetime | None) -> int | None:
        if value is None:
            return None
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return int(normalized.astimezone(timezone.utc).timestamp() * 1000)

    @staticmethod
    def _human_view_traffic_bytes(value: int | None) -> str | None:
        if value is None:
            return None

        bytes_value = int(value)
        gib = 1024 * 1024 * 1024
        mib = 1024 * 1024
        kib = 1024

        if bytes_value >= gib:
            gb_value = bytes_value / gib
            if bytes_value % gib == 0:
                return f"{int(gb_value)} GB"
            return f"{gb_value:.1f} GB"
        if bytes_value >= mib:
            mb_value = bytes_value / mib
            if bytes_value % mib == 0:
                return f"{int(mb_value)} MB"
            return f"{mb_value:.1f} MB"
        if bytes_value >= kib:
            kb_value = bytes_value / kib
            if bytes_value % kib == 0:
                return f"{int(kb_value)} KB"
            return f"{kb_value:.1f} KB"
        return f"{bytes_value} B"
