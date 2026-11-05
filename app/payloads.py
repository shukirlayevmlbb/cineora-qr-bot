from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import quote, urlencode

from . import validators


Validator = Callable[[str], Any]


@dataclass(frozen=True, slots=True)
class Step:
    key: str
    prompt: str
    validator: Validator
    kind: str = "text"
    choices: tuple[tuple[str, str], ...] = ()


TYPE_STEPS: dict[str, tuple[Step, ...]] = {
    "web": (
        Step("url", "Havolani yuboring.\n\nMasalan: <code>cineora.uz</code>", validators.website),
    ),
    "wifi": (
        Step("ssid", "Wi‑Fi tarmog‘i nomini kiriting:", lambda v: validators.nonempty(v, max_length=64)),
        Step("password", "Wi‑Fi parolini kiriting. Ochiq tarmoq bo‘lsa <code>-</code> yuboring:", lambda v: validators.optional_text(v, max_length=128)),
        Step("security", "Himoya turini tanlang:", validators.nonempty, "choice", (("WPA/WPA2/WPA3", "WPA"), ("WEP", "WEP"))),
        Step("hidden", "Tarmoq nomi yashirilganmi?", validators.nonempty, "choice", (("Yo‘q", "false"), ("Ha", "true"))),
    ),
    "phone": (
        Step("phone", "Telefon raqamini yuboring.\n\nMasalan: <code>+998901234567</code>", validators.phone),
    ),
    "text": (
        Step("text", "QR ichiga joylanadigan matnni yuboring (1200 belgigacha):", validators.nonempty),
    ),
    "telegram": (
        Step("username", "Telegram username yuboring.\n\nMasalan: <code>@CineoraUz</code>", validators.telegram),
    ),
    "email": (
        Step("email", "Qabul qiluvchining email manzilini kiriting:", validators.email),
        Step("subject", "Xat mavzusini kiriting. Kerak bo‘lmasa <code>-</code> yuboring:", validators.optional_text),
        Step("body", "Xat matnini kiriting. Kerak bo‘lmasa <code>-</code> yuboring:", lambda v: validators.optional_text(v, max_length=800)),
    ),
    "sms": (
        Step("phone", "SMS yuboriladigan raqamni kiriting:", validators.phone),
        Step("message", "Tayyor SMS matnini kiriting. Kerak bo‘lmasa <code>-</code> yuboring:", lambda v: validators.optional_text(v, max_length=500)),
    ),
    "whatsapp": (
        Step("phone", "WhatsApp raqamini xalqaro formatda kiriting:", validators.phone),
        Step("message", "Tayyor xabar matnini kiriting. Kerak bo‘lmasa <code>-</code> yuboring:", lambda v: validators.optional_text(v, max_length=500)),
    ),
    "contact": (
        Step("name", "Kontaktning ism-familiyasini kiriting:", lambda v: validators.nonempty(v, max_length=100)),
        Step("phone", "Telefon raqamini kiriting:", validators.phone),
        Step("email", "Email kiriting. Kerak bo‘lmasa <code>-</code> yuboring:", lambda v: "" if v.strip() in {"-", "—"} else validators.email(v)),
        Step("organization", "Tashkilot yoki lavozimni kiriting. Kerak bo‘lmasa <code>-</code> yuboring:", validators.optional_text),
    ),
    "location": (
        Step("coordinates", "Lokatsiya yuboring yoki koordinatani yozing.\n\nMasalan: <code>41.3111, 69.2797</code>", validators.coordinates, "location"),
    ),
    "event": (
        Step("title", "Tadbir nomini kiriting:", lambda v: validators.nonempty(v, max_length=150)),
        Step("start", "Boshlanish vaqtini kiriting.\n\nFormat: <code>25.12.2026 18:30</code>", validators.event_datetime),
        Step("end", "Tugash vaqtini kiriting.\n\nFormat: <code>25.12.2026 20:00</code>", validators.event_datetime),
        Step("location", "Tadbir manzilini kiriting. Kerak bo‘lmasa <code>-</code> yuboring:", validators.optional_text),
    ),
}


def _escape_wifi(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace(":", "\\:")


def _escape_vcard(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_payload(qr_type: str, data: dict[str, Any]) -> str:
    if qr_type == "web":
        return data["url"]
    if qr_type == "wifi":
        security = "nopass" if not data["password"] else data["security"]
        return f'WIFI:T:{security};S:{_escape_wifi(data["ssid"])};P:{_escape_wifi(data["password"])};H:{data["hidden"]};;'
    if qr_type == "phone":
        return f'tel:{data["phone"]}'
    if qr_type == "text":
        return data["text"]
    if qr_type == "telegram":
        return f'https://t.me/{data["username"]}'
    if qr_type == "email":
        query = urlencode({k: v for k, v in {"subject": data["subject"], "body": data["body"]}.items() if v})
        return f'mailto:{data["email"]}' + (f'?{query}' if query else "")
    if qr_type == "sms":
        return f'smsto:{data["phone"]}:{data["message"]}'
    if qr_type == "whatsapp":
        digits = data["phone"].lstrip("+")
        suffix = f'?text={quote(data["message"])}' if data["message"] else ""
        return f'https://wa.me/{digits}{suffix}'
    if qr_type == "contact":
        lines = [
            "BEGIN:VCARD", "VERSION:3.0",
            f'FN:{_escape_vcard(data["name"])}',
            f'TEL;TYPE=CELL:{data["phone"]}',
        ]
        if data["email"]:
            lines.append(f'EMAIL:{data["email"]}')
        if data["organization"]:
            lines.append(f'ORG:{_escape_vcard(data["organization"])}')
        lines.append("END:VCARD")
        return "\r\n".join(lines)
    if qr_type == "location":
        lat, lon = data["coordinates"]
        return f'geo:{lat},{lon}'
    if qr_type == "event":
        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0", "BEGIN:VEVENT",
            f'SUMMARY:{_escape_vcard(data["title"])}',
            f'DTSTART:{data["start"]}', f'DTEND:{data["end"]}',
        ]
        if data["location"]:
            lines.append(f'LOCATION:{_escape_vcard(data["location"])}')
        lines.extend(["END:VEVENT", "END:VCALENDAR"])
        return "\r\n".join(lines)
    raise ValueError(f"Noma’lum QR turi: {qr_type}")


def make_label(qr_type: str, data: dict[str, Any]) -> str:
    labels = {
        "web": data.get("url", "Havola"),
        "wifi": data.get("ssid", "Wi‑Fi"),
        "phone": data.get("phone", "Telefon"),
        "text": str(data.get("text", "Matn"))[:45],
        "telegram": "@" + data.get("username", "Telegram"),
        "email": data.get("email", "Email"),
        "sms": data.get("phone", "SMS"),
        "whatsapp": data.get("phone", "WhatsApp"),
        "contact": data.get("name", "Kontakt"),
        "location": "Joylashuv",
        "event": data.get("title", "Tadbir"),
    }
    return str(labels[qr_type])[:80]
