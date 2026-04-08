import asyncio
import json
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query, Request
import httpx
from sqlmodel import select

from backend.bootstrap import get_subscription_manager_service
from backend.schemas.subscription.subscription_formatted_info_schema import (
    SubscriptionFormattedInfoSchema,
)
from backend.services.subscription.subscription_manager_service import (
    SubscriptionManagerService,
)
from fastapi.responses import PlainTextResponse

from shared.config.config import (
    API_SERVERS,
    FRONTEND_LINK,
    LOCATION_LABELS,
    WHITELIST_API_SERVERS,
    build_subscription_url,
    get_server_inbound_specs,
    REDIS_SUBSCRIPTION_BUILD_TTL,
    REDIS_SUBSCRIPTION_INFO_TTL,
)
from shared.config.settings import get_product_settings
from shared.config.database.session import get_db_session
from shared.models.vpn.vpn_access_point_model import VpnAccessPoint
from shared.models.vpn.vpn_client_deployment_model import VpnClientDeployment
from shared.models.vpn.vpn_client_model import VpnClient
from shared.models.vpn.vpn_control_plane_model import VpnControlPlane
from shared.models.vpn.vpn_location_model import VpnLocation
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_WHITELIST
from shared.utils.logging_utils import logger
from backend.utils.async_redis_client import RedisClientError
from backend.utils.ttl_cache import TTLCache
from .utils import process_subscription_content

router = APIRouter(prefix="/subscription", tags=["subscription"])

# Cache with 60s TTL and max 1000 items
subscription_cache = TTLCache(ttl=60, max_size=1000)
subscription_info_cache = TTLCache(ttl=30, max_size=2000)
subscription_inflight: dict[str, asyncio.Task["SubscriptionBuildResult"]] = {}
subscription_inflight_lock = asyncio.Lock()

SUBSCRIPTION_PROFILE_UPDATE_INTERVAL = "1"
SUBSCRIPTION_AUTO_UPDATE_OPEN_ENABLE = "1"
_PRODUCT_SETTINGS = get_product_settings()
SUBSCRIPTION_REDIS_PREFIX = _PRODUCT_SETTINGS.redis_prefix
SUBSCRIPTION_PROFILE_TITLE = _PRODUCT_SETTINGS.profile_title
WHITELIST_SUBSCRIPTION_PROFILE_TITLE = _PRODUCT_SETTINGS.traffic_profile_title
SUBSCRIPTION_ANNOUNCE = _PRODUCT_SETTINGS.announce
SUBSCRIPTION_SUPPORT_URL = _PRODUCT_SETTINGS.support_link

SUBSCRIPTION_RESPONSE_HEADERS = {
    "profile-update-interval": SUBSCRIPTION_PROFILE_UPDATE_INTERVAL,
    "subscription-auto-update-open-enable": SUBSCRIPTION_AUTO_UPDATE_OPEN_ENABLE,
    "profile-title": SUBSCRIPTION_PROFILE_TITLE,
    "support-url": SUBSCRIPTION_SUPPORT_URL,
    "profile-web-page-url": FRONTEND_LINK,
    "announce": SUBSCRIPTION_ANNOUNCE,
}


@dataclass(frozen=True, slots=True)
class SubscriptionBuildTarget:
    source_name: str
    base_url: str
    inbound_labels: dict[int, str]


@dataclass(frozen=True, slots=True)
class SubscriptionBuildResult:
    body: str
    headers: dict[str, str]


SUBSCRIPTION_UPSTREAM_RESPONSE_HEADERS = frozenset(
    {
        "subscription-userinfo",
    }
)
SUBSCRIPTION_USERINFO_HEADER = "subscription-userinfo"
SUBSCRIPTION_USERINFO_ORDERED_KEYS = ("upload", "download", "total", "expire")
SUBSCRIPTION_USERINFO_SUM_KEYS = frozenset({"upload", "download"})
SUBSCRIPTION_USERINFO_MAX_KEYS = frozenset({"total", "expire"})


