from aiosend import MAINNET, CryptoPay
from aiosend.types import Invoice
import httpx

from shared.config.config import CRYPTOPAY_TOKEN
from shared.constants.payments import RUNTIME_PAYMENT_STATUS_PAID
from shared.utils.logging_utils import logger, log_with_throttle


class CryptoPayService:
    _API_BASE_URL = "https://pay.crypt.bot/api"
    _WARNING_LOG_COOLDOWN_SECONDS = 300.0

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            self._client = CryptoPay(token=CRYPTOPAY_TOKEN, network=MAINNET)
        return self._client

    async def create_payment(
        self,
        tg_id: int | None = None,
        return_url: str = "",
        product: dict | None = None,
        *,
        user_id: int | None = None,
        customer_email: str | None = None,
        channel: str = "telegram",
    ) -> dict:
        if product is None:
            raise ValueError("product is required")
        description = product["description"]
        payload = product["payload"]
        amount = product["amount"] / 100

        invoice: Invoice = await self._get_client().create_invoice(
            amount=amount,
            currency_type="fiat",
            fiat="RUB",
            description=description,
            payload=payload,
            allow_anonymous=True,
            allow_comments=False,
            paid_btn_name="openBot",
            paid_btn_url=return_url,
        )
        return {
            "id": str(invoice.invoice_id),
            "status": invoice.status,
            "url": invoice.bot_invoice_url,
            "confirmed": invoice.status == RUNTIME_PAYMENT_STATUS_PAID,
        }

    async def find_payment_status(self, invoice_id: int) -> str:
        try:
            invoices = await self._get_client().get_invoices(invoice_ids=[invoice_id])
            return self._extract_status(invoices)
        except Exception as exc:
            if "Failed to deserialize object" not in str(exc):
                raise

            log_with_throttle(
                "WARNING",
                f"cryptopay-sdk-deserialize:{invoice_id}",
                "CryptoPay SDK failed to deserialize invoice payload for "
                f"invoice_id={invoice_id}; trying raw API fallback: {exc}",
                cooldown_seconds=self._WARNING_LOG_COOLDOWN_SECONDS,
            )
            return await self._find_payment_status_via_raw_api(invoice_id)

    async def _find_payment_status_via_raw_api(self, invoice_id: int) -> str:
        request_payload = {"invoice_ids": str(invoice_id)}
        request_headers = {"Crypto-Pay-API-Token": CRYPTOPAY_TOKEN}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self._API_BASE_URL}/getInvoices",
                    headers=request_headers,
                    json=request_payload,
                )
                response.raise_for_status()
                response_payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log_with_throttle(
                "WARNING",
                f"cryptopay-raw-fallback:{invoice_id}:{type(exc).__name__}",
                "CryptoPay raw API fallback failed for "
                f"invoice_id={invoice_id}; returning unknown status: {exc}",
                cooldown_seconds=self._WARNING_LOG_COOLDOWN_SECONDS,
            )
            return "unknown"

        if not response_payload.get("ok"):
            logger.error(
                "CryptoPay raw API getInvoices returned non-ok response for "
                f"invoice_id={invoice_id}: {response_payload}"
            )
            return "unknown"

        result = response_payload.get("result")
        if isinstance(result, dict):
            invoices = result.get("items") or result.get("invoices") or []
        elif isinstance(result, list):
            invoices = result
        else:
            invoices = []
        return self._extract_status(invoices)

    @staticmethod
    def _extract_status(invoices: list) -> str:
        if not invoices:
            return "unknown"

        first_invoice = invoices[0]
        if isinstance(first_invoice, dict):
            return str(first_invoice.get("status", "unknown"))

        status = getattr(first_invoice, "status", None)
        return str(status) if status else "unknown"
