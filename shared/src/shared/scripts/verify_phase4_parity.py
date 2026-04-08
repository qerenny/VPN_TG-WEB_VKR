from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlmodel import select

from shared.config.config import API_SERVERS, INBOUND_ID_MAP
from shared.config.database.session import get_db_session
from shared.migration_support.models.users.user_model import User as LegacyUser
from shared.models import register_models
from shared.models.vpn.vpn_access_point_model import VpnAccessPoint
from shared.models.vpn.vpn_client_deployment_model import VpnClientDeployment
from shared.models.vpn.vpn_client_model import VpnClient
from shared.models.vpn.vpn_control_plane_model import VpnControlPlane
from shared.models.vpn.vpn_location_model import VpnLocation
from shared.product_constants import PRODUCT_SCOPE_STANDARD
from shared.scripts.rollout_support import RolloutCheck, print_checks, run_async

register_models()


async def main() -> None:
    async with get_db_session() as session:
        control_planes = (await session.execute(select(VpnControlPlane))).scalars().all()
        locations = (await session.execute(select(VpnLocation))).scalars().all()
        access_points = (await session.execute(select(VpnAccessPoint))).scalars().all()
        vpn_clients = (await session.execute(select(VpnClient))).scalars().all()
        deployments = (
            await session.execute(select(VpnClientDeployment))
        ).scalars().all()
        legacy_users = (await session.execute(select(LegacyUser))).scalars().all()

    expected_control_plane_codes = set(API_SERVERS.keys())
    actual_control_plane_codes = {
        str(control_plane.code)
        for control_plane in control_planes
        if control_plane.is_enabled
    }

    expected_location_codes = {str(code) for code in INBOUND_ID_MAP.values()}
    actual_location_codes = {
        str(location.code)
        for location in locations
        if location.is_active
    }

    expected_access_points = set()
    for server_name, server_config in API_SERVERS.items():
        inbound_ids = server_config.get("inbound_id", [])
        if not isinstance(inbound_ids, list):
            inbound_ids = [inbound_ids]
        for inbound_id in inbound_ids:
            expected_access_points.add(f"{server_name}-inbound-{int(inbound_id)}")
    actual_access_points = {
        str(access_point.code)
        for access_point in access_points
        if access_point.is_enabled and access_point.scope == PRODUCT_SCOPE_STANDARD
    }

    vpn_clients_by_uuid = {
        str(client.external_client_uuid): client
        for client in vpn_clients
        if client.deactivated_at is None and client.scope == PRODUCT_SCOPE_STANDARD
    }
    active_deployments_by_client_id: dict[int, list[VpnClientDeployment]] = defaultdict(list)
    for deployment in deployments:
        if deployment.removed_at is None:
            active_deployments_by_client_id[int(deployment.vpn_client_id)].append(deployment)

    active_access_points_by_id = {
        int(access_point.id): access_point
        for access_point in access_points
        if access_point.is_enabled and access_point.scope == PRODUCT_SCOPE_STANDARD
    }

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    active_legacy_users = [
        user
        for user in legacy_users
        if user.expiration_date is not None and int(user.expiration_date) > now_ms
    ]
    missing_vpn_clients = 0
    deployment_count_mismatches = 0
    deployment_remark_mismatches = 0
    for user in active_legacy_users:
        vpn_client = vpn_clients_by_uuid.get(str(user.uuid))
        if vpn_client is None:
            missing_vpn_clients += 1
            continue
        user_deployments = active_deployments_by_client_id.get(int(vpn_client.id), [])
        if len(user_deployments) != len(expected_access_points):
            deployment_count_mismatches += 1
            continue
        for deployment in user_deployments:
            access_point = active_access_points_by_id.get(int(deployment.access_point_id))
            if access_point is None:
                deployment_remark_mismatches += 1
                continue
            expected_remark = f"{user.email}_{access_point.external_id}"
            if deployment.external_client_id != str(user.uuid):
                deployment_remark_mismatches += 1
                continue
            if deployment.external_remark != expected_remark:
                deployment_remark_mismatches += 1

    checks = [
        RolloutCheck(
            name="configured control planes mapped to vpn_control_planes",
            ok=expected_control_plane_codes == actual_control_plane_codes,
            details=f"present={sorted(actual_control_plane_codes)}",
        ),
        RolloutCheck(
            name="configured locations mapped to vpn_locations",
            ok=expected_location_codes == actual_location_codes,
            details=f"present={sorted(actual_location_codes)}",
        ),
        RolloutCheck(
            name="configured access points mapped to vpn_access_points",
            ok=expected_access_points == actual_access_points,
            details=f"present={sorted(actual_access_points)}",
        ),
        RolloutCheck(
            name="active legacy users mapped to vpn_clients",
            ok=missing_vpn_clients == 0,
            details=f"missing={missing_vpn_clients}",
        ),
        RolloutCheck(
            name="active legacy users mapped to vpn_client_deployments",
            ok=deployment_count_mismatches == 0,
            details=f"mismatches={deployment_count_mismatches}",
        ),
        RolloutCheck(
            name="vpn_client_deployments external identifiers parity",
            ok=deployment_remark_mismatches == 0,
            details=f"mismatches={deployment_remark_mismatches}",
        ),
    ]
    print_checks(checks)
    if not all(check.ok for check in checks):
        raise SystemExit(1)


if __name__ == "__main__":
    run_async(main())
