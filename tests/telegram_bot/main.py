import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import telegram_bot.telegram_bot.main as main


@pytest.mark.asyncio
async def test_run_bot_successful_flow():
    handlers = [MagicMock() for _ in range(12)]
    reminder_service = MagicMock()
    reminder_service.check_expiring_users = AsyncMock(return_value="task")

    with (
        patch.object(main, "APIConnection") as api_cls,
        patch.object(main, "register_start_routes") as reg_start,
        patch.object(main, "register_subscription_routes") as reg_sub,
        patch.object(main, "register_referrals_routes") as reg_ref,
        patch.object(main, "register_admin_routes") as reg_admin,
        patch.object(main, "register_payments_routes") as reg_pay,
        patch.object(main, "bot") as bot_mock,
        patch.object(asyncio, "create_task") as create_task,
    ):
        api_inst = api_cls.return_value
        api_inst.login = AsyncMock()
        bot_mock.polling = AsyncMock()

        *initial_handlers, subscription_news_handler = handlers
        await main.run_bot(*initial_handlers, reminder_service, subscription_news_handler)

        api_inst.login.assert_awaited_once()
        reg_start.assert_called_once_with(handlers[0], handlers[1], handlers[2], handlers[3])
        reg_sub.assert_called_once_with(handlers[4], handlers[5], handlers[10], subscription_news_handler)
        reg_ref.assert_called_once_with(handlers[6])
        reg_admin.assert_called_once_with(handlers[7])
        reg_pay.assert_called_once_with(handlers[4], handlers[8])
        create_task.assert_called_once()
        reminder_service.check_expiring_users.assert_called_once()
        # close the created coroutine to avoid warnings
        create_task.call_args.args[0].close()
        bot_mock.polling.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_bot_login_failure():
    handlers = [MagicMock() for _ in range(12)]
    reminder_service = MagicMock()

    with patch.object(main, "APIConnection") as api_cls, patch.object(main, "bot") as bot_mock:
        api_inst = api_cls.return_value
        api_inst.login = AsyncMock(side_effect=RuntimeError("fail"))
        bot_mock.polling = AsyncMock()

        *initial_handlers, subscription_news_handler = handlers
        with pytest.raises(RuntimeError):
            await main.run_bot(*initial_handlers, reminder_service, subscription_news_handler)

        bot_mock.polling.assert_not_called()


def _patch_containers():
    names = [
        "StartContainer",
        "ProfileContainer",
        "SupportContainer",
        "HelpContainer",
        "PaymentCommandContainer",
        "SubscriptionMenuContainer",
        "ReferralContainer",
        "AdminCommandContainer",
        "PaymentStatusContainer",
        "ReferralStartContainer",
        "SubscriptionTrialContainer",
        "SubscriptionServicesContainer",
        "SubscriptionNewsChannelContainer",
    ]
    patches = {}
    instances = []
    for name in names:
        inst = MagicMock()
        patches[name] = MagicMock(return_value=inst)
        instances.append(inst)
    return patches, instances


def test_main_success():
    patchers, instances = _patch_containers()
    with (
        patch.multiple(main, **patchers),
        patch.object(main, "run_bot", new=MagicMock(return_value=None)),
        patch.object(asyncio, "run") as asyncio_run,
        patch.object(main, "logger") as log,
    ):
        asyncio_run.return_value = None
        main.main()

        asyncio_run.assert_called_once()
        for inst in instances:
            inst.wire.assert_called_once_with(modules=[main.__name__])
            inst.unwire.assert_called_once()
        log.error.assert_not_called()


def test_main_keyboard_interrupt():
    patchers, instances = _patch_containers()
    with (
        patch.multiple(main, **patchers),
        patch.object(main, "run_bot", new=MagicMock(return_value=None)),
        patch.object(asyncio, "run", side_effect=KeyboardInterrupt),
        patch.object(main, "logger") as log,
    ):
        main.main()
        log.info.assert_any_call("Bot is stopped by User.")
        for inst in instances:
            inst.unwire.assert_called_once()


def test_main_general_exception():
    patchers, instances = _patch_containers()
    with (
        patch.multiple(main, **patchers),
        patch.object(main, "run_bot", new=MagicMock(return_value=None)),
        patch.object(asyncio, "run", side_effect=RuntimeError("boom")),
        patch.object(main, "logger") as log,
    ):
        with pytest.raises(RuntimeError):
            main.main()
        log.error.assert_called_once()
        for inst in instances:
            inst.unwire.assert_called_once()
