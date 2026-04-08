# shared/contracts/payment_gateway.py
from abc import ABC, abstractmethod


class PaymentGateway(ABC):
    @abstractmethod
    async def create_payment(
        self,
        tg_id: int | None = None,
        return_url: str = "",
        product: dict | None = None,
        *,
        user_id: int | None = None,
        customer_email: str | None = None,
        channel: str = "telegram",
    ) -> dict: ...

    @abstractmethod
    async def find_payment_status(self, payment_id: str) -> str: ...
