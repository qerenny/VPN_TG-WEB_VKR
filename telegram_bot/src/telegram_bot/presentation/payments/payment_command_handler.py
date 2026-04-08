from telebot.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from shared.config.config import BOT_RETURN_URL, PHOTO_subscriptions
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
    PaymentSnapshot,
)
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.bot import bot
from telegram_bot.shared.utils.menu_rendering import render_photo_menu
from telegram_bot.shared.texts import messages


from telegram_bot.services.payments.payment_gateway import PaymentGateway


class PaymentCommandHandler:
    def __init__(
        self,
        gateways: dict[str, PaymentGateway],
        repo: PaymentRepository,
        timestamp: TimestampUtils,
    ):
        self.gateways = gateways
        self.repo = repo
        self.timestamp = timestamp

    async def ask_payment_method(self, target: Message | CallbackQuery, product: dict) -> None:
        message = target.message if isinstance(target, CallbackQuery) else target
        if int(product.get("amount", 0) or 0) <= 0:
            await bot.send_message(
                chat_id=message.chat.id,
                text="Цена для этого продукта пока не настроена. Сначала выстави стоимость пакета в каталоге планов и bot config.",
            )
            return

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton(
                messages.get_random_message("payments_pay_by_card"),
                callback_data=f"pay_method:yookassa:{product['payload']}",
            ),
        )
        markup.row(
            InlineKeyboardButton(
                messages.get_random_message("payments_pay_by_crypto"),
                callback_data=f"pay_method:cryptopay:{product['payload']}",
            ),
        )

        await render_photo_menu(
            target=target,
            photo=PHOTO_subscriptions,
            caption=f"*{product['label']}*\n\n{messages.get_random_message('payments_choose_payment_option')}",
            parse_mode="Markdown",
            reply_markup=markup,
            bot_client=bot,
        )
    async def initiate_payment(self, message: Message, product: dict, method: str) -> None:
        gateway = self.gateways.get(method)
        if not gateway:
            raise ValueError(f"Unsupported payment method: {method}")

        payment_data = await gateway.create_payment(
            return_url=BOT_RETURN_URL,
            product=product,
            tg_id=message.chat.id,
        )
        payment_id = payment_data["id"]

        payment = PaymentSnapshot(
            payment_id=payment_id,
            user_id=None,
            tg_id=message.chat.id,
            status=payment_data["status"],
            payload=product["payload"],
            created_at=self.timestamp.current_timestamp(),
            method=method,
            # confirmed means "fully fulfilled" (3x-ui + DB), not gateway-paid status.
            confirmed=False,
        )
        await self.repo.create(payment)

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(messages.get_random_message("payments_pay"), url=payment_data["url"]))

        logger.info(f"[{method}] Sending payment link to tg_id={message.chat.id}")
        
        if method == "cryptopay":
            await bot.send_message(
                chat_id=message.chat.id,
                text=f"*{messages.get_random_message('payments_pay_by_crypto_description')}\n{product['label']}*\n\n{messages.get_random_message('payments_pay_and_wait')}",
                parse_mode="Markdown",
                reply_markup=markup,
            )
        elif method == "yookassa":
            await bot.send_message(
                chat_id=message.chat.id,
                text=f"*{messages.get_random_message('payments_pay_by_card_description')}\n{product['label']}*\n\n{messages.get_random_message('payments_pay_and_wait')}",
                parse_mode="Markdown",
                reply_markup=markup,
            )
        else:
            logger.error(f"Unsupported payment method: {method}")
            raise ValueError(f"Unsupported payment method: {method}")
