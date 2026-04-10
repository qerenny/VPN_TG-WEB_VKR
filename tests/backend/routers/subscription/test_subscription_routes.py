import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.routers.subscription import subscription_routes as routes


def make_request(
    *,
    redis_client=None,
    http_client=None,
):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                redis_client=redis_client,
                http_client=http_client,
                settings=SimpleNamespace(features=SimpleNamespace()),
            )
        )
    )


@pytest.fixture(autouse=True)
def clear_subscription_caches():
    routes.subscription_cache.clear()
    routes.subscription_info_cache.clear()
    routes.subscription_inflight.clear()


@pytest.mark.asyncio
async def test_build_combined_subscription_uses_shared_http_client_and_writes_redis():
    http_client = AsyncMock()
    http_client.get.side_effect = [
        SimpleNamespace(
            status_code=200,
            content=b"a",
            text="ok",
            headers={
                "subscription-userinfo": "upload=1; download=2; total=3; expire=4"
            },
        ),
        SimpleNamespace(
            status_code=200,
            content=b"b",
            text="ok",
            headers={
                "subscription-userinfo": "upload=10; download=20; total=30; expire=40"
            },
        ),
    ]
    redis_client = AsyncMock()
    request = make_request(redis_client=redis_client, http_client=http_client)

    with (
        patch.object(
            routes,
            "API_SERVERS",
            {"de": {"host": "de"}, "ee": {"host": "ee"}},
        ),
        patch.object(
            routes,
            "_resolve_build_targets_from_deployments",
            new=AsyncMock(return_value=[]),
        ),
        patch.object(routes, "build_subscription_url", side_effect=["https://de/", "https://ee/"]),
        patch.object(
            routes,
            "process_subscription_content",
            side_effect=[["cfg-1"], ["cfg-2"]],
        ),
    ):
        result = await routes._build_combined_subscription(
            request,
            "uuid-1",
            redis_client=redis_client,
        )

    assert result.body == "cfg-1\ncfg-2"
    assert result.headers == {
        "subscription-userinfo": "upload=11; download=22; total=30; expire=40",
    }
    assert http_client.get.await_count == 2
    redis_client.set.assert_awaited_once_with(
        f"{routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:build:uuid-1",
        routes._encode_subscription_build_cache(result),
        ex=routes.REDIS_SUBSCRIPTION_BUILD_TTL,
    )


@pytest.mark.asyncio
async def test_build_combined_subscription_uses_deployment_targets_when_enabled():
    http_client = AsyncMock()
    http_client.get.side_effect = [
        SimpleNamespace(status_code=200, content=b"a", text="ok"),
        SimpleNamespace(status_code=200, content=b"b", text="ok"),
    ]
    request = make_request(http_client=http_client)

    with (
        patch.object(
            routes,
            "_resolve_build_targets",
            new=AsyncMock(
                return_value=[
                    routes.SubscriptionBuildTarget(
                        source_name="cp-a",
                        base_url="https://cp-a/sub/",
                        inbound_labels={},
                    ),
                    routes.SubscriptionBuildTarget(
                        source_name="cp-b",
                        base_url="https://cp-b/sub/",
                        inbound_labels={},
                    ),
                ]
            ),
        ),
        patch.object(
            routes,
            "process_subscription_content",
            side_effect=[["cfg-1"], ["cfg-2"]],
        ),
    ):
        result = await routes._build_combined_subscription(request, "uuid-deploy")

    assert result.body == "cfg-1\ncfg-2"
    assert http_client.get.await_count == 2
    http_client.get.assert_any_await("https://cp-a/sub/uuid-deploy")
    http_client.get.assert_any_await("https://cp-b/sub/uuid-deploy")


@pytest.mark.asyncio
async def test_get_combined_subscription_returns_redis_cached_value():
    redis_client = AsyncMock()
    redis_client.get.return_value = b"cached-subscription"
    request = make_request(redis_client=redis_client, http_client=None)

    result = await routes.get_combined_subscription(request, uuid="uuid-2")

    assert result.body.decode("utf-8") == "cached-subscription"
    assert result.headers["profile-update-interval"] == routes.SUBSCRIPTION_PROFILE_UPDATE_INTERVAL
    assert (
        result.headers["subscription-auto-update-open-enable"]
        == routes.SUBSCRIPTION_AUTO_UPDATE_OPEN_ENABLE
    )
    assert result.headers["profile-title"] == routes.SUBSCRIPTION_PROFILE_TITLE
    assert result.headers["support-url"] == routes.SUBSCRIPTION_SUPPORT_URL
    assert result.headers["profile-web-page-url"] == routes.FRONTEND_LINK
    assert result.headers["announce"] == routes.SUBSCRIPTION_ANNOUNCE
    redis_client.get.assert_awaited_once_with(
        f"{routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:build:uuid-2"
    )


