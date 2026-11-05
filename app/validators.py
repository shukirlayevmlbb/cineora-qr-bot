from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse


class ValidationError(ValueError):
    pass


PHONE_RE = re.compile(r"^\+?[0-9][0-9\s().-]{5,20}$")
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def nonempty(value: str, *, max_length: int = 1200) -> str:
    value = value.strip()
    if not value:
        raise ValidationError("Qiymat bo‘sh bo‘lishi mumkin emas.")
    if len(value) > max_length:
        raise ValidationError(f"Matn {max_length} belgidan oshmasin.")
    return value


def optional_text(value: str, *, max_length: int = 300) -> str:
    value = value.strip()
    if value in {"-", "—"}:
        return ""
    if len(value) > max_length:
        raise ValidationError(f"Matn {max_length} belgidan oshmasin.")
    return value


def website(value: str) -> str:
    value = nonempty(value, max_length=1500)
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or "." not in parsed.netloc:
        raise ValidationError("To‘g‘ri havola kiriting. Masalan: cineora.uz")
    return value


def phone(value: str) -> str:
    value = nonempty(value, max_length=25)
    if not PHONE_RE.fullmatch(value):
        raise ValidationError("Telefon raqamini xalqaro formatda kiriting. Masalan: +998901234567")
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7 or len(digits) > 15:
        raise ValidationError("Telefon raqami 7–15 ta raqamdan iborat bo‘lsin.")
    return "+" + digits


def email(value: str) -> str:
    value = nonempty(value, max_length=254).lower()
    if not EMAIL_RE.fullmatch(value):
        raise ValidationError("To‘g‘ri email kiriting. Masalan: name@example.com")
    return value


def telegram(value: str) -> str:
    value = nonempty(value, max_length=100)
    value = value.removeprefix("https://t.me/").removeprefix("http://t.me/").lstrip("@")
    value = value.strip("/")
    if not USERNAME_RE.fullmatch(value):
        raise ValidationError("Telegram username 5–32 ta harf, raqam yoki _ belgisidan iborat bo‘lsin.")
    return value


def coordinates(value: str) -> tuple[float, float]:
    normalized = value.replace(";", ",").strip()
    parts = [part.strip() for part in normalized.split(",")]
    if len(parts) != 2:
        raise ValidationError("Koordinatani vergul bilan kiriting. Masalan: 41.3111, 69.2797")
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError as exc:
        raise ValidationError("Koordinata faqat raqamlardan iborat bo‘lsin.") from exc
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValidationError("Kenglik -90..90, uzunlik -180..180 oralig‘ida bo‘lsin.")
    return round(lat, 7), round(lon, 7)


def event_datetime(value: str) -> str:
    value = nonempty(value, max_length=40)
    for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%dT%H%M00")
        except ValueError:
            pass
    raise ValidationError("Sana formati: 25.12.2026 18:30")
