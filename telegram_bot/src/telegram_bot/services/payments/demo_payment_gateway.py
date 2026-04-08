from __future__ import annotations

from urllib.parse import urlencode

from shared.config.config import (
    FRONTEND_LINK,
    PAYMENT_DEMO_AUTO_PAID,
    PAYMENT_DEMO_CHECKOUT_PATH,
)
from shared.constants.payments import (
    RUNTIME_PAYMENT_STATUS_PAID,
    RUNTIME_PAYMENT_STATUS_PENDING,
)
from shared.utils.logging_utils import logger
from telegram_bot.services.payments.payment_gateway import PaymentGateway
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator


class DemoPaymentGateway(PaymentGateway):
    def __init__(
        self,
        *,
        code: str,
        label: str,
        uuid: UUIDGenerator,
        frontend_link: str = FRONTEND_LINK,
        checkout_path: str = PAYMENT_DEMO_CHECKOUT_PATH,
        auto_paid: bool = PAYMENT_DEMO_AUTO_PAID,
    ) -> None:
        self.code = str(code).strip().lower()
        self.label = str(label).strip() or self.code
        self.uuid = uuid
        self.frontend_link = str(frontend_link).rstrip("/")
        self.checkout_path = "/" + str(checkout_path).strip().lstrip("/")
        self.auto_paid = bool(auto_paid)

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

        payment_id = f"{self.code}_{self.uuid.generate_id()}"
        status = RUNTIME_PAYMENT_STATUS_PENDING
        logger.info(
            "Demo payment created: "
            f"provider={self.code}, channel={channel}, tg_id={tg_id}, "
            f"user_id={user_id}, payment_id={payment_id}"
        )

        query = urlencode(
            {
                "payment_id": payment_id,
                "provider": self.label,
                "product": str(product.get("label") or product.get("payload") or ""),
                "amount": str(product.get("amount") or 0),
                "return_url": return_url,
            }
        )
        return {
            "id": payment_id,
            "status": status,
            "url": f"{self.frontend_link}{self.checkout_path}?{query}",
            "confirmed": False,
        }

    async def find_payment_status(self, payment_id: str) -> str:
        logger.info(
            f"Demo payment status requested: provider={self.code}, payment_id={payment_id}"
        )
        return RUNTIME_PAYMENT_STATUS_PAID if self.auto_paid else RUNTIME_PAYMENT_STATUS_PENDING


def build_demo_payment_gateways(uuid: UUIDGenerator) -> dict[str, DemoPaymentGateway]:
    from shared.config.config import (
        PAYMENT_PROVIDER_CARD_CODE,
        PAYMENT_PROVIDER_CARD_LABEL,
        PAYMENT_PROVIDER_WALLET_CODE,
        PAYMENT_PROVIDER_WALLET_LABEL,
    )

    return {
        PAYMENT_PROVIDER_CARD_CODE: DemoPaymentGateway(
            code=PAYMENT_PROVIDER_CARD_CODE,
            label=PAYMENT_PROVIDER_CARD_LABEL,
            uuid=uuid,
        ),
        PAYMENT_PROVIDER_WALLET_CODE: DemoPaymentGateway(
            code=PAYMENT_PROVIDER_WALLET_CODE,
            label=PAYMENT_PROVIDER_WALLET_LABEL,
            uuid=uuid,
        ),
    }
