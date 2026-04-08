from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import select

from shared.config.config import (
    WHITELIST_API_SERVERS,
    WHITELIST_TRAFFIC_SYNC_INTERVAL_SECONDS,
)
from shared.config.database.session import get_db_session
from shared.models.traffic.traffic_state_model import TrafficState
from shared.models.vpn.vpn_client_model import VpnClient
from shared.product_constants import PRODUCT_SCOPE_WHITELIST
from shared.utils.logging_utils import logger, log_with_throttle


@dataclass(frozen=True, slots=True)
class WhiteListTrafficSyncTarget:
    vpn_client_id: int
    external_email: str


class WhiteListTrafficSyncService:
    ERROR_LOG_COOLDOWN_SECONDS = 300.0

    def __init__(
        self,
        client_manager,
        scan_interval_seconds: int = WHITELIST_TRAFFIC_SYNC_INTERVAL_SECONDS,
    ):
        self.client_manager = client_manager
        self.scan_interval_seconds = scan_interval_seconds

    async def run_scheduler(self) -> None:
        logger.info(
            "WhiteList traffic sync scheduler started "
            f"(scan_interval={self.scan_interval_seconds}s)."
        )
        while True:
            try:
                await self.sync_all_clients_once()
            except Exception as err:
                log_with_throttle(
                    "ERROR",
                    f"whitelist-traffic-sync:{type(err).__name__}:{str(err)}",
                    f"WhiteList traffic sync failed: {err!r}",
                    cooldown_seconds=self.ERROR_LOG_COOLDOWN_SECONDS,
                )
            await asyncio.sleep(self.scan_interval_seconds)

    async def sync_all_clients_once(self) -> int:
        targets = await self._load_targets()
        if not targets:
            return 0

        synced_count = 0
        for target in targets:
            try:
                used_bytes = await self.client_manager.get_scoped_client_usage_bytes(
                    server_pool=WHITELIST_API_SERVERS,
                    cache_namespace=PRODUCT_SCOPE_WHITELIST,
                    email=str(target.external_email),
                )
                await self._apply_usage(target.vpn_client_id, used_bytes=used_bytes)
                synced_count += 1
            except Exception as err:
                log_with_throttle(
                    "ERROR",
                    (
                        "whitelist-traffic-sync-client:"
                        f"{target.vpn_client_id}:{type(err).__name__}:{str(err)}"
                    ),
                    (
                        "WhiteList traffic sync failed for "
                        f"vpn_client_id={target.vpn_client_id}: {err!r}"
                    ),
                    cooldown_seconds=self.ERROR_LOG_COOLDOWN_SECONDS,
                )
        return synced_count

    async def sync_user_once(self, *, user_id: int) -> bool:
        async with get_db_session() as session:
            row = (
                await session.execute(
                    select(VpnClient.id, VpnClient.external_email)
                    .join(TrafficState, TrafficState.vpn_client_id == VpnClient.id)
                    .where(
                        VpnClient.user_id == int(user_id),
                        VpnClient.scope == PRODUCT_SCOPE_WHITELIST,
                        VpnClient.deactivated_at.is_(None),
                    )
                    .limit(1)
                )
            ).one_or_none()

        if row is None:
            return False

        vpn_client_id, external_email = row
        used_bytes = await self.client_manager.get_scoped_client_usage_bytes(
            server_pool=WHITELIST_API_SERVERS,
            cache_namespace=PRODUCT_SCOPE_WHITELIST,
            email=str(external_email),
        )
        await self._apply_usage(int(vpn_client_id), used_bytes=used_bytes)
        return True

    async def _load_targets(self) -> list[WhiteListTrafficSyncTarget]:
        async with get_db_session() as session:
            rows = (
                await session.execute(
                    select(VpnClient.id, VpnClient.external_email)
                    .join(TrafficState, TrafficState.vpn_client_id == VpnClient.id)
                    .where(
                        VpnClient.scope == PRODUCT_SCOPE_WHITELIST,
                        VpnClient.deactivated_at.is_(None),
                    )
                    .order_by(VpnClient.id)
                )
            ).all()

        return [
            WhiteListTrafficSyncTarget(
                vpn_client_id=int(vpn_client_id),
                external_email=str(external_email),
            )
            for vpn_client_id, external_email in rows
        ]

    async def _apply_usage(self, vpn_client_id: int, *, used_bytes: int) -> None:
        async with get_db_session() as session:
            state = await session.get(TrafficState, int(vpn_client_id))
            if state is None:
                return

            allocated_bytes = int(state.allocated_bytes or 0)
            normalized_used = max(0, int(used_bytes))
            state.used_bytes = normalized_used
            state.remaining_bytes = max(0, allocated_bytes - normalized_used)
            state.is_blocked = False
            state.block_reason = None
            state.last_provider_sync_at = datetime.now(timezone.utc)
            state.updated_at = datetime.now(timezone.utc)
            await session.commit()
