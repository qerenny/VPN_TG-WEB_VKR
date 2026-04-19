from shared.config.config import _build_telegram_link, normalize_telegram_button_url


def test_normalize_telegram_button_url_keeps_public_url():
    assert (
        normalize_telegram_button_url("https://frontend.example.com/subscription/")
        == "https://frontend.example.com/subscription"
    )


def test_normalize_telegram_button_url_rejects_localhost():
    assert normalize_telegram_button_url("http://localhost:5173/subscription") == ""


def test_normalize_telegram_button_url_rejects_private_ip():
    assert normalize_telegram_button_url("http://192.168.1.10:5173/subscription") == ""


def test_build_telegram_link_from_username():
    assert _build_telegram_link("@remote_access_news") == "https://t.me/remote_access_news"


def test_build_telegram_link_keeps_invite_link():
    assert _build_telegram_link("https://t.me/+invite-token") == "https://t.me/+invite-token"


def test_build_telegram_link_rejects_display_name_with_spaces():
    assert _build_telegram_link("System Example") == ""
