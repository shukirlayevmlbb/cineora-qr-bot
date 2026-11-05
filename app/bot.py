from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiohttp import web

from .config import Config
from .db import Database
from .handlers import router
from .middleware import ThrottlingMiddleware


async def cleanup_loop(db: Database) -> None:
    while True:
        try:
            await asyncio.sleep(6 * 60 * 60)
            deleted = await db.cleanup_temporary()
            if deleted:
                logging.getLogger(__name__).info("Deleted %s expired temporary QR records", deleted)
        except asyncio.CancelledError:
            raise
        except Exception:
            logging.getLogger(__name__).exception("Temporary record cleanup failed")


async def start_health_server() -> web.AppRunner | None:
    """Expose a tiny HTTP endpoint so Render Web Service can verify the process."""
    raw_port = os.getenv("PORT", "").strip()
    if not raw_port:
        return None

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "service": "qr-studio-bot"})

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", int(raw_port))
    await site.start()
    logging.getLogger(__name__).info("Health server listening on port %s", raw_port)
    return runner


async def main() -> None:
    config = Config.from_env()
    logging.basicConfig(
        level=getattr(logging, config.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    db = Database(config.database_path)
    await db.initialize()
    await db.cleanup_temporary()

    bot = Bot(config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.message.middleware(ThrottlingMiddleware())
    dispatcher.include_router(router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Asosiy menyu"),
        BotCommand(command="help", description="Yordam"),
        BotCommand(command="cancel", description="Joriy amalni bekor qilish"),
    ])

    health_runner = await start_health_server()
    cleanup_task = asyncio.create_task(cleanup_loop(db))
    try:
        await dispatcher.start_polling(
            bot,
            db=db,
            config=config,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        cleanup_task.cancel()
        await asyncio.gather(cleanup_task, return_exceptions=True)
        if health_runner is not None:
            await health_runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
