import asyncio
import contextlib
import logging
import os

from aiogram.exceptions import TelegramNetworkError
from aiohttp import web

from bot import bot, dp
from bot.handlers import handlers_router
from bot.middlewares import AuthMiddleware
from config import settings
from database import async_engine
from models import Base
from scheduler import resume_interrupted_operations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


async def run_bot():
    while True:
        try:
            await dp.start_polling(bot)
            return
        except TelegramNetworkError as exc:
            logger.warning("Telegram unreachable (%s). Retrying in 30s…", exc)
            await asyncio.sleep(30)


async def health_check(request: web.Request) -> web.Response:
    return web.Response(text="OK")


async def run_web_server() -> None:
    port = int(os.getenv("PORT", "10000"))
    app = web.Application()
    app.add_routes([web.get("/", health_check)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Health check server running on 0.0.0.0:%s", port)

    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Shutting down health check server...")
        await runner.cleanup()
        raise


async def main():
    # 1. Create DB tables
    logger.info("Initialising database…")
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 2. Wire middleware + routers
    dp.message.middleware(AuthMiddleware())
    dp.callback_query.middleware(AuthMiddleware())
    dp.include_router(handlers_router)

    # 3. Resume any operations that were mid-flight before a restart
    logger.info("Checking for interrupted operations…")
    await resume_interrupted_operations()

    logger.info("Bot started. Owner ID: %s", settings.OWNER_TELEGRAM_ID)

    server_task = asyncio.create_task(run_web_server())
    try:
        await run_bot()
    finally:
        server_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await server_task


if __name__ == "__main__":
    asyncio.run(main())
