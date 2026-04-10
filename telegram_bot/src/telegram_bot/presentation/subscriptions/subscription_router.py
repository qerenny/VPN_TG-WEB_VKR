from telebot.types import CallbackQuery

from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.presentation.payments.payment_command_handler import PaymentCommandHandler
from telegram_bot.presentation.subscriptions.subscription_access_request_handler import (
    SubscriptionAccessRequestHandler,
)
from telegram_bot.presentation.subscriptions.subscription_menu_handler import SubscriptionMenuHandler
from telegram_bot.presentation.subscriptions.subscription_trial_handler import SubscriptionTrialHandler
from telegram_bot.presentation.subscriptions.subscription_info_channel_handler import SubscriptionInfoChannelHandler
from telegram_bot.shared.config.subscription_products import (
    MONTH1,
    MONTH3,
    MONTH6,
    TRAFFIC_LIMITED15GB,
    TRAFFIC_LIMITED35GB,
    TRAFFIC_LIMITED80GB,
    YEAR1,
)


PAID_PRODUCTS = {
    "sub_month1": MONTH1,
    "sub_month3": MONTH3,
    "sub_month6": MONTH6,
    "sub_year1": YEAR1,
    "sub_traffic_limited15gb": TRAFFIC_LIMITED15GB,
    "sub_traffic_limited35gb": TRAFFIC_LIMITED35GB,
    "sub_traffic_limited80gb": TRAFFIC_LIMITED80GB,
}
COMMERCE_DISABLED_CALLBACK_TEXT = "Оплата отключена"
STANDARD_CONFIG_DISABLED_CALLBACK_TEXT = "Базовые конфигурации отключены"
TRAFFIC_LIMITED_DISABLED_CALLBACK_TEXT = "Конфигурации с лимитом трафика отключены"


def register_subscription_routes(
    payment_command_handler: PaymentCommandHandler,
    subscription_menu_handler: SubscriptionMenuHandler,
    subscription_access_request_handler: SubscriptionAccessRequestHandler,
    subscription_trial_handler: SubscriptionTrialHandler,
    subscription_info_channel_handler: SubscriptionInfoChannelHandler,
    *,
    commerce_enabled: bool = True,
    access_requests_enabled: bool = False,
    standard_config_enabled: bool = True,
    traffic_limited_config_enabled: bool = True,
):
    @bot.callback_query_handler(func=lambda call: call.data == "profile_subscriptions")
    async def handle_show_subscriptions(call: CallbackQuery) -> None:
        await bot.answer_callback_query(call.id)
        await subscription_menu_handler.show_subscription_menu(call)
    @bot.callback_query_handler(func=lambda call: call.data.startswith("sub_"))
    async def handle_subscription_choice(call: CallbackQuery) -> None:
        data = call.data

        if data == "sub_trial":
            if not standard_config_enabled:
                await bot.answer_callback_query(call.id, STANDARD_CONFIG_DISABLED_CALLBACK_TEXT)
                return
            await bot.answer_callback_query(call.id)
            decorated = subscription_info_channel_handler.check_info_channel_subscription(
                subscription_trial_handler.grant_trial
            )
            await decorated(call)
        elif data == "sub_check_info_channel":
            await subscription_info_channel_handler.handle_check_info_channel(call)
        elif data == "sub_info_channel_menu":
            await bot.answer_callback_query(call.id)
            await subscription_info_channel_handler.show_info_channel_menu(call)
        elif data == "sub_traffic_limited_menu":
            if not traffic_limited_config_enabled:
                await bot.answer_callback_query(call.id, TRAFFIC_LIMITED_DISABLED_CALLBACK_TEXT)
                return
            await bot.answer_callback_query(call.id)
            await subscription_menu_handler.show_traffic_limited_menu(call)
        elif data == "sub_traffic_limited_trial":
            if not traffic_limited_config_enabled:
                await bot.answer_callback_query(call.id, TRAFFIC_LIMITED_DISABLED_CALLBACK_TEXT)
                return
            await bot.answer_callback_query(call.id)
            decorated = subscription_info_channel_handler.check_info_channel_subscription(
                subscription_trial_handler.grant_traffic_limited_trial
            )
            await decorated(call)
        elif data == "sub_access_request":
            if not access_requests_enabled:
                await bot.answer_callback_query(call.id, "Заявки на доступ отключены")
                return
            await bot.answer_callback_query(call.id)
            await subscription_access_request_handler.show_request_menu(call)
        elif data.startswith("sub_access_request_scope:"):
            if not access_requests_enabled:
                await bot.answer_callback_query(call.id, "Заявки на доступ отключены")
                return
            await bot.answer_callback_query(call.id)
            scope = str(data.split(":", 1)[1]).strip().lower()
            await subscription_access_request_handler.show_template_menu(call, scope=scope)
        elif data.startswith("sub_access_request_kind:"):
            if not access_requests_enabled:
                await bot.answer_callback_query(call.id, "Заявки на доступ отключены")
                return
            request_kind = str(data.split(":", 1)[1]).strip().lower() or "new_access"
            if request_kind == "renewal":
                await subscription_access_request_handler.submit_request(
                    call,
                    request_kind="renewal",
                    template_code=None,
                )
                return
            await bot.answer_callback_query(call.id)
            await subscription_access_request_handler.show_request_menu(call)
        elif data.startswith("sub_access_request_submit:"):
            if not access_requests_enabled:
                await bot.answer_callback_query(call.id, "Заявки на доступ отключены")
                return
            parts = data.split(":")
            template_code = parts[-1] if parts else ""
            normalized_template_code = None if template_code in {"", "auto"} else template_code
            if normalized_template_code is None:
                await bot.answer_callback_query(call.id, "Шаблон доступа не выбран")
                return
            await subscription_access_request_handler.submit_template_request(
                call,
                template_code=normalized_template_code,
            )
        elif data == "sub_access_request_status":
            if not access_requests_enabled:
                await bot.answer_callback_query(call.id, "Заявки на доступ отключены")
                return
            await subscription_access_request_handler.show_status(call, alert_on_empty=True)
        elif data in PAID_PRODUCTS:
            if data in {"sub_month1", "sub_month3", "sub_month6", "sub_year1"} and not standard_config_enabled:
                await bot.answer_callback_query(call.id, STANDARD_CONFIG_DISABLED_CALLBACK_TEXT)
                return
            if data.startswith("sub_traffic_limited") and not traffic_limited_config_enabled:
                await bot.answer_callback_query(call.id, TRAFFIC_LIMITED_DISABLED_CALLBACK_TEXT)
                return
            if not commerce_enabled:
                await bot.answer_callback_query(call.id, COMMERCE_DISABLED_CALLBACK_TEXT)
                return
            await bot.answer_callback_query(call.id)
            product = PAID_PRODUCTS[data]
            decorated = subscription_info_channel_handler.check_info_channel_subscription(
                lambda c: payment_command_handler.ask_payment_method(c, product)
            )
            await decorated(call)