def _build_subscription_response(
    payload: SubscriptionBuildResult | str,
    *,
    scope: str = PRODUCT_SCOPE_STANDARD,
) -> PlainTextResponse:
    result = _coerce_subscription_build_result(payload)
    response = PlainTextResponse(result.body)
    for header_name, header_value in _subscription_response_headers(scope).items():
        _set_response_header(response, header_name, header_value)
    for header_name, header_value in result.headers.items():
        _set_response_header(response, header_name, header_value)
    return response


def _coerce_subscription_build_result(
    payload: SubscriptionBuildResult | str,
) -> SubscriptionBuildResult:
    if isinstance(payload, SubscriptionBuildResult):
        return payload
    return SubscriptionBuildResult(body=str(payload), headers={})


def _subscription_response_headers(scope: str) -> dict[str, str]:
    headers = dict(SUBSCRIPTION_RESPONSE_HEADERS)
    if scope == PRODUCT_SCOPE_WHITELIST:
        headers["profile-title"] = WHITELIST_SUBSCRIPTION_PROFILE_TITLE
    return headers


def _set_response_header(
    response: PlainTextResponse,
    header_name: str,
    header_value: str,
) -> None:
    try:
        response.headers[header_name] = header_value
    except UnicodeEncodeError:
        raw_name = header_name.lower().encode("latin-1")
        response.raw_headers[:] = [
            (name, value)
            for name, value in response.raw_headers
            if name.lower() != raw_name
        ]
        response.raw_headers.append((raw_name, str(header_value).encode("utf-8")))


def _extract_upstream_subscription_headers(headers) -> dict[str, str]:
    copied: dict[str, str] = {}
    for header_name, header_value in getattr(headers, "items", lambda: [])():
        normalized_name = str(header_name).lower()
        if normalized_name in SUBSCRIPTION_UPSTREAM_RESPONSE_HEADERS and header_value:
            copied[normalized_name] = str(header_value)
    return copied


def _merge_upstream_subscription_headers(
    target: dict[str, str],
    incoming: dict[str, str],
) -> None:
    for header_name, header_value in incoming.items():
        if header_name == SUBSCRIPTION_USERINFO_HEADER:
            target[header_name] = _merge_subscription_userinfo_header(
                target.get(header_name),
                header_value,
            )
            continue
        target.setdefault(header_name, header_value)


def _merge_subscription_userinfo_header(existing: str | None, incoming: str) -> str:
    if not existing:
        return incoming

    existing_values = _parse_subscription_userinfo_header(existing)
    incoming_values = _parse_subscription_userinfo_header(incoming)
    if not existing_values or not incoming_values:
        return existing

    merged = dict(existing_values)
    for key, incoming_value in incoming_values.items():
        if key in SUBSCRIPTION_USERINFO_SUM_KEYS:
            merged[key] = str(
                _parse_int_header_value(existing_values.get(key))
                + _parse_int_header_value(incoming_value)
            )
        elif key in SUBSCRIPTION_USERINFO_MAX_KEYS:
            merged[key] = str(
                max(
                    _parse_int_header_value(existing_values.get(key)),
                    _parse_int_header_value(incoming_value),
                )
            )
        else:
            merged.setdefault(key, incoming_value)

    return _format_subscription_userinfo_header(merged)


