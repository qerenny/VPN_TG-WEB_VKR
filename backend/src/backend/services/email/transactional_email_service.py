from __future__ import annotations

from backend.services.email.email_delivery_service import EmailDeliveryService
from backend.services.email.email_template_service import EmailTemplateService


class TransactionalEmailService:
    def __init__(
        self,
        *,
        delivery_service: EmailDeliveryService,
        template_service: EmailTemplateService,
    ) -> None:
        self.delivery_service = delivery_service
        self.template_service = template_service

    async def send_verification_code(
        self,
        *,
        to_email: str,
        code: str,
        expires_minutes: int,
    ) -> None:
        await self.delivery_service.send(
            self.template_service.build_verification_code_email(
                to_email=to_email,
                code=code,
                expires_minutes=expires_minutes,
            )
        )

    async def send_password_reset_code(
        self,
        *,
        to_email: str,
        code: str,
        expires_minutes: int,
    ) -> None:
        await self.delivery_service.send(
            self.template_service.build_password_reset_code_email(
                to_email=to_email,
                code=code,
                expires_minutes=expires_minutes,
            )
        )

    async def send_linking_confirmation_code(
        self,
        *,
        to_email: str,
        code: str,
        expires_minutes: int,
    ) -> None:
        await self.delivery_service.send(
            self.template_service.build_linking_confirmation_email(
                to_email=to_email,
                code=code,
                expires_minutes=expires_minutes,
            )
        )
