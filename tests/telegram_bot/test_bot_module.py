import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import telegram_bot.bot as bot_module


def test_build_bot_initializes_telebot_with_context_middleware():
    bot_instance = MagicMock()
    context_middleware = MagicMock()
    maintenance_middleware = MagicMock()

    with (
        patch.object(bot_module, "AsyncTeleBot", return_value=bot_instance) as bot_class,
        patch.object(
            bot_module,
            "ContextMiddleware",
            return_value=context_middleware,
        ) as context_middleware_class,
        patch.object(
            bot_module,
            "MaintenanceModeMiddleware",
            return_value=maintenance_middleware,
        ) as maintenance_middleware_class,
        patch.object(bot_module, "_configure_telegram_api_timeouts") as configure_timeouts,
        patch.object(bot_module.asyncio_helper, "proxy", "http://old-proxy"),
        patch.object(bot_module.apihelper, "proxy", "http://old-proxy"),
        patch.object(bot_module, "_wrap_answer_callback_query") as wrap_answer_callback_query,
        patch.object(bot_module, "logger") as logger,
    ):
        result = bot_module.build_bot()

    configure_timeouts.assert_called_once_with()
    assert bot_module.asyncio_helper.proxy is None
    assert bot_module.apihelper.proxy is None
    wrap_answer_callback_query.assert_called_once_with(bot_instance)
    bot_class.assert_called_once_with(bot_module.BOT_API)
    context_middleware_class.assert_called_once_with()
    maintenance_middleware_class.assert_called_once_with(bot_instance)
    assert bot_instance.setup_middleware.call_args_list == [
        ((context_middleware,),),
        ((maintenance_middleware,),),
    ]
    logger.info.assert_called_once_with("Building new Telegram Bot instance...")
    assert result is bot_instance


def test_configure_telegram_api_timeouts_updates_asyncio_helper_defaults():
    with (
        patch.object(bot_module.asyncio_helper, "CONNECT_TIMEOUT", 15),
        patch.object(bot_module.asyncio_helper, "READ_TIMEOUT", 30),
        patch.object(bot_module.asyncio_helper, "REQUEST_TIMEOUT", 300),
    ):
        bot_module._configure_telegram_api_timeouts()

        assert (
            bot_module.asyncio_helper.CONNECT_TIMEOUT
            == bot_module.TELEGRAM_API_CONNECT_TIMEOUT_SECONDS
        )
        assert (
            bot_module.asyncio_helper.READ_TIMEOUT
            == bot_module.TELEGRAM_API_REQUEST_TIMEOUT_SECONDS
        )
        assert (
            bot_module.asyncio_helper.REQUEST_TIMEOUT
            == bot_module.TELEGRAM_API_REQUEST_TIMEOUT_SECONDS
        )



@pytest.mark.asyncio
async def test_send_message_retries_on_transient_error():
    send_message = AsyncMock(
        side_effect=[
            asyncio.TimeoutError("temporary timeout"),
            SimpleNamespace(message_id=77),
        ]
    )
    bot_instance = SimpleNamespace(send_message=send_message)

    with patch.object(bot_module, "logger") as logger:
        bot_module._wrap_transient_retry(bot_instance, "send_message")
        result = await bot_instance.send_message(chat_id=1, text="hello")

    assert result.message_id == 77
    assert send_message.await_count == 2
    logger.warning.assert_called_once()


def test_is_expired_callback_query_error_matches_expected_telegram_error():
    error = bot_module.ApiTelegramException(
        "answer_callback_query",
        None,
        {
            "error_code": 400,
            "description": (
                "Bad Request: query is too old and response timeout expired or query ID is invalid"
            ),
        },
    )

    assert bot_module._is_expired_callback_query_error(error) is True


@pytest.mark.asyncio
async def test_wrap_answer_callback_query_swallows_expired_callback_errors():
    error = bot_module.ApiTelegramException(
        "answer_callback_query",
        None,
        {
            "error_code": 400,
            "description": (
                "Bad Request: query is too old and response timeout expired or query ID is invalid"
            ),
        },
    )
    bot_instance = SimpleNamespace(
        answer_callback_query=AsyncMock(side_effect=error),
    )

    with patch.object(bot_module, "logger") as logger:
        bot_module._wrap_answer_callback_query(bot_instance)
        result = await bot_instance.answer_callback_query("callback-id")

    assert result is None
    logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_wrap_answer_callback_query_reraises_non_expired_errors():
    error = bot_module.ApiTelegramException(
        "answer_callback_query",
        None,
        {
            "error_code": 400,
            "description": "Bad Request: chat not found",
        },
    )
    bot_instance = SimpleNamespace(
        answer_callback_query=AsyncMock(side_effect=error),
    )

    bot_module._wrap_answer_callback_query(bot_instance)

    with pytest.raises(bot_module.ApiTelegramException, match="chat not found"):
        await bot_instance.answer_callback_query("callback-id")


