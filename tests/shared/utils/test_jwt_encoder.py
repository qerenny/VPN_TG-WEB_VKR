from datetime import datetime, timedelta, timezone

import pytest
import jwt
from jwt import ExpiredSignatureError, PyJWTError

from shared.utils.jwt_encoder import JWTEncoder

SECRET = "test_secret_with_at_least_32_bytes"
ALGHORITHM = "HS256"


@pytest.fixture
def encoder() -> JWTEncoder:
    return JWTEncoder(secret=SECRET, algorithm=ALGHORITHM, expire_minutes=1)


def test_jwt_encode_decode_success(encoder: JWTEncoder):
    payload = {"user_id": 123}
    token = encoder.encode(payload)

    decoded = encoder.decode(token)

    assert decoded["user_id"] == 123
    assert "exp" in decoded


def test_jwt_expired_token():
    encoder = JWTEncoder(secret=SECRET, algorithm=ALGHORITHM, expire_minutes=-1)
    payload = {"user_id": 456}
    token = encoder.encode(payload)

    with pytest.raises(ExpiredSignatureError):
        encoder.decode(token)


def test_jwt_invalid_token(encoder: JWTEncoder):
    fake_token = "abc.def.ghi"

    with pytest.raises(PyJWTError):
        encoder.decode(fake_token)


def test_jwt_token_expiry_exact_timestamp():
    encoder = JWTEncoder(secret=SECRET, algorithm=ALGHORITHM, expire_minutes=5)
    now = datetime.now(timezone.utc)
    token = encoder.encode({"sub": "test"})

    decoded = jwt.decode(token, SECRET, algorithms=[ALGHORITHM])
    exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)

    assert timedelta(minutes=4) <= (exp - now) <= timedelta(minutes=5)


def test_encode_does_not_mutate_input(encoder: JWTEncoder):
    original = {"user": "abc"}
    copy = original.copy()
    encoder.encode(original)
    assert original == copy


def test_exp_is_utc(encoder: JWTEncoder):
    token = encoder.encode({"some": "value"})
    decoded = jwt.decode(token, encoder.secret, algorithms=[encoder.algorithm], options={"verify_signature": False})
    exp = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
    assert exp.tzinfo is not None and exp.tzinfo.utcoffset(exp) == timedelta(0)


def test_jwtencoder_custom_parameters():
    encoder = JWTEncoder(secret="abc", algorithm="HS512", expire_minutes=10)
    assert encoder.secret == "abc"
    assert encoder.algorithm == "HS512"
    assert encoder.expire_minutes == 10
