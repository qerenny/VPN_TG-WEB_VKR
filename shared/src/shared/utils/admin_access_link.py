from __future__ import annotations

import math
import secrets
import time
from typing import Any

from shared.config.config import PRODUCT_REDIS_PREFIX
from shared.utils.jwt_encoder import JWTEncoder


ADMIN_BOOTSTRAP_KIND = "admin_bootstrap"
ADMIN_BOOTSTRAP_TTL_SECONDS = 120
_ADMIN_BOOTSTRAP_KEY_PREFIX = f"{PRODUCT_REDIS_PREFIX}:admin:bootstrap"
_memory_bootstrap_store: dict[str, float] = {}


async def create_admin_bootstrap_token(
    *,
    jwt_encoder: JWTEncoder,
    actor: str,
    tg_id: int,
    redis_client: Any | None,
    ttl_seconds: int = ADMIN_BOOTSTRAP_TTL_SECONDS,
) -> str:
    jti = secrets.token_urlsafe(16)
    expires_in_minutes = max(1, math.ceil(ttl_seconds / 60))
    token = JWTEncoder(
        secret=jwt_encoder.secret,
        algorithm=jwt_encoder.algorithm,
        expire_minutes=expires_in_minutes,
    ).encode(
        {
            "kind": ADMIN_BOOTSTRAP_KIND,
            "actor": actor,
            "tg_id": int(tg_id),
            "jti": jti,
        }
    )
    await _mark_bootstrap_jti(redis_client, jti, ttl_seconds)
    return token


async def consume_admin_bootstrap_token(
    *,
    jwt_encoder: JWTEncoder,
    token: str,
    redis_client: Any | None,
) -> dict[str, Any] | None:
    try:
        claims = jwt_encoder.decode(token)
    except Exception:
        return None

    if str(claims.get("kind") or "").strip() != ADMIN_BOOTSTRAP_KIND:
        return None

    jti = str(claims.get("jti") or "").strip()
    if not jti:
        return None

    if not await _consume_bootstrap_jti(redis_client, jti):
        return None

    return claims


async def _mark_bootstrap_jti(redis_client: Any | None, jti: str, ttl_seconds: int) -> None:
    if redis_client is None:
        _memory_bootstrap_store[jti] = time.time() + max(1, ttl_seconds)
        return

    try:
        await redis_client.set(
            f"{_ADMIN_BOOTSTRAP_KEY_PREFIX}:{jti}",
            "1",
            ex=max(1, ttl_seconds),
            nx=True,
        )
    except Exception:
        _memory_bootstrap_store[jti] = time.time() + max(1, ttl_seconds)


async def _consume_bootstrap_jti(redis_client: Any | None, jti: str) -> bool:
    if redis_client is None:
        return _consume_bootstrap_jti_from_memory(jti)

    key = f"{_ADMIN_BOOTSTRAP_KEY_PREFIX}:{jti}"
    try:
        exists = await redis_client.get(key)
        if not exists:
            return False
        await redis_client.delete(key)
        return True
    except Exception:
        return _consume_bootstrap_jti_from_memory(jti)


def _consume_bootstrap_jti_from_memory(jti: str) -> bool:
    expires_at = _memory_bootstrap_store.get(jti)
    if expires_at is None:
        return False
    if expires_at <= time.time():
        _memory_bootstrap_store.pop(jti, None)
        return False
    _memory_bootstrap_store.pop(jti, None)
    return True
