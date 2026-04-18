from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import select

from shared.config.config import (
    API_SERVERS,
    LOCATION_LABELS,
    TRAFFIC_LIMITED_API_SERVERS,
    build_base_url,
    build_inbound_api_base,
    build_subscription_url,
    get_server_inbound_specs,
)
from shared.config.database.session import get_db_session
from shared.config.settings import RuntimeSyncFlags
from shared.constants.vpn import VPN_PROVIDER_3X_UI
from shared.models import register_models
from shared.models.vpn.vpn_access_point_model import VpnAccessPoint
from shared.models.vpn.vpn_client_deployment_model import VpnClientDeployment
from shared.models.vpn.vpn_client_model import VpnClient
from shared.models.vpn.vpn_control_plane_model import VpnControlPlane
from shared.models.vpn.vpn_location_model import VpnLocation
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_TRAFFIC_LIMITED
from shared.utils.logging_utils import setup_logger

logger = setup_logger("vpn-topology.service", "database.log")

register_models()

@dataclass(frozen=True, slots=True)
class TopologySeedResult:
    control_planes_created: int
    locations_created: int
    access_points_created: int


class VpnTopologyService:
    def __init__(self, sync_flags: RuntimeSyncFlags):
        self.sync_flags = sync_flags

    async def seed_topology(
        self,
        *,
        allow_destructive_sync: bool = False,
    ) -> TopologySeedResult:
        async with get_db_session() as session:
            result = await self._seed_topology(
                session,
                datetime.now(timezone.utc),
                allow_destructive_sync=allow_destructive_sync,
            )
            await session.commit()
            return result

    async def sync_vpn_client_deployments(
        self,
        vpn_client_id: int,
        *,
        scope: str,
        synced_at: datetime | None = None,
        allow_destructive_sync: bool = False,
    ) -> int | None:
        if not self.sync_flags.vpn_topology_sync_enabled:
            return None

        async with get_db_session() as session:
            now = synced_at or datetime.now(timezone.utc)
            await self._seed_topology(
                session,
                now,
                allow_destructive_sync=allow_destructive_sync,
            )
            vpn_client = await session.get(VpnClient, int(vpn_client_id))
            if vpn_client is None or vpn_client.deactivated_at is not None:
                raise ValueError(f"Active vpn_client not found for id={vpn_client_id}")
            if str(vpn_client.scope) != str(scope):
                raise ValueError(
                    f"vpn_client scope mismatch for id={vpn_client_id}: "
                    f"expected {scope}, got {vpn_client.scope}"
                )

            synced_count = await self._sync_vpn_client_deployments(
                session,
                vpn_client=vpn_client,
                scope=str(scope),
                external_client_id=str(vpn_client.external_client_uuid),
                external_email=str(vpn_client.external_email),
                now=now,
            )
            await session.commit()
            return synced_count

    async def _seed_topology(
        self,
        session,
        now: datetime,
        *,
        allow_destructive_sync: bool,
    ) -> TopologySeedResult:
        control_planes_created = 0
        locations_created = 0
        access_points_created = 0

        location_ids_by_code, new_locations = await self._seed_locations(
            session,
            allow_destructive_sync=allow_destructive_sync,
        )
        locations_created += new_locations

        for scope, server_pool in self._configured_server_pools():
            result = await self._seed_scope_topology(
                session,
                now=now,
                scope=scope,
                server_pool=server_pool,
                location_ids_by_code=location_ids_by_code,
                allow_destructive_sync=allow_destructive_sync,
            )
            control_planes_created += result.control_planes_created
            access_points_created += result.access_points_created

        return TopologySeedResult(
            control_planes_created=control_planes_created,
            locations_created=locations_created,
            access_points_created=access_points_created,
        )

    async def _seed_locations(
        self,
        session,
        *,
        allow_destructive_sync: bool,
    ) -> tuple[dict[str, int], int]:
        location_ids_by_code: dict[str, int] = {}
        locations_created = 0

        configured_location_codes: list[str] = []
        for _scope, server_pool in self._configured_server_pools():
            for _server_name, server_config in server_pool.items():
                for inbound_spec in get_server_inbound_specs(server_config):
                    code = str(inbound_spec.get("location_code") or "").strip()
                    if code and code not in configured_location_codes:
                        configured_location_codes.append(code)

        existing_locations = (await session.execute(select(VpnLocation))).scalars().all()
        existing_locations_by_code = {
            str(location.code): location for location in existing_locations
        }

        for sort_order, code in enumerate(configured_location_codes, start=1):
            label = LOCATION_LABELS.get(code, code)
            location = existing_locations_by_code.get(code)
            if location is None:
                location = VpnLocation(
                    code=code,
                    label=label,
                    is_active=True,
                    sort_order=sort_order,
                )
                session.add(location)
                await session.flush()
                locations_created += 1
            else:
                location.label = label
                location.is_active = True
                location.sort_order = sort_order
            location_ids_by_code[code] = int(location.id)

        missing_location_codes = [
            code
            for code, location in existing_locations_by_code.items()
            if bool(location.is_active) and code not in configured_location_codes
        ]
        if missing_location_codes and not allow_destructive_sync:
            raise ValueError(
                "Refusing destructive vpn topology sync for locations. "
                "Configured topology does not include active location codes: "
                f"{sorted(missing_location_codes)}. "
                "Set the correct REMOTE_ACCESS_CONFIG_PATH or rerun with "
                "allow_destructive_sync=True."
            )

        if allow_destructive_sync:
            for code, location in existing_locations_by_code.items():
                if code not in configured_location_codes:
                    location.is_active = False

        return location_ids_by_code, locations_created

    async def _seed_scope_topology(
        self,
        session,
        *,
        now: datetime,
        scope: str,
        server_pool: dict[str, dict],
        location_ids_by_code: dict[str, int],
        allow_destructive_sync: bool,
    ) -> TopologySeedResult:
        control_planes_created = 0
        access_points_created = 0

        existing_control_planes = (await session.execute(select(VpnControlPlane))).scalars().all()
        existing_control_planes_by_code = {
            str(control_plane.code): control_plane for control_plane in existing_control_planes
        }
        control_plane_ids_by_code: dict[str, int] = {}
        configured_control_plane_codes: set[str] = set()

        for server_name, server_config in server_pool.items():
            control_plane_code = self._control_plane_code(scope, server_name)
            configured_control_plane_codes.add(control_plane_code)
            control_plane = existing_control_planes_by_code.get(control_plane_code)
            payload = {
                "scope": scope,
                "server_name": server_name,
                "provider": VPN_PROVIDER_3X_UI,
                "api_base_url": build_base_url(server_config),
                "subscription_base_url": build_subscription_url(server_config),
                "is_enabled": True,
                "accepts_new_deployments": True,
                "metadata_json": {
                    "scope": scope,
                    "server_name": server_name,
                    "domain": server_config.get("domain"),
                    "port": server_config.get("port"),
                    "path": server_config.get("path"),
                    "subscription_port": server_config.get("subscription_port"),
                    "subscription_path": server_config.get("subscription_path"),
                    "inbound_ids": self._normalize_inbound_ids(server_config),
                },
            }
            if control_plane is None:
                control_plane = VpnControlPlane(
                    code=control_plane_code,
                    created_at=now,
                    updated_at=now,
                    **payload,
                )
                session.add(control_plane)
                await session.flush()
                control_planes_created += 1
            else:
                control_plane.scope = payload["scope"]
                control_plane.server_name = payload["server_name"]
                control_plane.provider = payload["provider"]
                control_plane.api_base_url = payload["api_base_url"]
                control_plane.subscription_base_url = payload["subscription_base_url"]
                control_plane.is_enabled = payload["is_enabled"]
                control_plane.accepts_new_deployments = payload["accepts_new_deployments"]
                control_plane.metadata_json = payload["metadata_json"]
                control_plane.updated_at = now
            control_plane_ids_by_code[control_plane_code] = int(control_plane.id)

        missing_control_plane_codes = [
            code
            for code, control_plane in existing_control_planes_by_code.items()
            if str(control_plane.scope) == scope
            and bool(control_plane.is_enabled)
            and code not in configured_control_plane_codes
        ]
        if missing_control_plane_codes and not allow_destructive_sync:
            raise ValueError(
                "Refusing destructive vpn topology sync for control planes. "
                f"Scope {scope} is missing active control planes from config: "
                f"{sorted(missing_control_plane_codes)}. "
                "Set the correct REMOTE_ACCESS_CONFIG_PATH or rerun with "
                "allow_destructive_sync=True."
            )

        if allow_destructive_sync:
            for code, control_plane in existing_control_planes_by_code.items():
                if str(control_plane.scope) != scope:
                    continue
                if code in configured_control_plane_codes:
                    continue
                control_plane.is_enabled = False
                control_plane.accepts_new_deployments = False
                control_plane.updated_at = now

        existing_access_points = (await session.execute(select(VpnAccessPoint))).scalars().all()
        existing_access_points_by_code = {
            str(access_point.code): access_point for access_point in existing_access_points
        }
        configured_access_point_codes: set[str] = set()

        for server_name, server_config in server_pool.items():
            control_plane_code = self._control_plane_code(scope, server_name)
            for position, inbound_spec in enumerate(
                get_server_inbound_specs(server_config),
                start=1,
            ):
                inbound_id = int(inbound_spec["id"])
                code = self._access_point_code(scope, server_name, inbound_id)
                configured_access_point_codes.add(code)
                location_code = str(inbound_spec.get("location_code") or "").strip() or None
                access_point = existing_access_points_by_code.get(code)
                payload = {
                    "control_plane_id": control_plane_ids_by_code[control_plane_code],
                    "location_id": location_ids_by_code.get(location_code)
                    if location_code is not None
                    else None,
                    "scope": scope,
                    "kind": "inbound",
                    "external_id": str(inbound_id),
                    "is_enabled": True,
                    "priority": position,
                    "capacity_limit": None,
                    "metadata_json": {
                        "scope": scope,
                        "server_name": server_name,
                        "location_code": location_code,
                        "api_base_url": build_inbound_api_base(server_config),
                        "subscription_base_url": build_subscription_url(server_config),
                    },
                }
                if access_point is None:
                    access_point = VpnAccessPoint(
                        code=code,
                        created_at=now,
                        updated_at=now,
                        **payload,
                    )
                    session.add(access_point)
                    await session.flush()
                    access_points_created += 1
                    continue

                access_point.control_plane_id = payload["control_plane_id"]
                access_point.location_id = payload["location_id"]
                access_point.scope = payload["scope"]
                access_point.kind = payload["kind"]
                access_point.external_id = payload["external_id"]
                access_point.is_enabled = payload["is_enabled"]
                access_point.priority = payload["priority"]
                access_point.capacity_limit = payload["capacity_limit"]
                access_point.metadata_json = payload["metadata_json"]
                access_point.updated_at = now

        missing_access_point_codes = [
            code
            for code, access_point in existing_access_points_by_code.items()
            if str(access_point.scope) == scope
            and bool(access_point.is_enabled)
            and code not in configured_access_point_codes
        ]
        if missing_access_point_codes and not allow_destructive_sync:
            raise ValueError(
                "Refusing destructive vpn topology sync for access points. "
                f"Scope {scope} is missing active access points from config: "
                f"{sorted(missing_access_point_codes)}. "
                "Set the correct REMOTE_ACCESS_CONFIG_PATH or rerun with "
                "allow_destructive_sync=True."
            )

        if allow_destructive_sync:
            for code, access_point in existing_access_points_by_code.items():
                if str(access_point.scope) != scope:
                    continue
                if code in configured_access_point_codes:
                    continue
                access_point.is_enabled = False
                access_point.updated_at = now

        return TopologySeedResult(
            control_planes_created=control_planes_created,
            locations_created=0,
            access_points_created=access_points_created,
        )

    async def _sync_vpn_client_deployments(
        self,
        session,
        *,
        vpn_client: VpnClient,
        scope: str,
        external_client_id: str,
        external_email: str,
        now: datetime,
    ) -> int:
        access_points = (
            await session.execute(
                select(VpnAccessPoint)
                .where(
                    VpnAccessPoint.is_enabled.is_(True),
                    VpnAccessPoint.scope == str(scope),
                )
                .order_by(VpnAccessPoint.priority, VpnAccessPoint.id)
            )
        ).scalars().all()
        active_access_point_ids = set()
        synced_count = 0

        for access_point in access_points:
            active_access_point_ids.add(int(access_point.id))
            deployment = (
                await session.execute(
                    select(VpnClientDeployment).where(
                        VpnClientDeployment.vpn_client_id == int(vpn_client.id),
                        VpnClientDeployment.access_point_id == int(access_point.id),
                        VpnClientDeployment.removed_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if deployment is None:
                deployment = VpnClientDeployment(
                    vpn_client_id=int(vpn_client.id),
                    access_point_id=int(access_point.id),
                    external_client_id=str(external_client_id),
                    external_remark=self._build_external_remark(
                        str(external_email),
                        str(access_point.external_id or ""),
                    ),
                    status="active",
                    last_synced_at=now,
                    last_error=None,
                    removed_at=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(deployment)
                synced_count += 1
                continue

            deployment.external_client_id = str(external_client_id)
            deployment.external_remark = self._build_external_remark(
                str(external_email),
                str(access_point.external_id or ""),
            )
            deployment.status = "active"
            deployment.last_synced_at = now
            deployment.last_error = None
            deployment.removed_at = None
            deployment.updated_at = now

        existing_deployments = (
            await session.execute(
                select(VpnClientDeployment).where(
                    VpnClientDeployment.vpn_client_id == int(vpn_client.id),
                    VpnClientDeployment.removed_at.is_(None),
                )
            )
        ).scalars().all()
        for deployment in existing_deployments:
            if int(deployment.access_point_id) in active_access_point_ids:
                continue
            deployment.removed_at = now
            deployment.updated_at = now

        return synced_count

    @staticmethod
    def _configured_server_pools() -> list[tuple[str, dict[str, dict]]]:
        return [
            (PRODUCT_SCOPE_STANDARD, API_SERVERS),
            (PRODUCT_SCOPE_TRAFFIC_LIMITED, TRAFFIC_LIMITED_API_SERVERS),
        ]

    @staticmethod
    def _control_plane_code(scope: str, server_name: str) -> str:
        if scope == PRODUCT_SCOPE_STANDARD:
            return str(server_name)
        return f"{scope}:{server_name}"

    @classmethod
    def _access_point_code(cls, scope: str, server_name: str, inbound_id: int) -> str:
        if scope == PRODUCT_SCOPE_STANDARD:
            return f"{server_name}-inbound-{inbound_id}"
        return f"{cls._control_plane_code(scope, server_name)}-inbound-{inbound_id}"

    @staticmethod
    def _normalize_inbound_ids(server_config: dict) -> list[int]:
        return [int(spec["id"]) for spec in get_server_inbound_specs(server_config)]

    @staticmethod
    def _build_external_remark(base_email: str, external_id: str) -> str:
        suffix = str(external_id or "").strip()
        if not suffix:
            return str(base_email)
        return f"{base_email}_{suffix}"
