"""Primary SQLModel namespace for application data models."""


def register_models() -> None:
    """Import model modules so SQLModel metadata is populated."""
    from shared.models.growth.promo_code_model import PromoCode  # noqa: F401
    from shared.models.growth.promo_redemption_model import PromoRedemption  # noqa: F401
    from shared.models.growth.referral_edge_model import ReferralEdge  # noqa: F401
    from shared.models.growth.referral_reward_model import ReferralReward  # noqa: F401
    from shared.models.growth.referral_reward_rule_model import ReferralRewardRule  # noqa: F401
    from shared.models.payments.payment_attempt_model import PaymentAttempt  # noqa: F401
    from shared.models.payments.payment_order_model import PaymentOrder  # noqa: F401
    from shared.models.payments.payment_webhook_event_model import PaymentWebhookEvent  # noqa: F401
    from shared.models.payments.plan_model import Plan  # noqa: F401
    from shared.models.subscriptions.subscription_grant_model import SubscriptionGrant  # noqa: F401
    from shared.models.subscriptions.subscription_state_model import SubscriptionState  # noqa: F401
    from shared.models.traffic.traffic_grant_model import TrafficGrant  # noqa: F401
    from shared.models.traffic.traffic_state_model import TrafficState  # noqa: F401
    from shared.models.users.app_user_model import AppUser  # noqa: F401
    from shared.models.users.identity_link_token_model import IdentityLinkToken  # noqa: F401
    from shared.models.users.telegram_account_model import TelegramAccount  # noqa: F401
    from shared.models.users.web_auth_challenge_model import WebAuthChallenge  # noqa: F401
    from shared.models.users.web_account_model import WebAccount  # noqa: F401
    from shared.models.users.user_profile_model import UserProfile  # noqa: F401
    from shared.models.users.web_session_model import WebSession  # noqa: F401
    from shared.models.vpn.vpn_access_point_model import VpnAccessPoint  # noqa: F401
    from shared.models.vpn.vpn_client_deployment_model import VpnClientDeployment  # noqa: F401
    from shared.models.vpn.vpn_client_model import VpnClient  # noqa: F401
    from shared.models.vpn.vpn_control_plane_model import VpnControlPlane  # noqa: F401
    from shared.models.vpn.vpn_location_model import VpnLocation  # noqa: F401
