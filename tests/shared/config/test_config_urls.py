from shared.config.config import normalize_telegram_button_url


def test_normalize_telegram_button_url_keeps_public_url():
    assert (
        normalize_telegram_button_url("https://frontend.example.com/subscription/")
        == "https://frontend.example.com/subscription"
    )


def test_normalize_telegram_button_url_rejects_localhost():
    assert normalize_telegram_button_url("http://localhost:5173/subscription") == ""


def test_normalize_telegram_button_url_rejects_private_ip():
    assert normalize_telegram_button_url("http://192.168.1.10:5173/subscription") == ""
