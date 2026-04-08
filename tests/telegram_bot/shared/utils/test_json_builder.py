# tests/test_json_builder.py
import copy
import json

import pytest

from telegram_bot.shared.utils.json_builder import JSONBuilder


@pytest.fixture()
def base_template() -> dict:
    """Шаблон из infrastructure/api/json/post_user.py, упрощён до необходимого."""
    return {
        "id": "inbound_id",
        "settings": {
            "clients": [
                {
                    "id": None,
                    "flow": "xtls-rprx-vision",
                    "email": None,
                    "limitIp": 5,
                    "totalGB": 0,
                    "expiryTime": 0,
                    "enable": True,
                    "tgId": None,
                    "subId": None,
                    "reset": 0,
                }
            ]
        },
    }


def _assert_client_filled(client: dict, *, tg_id: int, uuid: str, email: str, period: int, sub_id: str) -> None:
    """Проверяет, что у клиента корректно обновлены ключевые поля."""
    assert client["id"] == uuid
    assert client["email"] == email
    assert client["tgId"] == str(tg_id)  # важна строка
    assert client["expiryTime"] == period
    assert client["subId"] == sub_id


# ---------- Хэппи-путь --------------------------------------------------------


def test_update_post_client_json_happy_path(base_template):
    tg_id = 123
    uuid = "uuid-1"
    email = "cat@mail.me"
    period = 3600
    sub_id = "sub-1"

    result = JSONBuilder.update_post_client_json(
        tg_id=tg_id,
        base_template=base_template,
        uuid=uuid,
        email=email,
        period=period,
        sub_id=sub_id,
    )

    # 1. settings превращены в строку JSON
    assert isinstance(result["settings"], str)

    # 2. Достаём клиентов из сериализованной строки и проверяем поля
    settings = json.loads(result["settings"])
    clients = settings["clients"]
    assert len(clients) == 1
    _assert_client_filled(clients[0], tg_id=tg_id, uuid=uuid, email=email, period=period, sub_id=sub_id)


# ---------- Несколько клиентов ------------------------------------------------


def test_update_post_client_json_multiple_clients(base_template):
    # клонируем клиента, имитируя несколько устройств
    base_template["settings"]["clients"].append(copy.deepcopy(base_template["settings"]["clients"][0]))

    tg_id = 555
    uuid = "uuid-x"
    email = "multi@cat.io"
    period = 7200
    sub_id = "sub-x"

    result = JSONBuilder.update_post_client_json(
        tg_id=tg_id,
        base_template=base_template,
        uuid=uuid,
        email=email,
        period=period,
        sub_id=sub_id,
    )

    settings = json.loads(result["settings"])
    clients = settings["clients"]
    assert len(clients) == 2
    for client in clients:
        _assert_client_filled(client, tg_id=tg_id, uuid=uuid, email=email, period=period, sub_id=sub_id)


# ---------- Шаблон не мутируется ---------------------------------------------


def test_update_post_client_json_does_not_mutate_template(base_template):
    snapshot = copy.deepcopy(base_template)

    JSONBuilder.update_post_client_json(
        tg_id=1,
        base_template=base_template,
        uuid="u",
        email="e",
        period=0,
        sub_id="s",
    )

    # базовый шаблон должен остаться неизменным
    assert base_template == snapshot


# ---------------------------------------------------------------------------
# 1. Отсутствие ключей / неверные типы
# ---------------------------------------------------------------------------


def test_missing_settings_key():
    tmp = {"id": "x"}
    with pytest.raises(KeyError):
        JSONBuilder.update_post_client_json(1, tmp, "u", "e", 1, "s")


def test_missing_clients_key():
    tmp = {"id": "x", "settings": {}}
    with pytest.raises(KeyError):
        JSONBuilder.update_post_client_json(1, tmp, "u", "e", 1, "s")


def test_clients_not_a_list():
    tmp = {"id": "x", "settings": {"clients": "not_list"}}
    with pytest.raises(AttributeError):
        JSONBuilder.update_post_client_json(1, tmp, "u", "e", 1, "s")


# ---------------------------------------------------------------------------
# 2. Пустой список клиентов
# ---------------------------------------------------------------------------


def test_clients_empty_list(base_template):
    base_template["settings"]["clients"] = []

    res = JSONBuilder.update_post_client_json(42, base_template, "uid", "mail@cat", 0, "sub")
    # settings должна остаться валидной JSON-строкой
    settings = json.loads(res["settings"])
    assert settings["clients"] == []


# ---------------------------------------------------------------------------
# 3. Сохранение «лишних» полей
# ---------------------------------------------------------------------------


def test_preserve_extra_fields(base_template):
    base_template["settings"]["clients"][0]["extra"] = "MEOW"

    res = JSONBuilder.update_post_client_json(7, base_template, "uid", "m@c", 10, "sub")
    settings = json.loads(res["settings"])
    assert settings["clients"][0]["extra"] == "MEOW"  # не стёрлось


# ---------------------------------------------------------------------------
# 4. Нулевой и отрицательный period
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("period", [0, -3600])
def test_period_edge_values(base_template, period):
    res = JSONBuilder.update_post_client_json(99, base_template, "u", "e", period, "s")
    settings = json.loads(res["settings"])
    assert settings["clients"][0]["expiryTime"] == period


# ---------------------------------------------------------------------------
# 5. Преобразование tg_id к строке
# ---------------------------------------------------------------------------


def test_tg_id_becomes_string(base_template):
    res = JSONBuilder.update_post_client_json(123, base_template, "u", "e", 1, "s")
    tg_id = json.loads(res["settings"])["clients"][0]["tgId"]
    assert tg_id == "123"
    assert isinstance(tg_id, str)


# ---------------------------------------------------------------------------
# 6. Идемпотентность
# ---------------------------------------------------------------------------


def test_idempotency(base_template):
    params = dict(tg_id=1, uuid="u", email="e", period=1, sub_id="s")

    first = JSONBuilder.update_post_client_json(base_template=base_template, **params)
    second = JSONBuilder.update_post_client_json(base_template=base_template, **params)

    assert first == second
    # ещё раз убеждаемся, что результат всегда даёт валидный JSON
    json.loads(first["settings"])


# ---------------------------------------------------------------------------
# 7. Шаблон не мутируется (safety-net)
# ---------------------------------------------------------------------------


def test_original_template_unchanged(base_template):
    snapshot = copy.deepcopy(base_template)
    JSONBuilder.update_post_client_json(1, base_template, "u", "e", 1, "s")
    assert base_template == snapshot


def test_update_post_client_json_sets_total_bytes_when_provided(base_template):
    result = JSONBuilder.update_post_client_json(
        tg_id=1,
        base_template=base_template,
        uuid="uuid-1",
        email="cat@mail.me",
        period=3600,
        sub_id="sub-1",
        total_bytes=123456789,
    )

    settings = json.loads(result["settings"])
    assert settings["clients"][0]["totalGB"] == 123456789
