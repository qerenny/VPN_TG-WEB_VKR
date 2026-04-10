from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlmodel import select

from shared.config.config import FRONTEND_LINK
from shared.config.settings import get_product_settings
from shared.config.database.session import get_db_session
from shared.models.payments.plan_model import Plan
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.user_profile_model import UserProfile
from shared.models.users.web_account_model import WebAccount
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_TRAFFIC_LIMITED
from shared.utils.timestamp_utils import TimestampUtils
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
    PaymentSnapshot,
)


@dataclass(frozen=True, slots=True)
class WebCheckoutResult:
    payment_id: str
    status: str
    checkout_url: str
    provider: str
    plan_code: str
    plan_name: str
    scope: str
    amount: str
    currency: str


class WebCheckoutService:
    def __init__(
        self,
        *,
        payment_repository: PaymentRepository,
        gateways: dict,
        timestamp: TimestampUtils,
    ) -> None:
        self.payment_repository = payment_repository
        self.gateways = gateways
        self.timestamp = timestamp

    async def create_checkout(
        self,
        *,
        user_id: int,
        plan_code: str,
        method: str,
        expected_scope: str | None = None,
    ) -> WebCheckoutResult:
        gateway = self.gateways.get(str(method).strip().lower())
        if gateway is None:
            raise ValueError(f"Unsupported payment method: {method}")

        async with get_db_session() as session:
            plan = (
                await session.execute(
                    select(Plan).where(Plan.code == str(plan_code).strip().lower())
                )
            ).scalar_one_or_none()
            if plan is None:
                raise ValueError(f"Plan not found: {plan_code}")
            if not bool(plan.is_active):
                raise ValueError(f"Plan {plan_code} is inactive")
            if expected_scope is not None and str(plan.scope) != str(expected_scope):
                raise ValueError(
                    f"Plan {plan_code} does not belong to scope {expected_scope}"
                )
            if plan.price_amount is None or Decimal(plan.price_amount) <= Decimal("0"):
                raise ValueError(f"Plan {plan_code} has no positive price")

            web_account = (
                await session.execute(
                    select(WebAccount).where(
                        WebAccount.user_id == int(user_id),
                        WebAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            user_profile = await session.get(UserProfile, int(user_id))

            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.user_id == int(user_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

        customer_email = None
        if web_account is not None and getattr(web_account, "email", None):
            customer_email = str(web_account.email)
        elif user_profile is not None and getattr(user_profile, "preferred_contact_email", None):
            customer_email = str(user_profile.preferred_contact_email)

        product = self._build_product(plan)
        payment_data = await gateway.create_payment(
            return_url=self._build_return_url(),
            product=product,
            tg_id=int(telegram_account.telegram_id) if telegram_account is not None else None,
            user_id=int(user_id),
            customer_email=customer_email,
            channel="web",
        )

        await self.payment_repository.create(
            PaymentSnapshot(
                payment_id=str(payment_data["id"]),
                user_id=int(user_id),
                tg_id=int(telegram_account.telegram_id) if telegram_account is not None else None,
                status=str(payment_data["status"]),
                payload=str(plan.payload),
                created_at=self.timestamp.current_timestamp(),
                confirmed=bool(payment_data.get("confirmed", False)),
                method=str(method).strip().lower(),
            )
        )

        return WebCheckoutResult(
            payment_id=str(payment_data["id"]),
            status=str(payment_data["status"]),
            checkout_url=str(payment_data["url"]),
            provider=str(method).strip().lower(),
            plan_code=str(plan.code),
            plan_name=str(plan.name),
            scope=str(plan.scope),
            amount=str(plan.price_amount),
            currency=str(plan.currency),
        )

    @staticmethod
    def _build_product(plan: Plan) -> dict:
        product_name = get_product_settings().name
        if str(plan.scope) == PRODUCT_SCOPE_TRAFFIC_LIMITED:
            label = f"Лимит трафика • {plan.name}"
            description = f"{product_name} traffic-limited access: {plan.name}"
        elif str(plan.scope) == PRODUCT_SCOPE_STANDARD:
            label = f"Доступ • {plan.name}"
            description = f"{product_name} time-limited access: {plan.name}"
        else:
            label = str(plan.name)
            description = f"{product_name}: {plan.name}"

        amount = int(Decimal(plan.price_amount) * 100)
        return {
            "payload": str(plan.payload),
            "label": label,
            "description": description,
            "amount": amount,
        }

    @staticmethod
    def _build_return_url() -> str:
        return f"{FRONTEND_LINK.rstrip('/')}/app/payments"
