from backend.services.email.email_template_service import EmailTemplateService
from shared.config.settings import MailSettings


def _mail_settings() -> MailSettings:
    return MailSettings(
        enabled=False,
        provider="noop",
        from_email="noreply@example.com",
        from_name="Remote Access Service",
        reply_to="support@example.com",
        smtp_host=None,
        smtp_port=587,
        smtp_username=None,
        smtp_password=None,
        smtp_starttls=True,
        smtp_ssl=False,
        timeout_seconds=10,
    )


def test_build_verification_code_email_contains_code_and_expiry():
    service = EmailTemplateService(_mail_settings())

    email = service.build_verification_code_email(
        to_email="user@example.com",
        code="123456",
        expires_minutes=15,
    )

    assert email.to_email == "user@example.com"
    assert email.subject == "Remote Access Service: код подтверждения email"
    assert "123456" in email.text_body
    assert "15" in email.text_body
    assert "123456" in (email.html_body or "")
    assert email.reply_to == "support@example.com"


def test_build_password_reset_email_contains_code_and_expiry():
    service = EmailTemplateService(_mail_settings())

    email = service.build_password_reset_code_email(
        to_email="user@example.com",
        code="654321",
        expires_minutes=20,
    )

    assert email.subject == "Remote Access Service: код сброса пароля"
    assert "654321" in email.text_body
    assert "20" in email.text_body


def test_build_linking_confirmation_email_contains_code_and_expiry():
    service = EmailTemplateService(_mail_settings())

    email = service.build_linking_confirmation_email(
        to_email="user@example.com",
        code="111222",
        expires_minutes=10,
    )

    assert email.subject == "Remote Access Service: подтверждение привязки аккаунта"
    assert "111222" in email.text_body
    assert "10" in email.text_body
