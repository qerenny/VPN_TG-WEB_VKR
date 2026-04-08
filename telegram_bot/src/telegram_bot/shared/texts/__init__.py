import random

from telegram_bot.shared.texts import (
    admin_messages,
    instructions_messages,
    payments_messages,
    referrals_messages,
    shared_messages,
    start_messages,
    subscriptions_messages,
    support_messages,
    users_messages,
)

_category_modules = {
    **subscriptions_messages.categories,
    **referrals_messages.categories,
    **start_messages.categories,
    **support_messages.categories,
    **payments_messages.categories,
    **instructions_messages.categories,
    **users_messages.categories,
    **admin_messages.categories,
    **shared_messages.categories,
}


class BotMessageService:
    def get_random_message(self, category: str, **kwargs) -> str:
        messages = _category_modules.get(category, [])
        message = random.choice(messages) if messages else ""
        return message.format(**kwargs) if kwargs else message


messages = BotMessageService()