def _parse_subscription_userinfo_header(header_value: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for part in str(header_value).split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip()
        if normalized_key and normalized_value:
            values[normalized_key] = normalized_value
    return values


def _format_subscription_userinfo_header(values: dict[str, str]) -> str:
    parts = [
        f"{key}={values[key]}"
        for key in SUBSCRIPTION_USERINFO_ORDERED_KEYS
        if key in values
    ]
    parts.extend(
        f"{key}={value}"
        for key, value in values.items()
        if key not in SUBSCRIPTION_USERINFO_ORDERED_KEYS
    )
    return "; ".join(parts)


def _parse_int_header_value(value: str | None) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except ValueError:
        return 0


def _encode_subscription_build_cache(result: SubscriptionBuildResult) -> str:
    return json.dumps(
        {
            "body": result.body,
            "headers": result.headers,
        },
        ensure_ascii=False,
    )


def _decode_subscription_build_cache(cached: bytes | str) -> SubscriptionBuildResult:
    if isinstance(cached, bytes):
        cached = cached.decode("utf-8")
    try:
        payload = json.loads(cached)
    except json.JSONDecodeError:
        return SubscriptionBuildResult(body=cached, headers={})
    if not isinstance(payload, dict) or not isinstance(payload.get("body"), str):
        return SubscriptionBuildResult(body=cached, headers={})
    headers = payload.get("headers")
    if not isinstance(headers, dict):
        headers = {}
    return SubscriptionBuildResult(
        body=payload["body"],
        headers={str(key).lower(): str(value) for key, value in headers.items() if value},
    )


def _subscription_info_source_tag(request: Request) -> str:
    return "v1"


async def _build_combined_subscription(
    request: Request,
    uuid: str,
    redis_client=None,
    *,
    scope: str = PRODUCT_SCOPE_STANDARD,
) -> SubscriptionBuildResult:
    all_configs = []
    subscription_headers: dict[str, str] = {}
    build_targets = await _resolve_build_targets(request, uuid=uuid, scope=scope)
    if not build_targets:
        raise HTTPException(
            status_code=404,
            detail=f"No upstream servers configured for scope {scope}",
        )

    async def fetch_server_config(target: SubscriptionBuildTarget, client):
        try:
            url = f"{target.base_url}{uuid}"
            resp = await client.get(url)

            if resp.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        f"Failed to fetch from {target.source_name}: "
                        f"{resp.status_code} - {resp.text}"
                    ),
                )

            _merge_upstream_subscription_headers(
                subscription_headers,
                _extract_upstream_subscription_headers(getattr(resp, "headers", {})),
            )

            return process_subscription_content(
                resp.content,
                source_name=target.source_name,
                scope=scope,
                inbound_labels=target.inbound_labels,
            )

        except Exception as server_error:
            logger.error(
                f"Error fetching from server {target.source_name}: {str(server_error)}"
            )
            return []

    # Use shared httpx client from app state
    client = getattr(request.app.state, "http_client", None)
    if not client:
        # Fallback if app state is not set (e.g. in tests without lifespan)
        async with httpx.AsyncClient(verify=False) as new_client:
            tasks = [
                fetch_server_config(target, new_client)
                for target in build_targets
            ]
            results = await asyncio.gather(*tasks)
    else:
        tasks = [
            fetch_server_config(target, client)
            for target in build_targets
        ]
        results = await asyncio.gather(*tasks)

    for configs in results:
        all_configs.extend(configs)

    if not all_configs:
        raise HTTPException(
            status_code=404,
            detail="No valid configurations found for the provided UUID",
        )

    combined = "\n".join(all_configs)
    result = SubscriptionBuildResult(body=combined, headers=subscription_headers)
    local_cache_key = _subscription_cache_key(scope, uuid)
    subscription_cache.set(local_cache_key, result)

    if redis_client is not None:
        try:
            await redis_client.set(
                _subscription_build_redis_key(scope, uuid),
                _encode_subscription_build_cache(result),
                ex=REDIS_SUBSCRIPTION_BUILD_TTL,
            )
        except RedisClientError as err:
            logger.warning(f"Failed to write build cache to Redis: {err}")

    return result


@router.get("/build", response_class=PlainTextResponse)
async def get_combined_subscription(request: Request, uuid: str = Query(...)):
    """
    Combines subscription configurations from all servers for a given UUID.
    Automatically decodes base64 if needed.
    """
    return await _get_scoped_combined_subscription(
        request,
        uuid=uuid,
        scope=PRODUCT_SCOPE_STANDARD,
    )


@router.get("/whitelist/build", response_class=PlainTextResponse)
async def get_whitelist_combined_subscription(request: Request, uuid: str = Query(...)):
    return await _get_scoped_combined_subscription(
        request,
        uuid=uuid,
        scope=PRODUCT_SCOPE_WHITELIST,
    )


