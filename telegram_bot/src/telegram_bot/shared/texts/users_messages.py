from shared.config.config import INBOUND_AMOUNT_OF_DEVICES

categories = {
    "users_options": [
        f"📱 На одну конфигурацию можно подключить до `{INBOUND_AMOUNT_OF_DEVICES}` устройств.",
        f"Максимум `{INBOUND_AMOUNT_OF_DEVICES}` устройств на одну конфигурацию.",
        f"Для стабильной работы — не больше `{INBOUND_AMOUNT_OF_DEVICES}` устройств на конфигурацию.",
    ],
    "users_subs_ended": ["истекла"],
    "users_subs_less_than_hour": ["осталось меньше часа"],
}
