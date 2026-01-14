from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from sqlalchemy import select

from src.bot.keyboards import get_main_keyboard, get_main_inline_keyboard
from src.database import async_session, User
from src.database.models import UserRole

router = Router(name="main")


async def get_or_create_user(telegram_id: int, first_name: str, last_name: str | None, username: str | None) -> User:
    """Get existing user or create new one."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                telegram_id=telegram_id,
                first_name=first_name,
                last_name=last_name,
                username=username,
                role=UserRole.CLIENT,
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)

        return user


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command."""
    user = await get_or_create_user(
        telegram_id=message.from_user.id,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        username=message.from_user.username,
    )

    welcome_text = f"""
👋 Привет, <b>{user.first_name}</b>!

Добро пожаловать в <b>Banya Bot</b> — твой помощник в поиске и бронировании бань!

🔥 <b>Что я умею:</b>
• 🔍 Искать бани по городу и фильтрам
• 👨‍🍳 Находить лучших пар-мастеров
• 📅 Бронировать онлайн
• ⭐ Показывать рейтинги и отзывы

Выбери действие в меню ниже или открой приложение для полного функционала!
"""

    await message.answer(welcome_text, reply_markup=get_main_keyboard())


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command."""
    help_text = """
📖 <b>Справка по командам:</b>

/start - Начать работу с ботом
/help - Показать справку
/search - Найти баню
/masters - Найти пар-мастера
/bookings - Мои бронирования
/profile - Мой профиль

💡 <b>Советы:</b>
• Используйте кнопку "Открыть приложение" для удобного бронирования
• Оставляйте отзывы после посещения
• Подписка Premium даёт скидки и приоритетное бронирование
"""
    await message.answer(help_text)


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    """Show main menu."""
    await message.answer("📋 Главное меню:", reply_markup=get_main_inline_keyboard())


@router.message(F.text == "👤 Профиль")
async def handle_profile_button(message: Message):
    """Handle profile button press."""
    # Redirect to profile handler
    from src.bot.handlers.profile import show_profile
    await show_profile(message)


@router.message(F.text == "📅 Мои бронирования")
async def handle_bookings_button(message: Message):
    """Handle bookings button press."""
    from src.bot.handlers.booking import show_my_bookings
    await show_my_bookings(message)


@router.message(F.text == "🔍 Найти баню")
async def handle_search_button(message: Message):
    """Handle search button press."""
    from src.bot.handlers.search import start_search
    await start_search(message)


@router.message(F.text == "👨‍🍳 Пар-мастера")
async def handle_masters_button(message: Message):
    """Handle masters button press."""
    from src.bot.handlers.search import search_masters
    await search_masters(message)


@router.callback_query(F.data == "cancel")
async def handle_cancel(callback: CallbackQuery):
    """Handle cancel callback."""
    await callback.message.edit_text("❌ Действие отменено")
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def handle_main_menu(callback: CallbackQuery):
    """Return to main menu."""
    await callback.message.edit_text("📋 Главное меню:", reply_markup=get_main_inline_keyboard())
    await callback.answer()
