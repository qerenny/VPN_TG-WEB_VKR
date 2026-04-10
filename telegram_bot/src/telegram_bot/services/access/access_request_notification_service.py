from __future__ import annotations

from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlmodel import select

from shared.config.config import BOT_ADMIN_IDS
from shared.config.database.session import get_db_session
from shared.config.settings import get_effective_product_feature_settings
from shared.models.users.telegram_account_model import TelegramAccount
from shared.models.users.web_account_model import WebAccount
from shared.utils.access_template_labels import format_access_template_label
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.shared.keyboards import build_profile_navigation_markup


class AccessRequestNotificationService:
    def __init__(self, telegram_link_service=None) -> None:
        self.telegram_link_service = telegram_link_service

    @staticmethod
    def _request_kind_label(request_kind: str) -> str:
        return "Продление доступа" if str(request_kind).strip().lower() == "renewal" else "Запрос доступа"

    @staticmethod
    def _source_type_label(source_type: str) -> str:
        normalized = str(source_type or "").strip().lower()
        if normalized == "request_approval":
            return "Заявка"
        if normalized == "access_registry":
            return "Реестр доступа"
        if normalized == "access_registry_auto_renew":
            return "Автопродление по реестру"
        if normalized == "admin_override":
            return "Административная выдача"
        if normalized == "payment":
            return "Оформление доступа"
        return normalized or "Не указан"

    async def notify_admins_request_created(
        self,
        *,
        request_id: int,
        user_id: int,
        request_kind: str,
        requested_template_code: str | None,
        channel: str,
        comment: str | None,
    ) -> None:
        if not self._telegram_runtime_enabled():
            return

        template_value = str(requested_template_code or "").strip().lower() or None
        requester_identity_line = await self._resolve_requester_identity_line(
            user_id=int(user_id),
            channel=channel,
        )
        text = (
            "*Новая заявка на доступ*\n\n"
            f"ID: `{request_id}`\n"
            f"User ID: `{user_id}`\n"
            f"{requester_identity_line}\n"
            f"Тип: {self._request_kind_label(request_kind)}\n"
            f"Канал: `{channel}`\n"
            f"Шаблон: {format_access_template_label(requested_template_code)}\n"
            f"Комментарий: {comment or '—'}"
        )
        if template_value is None:
            text += "\n\nДля быстрого подтверждения в Telegram пользователь должен указать шаблон доступа."
        await self._fanout_admin_message(
            text,
            reply_markup=self._build_admin_request_markup(
                request_id=int(request_id),
                template_code=template_value,
            ),
        )

    async def notify_user_request_reviewed(
        self,
        *,
        user_id: int,
        request_id: int,
        status: str,
        request_kind: str,
        template_code: str | None,
        review_note: str | None,
        reviewed_by_actor: str | None,
        auto_approved: bool = False,
    ) -> None:
        if not self._telegram_runtime_enabled():
            return

        tg_id = await self._resolve_user_tg_id(int(user_id))
        if tg_id is None:
            return

        status_label = {
            "approved": "одобрена",
            "rejected": "отклонена",
            "expired": "истекла",
        }.get(str(status).strip().lower(), str(status))
        source = "автоматически" if auto_approved else "администратором"
        text = (
            "*Решение по заявке на доступ*\n\n"
            f"Статус: *{status_label}*\n"
            f"Тип: {self._request_kind_label(request_kind)}\n"
            f"Шаблон: {format_access_template_label(template_code)}\n"
            f"Источник решения: {source}\n"
            f"Комментарий: {review_note or '—'}"
        )
        await self._send_message(
            tg_id=tg_id,
            text=text,
            reply_markup=await self._build_user_navigation_markup(tg_id=tg_id),
        )

    async def notify_user_access_activated(
        self,
        *,
        user_id: int,
        source_type: str,
        template_code: str,
    ) -> None:
        if not self._telegram_runtime_enabled():
            return
        tg_id = await self._resolve_user_tg_id(int(user_id))
        if tg_id is None:
            return
        text = (
            "*Доступ активирован*\n\n"
            f"Источник: {self._source_type_label(source_type)}\n"
            f"Шаблон: {format_access_template_label(template_code)}\n"
            "Конфигурация уже выдана и доступна в кабинете."
        )
        await self._send_message(
            tg_id=tg_id,
            text=text,
            reply_markup=await self._build_user_navigation_markup(tg_id=tg_id),
        )

    async def _resolve_user_tg_id(self, user_id: int) -> int | None:
        async with get_db_session() as session:
            telegram_id = (
                await session.execute(
                    select(TelegramAccount.telegram_id).where(
                        TelegramAccount.user_id == int(user_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        return int(telegram_id) if telegram_id is not None else None

    async def _resolve_requester_identity_line(self, *, user_id: int, channel: str) -> str:
        normalized_channel = str(channel or "").strip().lower()
        async with get_db_session() as session:
            telegram_account = (
                await session.execute(
                    select(TelegramAccount).where(
                        TelegramAccount.user_id == int(user_id),
                        TelegramAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            web_account = (
                await session.execute(
                    select(WebAccount).where(
                        WebAccount.user_id == int(user_id),
                        WebAccount.revoked_at.is_(None),
                    )
                )
            ).scalar_one_or_none()

        email = str(getattr(web_account, "email", "") or "").strip()
        username = str(getattr(telegram_account, "username", "") or "").strip()
        telegram_id = getattr(telegram_account, "telegram_id", None)

        if normalized_channel == "telegram":
            if username:
                return f"Telegram: `@{username.lstrip('@')}`"
            if telegram_id is not None:
                return f"Telegram ID: `{telegram_id}`"
            return f"Email: `{email}`" if email else "Контакт: `—`"

        if normalized_channel == "web":
            if email:
                return f"Email: `{email}`"
            if username:
                return f"Telegram: `@{username.lstrip('@')}`"
            return f"Telegram ID: `{telegram_id}`" if telegram_id is not None else "Контакт: `—`"

        if email:
            return f"Email: `{email}`"
        if username:
            return f"Telegram: `@{username.lstrip('@')}`"
        if telegram_id is not None:
            return f"Telegram ID: `{telegram_id}`"
        return "Контакт: `—`"

    async def _build_user_navigation_markup(self, *, tg_id: int) -> InlineKeyboardMarkup:
        cabinet_url = None
        if self.telegram_link_service is not None:
            try:
                cabinet_url = await self.telegram_link_service.create_web_link(tg_id=int(tg_id))
            except Exception as err:  # pragma: no cover - best effort
                logger.warning(f"Failed to build cabinet link for tg_id={tg_id}: {err}")
        return build_profile_navigation_markup(cabinet_url=cabinet_url)

    @staticmethod
    def _build_admin_request_markup(*, request_id: int, template_code: str | None) -> InlineKeyboardMarkup:
        markup = InlineKeyboardMarkup()
        if template_code:
            markup.add(
                InlineKeyboardButton(
                    "✅ Подтвердить",
                    callback_data=f"admin_access_request_approve:{int(request_id)}:{template_code}",
                ),
                InlineKeyboardButton(
                    "❌ Отклонить",
                    callback_data=f"admin_access_request_reject:{int(request_id)}",
                ),
            )
        else:
            markup.add(
                InlineKeyboardButton(
                    "❌ Отклонить",
                    callback_data=f"admin_access_request_reject:{int(request_id)}",
                ),
            )
        return markup

    async def _fanout_admin_message(self, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        for admin_id in BOT_ADMIN_IDS:
            try:
                await self._send_message(tg_id=int(admin_id), text=text, reply_markup=reply_markup)
            except Exception as err:  # pragma: no cover - best effort
                logger.warning(f"Failed to deliver access request admin notification to {admin_id}: {err}")

    @staticmethod
    async def _send_message(*, tg_id: int, text: str, reply_markup=None) -> None:
        await bot.send_message(chat_id=int(tg_id), text=text, parse_mode="Markdown", reply_markup=reply_markup)

    @staticmethod
    def _telegram_runtime_enabled() -> bool:
        return bool(get_effective_product_feature_settings().telegram_bot_enabled)
