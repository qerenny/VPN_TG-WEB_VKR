from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from backend.services.auth.auth_service import AuthService
from backend.services.auth.password_hasher import PasswordHasher
from backend.services.auth.web_auth_challenge_service import WebAuthChallengeService
from backend.services.auth.web_session_service import WebSessionService
from backend.services.email import (
    EmailTemplateService,
    TransactionalEmailService,
    build_email_delivery_service,
)
from backend.services.subscription.subscription_manager_service import (
    SubscriptionManagerService,
)
from backend.services.admin.admin_service import AdminService
from backend.services.account.account_service import AccountService
from backend.services.linking.linking_service import LinkingService
from backend.services.payments.web_checkout_service import WebCheckoutService
from backend.services.promo.web_promo_service import WebPromoService
from backend.services.user.user_manager_service import UserManagerService
from shared.config.settings import BackendSettings, get_backend_settings
from shared.infrastructure.access.access_grant_repository import AccessGrantRepository
from shared.infrastructure.access.access_registry_repository import AccessRegistryRepository
from shared.infrastructure.access.access_request_repository import AccessRequestRepository
from shared.services.access.access_request_service import AccessRequestService
from shared.services.access.access_registry_service import AccessRegistryService
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
)
from shared.infrastructure.identity_link_service import IdentityLinkService
from shared.infrastructure.promos.promo_code_repository import (
    PromoCodeRepository,
)
from shared.infrastructure.referrals.referral_repository import (
    ReferralRepository,
)
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.jwt_encoder import JWTEncoder
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.infrastructure.api.client_manager import ClientManager
from telegram_bot.services.access.access_issuance_service import AccessIssuanceService
from telegram_bot.services.access.access_request_notification_service import (
    AccessRequestNotificationService,
)
from telegram_bot.services.linking.telegram_link_service import TelegramLinkService
from telegram_bot.services.payments.demo_payment_gateway import build_demo_payment_gateways
from telegram_bot.services.subscriptions.standard_user_subscription_service import (
    StandardUserSubscriptionService,
)
from telegram_bot.shared.utils.json_builder import JSONBuilder
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator


@dataclass(slots=True)
class BackendDeps:
    settings: BackendSettings
    user_repository: TelegramUserRepository
    payment_repository: PaymentRepository
    referral_repository: ReferralRepository
    promo_code_repository: PromoCodeRepository
    jwt_encoder: JWTEncoder
    timestamp_utils: TimestampUtils
    auth_service: AuthService
    transactional_email_service: TransactionalEmailService
    account_service: AccountService
    linking_service: LinkingService
    web_checkout_service: WebCheckoutService
    user_manager_service: UserManagerService
    subscription_manager_service: SubscriptionManagerService
    web_promo_service: WebPromoService
    admin_service: AdminService
    access_registry_service: AccessRegistryService
    access_request_service: AccessRequestService


