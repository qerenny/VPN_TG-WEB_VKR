from __future__ import annotations

from datetime import timezone

from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.migration_support.models.users.user_model import User as LegacyUser
from shared.models import register_models
from shared.models.subscriptions.subscription_state_model import SubscriptionState
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.product_constants import PRODUCT_SCOPE_STANDARD
from shared.scripts.rollout_support import RolloutCheck, print_checks, run_async

register_models()


async def main() -> None:
    async with get_db_session() as session:
        legacy_users = (
            await session.execute(select(LegacyUser).order_by(LegacyUser.tg_id))
        ).scalars().all()
        telegram_accounts = (
            await session.execute(select(TelegramAccount))
        ).scalars().all()
        vpn_clients = (await session.execute(select(VpnClient))).scalars().all()
        subscription_states = (
            await session.execute(select(SubscriptionState))
        ).scalars().all()

    tg_account_by_tg_id = {account.telegram_id: account for account in telegram_accounts}
    vpn_client_by_user_id = {
        client.user_id: client
        for client in vpn_clients
        if client.deactivated_at is None and client.scope == PRODUCT_SCOPE_STANDARD
    }
    subscription_state_by_user_id = {state.user_id: state for state in subscription_states}

    missing_telegram = 0
    missing_vpn_clients = 0
    missing_subscription_state = 0
    expiration_mismatches = 0
    trial_mismatches = 0
    news_mismatches = 0

    for legacy_user in legacy_users:
        telegram_account = tg_account_by_tg_id.get(legacy_user.tg_id)
        if telegram_account is None:
            missing_telegram += 1
            continue

        vpn_client = vpn_client_by_user_id.get(telegram_account.user_id)
        if vpn_client is None:
            missing_vpn_clients += 1

        subscription_state = subscription_state_by_user_id.get(telegram_account.user_id)
        if subscription_state is None:
            missing_subscription_state += 1
            continue

        if _dt_to_legacy_ms(subscription_state.current_expires_at) != legacy_user.expiration_date:
            expiration_mismatches += 1
        if _dt_to_legacy_ms(subscription_state.trial_activated_at) != legacy_user.trial_date:
            trial_mismatches += 1
        if (
            _dt_to_legacy_ms(subscription_state.news_bonus_activated_at)
            != legacy_user.news_channel_date
        ):
            news_mismatches += 1

    checks = [
        RolloutCheck(
            name="legacy users mapped to telegram_accounts",
            ok=missing_telegram == 0,
            details=f"missing={missing_telegram}",
        ),
        RolloutCheck(
            name="legacy users mapped to active vpn_clients",
            ok=missing_vpn_clients == 0,
            details=f"missing={missing_vpn_clients}",
        ),
        RolloutCheck(
            name="legacy users mapped to subscription_state",
            ok=missing_subscription_state == 0,
            details=f"missing={missing_subscription_state}",
        ),
        RolloutCheck(
            name="subscription_state current_expires_at parity",
            ok=expiration_mismatches == 0,
            details=f"mismatches={expiration_mismatches}",
        ),
        RolloutCheck(
            name="subscription_state trial_activated_at parity",
            ok=trial_mismatches == 0,
            details=f"mismatches={trial_mismatches}",
        ),
        RolloutCheck(
            name="subscription_state news_bonus_activated_at parity",
            ok=news_mismatches == 0,
            details=f"mismatches={news_mismatches}",
        ),
    ]
    print_checks(checks)

    if not all(check.ok for check in checks):
        raise SystemExit(1)


def _dt_to_legacy_ms(value) -> int | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)


if __name__ == "__main__":
    run_async(main())
