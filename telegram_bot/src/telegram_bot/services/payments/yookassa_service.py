from yookassa import Configuration, Payment

from shared.config.config import CONFIGURATION_ACCOUNT_ID, CONFIGURATION_SECRET_KEY
from shared.utils.logging_utils import logger
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator

Configuration.account_id = CONFIGURATION_ACCOUNT_ID
Configuration.secret_key = CONFIGURATION_SECRET_KEY


class YooKassaService:
    def __init__(self, uuid: UUIDGenerator):
        self.uuid = uuid
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
        logger.info(
            "Starting payment creation for "
            f"channel={channel}, tg_id={tg_id}, user_id={user_id}, product={product['label']}"
        )

        idempotence_key = str(self.uuid.generate_id())
        amount = f"{product['amount'] / 100:.2f}"
        description = product["description"]
        payload = product["payload"]
        
        receipt_email = (
            str(customer_email)
            if customer_email
            else None
        )
        receipt = None
        if receipt_email:
            receipt = {
                "customer": {
                    "email": receipt_email,
                },
                "items": [
                    {
                        "description": product["label"],
                        "quantity": "1.00",
                        "amount": {
                            "value": f"{amount}",
                            "currency": "RUB"
                        },
                        "vat_code": 1,
                    }
                ],
            }
        metadata = {"tg_id": str(tg_id), "product": payload}
        if user_id is not None or str(channel).strip().lower() != "telegram":
            metadata.update(
                {
                    "channel": str(channel),
                    "user_id": str(user_id) if user_id is not None else "",
                }
            )
        payment_payload = {
            "amount": {"value": f"{amount}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": description,
            "metadata": metadata,
        }
        if receipt is not None:
            payment_payload["receipt"] = receipt
        payment = Payment.create(payment_payload, idempotence_key)
        logger.info(
            "Payment created for "
            f"channel={channel}, tg_id={tg_id}, user_id={user_id} with id={payment.id}"
        )

        return {
            "id": payment.id,
            "status": payment.status,
            "url": payment.confirmation.confirmation_url,
            "confirmed": False,
        }
    async def find_payment_status(self, payment_id: str) -> str:
        payment = Payment.find_one(payment_id)
        if payment is None:
            raise RuntimeError(f"YooKassa returned no payment object for payment_id={payment_id}")

        status = getattr(payment, "status", None)
        if not status:
            raise RuntimeError(
                f"YooKassa returned payment without status for payment_id={payment_id}"
            )
        logger.info(f"Checked status for payment_id={payment_id}: {status}")
        return str(status)
