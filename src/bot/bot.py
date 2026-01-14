from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from src.config import get_settings

settings = get_settings()

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)

dp = Dispatcher()


def setup_bot():
    """Setup bot with all routers."""
    from src.bot.handlers import (
        main_router,
        booking_router,
        search_router,
        profile_router,
        owner_router,
        master_router,
    )

    dp.include_router(main_router)
    dp.include_router(booking_router)
    dp.include_router(search_router)
    dp.include_router(profile_router)
    dp.include_router(owner_router)
    dp.include_router(master_router)
