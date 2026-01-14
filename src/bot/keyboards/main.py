from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)
from src.config import get_settings

settings = get_settings()


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Get main menu reply keyboard."""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍 Найти баню"),
                KeyboardButton(text="👨‍🍳 Пар-мастера"),
            ],
            [
                KeyboardButton(text="📅 Мои бронирования"),
                KeyboardButton(text="👤 Профиль"),
            ],
        ],
        resize_keyboard=True,
    )
    return keyboard


def get_main_inline_keyboard() -> InlineKeyboardMarkup:
    """Get main menu inline keyboard."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Найти баню", callback_data="search_banya"),
                InlineKeyboardButton(text="👨‍🍳 Пар-мастера", callback_data="search_masters"),
            ],
            [
                InlineKeyboardButton(text="📅 Мои бронирования", callback_data="my_bookings"),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            ],
        ]
    )
    return keyboard


def get_webapp_button(text: str = "🌐 Открыть приложение", path: str = "") -> InlineKeyboardMarkup:
    """Get WebApp button with optional path."""
    url = f"{settings.mini_app_url}{path}" if path else settings.mini_app_url
    # Only return WebApp button if URL is HTTPS
    if url.startswith("https://"):
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=text,
                        web_app=WebAppInfo(url=url),
                    ),
                ],
            ]
        )
        return keyboard
    return None