def build_backend_deps(settings: BackendSettings | None = None) -> BackendDeps:
    runtime_settings = settings or get_backend_settings()

    user_repository = TelegramUserRepository()
    payment_repository = PaymentRepository()
    access_grant_repository = AccessGrantRepository()
    access_registry_repository = AccessRegistryRepository()
    access_request_repository = AccessRequestRepository()
    referral_repository = ReferralRepository()
    promo_code_repository = PromoCodeRepository()
    password_hasher = PasswordHasher()
    uuid_generator = UUIDGenerator()
    web_session_service = WebSessionService(
        ttl_minutes=runtime_settings.auth.web_session_ttl_minutes,
    )
    web_auth_challenge_service = WebAuthChallengeService(
        code_ttl_minutes=runtime_settings.auth.email_code_ttl_minutes,
        resend_cooldown_seconds=runtime_settings.auth.challenge_resend_cooldown_seconds,
        request_window_seconds=runtime_settings.auth.challenge_request_window_seconds,
        max_requests_per_window_per_email=runtime_settings.auth.challenge_max_requests_per_window_per_email,
        max_requests_per_window_per_ip=runtime_settings.auth.challenge_max_requests_per_window_per_ip,
        max_failed_attempts=runtime_settings.auth.challenge_max_failed_attempts,
    )
    email_delivery_service = build_email_delivery_service(runtime_settings.mail)
    email_template_service = EmailTemplateService(runtime_settings.mail)
    transactional_email_service = TransactionalEmailService(
        delivery_service=email_delivery_service,
        template_service=email_template_service,
    )
    identity_link_service = IdentityLinkService(
        ttl_minutes=runtime_settings.auth.identity_link_token_ttl_minutes,
    )
    auth_service = AuthService(
        password_hasher=password_hasher,
        session_service=web_session_service,
        challenge_service=web_auth_challenge_service,
        transactional_email_service=transactional_email_service,
        identity_link_service=identity_link_service,
        email_code_ttl_minutes=runtime_settings.auth.email_code_ttl_minutes,
        password_min_length=runtime_settings.auth.password_min_length,
        telegram_web_login_secret=runtime_settings.jwt.secret,
    )
    jwt_encoder = JWTEncoder(
        secret=runtime_settings.jwt.secret,
        algorithm=runtime_settings.jwt.algorithm,
        expire_minutes=runtime_settings.jwt.expire_minutes,
    )
    timestamp_utils = TimestampUtils()
    account_service = AccountService(
        timestamp=timestamp_utils,
        access_registry_repository=access_registry_repository,
    )
    linking_service = LinkingService(
        identity_link_service=identity_link_service,
    )
    web_checkout_service = WebCheckoutService(
        payment_repository=payment_repository,
        gateways=build_demo_payment_gateways(uuid_generator),
        timestamp=timestamp_utils,
    )
    user_manager_service = UserManagerService(
        repo=user_repository,
        jwt_encoder=jwt_encoder,
    )
    subscription_manager_service = SubscriptionManagerService(
        repo=user_repository,
        jwt_encoder=jwt_encoder,
        timestamp=timestamp_utils,
    )
    client_manager = ClientManager(
        repo=user_repository,
        timestamp=timestamp_utils,
        jsonutils=JSONBuilder(),
        uuidgen=uuid_generator,
    )
    standard_user_subscription_service = StandardUserSubscriptionService(
        client_manager=client_manager,
        uuidgen=uuid_generator,
    )
    web_promo_service = WebPromoService(
        standard_user_subscription_service=standard_user_subscription_service,
    )
    admin_service = AdminService(
        settings=runtime_settings,
        user_repository=user_repository,
        payment_repository=payment_repository,
        referral_repository=referral_repository,
        promo_code_repository=promo_code_repository,
        jwt_encoder=jwt_encoder,
        timestamp=timestamp_utils,
    )
    access_issuance_service = AccessIssuanceService(
        access_grant_repository=access_grant_repository,
        subscription_flow_service=admin_service.subscription_flow_service,
        traffic_limited_service=admin_service.traffic_limited_service,
        standard_user_subscription_service=standard_user_subscription_service,
    )
    admin_service.access_issuance_service = access_issuance_service
    access_request_service = AccessRequestService(
        access_request_repository=access_request_repository,
        access_grant_repository=access_grant_repository,
        access_issuance_service=access_issuance_service,
        access_registry_service=AccessRegistryService(
            access_registry_repository=access_registry_repository,
            access_grant_repository=access_grant_repository,
        ),
        notification_service=AccessRequestNotificationService(
            telegram_link_service=TelegramLinkService(
                identity_link_service=identity_link_service,
                secret=runtime_settings.jwt.secret,
            ),
        ),
    )
    access_registry_service = access_request_service.access_registry_service

    return BackendDeps(
        settings=runtime_settings,
        user_repository=user_repository,
        payment_repository=payment_repository,
        referral_repository=referral_repository,
        promo_code_repository=promo_code_repository,
        jwt_encoder=jwt_encoder,
        timestamp_utils=timestamp_utils,
        auth_service=auth_service,
        transactional_email_service=transactional_email_service,
        account_service=account_service,
        linking_service=linking_service,
        web_checkout_service=web_checkout_service,
        user_manager_service=user_manager_service,
        subscription_manager_service=subscription_manager_service,
        web_promo_service=web_promo_service,
        admin_service=admin_service,
        access_registry_service=access_registry_service,
        access_request_service=access_request_service,
    )


def get_backend_deps(request: Request) -> BackendDeps:
    deps = getattr(request.app.state, "deps", None)
    if deps is None:
        raise RuntimeError("Backend dependencies are not initialized")
    return deps


def get_subscription_manager_service(request: Request) -> SubscriptionManagerService:
    return get_backend_deps(request).subscription_manager_service


def get_user_manager_service(request: Request) -> UserManagerService:
    return get_backend_deps(request).user_manager_service


def get_jwt_encoder(request: Request) -> JWTEncoder:
    return get_backend_deps(request).jwt_encoder


def get_admin_service(request: Request) -> AdminService:
    return get_backend_deps(request).admin_service


def get_auth_service(request: Request) -> AuthService:
    return get_backend_deps(request).auth_service


def get_transactional_email_service(request: Request) -> TransactionalEmailService:
    return get_backend_deps(request).transactional_email_service


def get_account_service(request: Request) -> AccountService:
    return get_backend_deps(request).account_service


def get_linking_service(request: Request) -> LinkingService:
    return get_backend_deps(request).linking_service


def get_web_checkout_service(request: Request) -> WebCheckoutService:
    return get_backend_deps(request).web_checkout_service


def get_web_promo_service(request: Request) -> WebPromoService:
    return get_backend_deps(request).web_promo_service


def get_access_request_service(request: Request) -> AccessRequestService:
    return get_backend_deps(request).access_request_service


def get_access_registry_service(request: Request) -> AccessRegistryService:
    return get_backend_deps(request).access_registry_service
