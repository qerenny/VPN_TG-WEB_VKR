from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass


TOKEN_PREFIX = "tgw"
TOKEN_PURPOSE = "telegram_web_login"


@dataclass(frozen=True, slots=True)
class TelegramWebLoginClaims:
    tg_id: int
    user_id: int
    purpose: str = TOKEN_PURPOSE
    version: int = 1


def issue_telegram_web_login_token(*, tg_id: int, user_id: int, secret: str) -> str:
    claims = {
        "v": 1,
        "purpose": TOKEN_PURPOSE,
        "tg_id": int(tg_id),
        "user_id": int(user_id),
    }
    payload_bytes = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_token = _b64encode(payload_bytes)
    signature_token = _b64encode(_sign(payload_bytes, secret))
    return f"{TOKEN_PREFIX}.{payload_token}.{signature_token}"


def verify_telegram_web_login_token(
    raw_token: str,
    *,
    secret: str,
) -> TelegramWebLoginClaims | None:
    token = str(raw_token or "").strip()
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_PREFIX:
        return None

    try:
        payload_bytes = _b64decode(parts[1])
        provided_signature = _b64decode(parts[2])
    except Exception:
        return None

    expected_signature = _sign(payload_bytes, secret)
    if not hmac.compare_digest(provided_signature, expected_signature):
        return None

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
        if payload.get("purpose") != TOKEN_PURPOSE:
            return None
        return TelegramWebLoginClaims(
            tg_id=int(payload["tg_id"]),
            user_id=int(payload["user_id"]),
            purpose=str(payload["purpose"]),
            version=int(payload.get("v", 1)),
        )
    except Exception:
        return None


def _sign(payload: bytes, secret: str) -> bytes:
    return hmac.new(str(secret).encode("utf-8"), payload, hashlib.sha256).digest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))
