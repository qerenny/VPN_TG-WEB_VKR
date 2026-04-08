from __future__ import annotations

from dataclasses import dataclass

from shared.config.config import AUTH_IDENTITY_LINK_TOKEN_TTL_MINUTES
from shared.config.settings import (
    RolloutFeatureFlags,
    TelegramBotSettings,
    get_product_feature_settings,
    load_settings,
)
from shared.infrastructure.identity_link_service import IdentityLinkService
from shared.infrastructure.payments.payment_repository import (
    PaymentRepository,
)
from shared.infrastructure.promos.promo_code_repository import (
    PromoCodeRepository,
)
from shared.infrastructure.promos.promo_code_usage_repository import (
    PromoCodeUsageRepository,
)
from shared.infrastructure.referrals.referral_repository import (
    ReferralRepository,
)
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.infrastructure.growth_sync_service import GrowthSyncService
from shared.infrastructure.payment_sync_service import PaymentSyncService
from shared.infrastructure.vpn_topology_sync_service import VpnTopologySyncService
from shared.utils.async_redis_client import AsyncRedisClient
from shared.utils.jwt_encoder import JWTEncoder
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.bot import bot
from telegram_bot.infrastructure.api.client_manager import ClientManager
from telegram_bot.presentation.admin.command_handler import AdminCommandHandler
from telegram_bot.presentation.instructions.help_handler import HelpHandler
from telegram_bot.presentation.payments.payment_command_handler import PaymentCommandHandler
from telegram_bot.presentation.referrals.referral_menu_handler import ReferralMenuHandler
from telegram_bot.presentation.referrals.referral_start_handler import ReferralStartHandler
from telegram_bot.presentation.start.start_handler import StartHandler
from telegram_bot.presentation.subscriptions.subscription_menu_handler import (
    SubscriptionMenuHandler,
)
from telegram_bot.presentation.subscriptions.subscription_news_channel_handler import (
    SubscriptionNewsChannelHandler,
)
from telegram_bot.presentation.subscriptions.subscription_promo_handler import (
    SubscriptionPromoHandler,
)
from telegram_bot.presentation.subscriptions.subscription_trial_handler import (
    SubscriptionTrialHandler,
)
from telegram_bot.presentation.support.support_handler import SupportHandler
from telegram_bot.presentation.users.profile_handler import ProfileHandler
from telegram_bot.services.payments.demo_payment_gateway import build_demo_payment_gateways
from telegram_bot.services.payments.payment_fulfillment_service import (
    PaymentFulfillmentService,
)
from telegram_bot.services.payments.payment_processing_service import (
    PaymentProcessingService,
)
from telegram_bot.services.payments.payment_queue_service import PaymentQueueService
from telegram_bot.services.payments.payment_status_update_service import (
    PaymentStatusChecker,
)
from telegram_bot.services.linking.telegram_link_service import TelegramLinkService
from telegram_bot.services.referrals.referral_bonus_service import ReferralBonusService
from telegram_bot.services.referrals.referral_registration_service import (
    ReferralRegistrationService,
)
from telegram_bot.services.referrals.referral_validator_service import (
    ReferralValidatorService,
)
from telegram_bot.services.referrals.referrals_stats_service import ReferralStatsService
from telegram_bot.services.subscriptions.reminder_queue_service import (
    ReminderQueueService,
)
from telegram_bot.services.subscriptions.subscription_flow_service import (
    SubscriptionFlowService,
)
from telegram_bot.services.subscriptions.subscription_provisioning_service import (
    SubscriptionProvisioningService,
)
from telegram_bot.services.subscriptions.standard_user_subscription_service import (
    StandardUserSubscriptionService,
)
from telegram_bot.services.subscriptions.whitelist_provisioning_service import (
    WhiteListProvisioningService,
)
from telegram_bot.services.subscriptions.whitelist_traffic_sync_service import (
    WhiteListTrafficSyncService,
)
from telegram_bot.services.subscriptions.whitelist_traffic_service import (
    WhiteListTrafficService,
)
from telegram_bot.services.subscriptions.subscription_reminder_service import (
    SubscriptionReminderService,
)
from telegram_bot.services.users.user_registration_service import UserRegistrationService
from telegram_bot.services.users.user_subscription_info_service import (
    UserSubscriptionInfoService,
)
from telegram_bot.shared.utils.json_builder import JSONBuilder
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator


