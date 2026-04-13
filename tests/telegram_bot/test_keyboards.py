from telegram_bot.shared import keyboards


def _button_texts(markup):
    return [button.text for row in markup.keyboard for button in row]


def test_build_main_menu_button_markup_returns_only_main_menu():
    markup = keyboards.build_main_menu_button_markup()

    texts = _button_texts(markup)
    assert texts == [keyboards.MAIN_MENU]
    assert markup.keyboard[0][0].callback_data == "menu_start"


def test_add_subscription_navigation_buttons_adds_back_and_main_menu():
    markup = keyboards.add_subscription_navigation_buttons(keyboards.InlineKeyboardMarkup())

    texts = _button_texts(markup)
    assert texts == [keyboards.BACK_TO_SUBSCRIPTIONS, keyboards.MAIN_MENU]
    assert markup.keyboard[0][0].callback_data == "profile_subscriptions"
    assert markup.keyboard[1][0].callback_data == "menu_start"


def test_add_access_request_back_button_adds_request_menu_button():
    markup = keyboards.add_access_request_back_button(keyboards.InlineKeyboardMarkup())

    texts = _button_texts(markup)
    assert texts == ["⬅️ К запросу доступа"]
    assert markup.keyboard[0][0].callback_data == "sub_access_request"


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