async def _get_scoped_combined_subscription(
    request: Request,
    *,
    uuid: str,
    scope: str,
):
    # Check cache first
    local_cache_key = _subscription_cache_key(scope, uuid)
    if cached := subscription_cache.get(local_cache_key):
        return _build_subscription_response(cached, scope=scope)

    redis_client = getattr(request.app.state, "redis_client", None)
    if redis_client is not None:
        try:
            redis_cached = await redis_client.get(_subscription_build_redis_key(scope, uuid))
            if redis_cached:
                result = _decode_subscription_build_cache(redis_cached)
                subscription_cache.set(local_cache_key, result)
                return _build_subscription_response(result, scope=scope)
        except RedisClientError as err:
            logger.warning(f"Failed to read build cache from Redis: {err}")

    created_task = False
    task: asyncio.Task[SubscriptionBuildResult] | None = None
    try:
        async with subscription_inflight_lock:
            task = subscription_inflight.get(local_cache_key)
            if task is None:
                task = asyncio.create_task(
                    _build_combined_subscription(
                        request,
                        uuid,
                        redis_client=redis_client,
                        scope=scope,
                    )
                )
                subscription_inflight[local_cache_key] = task
                created_task = True

        return _build_subscription_response(await task, scope=scope)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        if created_task and task:
            async with subscription_inflight_lock:
                if subscription_inflight.get(local_cache_key) is task:
                    subscription_inflight.pop(local_cache_key, None)


def _subscription_cache_key(scope: str, value: str) -> str:
    if scope == PRODUCT_SCOPE_STANDARD:
        return str(value)
    return f"{scope}:{value}"


def _subscription_build_redis_key(scope: str, uuid: str) -> str:
    if scope == PRODUCT_SCOPE_STANDARD:
        return f"{SUBSCRIPTION_REDIS_PREFIX}:subscription:build:{uuid}"
    return f"{SUBSCRIPTION_REDIS_PREFIX}:subscription:build:{scope}:{uuid}"


def _subscription_info_redis_key(scope: str, cache_key: str) -> str:
    if scope == PRODUCT_SCOPE_STANDARD:
        return f"{SUBSCRIPTION_REDIS_PREFIX}:subscription:info:{cache_key}"
    return f"{SUBSCRIPTION_REDIS_PREFIX}:subscription:info:{scope}:{cache_key}"


def _server_pool_for_scope(scope: str) -> dict[str, dict]:
    if scope == PRODUCT_SCOPE_STANDARD:
        return API_SERVERS
    if scope == PRODUCT_SCOPE_WHITELIST:
        return WHITELIST_API_SERVERS
    return {}


def _use_deployment_build(request: Request) -> bool:
    return True


async def _resolve_build_targets(
    request: Request,
    *,
    uuid: str,
    scope: str,
) -> list[SubscriptionBuildTarget]:
    if _use_deployment_build(request):
        targets = await _resolve_build_targets_from_deployments(uuid=uuid, scope=scope)
        if targets:
            return targets

    server_pool = _server_pool_for_scope(scope)
    return [
        SubscriptionBuildTarget(
            source_name=str(name),
            base_url=build_subscription_url(server),
            inbound_labels={
                int(spec["id"]): LOCATION_LABELS.get(
                    str(spec.get("location_code") or ""),
                    LOCATION_LABELS.get("default", "🌍VPN"),
                )
                for spec in get_server_inbound_specs(server)
            },
        )
        for name, server in server_pool.items()
    ]


