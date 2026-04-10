from shared.config.settings import get_product_settings

HELP = "📞 Поддержка"
INSTRUCTIONS = "💡 Помощь"
INSTRUCTIONS_DEVICES = "📱 Инструкции по установке"
REFERRALS = "🎁 Приглашения"
SUBSCRIPTIONS = "🔐 Получить доступ"
MAIN_MENU = "🏠 В главное меню"
FAQ = "❓ Частые вопросы"
WHO_WE_ARE = "👥 О нас"
INFO_CHANNEL = "📢 Канал с новостями"
INFO_CHANNEL_CONFIRMED = "✅ Готово"
FRONT_PROFILE = "🌐 Кабинет"
OPEN_CABINET = "🌐 Открыть кабинет"
TRAFFIC_LIMITED_ACCESS = "📊 Доступ с лимитом трафика"
ACCESS_REQUEST = "📝 Запросить доступ"
ACCESS_REQUEST_STATUS = "📋 Статус заявки"
BACK_TO_SUBSCRIPTIONS = "⬅️ К вариантам доступа"

_PRODUCT_SETTINGS = get_product_settings()
FAQ_LINK = _PRODUCT_SETTINGS.docs_links.get("faq", "")
INSTRUCTIONS_DEVICES_LINK = _PRODUCT_SETTINGS.docs_links.get("devices", "")
WHO_WE_ARE_LINK = _PRODUCT_SETTINGS.docs_links.get("about", "")
DOCS_MENU_ENABLED = bool(FAQ_LINK or INSTRUCTIONS_DEVICES_LINK)

EXPIRED = "0 дней"
LESS_THAN_HOUR = "Менее часа"
