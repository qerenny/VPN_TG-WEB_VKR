from sqlmodel import select

from shared.config.database.session import get_db_session
from shared.models.growth.referral_edge_model import ReferralEdge
from shared.models.users.app_user_model import AppUser
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.vpn.vpn_client_model import VpnClient
from shared.config.config import (
    FRONTEND_TELEGRAM_SUBSCRIPTION_LINK,
    FRONTEND_TELEGRAM_TRAFFIC_LIMITED_SUBSCRIPTION_LINK,
    TRAFFIC_LIMITED_API_SERVERS,
)
from shared.infrastructure.users.telegram_user_repository import (
    TelegramUserRepository,
    TelegramUserSnapshot,
)
from shared.product_constants import PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_TRAFFIC_LIMITED
from shared.utils.client_identity import build_generated_client_label
from shared.utils.jwt_encoder import JWTEncoder
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.infrastructure.api.client_manager import ClientManager
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator


class SubscriptionProvisioningService:
    def __init__(
        self,
        repo: TelegramUserRepository,
        timestamputils: TimestampUtils,
        client: ClientManager,
        jwt_encoder: JWTEncoder,
        uuidgen: UUIDGenerator,
    ):
        self.repo = repo
        self.timestamputils = timestamputils
        self.client = client
        self.jwt_encoder = jwt_encoder
        self.uuidgen = uuidgen

    async def create_or_update_user(
        self,
        tg_id: int,
        period: str,
        user: TelegramUserSnapshot | None = None,
    ):
        current_user = user or await self.repo.get(tg_id)
        if not current_user:
            raise AttributeError("User not found")
        current_user = await self._ensure_standard_identifiers(current_user)

        if current_user.expiration_date:
            client_exists = await self.client.client_exists(str(current_user.uuid))
            if not client_exists:
                target_expiration_date = self.timestamputils.update_client_date(
                    current_user.expiration_date,
                    period,
                )
                logger.warning(
                    f"User {tg_id} has expiration_date={current_user.expiration_date} "
                    "but no client in 3x-ui. Recreating client via add_client."
                )
                await self.client.add_client(
                    tg_id,
                    period,
                    user=current_user,
                    target_expiration_date=target_expiration_date,
                )
                logger.info(f"Recreated missing client for tg_id={tg_id}.")
                return

            await self.client.update_client(tg_id, period, user=current_user)
            logger.info(f"Updated existing user with tg_id={tg_id}.")
        else:
            await self.client.add_client(tg_id, period, user=current_user)
            logger.info(f"Created new user with tg_id={tg_id}.")

    async def _ensure_standard_identifiers(
        self,
        user: TelegramUserSnapshot,
    ) -> TelegramUserSnapshot:
        current_uuid = str(user.uuid or "").strip()
        current_email = str(user.email or "").strip()
        current_sub_id = str(user.sub_id or "").strip()
        if current_uuid and current_email and current_sub_id:
            return user

        generated_email = build_generated_client_label(
            seed=user.username,
            generated_value=self.uuidgen.generate_email(),
        )
        repaired_user = TelegramUserSnapshot(
            tg_id=int(user.tg_id),
            uuid=current_uuid or self.uuidgen.generate_id(),
            email=current_email or generated_email,
            expiration_date=user.expiration_date,
            login_date=int(user.login_date),
            trial_date=user.trial_date,
            info_channel_date=user.info_channel_date,
            sub_id=current_sub_id or self.uuidgen.generate_id(),
            username=user.username,
        )
        await self.repo.create(repaired_user, telegram_username=user.username)
        logger.warning(
            "Repaired empty standard identifiers for tg_id=%s before provisioning",
            user.tg_id,
        )
        return repaired_user

    async def get_subscription_link(
        self,
        tg_id: int,
        user: TelegramUserSnapshot | None = None,
        *,
        scope: str = PRODUCT_SCOPE_STANDARD,
    ) -> str:
        if scope == PRODUCT_SCOPE_TRAFFIC_LIMITED:
            return await self._get_traffic_limited_subscription_link(tg_id)

        if scope != PRODUCT_SCOPE_STANDARD:
            raise ValueError(f"Unsupported subscription scope: {scope}")

        current_user = user or await self.repo.get(tg_id)
        if not current_user:
            raise AttributeError("User not found")

        expiration_date = current_user.expiration_date
        if expiration_date:
            if not FRONTEND_TELEGRAM_SUBSCRIPTION_LINK:
                logger.info(
                    f"Subscription link is unavailable for tg_id={tg_id}: "
                    "no public Telegram-safe frontend URL configured."
                )
                return ""

            token = self.jwt_encoder.encode({"tg_id": tg_id, "email": current_user.email})
            base_url = FRONTEND_TELEGRAM_SUBSCRIPTION_LINK.rstrip("/")
            link = f"{base_url}/{token}"
            logger.info(f"Subscription link for tg_id={tg_id}: {link}.")
            return link
        else:
            return ""

    async def _get_traffic_limited_subscription_link(self, tg_id: int) -> str:
        if not FRONTEND_TELEGRAM_TRAFFIC_LIMITED_SUBSCRIPTION_LINK:
            logger.info(
                f"TrafficLimited subscription link is unavailable for tg_id={tg_id}: "
                "no public Telegram-safe traffic_limited frontend URL configured."
            )
            return ""

        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.telegram_id == int(tg_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if telegram_account is None:
                return ""

            vpn_client = (
                await session.execute(
                    select(VpnClient).where(
                        VpnClient.user_id == int(telegram_account.user_id),
                        VpnClient.scope == PRODUCT_SCOPE_TRAFFIC_LIMITED,
                        VpnClient.deactivated_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if vpn_client is None:
                return ""

        token = self.jwt_encoder.encode(
            {
                "tg_id": int(tg_id),
                "email": str(vpn_client.external_email),
                "scope": PRODUCT_SCOPE_TRAFFIC_LIMITED,
            }
        )
        base_url = FRONTEND_TELEGRAM_TRAFFIC_LIMITED_SUBSCRIPTION_LINK.rstrip("/")
        link = f"{base_url}/{token}"
        logger.info(f"TrafficLimited subscription link for tg_id={tg_id}: {link}.")
        return link

    async def client_exists(self, tg_id: int) -> bool:
        user = await self.repo.get(tg_id)
        if not user:
            return False
        return await self.client.client_exists(user.uuid)

    async def delete_client(self, tg_id: int) -> None:
        user = await self.repo.get(tg_id)
        if not user:
            raise AttributeError("User not found")
        await self.client.delete_client(user.uuid)

    async def delete_user(self, tg_id: int) -> bool:
        user = await self.repo.get(tg_id)
        if not user:
            return False

        for scope, client_uuid in await self._list_active_panel_clients(int(tg_id)):
            if str(scope) == PRODUCT_SCOPE_TRAFFIC_LIMITED:
                await self.client.delete_scoped_client(
                    server_pool=TRAFFIC_LIMITED_API_SERVERS,
                    cache_namespace=PRODUCT_SCOPE_TRAFFIC_LIMITED,
                    client_uuid=str(client_uuid),
                )
                continue

            if await self.client.client_exists(str(client_uuid)):
                await self.client.delete_client(str(client_uuid))

        await self._delete_from_datastores(int(tg_id))
        logger.info(f"Deleted user tg_id={tg_id} from current datastores and 3x-ui where present.")
        return True

    async def _list_active_panel_clients(self, tg_id: int) -> list[tuple[str, str]]:
        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.telegram_id == int(tg_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if telegram_account is None:
                return []

            rows = (
                await session.execute(
                    select(VpnClient.scope, VpnClient.external_client_uuid).where(
                        VpnClient.user_id == int(telegram_account.user_id),
                        VpnClient.deactivated_at.is_(None),
                    )
                )
            ).all()
        return [
            (str(scope or "").strip().lower(), str(client_uuid or "").strip())
            for scope, client_uuid in rows
            if str(client_uuid or "").strip()
        ]

    async def _delete_from_datastores(self, tg_id: int) -> None:
        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.telegram_id == int(tg_id)
                    )
                )
            ).scalar_one_or_none()
            if telegram_account is not None:
                inbound_referrals = (
                    await session.execute(
                        select(ReferralEdge).where(
                            ReferralEdge.referrer_user_id == telegram_account.user_id
                        )
                    )
                ).scalars().all()
                for edge in inbound_referrals:
                    await session.delete(edge)

                app_user = await session.get(AppUser, telegram_account.user_id)
                if app_user is not None:
                    await session.delete(app_user)

            await session.commit()
