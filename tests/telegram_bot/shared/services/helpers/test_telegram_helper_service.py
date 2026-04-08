from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.shared.services.helpers.telegram_helper_service import (
    TelegramHelperService,
)


@pytest.mark.asyncio
async def test_remove_message_delegates_to_bot_delete_message():
    service = TelegramHelperService()

    with (
        patch(
            "telegram_bot.shared.services.helpers.telegram_helper_service.bot.delete_message",
            new_callable=AsyncMock,
        ) as delete_message,
        patch(
            "telegram_bot.shared.services.helpers.telegram_helper_service.logger"
        ) as logger,
    ):
        await service.remove_message(123, 456)

    logger.info.assert_called_once_with("Removing message with ID 456 for user 123.")
    delete_message.assert_awaited_once_with(123, 456)
