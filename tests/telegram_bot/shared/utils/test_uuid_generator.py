# tests/test_uuid_generator.py
import re
import uuid

import pytest

from telegram_bot.shared.utils.uuid_generator import UUIDGenerator

# ---------------------------------------------------------------------------
# UUID-генерация
# ---------------------------------------------------------------------------


def test_generate_id_returns_valid_uuid4():
    raw = UUIDGenerator.generate_id()
    obj = uuid.UUID(raw, version=4)
    assert obj.version == 4
    assert str(obj) == raw.lower()


# ---------------------------------------------------------------------------
# Email-генерация (Haikunator)
# ---------------------------------------------------------------------------

HEX_RE = re.compile(r"^[0-9a-f]+$")
DEC_RE = re.compile(r"^[0-9]+$")


def _split_haikunated(email: str, delimiter: str):
    parts = email.split(delimiter)
    return parts


def test_generate_email_default():
    adjective, noun = _split_haikunated(UUIDGenerator.generate_email(), "-")

    assert adjective
    assert noun


@pytest.mark.parametrize(
    "delimiter,token_length",
    [("_", 6), (":", 2), (".", 8)],
)
def test_generate_email_custom_delimiter_and_length(delimiter, token_length):
    mail = UUIDGenerator.generate_email(delimiter=delimiter, token_length=token_length)

    assert delimiter in mail
    parts = _split_haikunated(mail, delimiter)
    assert len(parts) == 3
    token = parts[2]

    assert len(token) == token_length
    assert HEX_RE.fullmatch(token)


def test_generate_email_decimal_token():
    _, _, token = _split_haikunated(
        UUIDGenerator.generate_email(token_length=4, token_hex=False),
        "-",
    )

    assert len(token) == 4
    assert DEC_RE.fullmatch(token)
