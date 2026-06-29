from aiogram import Router

from bot.handlers.auth import router as auth_router
from bot.handlers.common import router as common_router
from bot.handlers.gmail import router as gmail_router
from bot.handlers.lists import router as lists_router
from bot.handlers.operations import router as operations_router

handlers_router = Router()
handlers_router.include_router(common_router)
handlers_router.include_router(auth_router)
handlers_router.include_router(gmail_router)
handlers_router.include_router(lists_router)
handlers_router.include_router(operations_router)
