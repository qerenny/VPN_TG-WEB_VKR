from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from jwt import PyJWTError

from backend.services.user.user_manager_service import UserManagerService


@pytest.fixture
def service_and_mocks():
    repo = AsyncMock()
    jwt_encoder = MagicMock()
    service = UserManagerService(repo=repo, jwt_encoder=jwt_encoder)
    return service, repo, jwt_encoder


@pytest.mark.asyncio
async def test_get_user_info_returns_snapshot(service_and_mocks):
    service, repo, jwt_encoder = service_and_mocks
    jwt_encoder.decode.return_value = {"tg_id": 123, "email": "user@example.com"}
    repo.get.return_value = SimpleNamespace(
        tg_id=123,
        email="user@example.com",
        expiration_date=1700000000,
        login_date=1690000000,
        sub_id="sub-123",
    )

    result = await service.get_user_info("token")

    assert result == {
        "tg_id": 123,
        "email": "user@example.com",
        "expiration_date": 1700000000,
        "login_date": 1690000000,
        "sub_id": "sub-123",
    }


@pytest.mark.asyncio
async def test_get_user_info_rejects_invalid_signature(service_and_mocks):
    service, repo, jwt_encoder = service_and_mocks
    jwt_encoder.decode.side_effect = PyJWTError("bad token")

    with pytest.raises(HTTPException) as exc:
        await service.get_user_info("token")

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid token signature or expired"


@pytest.mark.asyncio
async def test_get_user_info_rejects_invalid_payload(service_and_mocks):
    service, repo, jwt_encoder = service_and_mocks
    jwt_encoder.decode.return_value = {"email": "user@example.com"}

    with pytest.raises(HTTPException) as exc:
        await service.get_user_info("token")

    assert exc.value.status_code == 400
    assert exc.value.detail == "Invalid token format"


@pytest.mark.asyncio
async def test_get_user_info_rejects_email_mismatch(service_and_mocks):
    service, repo, jwt_encoder = service_and_mocks
    jwt_encoder.decode.return_value = {"tg_id": 123, "email": "user@example.com"}
    repo.get.return_value = SimpleNamespace(
        tg_id=123,
        email="other@example.com",
        expiration_date=None,
        login_date=1690000000,
        sub_id="sub-123",
    )

    with pytest.raises(HTTPException) as exc:
        await service.get_user_info("token")

    assert exc.value.status_code == 404
    assert exc.value.detail == "Email mismatch"
