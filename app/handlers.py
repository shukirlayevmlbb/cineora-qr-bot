from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ErrorEvent,
    InputMediaPhoto,
    Message,
    ReplyKeyboardRemove,
)

from .config import Config
from .db import Database, QRRecord
from .keyboards import (
    cancel_keyboard,
    choice_keyboard,
    confirm,
    history_detail,
    history_menu,
    location_keyboard,
    main_menu,
    qr_actions,
    settings_menu,
    settings_styles,
    types_menu,
)
from .payloads import TYPE_STEPS, build_payload, make_label
from .qr_builder import STYLES, build_png, build_svg
from .states import CreateQR
from .texts import CANCELLED, HELP, STYLE_LABELS, TYPE_LABELS, WELCOME
from .validators import ValidationError

router = Router(name="main")
logger = logging.getLogger(__name__)


def qr_caption(record: QRRecord) -> str:
    type_label = TYPE_LABELS.get(record.qr_type, "QR kod")
    return (
        f"<b>QR kod tayyor</b>\n\n"
        f"{type_label}\n"
        f"<b>Nomi:</b> {html.escape(record.label)}\n\n"
        "Rangni pastdagi tugmalardan almashtirishingiz mumkin. "
        "Ulashish uchun ushbu xabarni boshqa chatga yuboring."
    )


async def safe_edit(callback: CallbackQuery, text: str, reply_markup=None) -> None:
    if not callback.message:
        return
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as exc:
        if "message is not modified" not in str(exc).lower():
            await callback.message.answer(text, reply_markup=reply_markup)


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, db: Database, config: Config) -> None:
    await state.clear()
    assert message.from_user is not None
    await db.ensure_user(message.from_user.id)
    await message.answer(WELCOME, reply_markup=main_menu(config.webapp_url))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(HELP, reply_markup=main_menu())