async def _resolve_build_targets_from_deployments(
    *,
    uuid: str,
    scope: str,
) -> list[SubscriptionBuildTarget]:
    async with get_db_session() as session:
        vpn_client = (
            await session.execute(
                select(VpnClient).where(
                    VpnClient.subscription_external_id == str(uuid),
                    VpnClient.scope == str(scope),
                    VpnClient.deactivated_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if vpn_client is None:
            return []

        rows = (
            await session.execute(
                select(
                    VpnControlPlane.id,
                    VpnControlPlane.code,
                    VpnControlPlane.subscription_base_url,
                    VpnAccessPoint.external_id,
                    VpnLocation.label,
                )
                .join(
                    VpnAccessPoint,
                    VpnAccessPoint.control_plane_id == VpnControlPlane.id,
                )
                .outerjoin(
                    VpnLocation,
                    VpnLocation.id == VpnAccessPoint.location_id,
                )
                .join(
                    VpnClientDeployment,
                    VpnClientDeployment.access_point_id == VpnAccessPoint.id,
                )
                .where(
                    VpnClientDeployment.vpn_client_id == int(vpn_client.id),
                    VpnClientDeployment.removed_at.is_(None),
                    VpnAccessPoint.scope == str(scope),
                    VpnAccessPoint.is_enabled.is_(True),
                    VpnControlPlane.is_enabled.is_(True),
                )
                .order_by(VpnAccessPoint.priority, VpnAccessPoint.id)
            )
        ).all()

    grouped: dict[int, SubscriptionBuildTarget] = {}
    for (
        control_plane_id,
        control_plane_code,
        subscription_base_url,
        external_id,
        location_label,
    ) in rows:
        control_plane_id = int(control_plane_id)
        existing = grouped.get(control_plane_id)
        inbound_labels = dict(existing.inbound_labels) if existing else {}
        if external_id is not None and location_label:
            inbound_labels[int(external_id)] = str(location_label)
        grouped[control_plane_id] = SubscriptionBuildTarget(
            source_name=str(control_plane_code),
            base_url=str(subscription_base_url),
            inbound_labels=inbound_labels,
        )
    return list(grouped.values())


@router.get("/whitelist/{user_token}", response_model=SubscriptionFormattedInfoSchema)
async def get_whitelist_subscription_formatted_info(
    user_token: str,
    request: Request,
    service: SubscriptionManagerService = Depends(get_subscription_manager_service),
):
    return await _get_scoped_subscription_formatted_info(
        user_token=user_token,
        request=request,
        service=service,
        scope=PRODUCT_SCOPE_WHITELIST,
    )


# This route with path parameter must come AFTER more specific routes
@router.get("/{user_token}", response_model=SubscriptionFormattedInfoSchema)
async def get_subscription_formatted_info(
    user_token: str,
    request: Request,
    service: SubscriptionManagerService = Depends(get_subscription_manager_service),
):
    return await _get_scoped_subscription_formatted_info(
        user_token=user_token,
        request=request,
        service=service,
        scope=PRODUCT_SCOPE_STANDARD,
    )


async def _get_scoped_subscription_formatted_info(
    *,
    user_token: str,
    request: Request,
    service: SubscriptionManagerService,
    scope: str,
):
    """
    Gets formatted subscription information for a user token (JWT).
    """
    source_tag = _subscription_info_source_tag(request)
    base_cache_key = f"{source_tag}:{user_token}"
    cache_key = _subscription_cache_key(scope, base_cache_key)

    if cached := subscription_info_cache.get(cache_key):
        return _normalize_subscription_info_payload(cached, scope=scope)

    redis_client = getattr(request.app.state, "redis_client", None)
    redis_key = _subscription_info_redis_key(scope, base_cache_key)
    if redis_client is not None:
        try:
            redis_cached = await redis_client.get(redis_key)
            if redis_cached:
                if isinstance(redis_cached, bytes):
                    redis_cached = redis_cached.decode("utf-8")
                payload = _normalize_subscription_info_payload(
                    json.loads(redis_cached),
                    scope=scope,
                )
                subscription_info_cache.set(cache_key, payload)
                return payload
        except (RedisClientError, json.JSONDecodeError) as err:
            logger.warning(f"Failed to read formatted subscription cache from Redis: {err}")

    payload = _normalize_subscription_info_payload(
        await service.get_subscription_formatted_info(user_token, scope=scope),
        scope=scope,
    )
    subscription_info_cache.set(cache_key, payload)

    if redis_client is not None:
        try:
            await redis_client.set(
                redis_key,
                json.dumps(payload, ensure_ascii=False),
                ex=REDIS_SUBSCRIPTION_INFO_TTL,
            )
        except RedisClientError as err:
            logger.warning(f"Failed to write formatted subscription cache to Redis: {err}")

    return payload


def _normalize_subscription_info_payload(payload: dict | None, *, scope: str) -> dict | None:
    if not isinstance(payload, dict):
        return payload
    if payload.get("scope"):
        return payload
    normalized = dict(payload)
    normalized["scope"] = scope
    return normalized
