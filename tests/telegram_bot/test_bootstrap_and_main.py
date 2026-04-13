import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config.settings import get_effective_product_feature_settings, load_settings
from telegram_bot.bootstrap import build_bot_app
from telegram_bot.main import (
    POLLING_REQUEST_TIMEOUT_SECONDS,
    POLLING_TIMEOUT_SECONDS,
    _run_polling_with_backoff,
    main,
    run_bot,
)


def _features(**overrides):
    values = {
        "access_requests_enabled": False,
        "access_registry_enabled": False,
        "access_admin_override_enabled": False,
        "commerce_enabled": True,
        "referrals_enabled": True,
        "promos_enabled": True,
        "web_purchase_enabled": True,
        "telegram_bot_enabled": True,
        "standard_config_enabled": True,
        "traffic_limited_config_enabled": True,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_build_bot_app_wires_shared_dependencies():
    app = build_bot_app(load_settings())
    features = get_effective_product_feature_settings()

    assert app.subscription_trial_handler.start_handler is app.start_handler
    assert (
        app.subscription_trial_handler.traffic_limited_service
        is app.payment_fulfillment_service.payment_processing.traffic_limited_service
    )
    assert (
        app.subscription_trial_handler.subscription_service
        is app.start_handler.subscription_service
    )
    assert (
        app.subscription_info_channel_handler.subscription_menu_handler
        is app.subscription_menu_handler
    )
    assert (
        app.subscription_menu_handler.traffic_limited_service
        is app.payment_fulfillment_service.payment_processing.traffic_limited_service
    )
    assert (
        app.start_handler.subscription_service
        is app.payment_fulfillment_service.subscription_service
    )
    assert (
        app.admin_command_handler.payment_queue_service
        is app.payment_fulfillment_service.queue_service
    )
    assert (
        app.payment_fulfillment_service.payment_processing.referrals_enabled
        is features.referrals_enabled
    )


@pytest.mark.asyncio
async def test_run_bot_registers_routes_and_shuts_down_background_services():
    app = SimpleNamespace(
        bot=MagicMock(),
        start_handler=MagicMock(),
        profile_handler=MagicMock(),
        support_handler=MagicMock(),
        instructions_handler=MagicMock(),
        payment_command_handler=MagicMock(),
        subscription_menu_handler=MagicMock(),
        subscription_access_request_handler=MagicMock(),
        referral_menu_handler=MagicMock(),
        admin_command_handler=MagicMock(),
        payment_status_checker=SimpleNamespace(run_scheduler=AsyncMock()),
        payment_fulfillment_service=SimpleNamespace(
            run_scheduler=AsyncMock(),
            run_worker=AsyncMock(),
            shutdown=AsyncMock(),
        ),
        referral_start_handler=MagicMock(),
        subscription_trial_handler=MagicMock(),
        reminder_service=SimpleNamespace(
            run_scheduler=AsyncMock(),
            run_worker=AsyncMock(),
            shutdown=AsyncMock(),
        ),
        access_lifecycle_service=SimpleNamespace(
            run_scheduler=AsyncMock(),
            shutdown=AsyncMock(),
        ),
        traffic_limited_sync_service=SimpleNamespace(run_scheduler=AsyncMock()),
        subscription_info_channel_handler=MagicMock(),
        subscription_promo_handler=MagicMock(),
    )

    with (
        patch("telegram_bot.main.register_start_routes") as register_start,
        patch("telegram_bot.main.register_subscription_routes") as register_subscription,
        patch("telegram_bot.main.register_promo_routes") as register_promo,
        patch("telegram_bot.main.register_referrals_routes") as register_referrals,
        patch("telegram_bot.main.register_admin_routes") as register_admin,
        patch("telegram_bot.main.register_payments_routes") as register_payments,
        patch("telegram_bot.main.get_effective_product_feature_settings", return_value=_features()),
        patch("telegram_bot.main._run_polling_with_backoff", new=AsyncMock()) as polling,
    ):
        await run_bot(app)

    register_start.assert_called_once_with(
        app.start_handler,
        app.profile_handler,
        app.support_handler,
        app.instructions_handler,
    )
    register_subscription.assert_called_once_with(
        app.payment_command_handler,
        app.subscription_menu_handler,
        app.subscription_access_request_handler,
        app.subscription_trial_handler,
        app.subscription_info_channel_handler,
        access_requests_enabled=False,
        commerce_enabled=True,
        standard_config_enabled=True,
        traffic_limited_config_enabled=True,
    )
    register_promo.assert_called_once_with(app.subscription_promo_handler)
    register_referrals.assert_called_once_with(app.referral_menu_handler)
    register_admin.assert_called_once_with(app.admin_command_handler)
    register_payments.assert_called_once_with(app.payment_command_handler)
    polling.assert_awaited_once_with(app.bot)
    app.reminder_service.shutdown.assert_awaited_once()
    app.payment_fulfillment_service.shutdown.assert_awaited_once()
    app.access_lifecycle_service.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_bot_skips_optional_commerce_routes_and_workers_when_disabled():
    app = SimpleNamespace(
        bot=MagicMock(),
        start_handler=MagicMock(),
        profile_handler=MagicMock(),
        support_handler=MagicMock(),
        instructions_handler=MagicMock(),
        payment_command_handler=MagicMock(),
        subscription_menu_handler=MagicMock(),
        subscription_access_request_handler=MagicMock(),
        referral_menu_handler=MagicMock(),
        admin_command_handler=MagicMock(),
        payment_status_checker=SimpleNamespace(run_scheduler=AsyncMock()),
        payment_fulfillment_service=SimpleNamespace(
            run_scheduler=AsyncMock(),
            run_worker=AsyncMock(),
            shutdown=AsyncMock(),
        ),
        referral_start_handler=MagicMock(),
        subscription_trial_handler=MagicMock(),
        reminder_service=SimpleNamespace(
            run_scheduler=AsyncMock(),
            run_worker=AsyncMock(),
            shutdown=AsyncMock(),
        ),
        access_lifecycle_service=SimpleNamespace(
            run_scheduler=AsyncMock(),
            shutdown=AsyncMock(),
        ),
        traffic_limited_sync_service=SimpleNamespace(run_scheduler=AsyncMock()),
        subscription_info_channel_handler=MagicMock(),
        subscription_promo_handler=MagicMock(),
    )

    with (
        patch("telegram_bot.main.register_start_routes"),
        patch("telegram_bot.main.register_subscription_routes") as register_subscription,
        patch("telegram_bot.main.register_promo_routes") as register_promo,
        patch("telegram_bot.main.register_referrals_routes") as register_referrals,
        patch("telegram_bot.main.register_admin_routes"),
        patch("telegram_bot.main.register_payments_routes") as register_payments,
        patch(
            "telegram_bot.main.get_effective_product_feature_settings",
            return_value=_features(
                commerce_enabled=False,
                referrals_enabled=False,
                promos_enabled=False,
            ),
        ),
        patch("telegram_bot.main._run_polling_with_backoff", new=AsyncMock()),
    ):
        await run_bot(app)

    assert register_subscription.call_args.kwargs["commerce_enabled"] is False
    assert register_subscription.call_args.kwargs["standard_config_enabled"] is True
    assert register_subscription.call_args.kwargs["traffic_limited_config_enabled"] is True
    register_promo.assert_not_called()
    register_referrals.assert_not_called()
    register_payments.assert_not_called()
    app.payment_status_checker.run_scheduler.assert_not_called()
    app.payment_fulfillment_service.run_scheduler.assert_not_called()
    app.payment_fulfillment_service.run_worker.assert_not_called()
    app.access_lifecycle_service.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_polling_with_backoff_uses_short_request_timeout():
    bot = SimpleNamespace(infinity_polling=AsyncMock(side_effect=asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await _run_polling_with_backoff(bot)

    bot.infinity_polling.assert_awaited_once_with(
        timeout=POLLING_TIMEOUT_SECONDS,
        request_timeout=POLLING_REQUEST_TIMEOUT_SECONDS,
    )


def test_main_uses_settings_and_bootstrap():
    settings = object()
    app = object()

    with (
        patch("telegram_bot.main.load_settings", return_value=settings) as load_settings_mock,
        patch(
            "telegram_bot.main.get_effective_product_feature_settings",
            return_value=_features(telegram_bot_enabled=True),
        ),
        patch("telegram_bot.main.build_bot_app", return_value=app) as build_app_mock,
        patch("telegram_bot.main.run_bot", new=AsyncMock()) as run_bot_mock,
        patch("telegram_bot.main.asyncio.run") as asyncio_run_mock,
    ):
        def fake_asyncio_run(coro):
            coro.close()
            return None

        asyncio_run_mock.side_effect = fake_asyncio_run

        main()

    load_settings_mock.assert_called_once_with()
    build_app_mock.assert_called_once_with(settings)
    run_bot_mock.assert_called_once_with(app)
    asyncio_run_mock.assert_called_once()


def test_main_skips_bot_bootstrap_when_telegram_runtime_disabled():
    settings = object()

    with (
        patch("telegram_bot.main.load_settings", return_value=settings) as load_settings_mock,
        patch(
            "telegram_bot.main.get_effective_product_feature_settings",
            return_value=_features(telegram_bot_enabled=False),
        ),
        patch("telegram_bot.main.build_bot_app") as build_app_mock,
        patch("telegram_bot.main._run_disabled_bot_runtime", new=AsyncMock()) as idle_mock,
        patch("telegram_bot.main.asyncio.run") as asyncio_run_mock,
    ):
        def fake_asyncio_run(coro):
            coro.close()
            return None

        asyncio_run_mock.side_effect = fake_asyncio_run

        main()

    load_settings_mock.assert_called_once_with()
    build_app_mock.assert_not_called()
    asyncio_run_mock.assert_called_once()


@pytest.mark.asyncio
async def test_run_bot_stays_idle_when_telegram_runtime_disabled():
    with (
        patch(
            "telegram_bot.main.get_effective_product_feature_settings",
            return_value=_features(telegram_bot_enabled=False),
        ),
        patch("telegram_bot.main._run_disabled_bot_runtime", new=AsyncMock()) as idle_mock,
    ):
        await run_bot(SimpleNamespace())

    idle_mock.assert_awaited_once_with()
