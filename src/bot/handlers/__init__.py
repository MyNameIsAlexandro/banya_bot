from src.bot.handlers.main import router as main_router
from src.bot.handlers.booking import router as booking_router
from src.bot.handlers.search import router as search_router
from src.bot.handlers.profile import router as profile_router
from src.bot.handlers.owner import router as owner_router
from src.bot.handlers.master import router as master_router

__all__ = [
    "main_router",
    "booking_router",
    "search_router",
    "profile_router",
    "owner_router",
    "master_router",
]
