import base64

import pytest

from backend.routers.subscription import utils


@pytest.fixture(autouse=True)
def subscription_labels(monkeypatch):
    monkeypatch.setattr(
        utils,
        "LOCATION_LABELS",
        {
            "default": "VPN",
            "germany": "Germany",
            "estonia": "Estonia",
        },
    )
    monkeypatch.setattr(utils, "KEY_PROFILE_TAG", "::")
    monkeypatch.setattr(utils, "INBOUND_ID_MAP", {1: "germany", 2: "estonia"})


def test_process_subscription_content_uses_default_label_without_known_suffix():
    result = utils.process_subscription_content(
        b"vless://uuid@server:443?type=tcp#vikktoriia21"
    )

    assert result == ["vless://uuid@server:443?type=tcp#VPN::"]


def test_process_subscription_content_uses_inbound_label_for_suffix():
    result = utils.process_subscription_content(
        b"vless://uuid@server:443?type=tcp#user_2"
    )

    assert result == ["vless://uuid@server:443?type=tcp#Estonia::"]


def test_process_subscription_content_uses_numeric_suffix_without_underscore():
    result = utils.process_subscription_content(
        b"vless://uuid@server:443?type=tcp#remote_access_support@weathered-silence1"
    )

    assert result == ["vless://uuid@server:443?type=tcp#Germany::"]


def test_process_subscription_content_uses_source_name_fallback():
    result = utils.process_subscription_content(
        b"vless://uuid@server:443?type=tcp#remark-without-id",
        source_name="estonia",
    )

    assert result == ["vless://uuid@server:443?type=tcp#Estonia::"]


def test_process_subscription_content_decodes_base64_input():
    encoded = base64.b64encode(b"vless://uuid@server:443?type=tcp#user_2")

    result = utils.process_subscription_content(encoded)

    assert result == ["vless://uuid@server:443?type=tcp#Estonia::"]


def test_process_subscription_content_prefers_explicit_inbound_labels():
    result = utils.process_subscription_content(
        b"vless://uuid@server:443?type=tcp#user_2",
        inbound_labels={2: "Finland"},
    )

    assert result == ["vless://uuid@server:443?type=tcp#Finland::"]


def test_process_subscription_content_formats_traffic_limited_location_label(monkeypatch):
    monkeypatch.setattr(utils, "KEY_PROFILE_TAG", "🔐")

    result = utils.process_subscription_content(
        b"vless://uuid@server:443?type=tcp#remote_access_support@bold-union-6aa5f0f9_1",
        scope="traffic_limited",
    )

    assert result == ["vless://uuid@server:443?type=tcp#Germany🔐🏳️"]


def test_process_subscription_content_formats_traffic_limited_explicit_inbound_label(monkeypatch):
    monkeypatch.setattr(utils, "KEY_PROFILE_TAG", "🔐")

    result = utils.process_subscription_content(
        b"vless://uuid@server:443?type=tcp#user_2",
        scope="traffic_limited",
        inbound_labels={2: "Finland"},
    )

    assert result == ["vless://uuid@server:443?type=tcp#Finland🔐🏳️"]


def test_process_subscription_content_does_not_duplicate_traffic_limited_decorations(monkeypatch):
    monkeypatch.setattr(utils, "KEY_PROFILE_TAG", "🔐")

    result = utils.process_subscription_content(
        b"vless://uuid@server:443?type=tcp#user_2",
        scope="traffic_limited",
        inbound_labels={2: "🏳️ Finland🔐🏳️"},
    )

    assert result == ["vless://uuid@server:443?type=tcp#Finland🔐🏳️"]
