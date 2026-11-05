from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from .db import QRRecord, UserSettings
from .texts import STYLE_LABELS, TYPE_LABELS


def main_menu(webapp_url: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if webapp_url:
        builder.row(InlineKeyboardButton(text="Cineora QR Mini App", web_app=WebAppInfo(url=webapp_url)))
    builder.button(text="＋ QR yaratish", callback_data="menu:create")
    builder.button(text="🕘 Mening QRlarim", callback_data="menu:history:0")
    builder.button(text="⚙️ Sozlamalar", callback_data="menu:settings")
    builder.button(text="ℹ️ Yordam", callback_data="menu:help")
    builder.adjust(1, 1, 2, 1)
    return builder.as_markup()


def types_menu(page: int = 0) -> InlineKeyboardMarkup:
    first = ["web", "wifi", "phone", "text", "telegram"]
    second = ["email", "sms", "whatsapp", "contact", "location", "event"]
    items = first if page == 0 else second
    builder = InlineKeyboardBuilder()
    for item in items:
        builder.button(text=TYPE_LABELS[item], callback_data=f"type:{item}")
    builder.adjust(2)
    if page == 0:
        builder.row(InlineKeyboardButton(text="Yana turlar →", callback_data="types:1"))
    else:
        builder.row(InlineKeyboardButton(text="← Asosiy turlar", callback_data="types:0"))
    builder.row(InlineKeyboardButton(text="‹ Bosh menyu", callback_data="menu:home"))
    return builder.as_markup()


def choice_keyboard(choices: tuple[tuple[str, str], ...]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for label, value in choices:
        builder.button(text=label, callback_data=f"choice:{value}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="✕ Bekor qilish", callback_data="flow:cancel"))
    return builder.as_markup()


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✕ Bekor qilish", callback_data="flow:cancel")
    ]])


def location_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Hozirgi lokatsiyani yuborish", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Lokatsiya yoki koordinata",
    )


def qr_actions(record_id: int, current_style: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for style, label in STYLE_LABELS.items():
        prefix = "✓ " if style == current_style else ""
        builder.button(text=prefix + label, callback_data=f"qr:style:{record_id}:{style}")
    builder.adjust(3, 2)
    builder.row(
        InlineKeyboardButton(text="SVG yuklash", callback_data=f"qr:svg:{record_id}"),
        InlineKeyboardButton(text="Yangi QR", callback_data="menu:create"),
    )
    return builder.as_markup()


def history_menu(records: list[QRRecord], page: int, total: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for record in records:
        icon = TYPE_LABELS.get(record.qr_type, "QR").split()[0]
        builder.button(text=f"{icon} {record.label[:34]}", callback_data=f"history:view:{record.id}")
    builder.adjust(1)
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="←", callback_data=f"menu:history:{page - 1}"))
    if (page + 1) * 8 < total:
        nav.append(InlineKeyboardButton(text="→", callback_data=f"menu:history:{page + 1}"))
    if nav:
        builder.row(*nav)
    if total:
        builder.row(InlineKeyboardButton(text="Tarixni tozalash", callback_data="history:clear:ask"))
    builder.row(InlineKeyboardButton(text="‹ Bosh menyu", callback_data="menu:home"))
    return builder.as_markup()


def history_detail(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="QRni ochish", callback_data=f"history:open:{record_id}"),
            InlineKeyboardButton(text="O‘chirish", callback_data=f"history:delete:ask:{record_id}"),
        ],
        [InlineKeyboardButton(text="‹ Tarix", callback_data="menu:history:0")],
    ])


def settings_menu(settings: UserSettings) -> InlineKeyboardMarkup:
    history = "Yoqilgan" if settings.history_enabled else "O‘chiq"
    wifi = "Yoqilgan" if settings.save_wifi_history else "O‘chiq"
    builder = InlineKeyboardBuilder()
    style_label = STYLE_LABELS.get(settings.default_style, STYLE_LABELS["classic"])
    builder.button(text=f"Dizayn: {style_label}", callback_data="settings:styles")
    builder.button(text=f"Tarix: {history}", callback_data="settings:toggle_history")
    builder.button(text=f"Wi‑Fi tarixda: {wifi}", callback_data="settings:toggle_wifi")
    builder.button(text="‹ Bosh menyu", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def settings_styles(current: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for style, label in STYLE_LABELS.items():
        prefix = "✓ " if style == current else ""
        builder.button(text=prefix + label, callback_data=f"settings:style:{style}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="‹ Sozlamalar", callback_data="menu:settings"))
    return builder.as_markup()


def confirm(action: str, target: str = "") -> InlineKeyboardMarkup:
    suffix = f":{target}" if target else ""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Ha, o‘chirish", callback_data=f"{action}:yes{suffix}"),
            InlineKeyboardButton(text="Yo‘q", callback_data="menu:history:0"),
        ]
    ])
