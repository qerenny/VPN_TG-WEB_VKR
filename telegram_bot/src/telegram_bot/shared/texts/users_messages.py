from shared.config.config import INBOUND_AMOUNT_OF_DEVICES

categories = {
    "users_options": [
        f"*Важно:* на `1` конфигурацию можно подключить не более `{INBOUND_AMOUNT_OF_DEVICES}` устройств.",
        f"Ограничение: максимум `{INBOUND_AMOUNT_OF_DEVICES}` устройств на одну конфигурацию.",
        f"Для стабильной работы используйте не более `{INBOUND_AMOUNT_OF_DEVICES}` устройств на одну конфигурацию.",
    ],
    "users_subs_ended": [" истекла"],
    "users_subs_less_than_hour": [" осталось меньше 1 часа"],
}
