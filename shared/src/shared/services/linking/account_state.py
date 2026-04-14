from __future__ import annotations

from sqlalchemy import and_, select

from shared.models.payments.payment_order_model import PaymentOrder
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient


async def is_empty_web_shell(session, user_id: int) -> bool:
    has_telegram = (
        await session.execute(
            select(TelegramAccount.id).where(
                and_(
                    TelegramAccount.user_id == int(user_id),
                    TelegramAccount.revoked_at.is_(None),
                )
            )
        )
    ).scalar_one_or_none()
    if has_telegram is not None:
        return False

    has_payments = (
        await session.execute(
            select(PaymentOrder.id).where(PaymentOrder.user_id == int(user_id)).limit(1)
        )
    ).scalar_one_or_none()
    if has_payments is not None:
        return False

    has_vpn_clients = (
        await session.execute(
            select(VpnClient.id)
            .where(
                VpnClient.user_id == int(user_id),
                VpnClient.deactivated_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if has_vpn_clients is not None:
        return False

    subscription_state = await session.get(SubscriptionState, int(user_id))
    if subscription_state is not None and any(
        [
            subscription_state.current_expires_at is not None,
            subscription_state.trial_activated_at is not None,
            subscription_state.info_channel_activated_at is not None,
        ]
    ):
        return False

    return True
