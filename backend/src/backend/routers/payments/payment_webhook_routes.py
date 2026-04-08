import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.services.payments.payment_webhook_service import PaymentWebhookService
from shared.config.config import (
    PAYMENT_PROVIDER_CARD_CODE,
    PAYMENT_PROVIDER_WALLET_CODE,
    PAYMENT_WEBHOOK_TOKEN,
    REDIS_PAYMENT_DEDUPE_PREFIX,
    REDIS_PAYMENT_DEDUPE_TTL_SECONDS,
    REDIS_PAYMENT_READY_QUEUE_KEY,
)
from shared.config.settings import RolloutFeatureFlags, get_product_feature_settings
from shared.constants.payments import RUNTIME_PAYMENT_STATUS_PAID
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
)
from shared.infrastructure.payment_sync_service import PaymentSyncService

router = APIRouter(prefix="/payments", tags=["payments"])


def _is_token_valid(token: str) -> bool:
    if not PAYMENT_WEBHOOK_TOKEN:
        return False
    return hmac.compare_digest(token, PAYMENT_WEBHOOK_TOKEN)


def _assert_webhook_auth(token: str) -> None:
    if not get_product_feature_settings().commerce_enabled:
        raise HTTPException(status_code=404, detail="Feature is disabled")
    if not PAYMENT_WEBHOOK_TOKEN:
        raise HTTPException(status_code=503, detail="Webhook token is not configured")
    if not _is_token_valid(token):
        raise HTTPException(status_code=403, detail="Invalid webhook token")


def _build_service(request: Request) -> PaymentWebhookService:
    redis_client = getattr(request.app.state, "redis_client", None)
    return PaymentWebhookService(
        repo=PaymentRepository(),
        redis_client=redis_client,
        ready_queue_key=REDIS_PAYMENT_READY_QUEUE_KEY,
        dedupe_prefix=REDIS_PAYMENT_DEDUPE_PREFIX,
        dedupe_ttl_seconds=REDIS_PAYMENT_DEDUPE_TTL_SECONDS,
        sync_service=PaymentSyncService(
            RolloutFeatureFlags(db_dual_write_payments=True)
        ),
    )


def _extract_yookassa_update(payload: dict[str, Any]) -> tuple[str, str]:
    obj = payload.get("object")
    if not isinstance(obj, dict):
        raise HTTPException(status_code=400, detail="Missing yookassa object")

    payment_id = str(obj.get("id", "")).strip()
    status = str(obj.get("status", "")).strip().lower()
    if not payment_id or not status:
        raise HTTPException(status_code=400, detail="Missing yookassa payment id or status")
    return payment_id, status


def _extract_cryptopay_update(payload: dict[str, Any]) -> tuple[str, str]:
    nested = payload.get("payload")
    source = nested if isinstance(nested, dict) else payload

    invoice_id = source.get("invoice_id")
    status_raw = source.get("status")
    if status_raw is None and str(payload.get("update_type", "")).lower() == "invoice_paid":
        status_raw = RUNTIME_PAYMENT_STATUS_PAID

    payment_id = str(invoice_id or "").strip()
    status = str(status_raw or "").strip().lower()
    if not payment_id or not status:
        raise HTTPException(status_code=400, detail="Missing cryptopay invoice id or status")
    return payment_id, status


def _extract_external_gateway_update(payload: dict[str, Any]) -> tuple[str, str]:
    payment_id = str(payload.get("payment_id", "")).strip()
    status = str(payload.get("status", "")).strip().lower()
    if not payment_id or not status:
        raise HTTPException(status_code=400, detail="Missing payment id or status")
    return payment_id, status


@router.post("/webhook/external/{method}/{token}")
async def external_gateway_webhook(method: str, token: str, request: Request):
    _assert_webhook_auth(token)
    method_key = str(method).strip().lower()
    allowed_methods = {PAYMENT_PROVIDER_CARD_CODE, PAYMENT_PROVIDER_WALLET_CODE}
    if method_key not in allowed_methods:
        raise HTTPException(status_code=404, detail="Payment method is not configured")

    try:
        payload = await request.json()
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from err
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    payment_id, status = _extract_external_gateway_update(payload)
    service = _build_service(request)
    result = await service.process_status_update(
        method=method_key,
        payment_id=payment_id,
        status=status,
        payload=payload,
    )

    return {"ok": True, **result}


@router.post("/webhook/yookassa/{token}")
async def yookassa_webhook(token: str, request: Request):
    _assert_webhook_auth(token)

    try:
        payload = await request.json()
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from err
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    payment_id, status = _extract_yookassa_update(payload)
    service = _build_service(request)
    result = await service.process_status_update(
        method="yookassa",
        payment_id=payment_id,
        status=status,
        payload=payload,
    )

    return {"ok": True, **result}


@router.post("/webhook/cryptopay/{token}")
async def cryptopay_webhook(token: str, request: Request):
    _assert_webhook_auth(token)

    try:
        payload = await request.json()
    except Exception as err:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from err
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    payment_id, status = _extract_cryptopay_update(payload)
    service = _build_service(request)
    result = await service.process_status_update(
        method="cryptopay",
        payment_id=payment_id,
        status=status,
        payload=payload,
    )

    return {"ok": True, **result}
