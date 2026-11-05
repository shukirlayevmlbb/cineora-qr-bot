from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from aiohttp import web

from . import validators
from .config import Config
from .db import Database, QRRecord
from .payloads import build_payload, make_label
from .qr_builder import build_custom_png, build_custom_svg

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
ALLOWED_LANGUAGES = {"uz", "ru", "en"}
ALLOWED_THEMES = {"auto", "light", "dark"}


class WebAppAuthError(web.HTTPUnauthorized):
    def __init__(self, code: str = "unauthorized") -> None:
        super().__init__(
            text=json.dumps({"ok": False, "error": code}),
            content_type="application/json",
        )


def verify_init_data(init_data: str, bot_token: str, max_age: int = 86_400) -> dict[str, Any]:
    values = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = values.pop("hash", "")
    if not received_hash:
        raise ValueError("hash_missing")
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected_hash = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("invalid_hash")
    auth_date = int(values.get("auth_date", "0"))
    if auth_date <= 0 or abs(int(time.time()) - auth_date) > max_age:
        raise ValueError("expired")
    try:
        user = json.loads(values["user"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise ValueError("user_missing") from exc
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise ValueError("user_invalid")
    return user


async def telegram_user(request: web.Request) -> dict[str, Any]:
    config: Config = request.app["config"]
    init_data = request.headers.get("X-Telegram-Init-Data", "")
    if init_data:
        try:
            return verify_init_data(init_data, config.bot_token)
        except ValueError as exc:
            raise WebAppAuthError(str(exc)) from exc
    if config.webapp_preview:
        return {"id": 1, "first_name": "Preview", "username": "preview"}
    raise WebAppAuthError()


def normalize_form(qr_type: str, raw: dict[str, Any]) -> dict[str, Any]:
    def value(key: str) -> str:
        return str(raw.get(key, ""))

    if qr_type == "web":
        return {"url": validators.website(value("url"))}
    if qr_type == "wifi":
        security = value("security").upper() or "WPA"
        if security not in {"WPA", "WEP"}:
            raise validators.ValidationError("Wi‑Fi himoya turi noto‘g‘ri.")
        password = validators.optional_text(value("password"), max_length=128)
        return {
            "ssid": validators.nonempty(value("ssid"), max_length=64),
            "password": password,
            "security": security,
            "hidden": "true" if bool(raw.get("hidden")) else "false",
        }
    if qr_type == "phone":
        return {"phone": validators.phone(value("phone"))}
    if qr_type == "text":
        return {"text": validators.nonempty(value("text"), max_length=1200)}
    if qr_type == "telegram":
        return {"username": validators.telegram(value("username"))}
    if qr_type == "email":
        return {
            "email": validators.email(value("email")),
            "subject": validators.optional_text(value("subject"), max_length=180),
            "body": validators.optional_text(value("body"), max_length=800),
        }
    if qr_type == "sms":
        return {
            "phone": validators.phone(value("phone")),
            "message": validators.optional_text(value("message"), max_length=500),
        }
    if qr_type == "whatsapp":
        return {
            "phone": validators.phone(value("phone")),
            "message": validators.optional_text(value("message"), max_length=500),
        }
    if qr_type == "contact":
        email = value("email").strip()
        return {
            "name": validators.nonempty(value("name"), max_length=100),
            "phone": validators.phone(value("phone")),
            "email": validators.email(email) if email else "",
            "organization": validators.optional_text(value("organization"), max_length=160),
        }
    if qr_type == "location":
        return {"coordinates": validators.coordinates(value("coordinates"))}
    if qr_type == "event":
        start = validators.event_datetime(value("start"))
        end = validators.event_datetime(value("end"))
        if end <= start:
            raise validators.ValidationError("Tugash vaqti boshlanish vaqtidan keyin bo‘lsin.")
        return {
            "title": validators.nonempty(value("title"), max_length=150),
            "start": start,
            "end": end,
            "location": validators.optional_text(value("location"), max_length=220),
        }
    raise validators.ValidationError("Noma’lum QR turi.")


def record_json(record: QRRecord) -> dict[str, Any]:
    try:
        design = json.loads(record.design_json)
    except json.JSONDecodeError:
        design = {}
    return {
        "id": record.id,
        "type": record.qr_type,
        "payload": record.payload,
        "label": record.label,
        "style": record.style,
        "design": design,
        "favorite": record.is_favorite,
        "createdAt": record.created_at,
    }


@web.middleware
async def security_headers(request: web.Request, handler):
    try:
        response = await handler(request)
    except validators.ValidationError as exc:
        response = web.json_response({"ok": False, "error": "validation", "message": str(exc)}, status=400)
    except web.HTTPException:
        raise
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        response = web.json_response({"ok": False, "error": "bad_request", "message": str(exc)}, status=400)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(self)"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://telegram.org https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; "
        "media-src 'self' blob:; frame-ancestors https://web.telegram.org https://*.telegram.org"
    )
    return response


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "cineora-qr"})


async def index(_: web.Request) -> web.Response:
    return web.FileResponse(WEB_ROOT / "index.html", headers={"Cache-Control": "no-cache"})


async def api_config(request: web.Request) -> web.Response:
    config: Config = request.app["config"]
    return web.json_response({
        "ok": True,
        "name": "Cineora QR",
        "languages": ["uz", "ru", "en"],
        "preview": config.webapp_preview,
    })


