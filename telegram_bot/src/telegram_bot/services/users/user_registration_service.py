from sqlalchemy.exc import IntegrityError
from telebot.types import Message

from shared.infrastructure.users.telegram_user_repository import (
    TelegramUserRepository,
    TelegramUserSnapshot,
)
from shared.utils.client_identity import build_generated_client_label
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.shared.utils.uuid_generator import UUIDGenerator


class UserRegistrationService:
    def __init__(
        self,
        repo: TelegramUserRepository,
        timestamp: TimestampUtils,
        uuidgen: UUIDGenerator,
    ):
        self.repo = repo
        self.timestamp = timestamp
        self.uuidgen = uuidgen

    async def register_user(self, message: Message) -> bool:
        """
        Registers a user in the system.
        """
        tg_id = message.chat.id
        exists = await self.repo.get(tg_id)

        if not exists:
            user_id = self.uuidgen.generate_id()
            email = build_generated_client_label(
                seed=message.chat.username,
                generated_value=self.uuidgen.generate_email(),
            )
            sub_id = self.uuidgen.generate_id()
            login_date = self.timestamp.current_timestamp()

            user = TelegramUserSnapshot(
                tg_id=tg_id,
                uuid=user_id,
                email=email,
                expiration_date=None,
                sub_id=sub_id,
                login_date=login_date,
                trial_date=None,
                info_channel_date=None,
            )

            try:
                await self.repo.create(user, telegram_username=message.chat.username)
                logger.info(f"User {tg_id} registered successfully.")
                return True
            except IntegrityError as error:
                if "telegram_accounts_telegram_id_key" not in str(error):
                    raise

                await self.repo.touch_identity(
                    tg_id=tg_id,
                    telegram_username=message.chat.username,
                    seen_at=login_date,
                )
                logger.warning(
                    f"User {tg_id} registration raced with an existing telegram account. "
                    "Identity was refreshed instead."
                )
                return False
        else:
            await self.repo.touch_identity(
                tg_id=tg_id,
                telegram_username=message.chat.username,
                seen_at=self.timestamp.current_timestamp(),
            )
            logger.info(f"User {tg_id} already exists.")
            return False
