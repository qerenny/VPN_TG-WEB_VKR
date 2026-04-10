from telebot.types import Message

from shared.infrastructure.promos.promo_code_repository import (
    PromoCodeRepository,
)
from shared.infrastructure.promos.promo_code_usage_repository import (
    PromoCodeUsageRepository,
)
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.presentation.start.start_handler import StartHandler
from telegram_bot.services.subscriptions.subscription_flow_service import (
    SubscriptionFlowService,
)
from telegram_bot.shared.texts import messages


class SubscriptionPromoHandler:
    def __init__(
        self,
        subscription_flow_service: SubscriptionFlowService,
        start_handler: StartHandler,
        promo_repo: PromoCodeUsageRepository,
        promo_code_repo: PromoCodeRepository,
    ):
        self.subscription_flow_service = subscription_flow_service
        self.start_handler = start_handler
        self.promo_repo = promo_repo
        self.promo_code_repo = promo_code_repo

    async def activate_promo(self, message: Message) -> None:
        tg_id = message.chat.id
        parts = message.text.split(maxsplit=1)
        if len(parts) < 2:
            await bot.send_message(
                chat_id=tg_id,
                text=messages.get_random_message("promo_invalid_code"),
            )
            return

        promo_code = parts[1].strip()
        if await self.promo_repo.is_used(tg_id, promo_code):
            await bot.send_message(
                chat_id=tg_id,
                text=messages.get_random_message("promo_already_used"),
            )
            return

        promo = await self.promo_code_repo.get_by_code(promo_code)
        if promo is None or (promo.remaining_uses is not None and promo.remaining_uses <= 0):
            await bot.send_message(
                chat_id=tg_id,
                text=messages.get_random_message("promo_invalid_code"),
            )
            return

        subscription_text, key_text = (
            await self.subscription_flow_service.activate_or_extend_subscription(
                tg_id=tg_id,
                period=promo.duration,
            )
        )
        await self.promo_repo.mark_used(tg_id, promo_code)

        promo_text = messages.get_random_message("promo_activated").format(
            promo_code=promo_code
        )
        logger.info(f"Promo code {promo_code} activated for tg_id={tg_id}.")
        await bot.send_message(
            chat_id=tg_id,
            text=promo_text,
            parse_mode="Markdown",
        )
        await bot.send_message(
            chat_id=tg_id,
            text=f"{subscription_text}\n\n{key_text}",
            parse_mode="Markdown",
        )
        await self.start_handler.send_main_menu(message)
