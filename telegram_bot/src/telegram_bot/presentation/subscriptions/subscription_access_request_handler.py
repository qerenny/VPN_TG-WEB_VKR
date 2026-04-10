from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from telebot import types
from telebot.types import CallbackQuery

from fastapi import HTTPException
from shared.config.config import PHOTO_subscriptions
from shared.product_constants import ACCESS_REQUEST_KIND_NEW_ACCESS, ACCESS_REQUEST_KIND_RENEWAL, PRODUCT_SCOPE_STANDARD, PRODUCT_SCOPE_TRAFFIC_LIMITED
from shared.utils.access_template_labels import format_access_template_label
from shared.utils.logging_utils import logger
from telegram_bot.bot import bot
from telegram_bot.shared.config.navigation import BACK_TO_SUBSCRIPTIONS, MAIN_MENU
from telegram_bot.shared.texts import messages
from telegram_bot.shared.utils.menu_rendering import render_photo_menu
from telegram_bot.services.access.telegram_access_request_service import TelegramAccessRequestService


class SubscriptionAccessRequestHandler:
    DISPLAY_TIMEZONE = ZoneInfo("Europe/Moscow")
    SCOPE_LABELS = {
        PRODUCT_SCOPE_STANDARD: "🔑 Базовая конфигурация",
        PRODUCT_SCOPE_TRAFFIC_LIMITED: "📊 Доступ с лимитом трафика",
    }
    STANDARD_REQUEST_TEMPLATES = (
        ("month_1", "🔑 1 месяц · Базовая"),
        ("month_3", "🛡️ 3 месяца · Базовая"),
        ("month_6", "⭐ 6 месяцев · Базовая"),
        ("year_1", "👑 12 месяцев · Базовая"),
    )
    TRAFFIC_LIMITED_REQUEST_TEMPLATES = (
        ("traffic_limited_15gb", "📦 15 GB"),
        ("traffic_limited_35gb", "📦 35 GB"),
        ("traffic_limited_80gb", "📦 80 GB"),
    )

    def __init__(
        self,
        service: TelegramAccessRequestService,
        *,
        standard_config_enabled: bool = True,
        traffic_limited_config_enabled: bool = True,
    ) -> None:
        self.service = service
        self.standard_config_enabled = standard_config_enabled
        self.traffic_limited_config_enabled = traffic_limited_config_enabled

    async def submit_request(
        self,
        call: CallbackQuery,
        *,
        request_kind: str = "new_access",
        template_code: str | None = None,
    ) -> None:
        tg_id = int(call.message.chat.id)
        try:
            snapshot, created = await self.service.create_or_get_pending_request(
                tg_id=tg_id,
                request_kind=request_kind,
                template_code=template_code,
            )
        except HTTPException as exc:
            await bot.answer_callback_query(call.id, str(exc.detail), show_alert=True)
            return
        if created and self._is_auto_approved(snapshot):
            await bot.answer_callback_query(call.id, "Доступ активирован")
            await self.show_status(
                call,
                notice=messages.get_random_message("subscription_access_request_auto_approved"),
            )
            logger.info(f"Auto-approved Telegram access request id={snapshot.id} for tg_id={tg_id}")
            return
        if created:
            await bot.answer_callback_query(call.id, "Заявка отправлена")
            await self.show_status(
                call,
                notice=messages.get_random_message("subscription_access_request_created"),
            )
            logger.info(f"Created Telegram access request id={snapshot.id} for tg_id={tg_id}")
            return

        await bot.answer_callback_query(call.id, "У вас уже есть активная заявка")
        await self.show_status(
            call,
            notice=messages.get_random_message("subscription_access_request_pending_exists"),
        )

    async def show_request_menu(self, call: CallbackQuery) -> None:
        tg_id = int(call.message.chat.id)
        has_active_access = await self.service.has_active_access(tg_id=tg_id)
        is_registry_managed = await self.service.is_registry_managed(tg_id=int(call.message.chat.id))
        markup = types.InlineKeyboardMarkup()
        if not is_registry_managed:
            for scope, label in self._scope_buttons():
                markup.add(
                    types.InlineKeyboardButton(label, callback_data=f"sub_access_request_scope:{scope}"),
                )
        markup.add(types.InlineKeyboardButton(BACK_TO_SUBSCRIPTIONS, callback_data="profile_subscriptions"))
        markup.add(types.InlineKeyboardButton(MAIN_MENU, callback_data="menu_start"))

        if is_registry_managed:
            flow_copy = "Доступ для этого аккаунта управляется автоматически через реестр. Дополнительные заявки не нужны."
        elif has_active_access:
            flow_copy = "У тебя есть активный доступ. Выбери тип конфигурации — можно продлить текущий шаблон или выбрать другой."
        else:
            flow_copy = "Выбери тип конфигурации, а затем нужный шаблон доступа."

        await render_photo_menu(
            target=call,
            photo=PHOTO_subscriptions,
            caption=(
                "*📝 Запрос доступа*\n\n"
                f"{flow_copy}"
            ),
            reply_markup=markup,
            parse_mode="Markdown",
            bot_client=bot,
        )

    async def show_template_menu(self, call: CallbackQuery, *, scope: str) -> None:
        tg_id = int(call.message.chat.id)
        active_templates = await self.service.get_active_template_codes_by_scope(tg_id=tg_id)
        current_template_code = active_templates.get(str(scope).strip().lower())
        markup = types.InlineKeyboardMarkup()
        for code, label in self._template_buttons(scope=str(scope).strip().lower()):
            display_label = f"✅ {label}" if code == current_template_code else label
            markup.add(
                types.InlineKeyboardButton(
                    display_label,
                    callback_data=f"sub_access_request_submit:{code}",
                )
            )

        markup.add(types.InlineKeyboardButton("⬅️ К запросу доступа", callback_data="sub_access_request"))
        markup.add(types.InlineKeyboardButton(BACK_TO_SUBSCRIPTIONS, callback_data="profile_subscriptions"))

        title = self.SCOPE_LABELS.get(str(scope).strip().lower(), "Шаблон доступа")
        description = (
            "Текущий шаблон отмечен ✅. Выбери его для продления или другой — для замены."
            if current_template_code
            else "Выбери шаблон доступа:"
        )
        await render_photo_menu(
            target=call,
            photo=PHOTO_subscriptions,
            caption=f"*{title}*\n\n{description}",
            reply_markup=markup,
            parse_mode="Markdown",
            bot_client=bot,
        )

    async def submit_template_request(self, call: CallbackQuery, *, template_code: str) -> None:
        tg_id = int(call.message.chat.id)
        normalized_template_code = str(template_code or "").strip().lower()
        if not normalized_template_code:
            await bot.answer_callback_query(call.id, "Шаблон доступа не выбран", show_alert=True)
            return
        active_templates = await self.service.get_active_template_codes_by_scope(tg_id=tg_id)
        scope = self._scope_for_template(normalized_template_code)
        request_kind = ACCESS_REQUEST_KIND_NEW_ACCESS
        if scope is not None and active_templates.get(scope) == normalized_template_code:
            request_kind = ACCESS_REQUEST_KIND_RENEWAL
        await self.submit_request(
            call,
            request_kind=request_kind,
            template_code=normalized_template_code,
        )

    async def show_status(
        self,
        call: CallbackQuery,
        *,
        notice: str | None = None,
        alert_on_empty: bool = False,
    ) -> None:
        tg_id = int(call.message.chat.id)
        items = await self.service.list_requests(tg_id=tg_id, limit=5)
        if not items and alert_on_empty and not notice:
            await bot.answer_callback_query(
                call.id,
                messages.get_random_message("subscription_access_request_empty"),
                show_alert=True,
            )
            await self.show_request_menu(call)
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ К запросу доступа", callback_data="sub_access_request"))
        markup.add(types.InlineKeyboardButton(BACK_TO_SUBSCRIPTIONS, callback_data="profile_subscriptions"))
        markup.add(types.InlineKeyboardButton(MAIN_MENU, callback_data="menu_start"))

        text_parts: list[str] = []
        if notice:
            text_parts.append(notice)
        if not items:
            text_parts.append(messages.get_random_message("subscription_access_request_empty"))
        else:
            text_parts.append(messages.get_random_message("subscription_access_request_status_intro"))
            text_parts.append(self._format_request(items[0]))
            if len(items) > 1:
                text_parts.append(self._format_compact_history(items[1:]))

        await render_photo_menu(
            target=call,
            photo=PHOTO_subscriptions,
            caption="\n\n".join(part for part in text_parts if str(part).strip()),
            reply_markup=markup,
            parse_mode="Markdown",
            bot_client=bot,
        )

    def _format_request(self, item) -> str:
        status = SubscriptionAccessRequestHandler._status_label(item.status)
        normalized_request_kind = str(getattr(item, "request_kind", "")).strip().lower()
        request_kind = "Продление" if normalized_request_kind == "renewal" else "Новый доступ"
        status_icon = {"pending": "⏳", "approved": "✅", "rejected": "❌"}.get(
            str(item.status).strip().lower(), "📋"
        )

        lines = [
            f"{status_icon} *{status}* · {request_kind}",
            f"📅 {self._format_datetime(item.requested_at)}",
        ]

        approved_template_code = str(item.metadata.get("approved_template_code") or "").strip()
        requested_template_code = str(getattr(item, "requested_template_code", "") or "").strip()
        if approved_template_code:
            lines.append(f"Шаблон: {self._resolve_template_label(approved_template_code, request_kind=normalized_request_kind)}")
        elif requested_template_code:
            lines.append(f"Шаблон: {self._resolve_template_label(requested_template_code, request_kind=normalized_request_kind)}")
        elif normalized_request_kind == "renewal":
            lines.append("Шаблон: без смены")

        if getattr(item, "expires_at", None) and str(item.status).strip().lower() == "pending":
            lines.append(f"⏰ Истечёт: {self._format_datetime(item.expires_at)}")

        if SubscriptionAccessRequestHandler._is_auto_approved(item):
            lines.append("Решение: автоматически")
        elif getattr(item, "reviewed_by_actor", None):
            lines.append("Решение: администратор")

        if item.reviewed_at:
            lines.append(f"Рассмотрена: {self._format_datetime(item.reviewed_at)}")
        if item.review_note:
            lines.append(f"💬 {item.review_note}")

        return "\n".join(lines)

    def _format_compact_history(self, items) -> str:
        lines = ["*Ранее*"]
        for item in items:
            normalized_request_kind = str(getattr(item, "request_kind", "")).strip().lower()
            kind = "продление" if normalized_request_kind == "renewal" else "новый"
            status_icon = {"approved": "✅", "rejected": "❌", "pending": "⏳"}.get(
                str(item.status).strip().lower(), "•"
            )
            event_time = getattr(item, "reviewed_at", None) or getattr(item, "requested_at", None)
            lines.append(
                f"{status_icon} {kind} · {self._format_datetime(event_time)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _status_label(status: str) -> str:
        normalized = str(status or "").strip().lower()
        if normalized == "pending":
            return "На рассмотрении"
        if normalized == "approved":
            return "Одобрена"
        if normalized == "rejected":
            return "Отклонена"
        return normalized or "Неизвестно"

    @staticmethod
    def _is_auto_approved(item) -> bool:
        metadata = getattr(item, "metadata", {}) or {}
        return bool(metadata.get("auto_approved"))

    def _scope_buttons(self) -> list[tuple[str, str]]:
        buttons: list[tuple[str, str]] = []
        if self.standard_config_enabled:
            buttons.append((PRODUCT_SCOPE_STANDARD, self.SCOPE_LABELS[PRODUCT_SCOPE_STANDARD]))
        if self.traffic_limited_config_enabled:
            buttons.append((PRODUCT_SCOPE_TRAFFIC_LIMITED, self.SCOPE_LABELS[PRODUCT_SCOPE_TRAFFIC_LIMITED]))
        return buttons

    def _template_buttons(self, scope: str | None = None) -> list[tuple[str, str]]:
        buttons: list[tuple[str, str]] = []
        normalized_scope = str(scope or "").strip().lower()
        if self.standard_config_enabled and normalized_scope in {"", PRODUCT_SCOPE_STANDARD}:
            buttons.extend(self.STANDARD_REQUEST_TEMPLATES)
        if self.traffic_limited_config_enabled and normalized_scope in {"", PRODUCT_SCOPE_TRAFFIC_LIMITED}:
            buttons.extend(self.TRAFFIC_LIMITED_REQUEST_TEMPLATES)
        return buttons

    def _resolve_template_label(self, template_code: str | None, *, request_kind: str) -> str:
        normalized = str(template_code or "").strip().lower()
        if not normalized and str(request_kind).strip().lower() == ACCESS_REQUEST_KIND_RENEWAL:
            return "Продление без смены шаблона"
        for code, label in self._template_buttons():
            if code == normalized:
                return label
        return format_access_template_label(normalized)

    @staticmethod
    def _scope_for_template(template_code: str | None) -> str | None:
        normalized = str(template_code or "").strip().lower()
        if normalized.startswith("traffic_limited_"):
            return PRODUCT_SCOPE_TRAFFIC_LIMITED
        if normalized:
            return PRODUCT_SCOPE_STANDARD
        return None

    @classmethod
    def _format_datetime(cls, value: str | None) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            return "—"
        try:
            dt = datetime.fromisoformat(normalized)
        except ValueError:
            return normalized
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(cls.DISPLAY_TIMEZONE).replace(microsecond=0).strftime("%d.%m.%Y %H:%M")
