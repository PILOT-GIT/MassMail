import asyncio
import logging

from aiogram.exceptions import TelegramNetworkError

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
    await run_bot()


if __name__ == "__main__":
    asyncio.run(main())