@pytest.mark.asyncio
async def test_get_combined_subscription_returns_redis_cached_headers():
    cached_result = routes.SubscriptionBuildResult(
        body="cached-subscription",
        headers={
            "subscription-userinfo": "upload=1; download=2; total=3; expire=4",
        },
    )
    redis_client = AsyncMock()
    redis_client.get.return_value = routes._encode_subscription_build_cache(cached_result).encode(
        "utf-8"
    )
    request = make_request(redis_client=redis_client, http_client=None)

    result = await routes.get_combined_subscription(request, uuid="uuid-headers")

    assert result.body.decode("utf-8") == "cached-subscription"
    assert (
        result.headers["subscription-userinfo"]
        == "upload=1; download=2; total=3; expire=4"
    )
    redis_client.get.assert_awaited_once_with(
        f"{routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:build:uuid-headers"
    )


@pytest.mark.asyncio
async def test_get_traffic_limited_combined_subscription_uses_traffic_limited_cache_namespace():
    redis_client = AsyncMock()
    redis_client.get.return_value = b"cached-traffic_limited-subscription"
    request = make_request(redis_client=redis_client, http_client=None)

    result = await routes.get_traffic_limited_combined_subscription(request, uuid="uuid-wl-2")

    assert result.body.decode("utf-8") == "cached-traffic_limited-subscription"
    raw_headers = dict(result.raw_headers)
    assert (
        raw_headers[b"profile-title"].decode("utf-8")
        == routes.TRAFFIC_LIMITED_SUBSCRIPTION_PROFILE_TITLE
    )
    redis_client.get.assert_awaited_once_with(
        f"{routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:build:traffic_limited:uuid-wl-2"
    )


@pytest.mark.asyncio
async def test_get_combined_subscription_wraps_unexpected_error_and_clears_inflight():
    request = make_request(redis_client=None, http_client=None)

    with patch.object(
        routes,
        "_build_combined_subscription",
        side_effect=RuntimeError("boom"),
    ):
        with pytest.raises(routes.HTTPException) as exc_info:
            await routes.get_combined_subscription(request, uuid="uuid-3")

    assert exc_info.value.status_code == 500
    assert "Internal server error" in exc_info.value.detail
    assert routes.subscription_inflight == {}


@pytest.mark.asyncio
async def test_get_subscription_formatted_info_returns_redis_cached_payload():
    redis_client = AsyncMock()
    redis_client.get.return_value = json.dumps({"sub_is_active": True}).encode("utf-8")
    request = make_request(redis_client=redis_client)
    service = AsyncMock()

    result = await routes.get_subscription_formatted_info(
        "token-1",
        request,
        service=service,
    )

    assert result == {"sub_is_active": True, "scope": "standard"}
    redis_client.get.assert_awaited_once_with(
        f"{routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:info:v1:token-1"
    )
    service.get_subscription_formatted_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_subscription_formatted_info_calls_service_and_writes_redis():
    redis_client = AsyncMock()
    redis_client.get.return_value = None
    request = make_request(redis_client=redis_client)
    service = AsyncMock()
    service.get_subscription_formatted_info.return_value = {"sub_link": "https://sub"}

    result = await routes.get_subscription_formatted_info(
        "token-2",
        request,
        service=service,
    )

    assert result == {"sub_link": "https://sub", "scope": "standard"}
    service.get_subscription_formatted_info.assert_awaited_once_with(
        "token-2",
        scope="standard",
    )
    redis_client.set.assert_awaited_once_with(
        f"{routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:info:v1:token-2",
        json.dumps({"sub_link": "https://sub", "scope": "standard"}, ensure_ascii=False),
        ex=routes.REDIS_SUBSCRIPTION_INFO_TTL,
    )


@pytest.mark.asyncio
async def test_get_traffic_limited_subscription_formatted_info_calls_service_and_writes_redis():
    redis_client = AsyncMock()
    redis_client.get.return_value = None
    request = make_request(redis_client=redis_client)
    service = AsyncMock()
    service.get_subscription_formatted_info.return_value = {"sub_link": "https://sub-wl"}

    result = await routes.get_traffic_limited_subscription_formatted_info(
        "token-wl",
        request,
        service=service,
    )

    assert result == {"sub_link": "https://sub-wl", "scope": "traffic_limited"}
    service.get_subscription_formatted_info.assert_awaited_once_with(
        "token-wl",
        scope="traffic_limited",
    )
    redis_client.set.assert_awaited_once_with(
        f"{routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:info:traffic_limited:v1:token-wl",
        json.dumps({"sub_link": "https://sub-wl", "scope": "traffic_limited"}, ensure_ascii=False),
        ex=routes.REDIS_SUBSCRIPTION_INFO_TTL,
    )


@pytest.mark.asyncio
async def test_get_traffic_limited_subscription_formatted_info_returns_legacy_redis_payload_with_scope():
    redis_client = AsyncMock()
    redis_client.get.return_value = json.dumps({"sub_is_active": False}).encode("utf-8")
    request = make_request(redis_client=redis_client)
    service = AsyncMock()

    result = await routes.get_traffic_limited_subscription_formatted_info(
        "token-wl-legacy",
        request,
        service=service,
    )

    assert result == {"sub_is_active": False, "scope": "traffic_limited"}
    redis_client.get.assert_awaited_once_with(
        f"{routes.SUBSCRIPTION_REDIS_PREFIX}:subscription:info:traffic_limited:v1:token-wl-legacy"
    )
    service.get_subscription_formatted_info.assert_not_awaited()
