from __future__ import annotations

from backend.services.email.email_types import OutgoingEmail
from shared.config.settings import MailSettings


class EmailTemplateService:
    def __init__(self, settings: MailSettings) -> None:
        self.settings = settings

    @property
    def service_name(self) -> str:
        return self.settings.from_name or "Remote Access Service"

    def build_verification_code_email(
        self,
        *,
        to_email: str,
        code: str,
        expires_minutes: int,
    ) -> OutgoingEmail:
        return self._build_code_email(
            to_email=to_email,
            subject=f"{self.service_name}: код подтверждения email",
            intro=f"Код подтверждения для входа в {self.service_name}.",
            code=code,
            expires_minutes=expires_minutes,
            outro="Если вы не запрашивали этот код, просто проигнорируйте письмо.",
        )

    def build_password_reset_code_email(
        self,
        *,
        to_email: str,
        code: str,
        expires_minutes: int,
    ) -> OutgoingEmail:
        return self._build_code_email(
            to_email=to_email,
            subject=f"{self.service_name}: код сброса пароля",
            intro=f"Код для сброса пароля {self.service_name}.",
            code=code,
            expires_minutes=expires_minutes,
            outro="Если вы не запрашивали сброс пароля, просто проигнорируйте письмо.",
        )

    def build_linking_confirmation_email(
        self,
        *,
        to_email: str,
        code: str,
        expires_minutes: int,
    ) -> OutgoingEmail:
        return self._build_code_email(
            to_email=to_email,
            subject=f"{self.service_name}: подтверждение привязки аккаунта",
            intro=f"Код подтверждения привязки аккаунта {self.service_name}.",
            code=code,
            expires_minutes=expires_minutes,
            outro="Если вы не запрашивали привязку аккаунта, просто проигнорируйте письмо.",
        )

    def _build_code_email(
        self,
        *,
        to_email: str,
        subject: str,
        intro: str,
        code: str,
        expires_minutes: int,
        outro: str,
    ) -> OutgoingEmail:
        text_body = (
            f"{intro}\n\n"
            f"Код: {code}\n"
            f"Действует {expires_minutes} минут.\n\n"
            f"{outro}"
        )
        html_body = (
            f"<p>{intro}</p>"
            f"<p><strong>{code}</strong></p>"
            f"<p>Код действует {expires_minutes} минут.</p>"
            f"<p>{outro}</p>"
        )
        return OutgoingEmail(
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            reply_to=self.settings.reply_to or None,
        )
