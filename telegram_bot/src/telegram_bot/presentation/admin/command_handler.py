import os
import asyncio
import io
from types import SimpleNamespace

from fastapi import HTTPException
from telebot.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from shared.config.config import BACKEND_TELEGRAM_BASE_LINK, BOT_ADMIN_IDS, FRONTEND_ADMIN_PATH
from shared.infrastructure.users.telegram_user_repository import TelegramUserRepository
from shared.utils.admin_access_link import (
    ADMIN_BOOTSTRAP_TTL_SECONDS,
    create_admin_bootstrap_token,
)
from shared.utils.jwt_encoder import JWTEncoder
from shared.utils.logging_utils import logger
from shared.utils.timestamp_utils import TimestampUtils
from telegram_bot.bot import bot
from telegram_bot.presentation.instructions.help_handler import HelpHandler
from telegram_bot.services.payments.payment_queue_service import PaymentQueueService
from telegram_bot.services.subscriptions.subscription_provisioning_service import (
    SubscriptionProvisioningService,
)

photos_db = {}  # temp file_id store


def read_file_content(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


class AdminCommandHandler:
    def __init__(
        self,
        repo: TelegramUserRepository,
        subscription_user_service: SubscriptionProvisioningService,
        instruction: HelpHandler,
        timestamp: TimestampUtils,
        payment_queue_service: PaymentQueueService,
        jwt_encoder: JWTEncoder,
        access_request_service=None,
    ):
        self.repo = repo
        self.subscription_user_service = subscription_user_service
        self.instruction = instruction
        self.timestamp = timestamp
        self.payment_queue_service = payment_queue_service
        self.jwt_encoder = jwt_encoder
        self.access_request_service = access_request_service
        self.sessions: dict[int, dict] = {}

    def _is_admin(self, chat_id: int) -> bool:
        return chat_id in BOT_ADMIN_IDS

    def has_pending_input(self, chat_id: int) -> bool:
        session = self.sessions.get(chat_id)
        if not session:
            return False
        return session.get("state") in {
            "await_text_all",
            "await_text_active",
            "await_search_user",
        }
    async def upload_photos(self, message: Message):
        if not self._is_admin(message.chat.id):
            await bot.send_message(
                chat_id=message.chat.id,
                text="У вас нет прав для использования этой команды.",
            )
            return

        folder_path = "/app/telegram_bot/src/telegram_bot/shared/assets/images"
        if not os.path.exists(folder_path):
            await bot.send_message(
                chat_id=message.chat.id, text=f"Папка '{folder_path}' не найдена."
            )
            return

        file_list = [f for f in os.listdir(folder_path) if not f.startswith(".")]
        if not file_list:
            await bot.send_message(
                chat_id=message.chat.id,
                text=f"В папке '{folder_path}' нет изображений.",
            )
            return

        await bot.send_message(
            chat_id=message.chat.id, text=f"Загружаю {len(file_list)} фото..."
        )

        count = 0
        for filename in file_list:
            full_path = os.path.join(folder_path, filename)
            if not os.path.isfile(full_path):
                continue

            try:
                photo_data = await asyncio.get_running_loop().run_in_executor(
                    None, read_file_content, full_path
                )
                photo_file = io.BytesIO(photo_data)
                photo_file.name = filename

                msg = await bot.send_photo(
                    chat_id=message.chat.id, photo=photo_file, caption=filename
                )
                file_id = msg.photo[-1].file_id
                photos_db[filename] = file_id
                count += 1
            except Exception as e:
                await bot.send_message(
                    chat_id=message.chat.id,
                    text=f"Не удалось загрузить {filename}: {e}",
                )

        await bot.send_message(
            chat_id=message.chat.id,
            text=f"✅ Загружено {count} изображений. Все file_id сохранены локально.",
        )
    async def show_photos(self, message: Message):
        if not self._is_admin(message.chat.id):
            await bot.send_message(
                chat_id=message.chat.id,
                text="У вас нет прав для использования этой команды.",
            )
            return

        if not photos_db:
            await bot.send_message(
                chat_id=message.chat.id, text="Ни одно изображение не загружено."
            )
            return

        text_lines = [f"{name} -> {file_id}" for name, file_id in photos_db.items()]
        await bot.send_message(chat_id=message.chat.id, text="\n".join(text_lines))

    async def show_photo_file_id(self, message: Message) -> None:
        if not self._is_admin(message.chat.id):
            return

        if not message.photo:
            return

        largest = message.photo[-1]
        await bot.reply_to(message, f"file_id: {largest.file_id}")

    # === New admin functionality ===
    async def show_admin_panel(self, message: Message) -> None:
        if not self._is_admin(message.chat.id):
            await bot.send_message(
                chat_id=message.chat.id,
                text="У вас нет прав для использования этой команды.",
            )
            return

        if not BACKEND_TELEGRAM_BASE_LINK or not FRONTEND_ADMIN_PATH:
            await bot.send_message(
                chat_id=message.chat.id,
                text="Web-админка не настроена. Нужны frontend.admin_path и публичный backend URL.",
            )
            return

        grant = await create_admin_bootstrap_token(
            jwt_encoder=self.jwt_encoder,
            actor=f"tg-admin-{message.chat.id}",
            tg_id=message.chat.id,
            redis_client=getattr(self.payment_queue_service, "redis_client", None),
        )
        admin_link = f"{BACKEND_TELEGRAM_BASE_LINK}/admin/session/bootstrap?grant={grant}"
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "Открыть web-админку",
                url=admin_link,
            )
        )

        await bot.send_message(
            chat_id=message.chat.id,
            text=(
                "Открою web-админку по временной ссылке.\n"
                f"Ссылка действует примерно {max(1, ADMIN_BOOTSTRAP_TTL_SECONDS // 60)} мин."
            ),
            reply_markup=markup,
        )
    async def handle_admin_callback(self, call: CallbackQuery) -> None:
        chat_id = call.message.chat.id
        if not self._is_admin(chat_id):
            return

        await bot.answer_callback_query(call.id)
        data = call.data

        if data == "admin_del_values":
            user = await self.repo.get(chat_id)
            if not user:
                await bot.send_message(chat_id, "Client not found")
                return

            self.sessions[chat_id] = {
                "state": "confirm_delete_self",
                "target_tg_id": chat_id,
            }
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("Confirm", callback_data="admin_confirm_delete"),
                InlineKeyboardButton("Cancel", callback_data="admin_cancel"),
            )
            await bot.send_message(chat_id, "Delete your client?", reply_markup=markup)

        elif data == "admin_send_all":
            self.sessions[chat_id] = {"state": "await_text_all"}
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Cancel", callback_data="admin_cancel"))
            await bot.send_message(chat_id, "Type your mess", reply_markup=markup)

        elif data == "admin_send_active":
            self.sessions[chat_id] = {"state": "await_text_active"}
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Cancel", callback_data="admin_cancel"))
            await bot.send_message(chat_id, "Type your mess", reply_markup=markup)

        elif data == "admin_cancel":
            self.sessions.pop(chat_id, None)
            await bot.send_message(chat_id, "Canceled")

        elif data == "admin_confirm_delete":
            session = self.sessions.pop(chat_id, {})
            target_tg_id = int(session.get("target_tg_id", chat_id))
            deleted = await self.subscription_user_service.delete_user(target_tg_id)
            await bot.send_message(
                chat_id,
                "Client deleted" if deleted else "User not found",
            )

        elif data == "admin_confirm_send_all":
            session = self.sessions.get(chat_id)
            if session:
                await self._broadcast_to_all(
                    session.get("text"), session.get("photo"), chat_id
                )
            self.sessions.pop(chat_id, None)

        elif data == "admin_last_users":
            await self.show_last_users(chat_id)

        elif data == "admin_search_user":
            self.sessions[chat_id] = {"state": "await_search_user"}
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("Cancel", callback_data="admin_cancel"))
            await bot.send_message(chat_id, "Enter TG ID:", reply_markup=markup)

        elif data.startswith("admin_user_"):
            target_tg_id = int(data.split("_")[2])
            await self.show_user_management(chat_id, target_tg_id)

        elif data.startswith("admin_del_user_"):
            target_tg_id = int(data.split("_")[3])
            self.sessions[chat_id] = {
                "state": "confirm_delete_user",
                "target_tg_id": target_tg_id,
            }
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    "Confirm",
                    callback_data="admin_confirm_delete_user",
                ),
                InlineKeyboardButton("Cancel", callback_data="admin_cancel"),
            )
            await bot.send_message(
                chat_id,
                f"Delete user {target_tg_id}?",
                reply_markup=markup,
            )

        elif data == "admin_confirm_delete_user":
            session = self.sessions.pop(chat_id, {})
            target_tg_id = session.get("target_tg_id")
            if target_tg_id is None:
                await bot.send_message(chat_id, "Delete session expired")
                return

            deleted = await self.subscription_user_service.delete_user(int(target_tg_id))
            await bot.send_message(
                chat_id,
                (
                    f"User {target_tg_id} deleted"
                    if deleted
                    else f"User {target_tg_id} not found"
                ),
            )

        elif data.startswith("admin_sub_"):
            target_tg_id = int(data.split("_")[2])
            await self.show_subscription_extension(chat_id, target_tg_id)

        elif data.startswith("admin_extend_"):
            parts = data.split("_")
            target_tg_id = int(parts[2])
            period = parts[3]
            await self.handle_extend_subscription(chat_id, target_tg_id, period)

        elif data == "admin_confirm_send_active":
            session = self.sessions.get(chat_id)
            if session:
                await self._broadcast_to_active(
                    session.get("text"), session.get("photo"), chat_id
                )
            self.sessions.pop(chat_id, None)

        elif data == "admin_retry_payment_dlq":
            await self.retry_payment_dlq(chat_id=chat_id, limit=100)
        elif data.startswith("admin_access_request_approve:"):
            if self.access_request_service is None:
                await bot.send_message(chat_id, "Модуль заявок недоступен")
                return
            _, request_id_raw, template_code = (data.split(":", 2) + ["", ""])[:3]
            try:
                result = await self.access_request_service.review_request(
                    request_id=int(request_id_raw),
                    decision="approve",
                    principal=SimpleNamespace(actor=f"tg-admin-{chat_id}"),
                    review_note="Approved from Telegram admin panel",
                    template_code=str(template_code or "").strip() or None,
                )
            except HTTPException as exc:
                if int(getattr(exc, "status_code", 0) or 0) == 409:
                    await self._finalize_access_request_message(
                        call,
                        text=(
                            "*Заявка уже обработана*\n\n"
                            "Доступ уже выдан или заявка уже закрыта в другом интерфейсе."
                        ),
                    )
                    return
                await bot.send_message(chat_id, str(exc.detail))
                return
            await self._finalize_access_request_message(
                call,
                text=(
                    "*Заявка одобрена*\n\n"
                    f"Шаблон: {getattr(result, 'approved_template_label', None) or getattr(result, 'requested_template_label', None) or 'не указан'}"
                ),
            )
            await bot.send_message(
                chat_id,
                f"Заявка одобрена. Шаблон: {getattr(result, 'approved_template_label', None) or getattr(result, 'requested_template_label', None) or 'не указан'}",
            )
        elif data.startswith("admin_access_request_reject:"):
            if self.access_request_service is None:
                await bot.send_message(chat_id, "Модуль заявок недоступен")
                return
            _, request_id_raw = (data.split(":", 1) + [""])[:2]
            try:
                await self.access_request_service.review_request(
                    request_id=int(request_id_raw),
                    decision="reject",
                    principal=SimpleNamespace(actor=f"tg-admin-{chat_id}"),
                    review_note="Rejected from Telegram admin panel",
                )
            except HTTPException as exc:
                if int(getattr(exc, "status_code", 0) or 0) == 409:
                    await self._finalize_access_request_message(
                        call,
                        text="*Заявка уже обработана*\n\nКнопки отключены, повторное решение не требуется.",
                    )
                    return
                await bot.send_message(chat_id, str(exc.detail))
                return
            await self._finalize_access_request_message(
                call,
                text="*Заявка отклонена*\n\nПовторное решение больше не требуется.",
            )
            await bot.send_message(chat_id, "Заявка отклонена.")

    @staticmethod
    async def _finalize_access_request_message(call: CallbackQuery, *, text: str) -> None:
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="Markdown",
                reply_markup=None,
            )
            return
        except Exception:
            await bot.edit_message_reply_markup(
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None,
            )
    async def handle_admin_text(self, message: Message) -> None:
        chat_id = message.chat.id
        if not self._is_admin(chat_id):
            return

        session = self.sessions.get(chat_id)
        if not session:
            return

        state = session.get("state")
        
        if state == "await_text_all":
            session["text"] = message.text or message.caption
            if message.photo:
                session["photo"] = message.photo[-1].file_id
            session["state"] = "confirm_send_all"
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("Confirm", callback_data="admin_confirm_send_all"),
                InlineKeyboardButton("Cancel", callback_data="admin_cancel"),
            )
            confirm_text = "Send message to all users?"
            if session.get("photo"):
                await bot.send_photo(
                    chat_id,
                    photo=session["photo"],
                    caption=f"{session['text']}\n\n{confirm_text}",
                    reply_markup=markup,
                    parse_mode='HTML'
                )
            else:
                await bot.send_message(
                    chat_id,
                    f"{session['text']}\n\n{confirm_text}",
                    reply_markup=markup,
                    parse_mode='HTML'
                )

        elif state == "await_text_active":
            session["text"] = message.text or message.caption
            if message.photo:
                session["photo"] = message.photo[-1].file_id
            session["state"] = "confirm_send_active"
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    "Confirm", callback_data="admin_confirm_send_active"
                ),
                InlineKeyboardButton("Cancel", callback_data="admin_cancel"),
            )
            confirm_text = "Send message to active users?"
            if session.get("photo"):
                await bot.send_photo(
                    chat_id,
                    photo=session["photo"],
                    caption=f"{session['text']}\n\n{confirm_text}",
                    reply_markup=markup, parse_mode='HTML'
                )
            else:
                await bot.send_message(
                    chat_id,
                    f"{session['text']}\n\n{confirm_text}",
                    reply_markup=markup, parse_mode='HTML'
                )

        elif state == "await_search_user":
            try:
                target_tg_id = int(message.text)
                user = await self.repo.get(target_tg_id)
                if user:
                    self.sessions.pop(chat_id, None)
                    await self.show_user_management(chat_id, target_tg_id)
                else:
                    await bot.send_message(chat_id, "User not found. Try again or cancel.")
            except ValueError:
                await bot.send_message(chat_id, "Invalid ID format. Please enter numbers only.")

    async def _broadcast_to_all(
        self, text: str | None, photo: str | None, admin_chat_id: int
    ) -> None:
        users = await self.repo.get_all()
        total = len(users)
        sent = 0
        for user in users:
            try:
                if photo:
                    await bot.send_photo(
                        chat_id=user.tg_id, photo=photo, caption=text or "", parse_mode='HTML'
                    )
                else:
                    await bot.send_message(chat_id=user.tg_id, text=text or "", parse_mode='HTML')
                sent += 1
                
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Failed to send to {user.tg_id}: {e}")

        await bot.send_message(
            admin_chat_id,
            f"Sent to {sent} of {total} users",
        )

    async def _broadcast_to_active(
        self, text: str | None, photo: str | None, admin_chat_id: int
    ) -> None:
        now_ts = self.timestamp.current_timestamp()
        active_users = await self.repo.get_active_users(now_ts)
        total = len(active_users)
        sent = 0
        for user in active_users:
            try:
                if photo:
                    await bot.send_photo(
                        chat_id=user.tg_id, photo=photo, caption=text or "", parse_mode='HTML'
                    )
                else:
                    await bot.send_message(chat_id=user.tg_id, text=text or "", parse_mode='HTML')
                sent += 1
            except Exception as e:
                logger.error(f"Failed to send to {user.tg_id}: {e}")

        await bot.send_message(
            admin_chat_id,
            f"Sent to {sent} of {total} active users",
        )

    async def show_last_users(self, admin_chat_id: int):
        users = await self.repo.get_last_users(10)
        markup = InlineKeyboardMarkup()
        for user in users:
            # We assume email or tg_id as label
            label = f"{user.email} ({user.tg_id})"
            markup.add(InlineKeyboardButton(label, callback_data=f"admin_user_{user.tg_id}"))

        await bot.send_message(admin_chat_id, "Last 10 registered users:", reply_markup=markup)

    async def show_user_management(self, admin_chat_id: int, target_tg_id: int):
        user = await self.repo.get(target_tg_id)
        if not user:
            await bot.send_message(admin_chat_id, "User not found")
            return

        info_text = (
            f"User: {user.email}\n"
            f"ID: {user.tg_id}\n"
            f"Expiration: {user.expiration_date or 'None'}"
        )
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(
                "Extend Subscription",
                callback_data=f"admin_sub_{target_tg_id}",
            )
        )
        markup.add(
            InlineKeyboardButton(
                "Delete User",
                callback_data=f"admin_del_user_{target_tg_id}",
            )
        )

        await bot.send_message(admin_chat_id, info_text, reply_markup=markup)

    async def show_subscription_extension(self, admin_chat_id: int, target_tg_id: int):
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("1 Month", callback_data=f"admin_extend_{target_tg_id}_month1"),
            InlineKeyboardButton("3 Months", callback_data=f"admin_extend_{target_tg_id}_month3"),
        )
        markup.add(
            InlineKeyboardButton("6 Months", callback_data=f"admin_extend_{target_tg_id}_month6"),
            InlineKeyboardButton("1 Year", callback_data=f"admin_extend_{target_tg_id}_year1"),
        )
        await bot.send_message(admin_chat_id, f"Select extension period for user {target_tg_id}:", reply_markup=markup)

    async def handle_extend_subscription(self, admin_chat_id: int, target_tg_id: int, period: str):
        try:
            await self.subscription_user_service.create_or_update_user(target_tg_id, period)
            await bot.send_message(admin_chat_id, f"Successfully extended subscription for user {target_tg_id} by {period}")
        except Exception as e:
            logger.error(f"Failed to extend subscription: {e}")
            await bot.send_message(admin_chat_id, f"Error extending subscription: {e}")

    async def retry_payment_dlq(self, chat_id: int, limit: int = 100) -> None:
        if not self._is_admin(chat_id):
            await bot.send_message(
                chat_id=chat_id,
                text="У вас нет прав для использования этой команды.",
            )
            return

        if limit <= 0:
            await bot.send_message(chat_id=chat_id, text="Limit должен быть > 0.")
            return

        safe_limit = min(limit, 1000)
        try:
            requeued, skipped = await self.payment_queue_service.requeue_dead_letters(
                limit=safe_limit,
            )
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    f"Payment DLQ retry finished.\n"
                    f"Requeued: {requeued}\n"
                    f"Skipped malformed: {skipped}\n"
                    f"Limit: {safe_limit}"
                ),
            )
        except Exception as err:
            logger.error(f"Failed to retry payment DLQ: {err}")
            await bot.send_message(
                chat_id=chat_id,
                text=f"Payment DLQ retry failed: {err}",
            )

    # @log_function_call(logger)
    # async def broadcast_to_all(self, message: Message):
    #     if not self._is_admin(message.chat.id):
    #         return

    #     broadcast_text = "Есть важное обновление сервиса..."
    #     from users.infrastructure.sql_user_repository import SQLUserRepository
    #     repo = build_user_repository()
    #     users = repo.get_all()
    #     success = 0

    #     for tg_id in users:
    #         try:
    #             tg_id = tg_id.tg_id
    #             subs_link = f"`{self.subscription_user_service.get_subscription_link(tg_id)}`"
    #             await bot_fun.send_message(chat_id=tg_id, text=broadcast_text)
    #             await bot_fun.send_message(chat_id=tg_id, text=subs_link, parse_mode='HTML')
    #             await self.instruction.show(message)
    #             success += 1
    #         except Exception as e:
    #             if "Forbidden" in str(e):
    #                 logger.info(f"User {tg_id} blocked bot_fun.")
    #             else:
    #                 logger.error(f"Send error to {tg_id}: {e}")