@router.message(Command("cancel"))
async def cancel_command(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(CANCELLED, reply_markup=ReplyKeyboardRemove())
    await message.answer(WELCOME, reply_markup=main_menu())


@router.message(Command("stats"))
async def stats_command(message: Message, db: Database, config: Config) -> None:
    if not message.from_user or message.from_user.id not in config.admin_ids:
        return
    values = await db.stats()
    await message.answer(
        "<b>Bot statistikasi</b>\n\n"
        f"Foydalanuvchilar: <b>{values['users']}</b>\n"
        f"Jami QR: <b>{values['total']}</b>\n"
        f"Bugun: <b>{values['today']}</b>"
    )


@router.callback_query(F.data == "menu:home")
async def menu_home(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    await safe_edit(callback, WELCOME, main_menu())


@router.callback_query(F.data == "menu:create")
async def menu_create(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    text = "<b>QR turini tanlang</b>\n\nEng ko‘p ishlatiladigan turlar quyida."
    if callback.message and callback.message.photo:
        await callback.message.answer(text, reply_markup=types_menu(0))
    else:
        await safe_edit(callback, text, types_menu(0))


@router.callback_query(F.data.startswith("types:"))
async def types_page(callback: CallbackQuery) -> None:
    await callback.answer()
    page = int(callback.data.rsplit(":", 1)[1])
    title = "<b>QR turini tanlang</b>\n\n" + ("Asosiy turlar:" if page == 0 else "Qo‘shimcha turlar:")
    await safe_edit(callback, title, types_menu(page))


@router.callback_query(F.data.startswith("type:"))
async def select_type(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    qr_type = callback.data.split(":", 1)[1]
    if qr_type not in TYPE_STEPS:
        await callback.answer("Bu tur topilmadi.", show_alert=True)
        return
    await state.set_state(CreateQR.waiting_input)
    await state.set_data({"qr_type": qr_type, "step": 0, "values": {}})
    await ask_current_step(callback.message, state)


async def ask_current_step(message: Message | None, state: FSMContext) -> None:
    if not message:
        return
    data = await state.get_data()
    qr_type = data["qr_type"]
    index = int(data["step"])
    step = TYPE_STEPS[qr_type][index]
    progress = f"<b>{TYPE_LABELS[qr_type]}</b> · {index + 1}/{len(TYPE_STEPS[qr_type])}\n\n"
    if step.kind == "choice":
        await state.set_state(CreateQR.waiting_choice)
        await message.answer(progress + step.prompt, reply_markup=choice_keyboard(step.choices))
    elif step.kind == "location":
        await state.set_state(CreateQR.waiting_input)
        await message.answer(progress + step.prompt, reply_markup=location_keyboard())
    else:
        await state.set_state(CreateQR.waiting_input)
        await message.answer(progress + step.prompt, reply_markup=cancel_keyboard())


@router.callback_query(F.data == "flow:cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer(CANCELLED)
    await state.clear()
    if callback.message:
        await callback.message.answer(WELCOME, reply_markup=main_menu())


@router.callback_query(CreateQR.waiting_choice, F.data.startswith("choice:"))
async def receive_choice(callback: CallbackQuery, state: FSMContext, db: Database) -> None:
    await callback.answer()
    data = await state.get_data()
    qr_type = data["qr_type"]
    index = int(data["step"])
    step = TYPE_STEPS[qr_type][index]
    value = callback.data.split(":", 1)[1]
    allowed = {choice_value for _, choice_value in step.choices}
    if value not in allowed:
        await callback.answer("Noto‘g‘ri tanlov.", show_alert=True)
        return
    values = dict(data["values"])
    values[step.key] = value
    await advance(callback.message, state, db, qr_type, index, values, callback.from_user.id)


@router.message(CreateQR.waiting_input)
async def receive_input(message: Message, state: FSMContext, db: Database) -> None:
    if not message.from_user:
        return
    data = await state.get_data()
    qr_type = data["qr_type"]
    index = int(data["step"])
    step = TYPE_STEPS[qr_type][index]

    try:
        if step.kind == "location" and message.location:
            value = (round(message.location.latitude, 7), round(message.location.longitude, 7))
        elif message.text:
            value = step.validator(message.text)
        else:
            raise ValidationError("Iltimos, matn ko‘rinishida javob yuboring.")
    except ValidationError as exc:
        await message.answer(f"⚠️ {html.escape(str(exc))}\n\nQayta kiriting:", reply_markup=cancel_keyboard())
        return

    values = dict(data["values"])
    values[step.key] = value
    await advance(message, state, db, qr_type, index, values, message.from_user.id)


async def advance(
    message: Message | None,
    state: FSMContext,
    db: Database,
    qr_type: str,
    index: int,
    values: dict,
    user_id: int,
) -> None:
    if not message:
        return
    next_index = index + 1
    if qr_type == "wifi" and index == 1 and not values.get("password"):
        values["security"] = "nopass"
        next_index = 3
    if next_index < len(TYPE_STEPS[qr_type]):
        await state.update_data(step=next_index, values=values)
        await ask_current_step(message, state)
        return

    payload = build_payload(qr_type, values)
    if qr_type == "event" and values["end"] <= values["start"]:
        await state.update_data(step=2, values=values)
        await state.set_state(CreateQR.waiting_input)
        await message.answer(
            "⚠️ Tugash vaqti boshlanish vaqtidan keyin bo‘lishi kerak.\n\n"
            "Tugash vaqtini qayta kiriting:",
            reply_markup=cancel_keyboard(),
        )
        return
    label = make_label(qr_type, values)
    settings = await db.get_settings(user_id)
    is_saved = settings.history_enabled and (qr_type != "wifi" or settings.save_wifi_history)
    record_id = await db.add_record(
        user_id, qr_type, payload, label, settings.default_style, is_saved
    )
    record = await db.get_record(record_id, user_id)
    assert record is not None
    await state.clear()
    await message.answer("QR kod tayyorlanmoqda…", reply_markup=ReplyKeyboardRemove())
    try:
        image = await asyncio.to_thread(build_png, payload, settings.default_style)
    except Exception:
        logger.exception("QR generation failed")
        await message.answer("QR kodni yaratishda xato yuz berdi. Ma’lumotni qisqartirib qayta urinib ko‘ring.")
        return
    if qr_type == "wifi" and not settings.save_wifi_history:
        history_note = "\n\n<i>Wi‑Fi paroli maxfiyligi uchun bu QR tarixga saqlanmadi.</i>"
    elif not settings.history_enabled:
        history_note = "\n\n<i>Tarix o‘chiq: bu QR 24 soatdan keyin avtomatik o‘chadi.</i>"
    else:
        history_note = ""
    await message.answer_photo(
        BufferedInputFile(image, filename="qr-code.png"),
        caption=qr_caption(record) + history_note,
        reply_markup=qr_actions(record.id, record.style),
    )


@router.callback_query(F.data.startswith("qr:style:"))
async def change_qr_style(callback: CallbackQuery, db: Database) -> None:
    _, _, record_id_raw, style = callback.data.split(":", 3)
    if style not in STYLES:
        await callback.answer("Noto‘g‘ri dizayn.", show_alert=True)
        return
    record = await db.get_record(int(record_id_raw), callback.from_user.id)
    if not record:
        await callback.answer("QR topilmadi yoki muddati tugagan.", show_alert=True)
        return
    await callback.answer("Dizayn yangilanmoqda…")
    image = await asyncio.to_thread(build_png, record.payload, style)
    await db.update_style(record.id, callback.from_user.id, style)
    record = await db.get_record(record.id, callback.from_user.id)
    assert record is not None
    if callback.message:
        try:
            await callback.message.edit_media(
                media=InputMediaPhoto(
                    media=BufferedInputFile(image, filename="qr-code.png"),
                    caption=qr_caption(record),
                    parse_mode="HTML",
                ),
                reply_markup=qr_actions(record.id, style),
            )
        except TelegramBadRequest:
            await callback.message.answer_photo(
                BufferedInputFile(image, filename="qr-code.png"),
                caption=qr_caption(record), reply_markup=qr_actions(record.id, style),
            )


@router.callback_query(F.data.startswith("qr:svg:"))
async def download_svg(callback: CallbackQuery, db: Database) -> None:
    record_id = int(callback.data.rsplit(":", 1)[1])
    record = await db.get_record(record_id, callback.from_user.id)
    if not record or not callback.message:
        await callback.answer("QR topilmadi yoki muddati tugagan.", show_alert=True)
        return
    await callback.answer("SVG tayyorlanmoqda…")
    data = await asyncio.to_thread(build_svg, record.payload)
    safe_name = "".join(ch for ch in record.label if ch.isalnum() or ch in "-_ ").strip()[:35] or "qr-code"
    await callback.message.answer_document(
        BufferedInputFile(data, filename=f"{safe_name}.svg"),
        caption="SVG — bosma va katta o‘lchamlar uchun sifat yo‘qotmaydigan format.",
    )


@router.callback_query(F.data.startswith("menu:history:"))
async def show_history(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    page = max(0, int(callback.data.rsplit(":", 1)[1]))
    total = await db.history_count(callback.from_user.id)
    records = await db.list_history(callback.from_user.id, limit=8, offset=page * 8)
    if not records and page > 0:
        page = 0
        records = await db.list_history(callback.from_user.id, limit=8)
    text = (
        f"<b>Mening QRlarim</b>\n\nJami: {total}. Kerakli QR kodni tanlang."
        if total else
        "<b>Mening QRlarim</b>\n\nHozircha saqlangan QR kod yo‘q."
    )
    if callback.message and callback.message.photo:
        await callback.message.answer(text, reply_markup=history_menu(records, page, total))
    else:
        await safe_edit(callback, text, history_menu(records, page, total))


@router.callback_query(F.data.startswith("history:view:"))
async def history_view(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    record_id = int(callback.data.rsplit(":", 1)[1])
    record = await db.get_record(record_id, callback.from_user.id)
    if not record:
        await callback.answer("QR topilmadi.", show_alert=True)
        return
    created = (
        datetime.fromisoformat(record.created_at)
        .astimezone(ZoneInfo("Asia/Tashkent"))
        .strftime("%d.%m.%Y %H:%M")
    )
    text = (
        f"<b>{html.escape(record.label)}</b>\n\n"
        f"Turi: {TYPE_LABELS.get(record.qr_type, 'QR')}\n"
        f"Dizayn: {STYLE_LABELS.get(record.style, record.style)}\n"
        f"Yaratilgan: {created}"
    )
    await safe_edit(callback, text, history_detail(record.id))


@router.callback_query(F.data.startswith("history:open:"))
async def history_open(callback: CallbackQuery, db: Database) -> None:
    record_id = int(callback.data.rsplit(":", 1)[1])
    record = await db.get_record(record_id, callback.from_user.id)
    if not record or not callback.message:
        await callback.answer("QR topilmadi.", show_alert=True)
        return
    await callback.answer("QR ochilmoqda…")
    image = await asyncio.to_thread(build_png, record.payload, record.style)
    await callback.message.answer_photo(
        BufferedInputFile(image, filename="qr-code.png"),
        caption=qr_caption(record), reply_markup=qr_actions(record.id, record.style),
    )


@router.callback_query(F.data.startswith("history:delete:ask:"))
async def history_delete_ask(callback: CallbackQuery) -> None:
    await callback.answer()
    record_id = callback.data.rsplit(":", 1)[1]
    await safe_edit(callback, "Bu QR kodni tarixdan o‘chirasizmi?", confirm("history:delete", record_id))


@router.callback_query(F.data.startswith("history:delete:yes:"))
async def history_delete_yes(callback: CallbackQuery, db: Database) -> None:
    await callback.answer("O‘chirildi")
    record_id = int(callback.data.rsplit(":", 1)[1])
    await db.delete_record(record_id, callback.from_user.id)
    total = await db.history_count(callback.from_user.id)
    records = await db.list_history(callback.from_user.id, limit=8)
    await safe_edit(callback, "<b>Mening QRlarim</b>\n\nQR kod o‘chirildi.", history_menu(records, 0, total))


@router.callback_query(F.data == "history:clear:ask")
async def history_clear_ask(callback: CallbackQuery) -> None:
    await callback.answer()
    await safe_edit(callback, "Barcha saqlangan QR kodlarni o‘chirasizmi? Bu amalni qaytarib bo‘lmaydi.", confirm("history:clear"))


@router.callback_query(F.data == "history:clear:yes")
async def history_clear_yes(callback: CallbackQuery, db: Database) -> None:
    count = await db.clear_history(callback.from_user.id)
    await callback.answer(f"{count} ta QR o‘chirildi")
    await safe_edit(callback, "<b>Mening QRlarim</b>\n\nTarix tozalandi.", history_menu([], 0, 0))


@router.callback_query(F.data == "menu:settings")
async def show_settings(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    settings = await db.get_settings(callback.from_user.id)
    text = (
        "<b>Sozlamalar</b>\n\n"
        "Dizayn — yangi QR kodlar uchun standart rang.\n"
        "Wi‑Fi tarixi o‘chiq bo‘lsa, parol bazada doimiy saqlanmaydi."
    )
    if callback.message and callback.message.photo:
        await callback.message.answer(text, reply_markup=settings_menu(settings))
    else:
        await safe_edit(callback, text, settings_menu(settings))


@router.callback_query(F.data == "settings:styles")
async def settings_style_list(callback: CallbackQuery, db: Database) -> None:
    await callback.answer()
    settings = await db.get_settings(callback.from_user.id)
    await safe_edit(callback, "<b>Standart dizayn</b>\n\nYangi QR kodlar uchun rangni tanlang:", settings_styles(settings.default_style))


@router.callback_query(F.data.startswith("settings:style:"))
async def settings_set_style(callback: CallbackQuery, db: Database) -> None:
    style = callback.data.rsplit(":", 1)[1]
    if style not in STYLES:
        await callback.answer("Noto‘g‘ri rang.", show_alert=True)
        return
    await db.set_setting(callback.from_user.id, "default_style", style)
    await callback.answer("Standart dizayn saqlandi")
    settings = await db.get_settings(callback.from_user.id)
    await safe_edit(callback, "<b>Standart dizayn</b>\n\nTanlov saqlandi.", settings_styles(settings.default_style))


@router.callback_query(F.data == "settings:toggle_history")
async def toggle_history(callback: CallbackQuery, db: Database) -> None:
    settings = await db.get_settings(callback.from_user.id)
    await db.set_setting(callback.from_user.id, "history_enabled", int(not settings.history_enabled))
    await callback.answer("Sozlama yangilandi")
    updated = await db.get_settings(callback.from_user.id)
    await safe_edit(callback, "<b>Sozlamalar</b>\n\nO‘zgarish saqlandi.", settings_menu(updated))


@router.callback_query(F.data == "settings:toggle_wifi")
async def toggle_wifi_history(callback: CallbackQuery, db: Database) -> None:
    settings = await db.get_settings(callback.from_user.id)
    await db.set_setting(callback.from_user.id, "save_wifi_history", int(not settings.save_wifi_history))
    await callback.answer("Wi‑Fi tarixi sozlamasi yangilandi")
    updated = await db.get_settings(callback.from_user.id)
    await safe_edit(callback, "<b>Sozlamalar</b>\n\nO‘zgarish saqlandi.", settings_menu(updated))


@router.callback_query(F.data == "menu:help")
async def menu_help(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message and callback.message.photo:
        await callback.message.answer(HELP, reply_markup=main_menu())
    else:
        await safe_edit(callback, HELP, main_menu())


@router.error()
async def error_handler(event: ErrorEvent) -> bool:
    exc = event.exception
    logger.error("Unhandled update error", exc_info=(type(exc), exc, exc.__traceback__))
    update = event.update
    message = update.message or (update.callback_query.message if update.callback_query else None)
    if message:
        try:
            await message.answer("Kutilmagan xato yuz berdi. /start buyrug‘i bilan qayta urinib ko‘ring.")
        except Exception:
            logger.exception("Could not send error notification")
    return True