@pytest.mark.asyncio
async def test_wrap_answer_callback_query_retries_on_transient_error():
    original_method = AsyncMock(
        side_effect=[
            asyncio.TimeoutError("temporary timeout"),
            None,
        ]
    )
    bot_instance = SimpleNamespace(
        answer_callback_query=original_method,
    )

    with patch.object(bot_module, "logger") as logger:
        bot_module._wrap_answer_callback_query(bot_instance)
        result = await bot_instance.answer_callback_query("callback-id")

    assert result is None
    assert original_method.await_count == 2
    logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_context_middleware_sets_context_for_message_update():
    class FakeMessage:
        pass

    update = FakeMessage()
    update.chat = SimpleNamespace(id=101)
    update.from_user = SimpleNamespace(id=202, username="alice")

    chat_ctx = SimpleNamespace(set=MagicMock())
    user_ctx = SimpleNamespace(set=MagicMock())
    username_ctx = SimpleNamespace(set=MagicMock())

    with (
        patch.object(bot_module, "Message", FakeMessage),
        patch.object(bot_module, "chat_id_var", chat_ctx),
        patch.object(bot_module, "user_id_var", user_ctx),
        patch.object(bot_module, "username_var", username_ctx),
    ):
        await bot_module.ContextMiddleware().pre_process(update, {})

    chat_ctx.set.assert_called_once_with(101)
    user_ctx.set.assert_called_once_with(202)
    username_ctx.set.assert_called_once_with("alice")


@pytest.mark.asyncio
async def test_context_middleware_sets_context_for_callback_query():
    class FakeCallbackQuery:
        pass

    update = FakeCallbackQuery()
    update.message = SimpleNamespace(chat=SimpleNamespace(id=303))
    update.from_user = SimpleNamespace(id=404, username="bob")

    chat_ctx = SimpleNamespace(set=MagicMock())
    user_ctx = SimpleNamespace(set=MagicMock())
    username_ctx = SimpleNamespace(set=MagicMock())

    with (
        patch.object(bot_module, "CallbackQuery", FakeCallbackQuery),
        patch.object(bot_module, "chat_id_var", chat_ctx),
        patch.object(bot_module, "user_id_var", user_ctx),
        patch.object(bot_module, "username_var", username_ctx),
    ):
        await bot_module.ContextMiddleware().pre_process(update, {})

    chat_ctx.set.assert_called_once_with(303)
    user_ctx.set.assert_called_once_with(404)
    username_ctx.set.assert_called_once_with("bob")


@pytest.mark.asyncio
async def test_maintenance_mode_middleware_skips_non_admin_message_updates():
    class FakeMessage:
        pass

    update = FakeMessage()
    update.chat = SimpleNamespace(id=101)
    update.from_user = SimpleNamespace(id=202)
    bot_instance = SimpleNamespace(send_message=AsyncMock(), answer_callback_query=AsyncMock())

    with (
        patch.object(bot_module, "Message", FakeMessage),
        patch.object(bot_module, "BOT_MAINTENANCE_MODE", True),
        patch.object(bot_module, "BOT_ADMIN_IDS", [999]),
        patch.object(bot_module, "BOT_MAINTENANCE_MESSAGE", "maintenance"),
    ):
        result = await bot_module.MaintenanceModeMiddleware(bot_instance).pre_process(update, {})

    assert isinstance(result, bot_module.CancelUpdate)
    bot_instance.send_message.assert_awaited_once_with(chat_id=101, text="maintenance")
    bot_instance.answer_callback_query.assert_not_called()


@pytest.mark.asyncio
async def test_maintenance_mode_middleware_skips_non_admin_callback_queries():
    class FakeCallbackQuery:
        pass

    update = FakeCallbackQuery()
    update.id = "cbq-1"
    update.message = SimpleNamespace(chat=SimpleNamespace(id=101))
    update.from_user = SimpleNamespace(id=202)
    bot_instance = SimpleNamespace(send_message=AsyncMock(), answer_callback_query=AsyncMock())

    with (
        patch.object(bot_module, "CallbackQuery", FakeCallbackQuery),
        patch.object(bot_module, "BOT_MAINTENANCE_MODE", True),
        patch.object(bot_module, "BOT_ADMIN_IDS", [999]),
        patch.object(bot_module, "BOT_MAINTENANCE_MESSAGE", "maintenance"),
    ):
        result = await bot_module.MaintenanceModeMiddleware(bot_instance).pre_process(update, {})

    assert isinstance(result, bot_module.CancelUpdate)
    bot_instance.answer_callback_query.assert_awaited_once_with(
        callback_query_id="cbq-1",
        text="maintenance",
        show_alert=True,
    )
    bot_instance.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_maintenance_mode_middleware_allows_admins():
    class FakeMessage:
        pass

    update = FakeMessage()
    update.chat = SimpleNamespace(id=101)
    update.from_user = SimpleNamespace(id=202)
    bot_instance = SimpleNamespace(send_message=AsyncMock(), answer_callback_query=AsyncMock())

    with (
        patch.object(bot_module, "Message", FakeMessage),
        patch.object(bot_module, "BOT_MAINTENANCE_MODE", True),
        patch.object(bot_module, "BOT_ADMIN_IDS", [202]),
    ):
        result = await bot_module.MaintenanceModeMiddleware(bot_instance).pre_process(update, {})

    assert result is None
    bot_instance.send_message.assert_not_called()
    bot_instance.answer_callback_query.assert_not_called()