async def api_bootstrap(request: web.Request) -> web.Response:
    user = await telegram_user(request)
    db: Database = request.app["db"]
    user_id = int(user["id"])
    settings = await db.get_settings(user_id)
    history = await db.list_history(user_id, limit=24)
    return web.json_response({
        "ok": True,
        "user": {
            "id": user_id,
            "firstName": user.get("first_name", ""),
            "username": user.get("username", ""),
            "photoUrl": user.get("photo_url", ""),
        },
        "settings": {
            "style": settings.default_style,
            "historyEnabled": settings.history_enabled,
            "saveWifiHistory": settings.save_wifi_history,
            "language": settings.language,
            "theme": settings.theme,
        },
        "history": [record_json(item) for item in history],
        "historyCount": await db.history_count(user_id),
        "storage": "postgres" if db.is_postgres else "sqlite",
    })


async def qr_response(request: web.Request, output: str) -> web.Response:
    await telegram_user(request)
    body = await request.json(loads=json.loads)
    if body.get("payload"):
        payload = validators.nonempty(str(body["payload"]), max_length=4000)
    else:
        qr_type = str(body.get("type", ""))
        data = normalize_form(qr_type, body.get("data") or {})
        payload = build_payload(qr_type, data)
    design = body.get("design") if isinstance(body.get("design"), dict) else {}
    if output == "svg":
        content = build_custom_svg(payload, design)
        return web.Response(body=content, content_type="image/svg+xml")
    content = build_custom_png(payload, design)
    return web.Response(body=content, content_type="image/png")


async def api_preview(request: web.Request) -> web.Response:
    return await qr_response(request, "png")


async def api_svg(request: web.Request) -> web.Response:
    return await qr_response(request, "svg")


async def api_history(request: web.Request) -> web.Response:
    user = await telegram_user(request)
    db: Database = request.app["db"]
    records = await db.list_history(
        int(user["id"]),
        limit=int(request.query.get("limit", "30")),
        offset=int(request.query.get("offset", "0")),
        favorites_only=request.query.get("favorites") == "1",
    )
    return web.json_response({"ok": True, "items": [record_json(item) for item in records]})


async def api_save_history(request: web.Request) -> web.Response:
    user = await telegram_user(request)
    db: Database = request.app["db"]
    body = await request.json(loads=json.loads)
    qr_type = str(body.get("type", ""))
    data = normalize_form(qr_type, body.get("data") or {})
    payload = build_payload(qr_type, data)
    design = dict(body.get("design")) if isinstance(body.get("design"), dict) else {}
    design["_data"] = data
    label = str(body.get("label") or make_label(qr_type, data)).strip()[:80]
    settings = await db.get_settings(int(user["id"]))
    saved = settings.history_enabled and (qr_type != "wifi" or settings.save_wifi_history)
    record_id = await db.add_record(
        int(user["id"]), qr_type, payload, label, str(design.get("preset", "custom")), saved,
        json.dumps(design, ensure_ascii=False),
    )
    record = await db.get_record(record_id, int(user["id"]))
    return web.json_response({"ok": True, "record": record_json(record) if record else None})


async def api_history_action(request: web.Request) -> web.Response:
    user = await telegram_user(request)
    db: Database = request.app["db"]
    record_id = int(request.match_info["record_id"])
    if request.method == "DELETE":
        deleted = await db.delete_record(record_id, int(user["id"]))
        return web.json_response({"ok": True, "deleted": deleted})
    body = await request.json(loads=json.loads)
    if "favorite" in body:
        updated = await db.set_favorite(record_id, int(user["id"]), bool(body["favorite"]))
        return web.json_response({"ok": True, "updated": updated})
    raise web.HTTPBadRequest(text="Unknown action")


async def api_clear_history(request: web.Request) -> web.Response:
    user = await telegram_user(request)
    db: Database = request.app["db"]
    count = await db.clear_history(int(user["id"]))
    return web.json_response({"ok": True, "deleted": count})


async def api_settings(request: web.Request) -> web.Response:
    user = await telegram_user(request)
    db: Database = request.app["db"]
    body = await request.json(loads=json.loads)
    mapping = {
        "style": ("default_style", str),
        "historyEnabled": ("history_enabled", bool),
        "saveWifiHistory": ("save_wifi_history", bool),
        "language": ("language", str),
        "theme": ("theme", str),
    }
    for client_key, (db_key, cast) in mapping.items():
        if client_key not in body:
            continue
        value = cast(body[client_key])
        if client_key == "language" and value not in ALLOWED_LANGUAGES:
            raise validators.ValidationError("Til qo‘llab-quvvatlanmaydi.")
        if client_key == "theme" and value not in ALLOWED_THEMES:
            raise validators.ValidationError("Mavzu qo‘llab-quvvatlanmaydi.")
        await db.set_setting(int(user["id"]), db_key, value)
    return web.json_response({"ok": True})


def create_web_application(db: Database, config: Config) -> web.Application:
    app = web.Application(middlewares=[security_headers], client_max_size=2 * 1024 * 1024)
    app["db"] = db
    app["config"] = config
    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_get("/api/config", api_config)
    app.router.add_get("/api/bootstrap", api_bootstrap)
    app.router.add_post("/api/qr/preview", api_preview)
    app.router.add_post("/api/qr/svg", api_svg)
    app.router.add_get("/api/history", api_history)
    app.router.add_post("/api/history", api_save_history)
    app.router.add_patch("/api/history/{record_id}", api_history_action)
    app.router.add_delete("/api/history/{record_id}", api_history_action)
    app.router.add_delete("/api/history", api_clear_history)
    app.router.add_patch("/api/settings", api_settings)
    app.router.add_static("/assets", WEB_ROOT, append_version=True)
    return app
