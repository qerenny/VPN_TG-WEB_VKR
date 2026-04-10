from telegram_bot.shared import keyboards


def _button_texts(markup):
    return [button.text for row in markup.keyboard for button in row]


def test_build_main_menu_markup_hides_info_channel_when_disabled(monkeypatch):
    monkeypatch.setattr(keyboards, "BOT_INFO_CHANNEL_ENABLED", False)
    monkeypatch.setattr(keyboards, "WHO_WE_ARE_LINK", "")
    monkeypatch.setattr(keyboards, "DOCS_MENU_ENABLED", False)

    markup = keyboards.build_main_menu_markup(referrals_enabled=False)

    texts = _button_texts(markup)
    assert keyboards.INFO_CHANNEL not in texts
    assert keyboards.WHO_WE_ARE not in texts
    assert keyboards.INSTRUCTIONS not in texts
    assert keyboards.HELP in texts


def test_build_main_menu_markup_shows_info_channel_when_enabled(monkeypatch):
    monkeypatch.setattr(keyboards, "BOT_INFO_CHANNEL_ENABLED", True)
    monkeypatch.setattr(keyboards, "BOT_INFO_CHANNEL_TG_LINK", "https://t.me/remote_access_info")
    monkeypatch.setattr(keyboards, "WHO_WE_ARE_LINK", "https://example.com/about")
    monkeypatch.setattr(keyboards, "DOCS_MENU_ENABLED", True)

    markup = keyboards.build_main_menu_markup(referrals_enabled=False)

    texts = _button_texts(markup)
    assert keyboards.INFO_CHANNEL in texts
    assert keyboards.WHO_WE_ARE in texts
    assert keyboards.INSTRUCTIONS in texts