@dataclass(slots=True)
class TelegramBotApp:
    settings: TelegramBotSettings
    bot: object
    start_handler: StartHandler
    profile_handler: ProfileHandler
    support_handler: SupportHandler
    instructions_handler: HelpHandler
    payment_command_handler: PaymentCommandHandler
    subscription_menu_handler: SubscriptionMenuHandler
    referral_menu_handler: ReferralMenuHandler
    admin_command_handler: AdminCommandHandler
    payment_status_checker: PaymentStatusChecker
    payment_fulfillment_service: PaymentFulfillmentService
    referral_start_handler: ReferralStartHandler
    subscription_trial_handler: SubscriptionTrialHandler
    reminder_service: SubscriptionReminderService
    subscription_news_channel_handler: SubscriptionNewsChannelHandler
    subscription_promo_handler: SubscriptionPromoHandler
    whitelist_traffic_sync_service: WhiteListTrafficSyncService


def _build_redis_client(redis_url: str, worker_pop_timeout_seconds: int) -> AsyncRedisClient:
    return AsyncRedisClient(
        redis_url=redis_url,
        timeout=max(5.0, float(worker_pop_timeout_seconds + 2)),
    )


def build_bot_app(settings: TelegramBotSettings | None = None) -> TelegramBotApp:
    runtime_settings = settings or load_settings()
    product_features = get_product_feature_settings()

    user_repository = TelegramUserRepository()
    referral_repository = ReferralRepository()
    payment_repository = PaymentRepository()
    promo_code_repository = PromoCodeRepository()
    promo_code_usage_repository = PromoCodeUsageRepository()

    timestamp_utils = TimestampUtils()
    jwt_encoder = JWTEncoder(
        secret=runtime_settings.jwt.secret,
        algorithm=runtime_settings.jwt.algorithm,
        expire_minutes=runtime_settings.jwt.expire_minutes,
    )
    uuid_generator = UUIDGenerator()
    json_builder = JSONBuilder()
    payment_sync_service = PaymentSyncService(
        RolloutFeatureFlags(db_dual_write_payments=True)
    )
    growth_sync_service = GrowthSyncService(
        RolloutFeatureFlags(db_dual_write_growth=True)
    )
    vpn_topology_sync_service = VpnTopologySyncService(
        RolloutFeatureFlags(db_dual_write_vpn_topology=True)
    )

    client_manager = ClientManager(
        repo=user_repository,
        timestamp=timestamp_utils,
        jsonutils=json_builder,
        uuidgen=uuid_generator,
        topology_sync_service=vpn_topology_sync_service,
    )

    user_subscription_service = SubscriptionProvisioningService(
        repo=user_repository,
        timestamputils=timestamp_utils,
        client=client_manager,
        jwt_encoder=jwt_encoder,
        uuidgen=uuid_generator,
    )
    user_subscription_info_service = UserSubscriptionInfoService(
        repo=user_repository,
        timestamp=timestamp_utils,
    )
    user_registration_service = UserRegistrationService(
        repo=user_repository,
        timestamp=timestamp_utils,
        uuidgen=uuid_generator,
    )
    whitelist_provisioning_service = WhiteListProvisioningService(
        repo=user_repository,
        timestamp=timestamp_utils,
        client_manager=client_manager,
        uuidgen=uuid_generator,
    )
    whitelist_traffic_service = WhiteListTrafficService(
        provisioning_service=whitelist_provisioning_service,
        timestamp=timestamp_utils,
        client_manager=client_manager,
    )
    standard_user_subscription_service = StandardUserSubscriptionService(
        client_manager=client_manager,
        uuidgen=uuid_generator,
    )
    telegram_link_service = TelegramLinkService(
        identity_link_service=IdentityLinkService(
            ttl_minutes=AUTH_IDENTITY_LINK_TOKEN_TTL_MINUTES,
        ),
        secret=runtime_settings.jwt.secret,
    )
    whitelist_traffic_sync_service = WhiteListTrafficSyncService(
        client_manager=client_manager,
    )

    referral_validator_service = ReferralValidatorService(repo=referral_repository)
    referral_bonus_service = ReferralBonusService(
        repo_referrals=referral_repository,
        repo_user=user_repository,
        timestamp=timestamp_utils,
        client=client_manager,
        sync_service=growth_sync_service,
    )
    referral_registration_service = ReferralRegistrationService(
        repo=referral_repository,
        user_repo=user_repository,
        payment_repo=payment_repository,
        promo_usage_repo=promo_code_usage_repository,
        validator=referral_validator_service,
        bonuses=referral_bonus_service,
        sync_service=growth_sync_service,
    )
    referral_stats_service = ReferralStatsService(repo=referral_repository)

    instructions_handler = HelpHandler()
    support_handler = SupportHandler()

    subscription_flow_service = SubscriptionFlowService(
        repo=user_repository,
        subscription_service=user_subscription_service,
        instruction=instructions_handler,
        user_subscription_info_service=user_subscription_info_service,
        timestamp=timestamp_utils,
    )

    referral_start_handler = ReferralStartHandler(
        registration_service=referral_registration_service,
    )
    start_handler = StartHandler(
        referral_start=referral_start_handler,
        user_register=user_registration_service,
        repo=user_repository,
        subscription_service=user_subscription_service,
        telegram_link_service=telegram_link_service,
        referrals_enabled=product_features.referrals_enabled,
    )
    profile_handler = ProfileHandler(
        repo=user_repository,
        user_subscription_info_service=user_subscription_info_service,
        subscription_service=user_subscription_service,
        telegram_link_service=telegram_link_service,
    )
    referral_menu_handler = ReferralMenuHandler(stats_service=referral_stats_service)
    subscription_menu_handler = SubscriptionMenuHandler(
        repo=user_repository,
        whitelist_traffic_service=whitelist_traffic_service,
        commerce_enabled=product_features.commerce_enabled,
        traffic_limited_config_enabled=product_features.traffic_limited_config_enabled,
    )
    subscription_trial_handler = SubscriptionTrialHandler(
        subscription_flow_service=subscription_flow_service,
        user_subscription_info_service=user_subscription_info_service,
        start_handler=start_handler,
        telegram_link_service=telegram_link_service,
        whitelist_traffic_service=whitelist_traffic_service,
        subscription_service=user_subscription_service,
    )
    subscription_news_channel_handler = SubscriptionNewsChannelHandler(
        repo=user_repository,
        subscription_flow_service=subscription_flow_service,
        subscription_menu_handler=subscription_menu_handler,
    )
    subscription_promo_handler = SubscriptionPromoHandler(
        subscription_flow_service=subscription_flow_service,
        start_handler=start_handler,
        promo_repo=promo_code_usage_repository,
        promo_code_repo=promo_code_repository,
        sync_service=growth_sync_service,
    )

    payment_gateways = build_demo_payment_gateways(uuid_generator)
    payment_command_handler = PaymentCommandHandler(
        gateways=payment_gateways,
        repo=payment_repository,
        timestamp=timestamp_utils,
        gateway_labels={
            method: gateway.label for method, gateway in payment_gateways.items()
        },
    )

    reminder_redis_client = _build_redis_client(
        redis_url=runtime_settings.redis_url,
        worker_pop_timeout_seconds=runtime_settings.reminders.worker_pop_timeout_seconds,
    )
    reminder_queue_service = ReminderQueueService(
        redis_client=reminder_redis_client,
        ready_queue_key=runtime_settings.reminders.ready_queue_key,
        retry_queue_key=runtime_settings.reminders.retry_queue_key,
        dead_letter_queue_key=runtime_settings.reminders.dead_letter_queue_key,
        dedupe_prefix=runtime_settings.reminders.dedupe_prefix,
    )
    reminder_service = SubscriptionReminderService(
        repo=user_repository,
        user_subscription_info_service=user_subscription_info_service,
        timestamp=timestamp_utils,
        reminder_queue_service=reminder_queue_service,
        scan_interval_seconds=runtime_settings.reminders.scan_interval_seconds,
        lookahead_hours=runtime_settings.reminders.lookahead_hours,
        retry_base_seconds=runtime_settings.reminders.retry_base_seconds,
        max_retries=runtime_settings.reminders.max_retries,
        worker_pop_timeout_seconds=runtime_settings.reminders.worker_pop_timeout_seconds,
        dedupe_ttl_seconds=runtime_settings.reminders.dedupe_ttl_seconds,
    )

    payment_redis_client = _build_redis_client(
        redis_url=runtime_settings.redis_url,
        worker_pop_timeout_seconds=runtime_settings.payments.worker_pop_timeout_seconds,
    )
    payment_queue_service = PaymentQueueService(
        redis_client=payment_redis_client,
        ready_queue_key=runtime_settings.payments.ready_queue_key,
        retry_queue_key=runtime_settings.payments.retry_queue_key,
        dead_letter_queue_key=runtime_settings.payments.dead_letter_queue_key,
        dedupe_prefix=runtime_settings.payments.dedupe_prefix,
    )
    payment_processing_service = PaymentProcessingService(
        subscription_manager=subscription_flow_service,
        bonuses=referral_bonus_service,
        whitelist_traffic_service=whitelist_traffic_service,
        standard_user_subscription_service=standard_user_subscription_service,
        referrals_enabled=product_features.referrals_enabled,
    )
    payment_fulfillment_service = PaymentFulfillmentService(
        repo=payment_repository,
        payment_processing=payment_processing_service,
        queue_service=payment_queue_service,
        subscription_service=user_subscription_service,
        scan_interval_seconds=runtime_settings.payments.scan_interval_seconds,
        retry_base_seconds=runtime_settings.payments.retry_base_seconds,
        max_retries=runtime_settings.payments.max_retries,
        worker_pop_timeout_seconds=runtime_settings.payments.worker_pop_timeout_seconds,
        dedupe_ttl_seconds=runtime_settings.payments.dedupe_ttl_seconds,
        telegram_link_service=telegram_link_service,
        sync_service=payment_sync_service,
    )
    payment_status_checker = PaymentStatusChecker(
        repo=payment_repository,
        gateways=payment_gateways,
        payment_fulfillment_service=payment_fulfillment_service,
        scan_interval_seconds=runtime_settings.payments.status_scan_interval_seconds,
        sync_service=payment_sync_service,
    )

    admin_command_handler = AdminCommandHandler(
        repo=user_repository,
        subscription_user_service=user_subscription_service,
        instruction=instructions_handler,
        timestamp=timestamp_utils,
        payment_queue_service=payment_queue_service,
        jwt_encoder=jwt_encoder,
    )

    return TelegramBotApp(
        settings=runtime_settings,
        bot=bot,
        start_handler=start_handler,
        profile_handler=profile_handler,
        support_handler=support_handler,
        instructions_handler=instructions_handler,
        payment_command_handler=payment_command_handler,
        subscription_menu_handler=subscription_menu_handler,
        referral_menu_handler=referral_menu_handler,
        admin_command_handler=admin_command_handler,
        payment_status_checker=payment_status_checker,
        payment_fulfillment_service=payment_fulfillment_service,
        referral_start_handler=referral_start_handler,
        subscription_trial_handler=subscription_trial_handler,
        reminder_service=reminder_service,
        subscription_news_channel_handler=subscription_news_channel_handler,
        subscription_promo_handler=subscription_promo_handler,
        whitelist_traffic_sync_service=whitelist_traffic_sync_service,
    )
