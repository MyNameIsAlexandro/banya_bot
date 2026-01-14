from aiogram import Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.bot.keyboards import get_main_keyboard, get_main_inline_keyboard
from src.database import async_session, User
from src.database.models import UserRole, City

router = Router(name="main")


async def get_or_create_user(telegram_id: int, first_name: str, last_name: str | None, username: str | None) -> tuple[User, bool]:
    """Get existing user or create new one. Returns (user, is_new)."""
    async with async_session() as session:
        result = await session.execute(
            select(User).options(selectinload(User.city)).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        is_new = False

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
            is_new = True

        return user, is_new


def get_role_selection_keyboard() -> InlineKeyboardMarkup:
    """Get keyboard for role selection."""
    buttons = [
        [InlineKeyboardButton(
            text="👤 Я клиент — хочу бронировать бани",
            callback_data="select_role_client"
        )],
        [InlineKeyboardButton(
            text="🏢 Я владелец бани — хочу принимать брони",
            callback_data="select_role_owner"
        )],
        [InlineKeyboardButton(
            text="👨‍🍳 Я пар-мастер — хочу получать заказы",
            callback_data="select_role_master"
        )],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def get_city_selection_keyboard(back_button: bool = False) -> InlineKeyboardMarkup:
    """Get keyboard with available cities."""
    async with async_session() as session:
        result = await session.execute(select(City).order_by(City.name))
        cities = result.scalars().all()

    buttons = []
    for city in cities:
        buttons.append([InlineKeyboardButton(
            text=f"🏙 {city.name}",
            callback_data=f"select_city_{city.id}"
        )])

    if back_button:
        buttons.append([InlineKeyboardButton(
            text="🔙 Назад",
            callback_data="back_to_role_selection"
        )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(message: Message):
    """Handle /start command."""
    user, is_new = await get_or_create_user(
        telegram_id=message.from_user.id,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        username=message.from_user.username,
    )

    # New user - ask for role selection first
    if is_new:
        welcome_text = f"""
👋 Привет, <b>{user.first_name}</b>!

Добро пожаловать в <b>Banya Bot</b> — платформу для бронирования бань и услуг пар-мастеров!

🎯 <b>Кто вы?</b>
"""
        await message.answer(welcome_text, reply_markup=get_role_selection_keyboard())
        return

    # Existing user without city - ask for city
    if not user.city_id:
        keyboard = await get_city_selection_keyboard()
        await message.answer(
            "🏙 <b>Выберите ваш город:</b>",
            reply_markup=keyboard
        )
        return

    # Show appropriate menu based on role
    await show_role_menu(message, user)


async def show_role_menu(message: Message, user: User):
    """Show menu based on user role."""
    city_name = user.city.name if user.city else "Не выбран"

    if user.role == UserRole.CLIENT:
        welcome_text = f"""
👋 Привет, <b>{user.first_name}</b>!

🏙 <b>Ваш город:</b> {city_name}

🔥 <b>Что я умею:</b>
• 🔍 Искать бани по городу и фильтрам
• 👨‍🍳 Находить лучших пар-мастеров
• 📅 Бронировать онлайн
• ⭐ Показывать рейтинги и отзывы

Выбери действие в меню ниже!
"""
        await message.answer(welcome_text, reply_markup=get_main_keyboard())

    elif user.role == UserRole.BANYA_OWNER:
        from src.bot.handlers.owner import get_owner_keyboard, get_owner_stats
        stats = await get_owner_stats(user.id)
        welcome_text = f"""
👋 Привет, <b>{user.first_name}</b>!

🏢 <b>Личный кабинет владельца бани</b>

📊 <b>Статистика:</b>
🏠 Ваших бань: {stats['banyas_count']}
📅 Активных броней: {stats['active_bookings']}
✅ Всего бронирований: {stats['total_bookings']}

Выберите действие:
"""
        await message.answer(welcome_text, reply_markup=get_owner_keyboard())

    elif user.role == UserRole.BATH_MASTER:
        from src.bot.handlers.master import get_master_keyboard, get_master_stats
        stats = await get_master_stats(user.id)
        welcome_text = f"""
👋 Привет, <b>{user.first_name}</b>!

👨‍🍳 <b>Личный кабинет пар-мастера</b>

📊 <b>Статистика:</b>
📅 Активных заказов: {stats['active_bookings']}
✅ Завершённых: {stats['completed_bookings']}
⭐ Рейтинг: {stats['rating']:.1f} ({stats['rating_count']} отзывов)

Выберите действие:
"""
        await message.answer(welcome_text, reply_markup=get_master_keyboard())


@router.callback_query(F.data.startswith("select_role_"))
async def handle_role_selection(callback: CallbackQuery):
    """Handle role selection."""
    role_str = callback.data.replace("select_role_", "")

    role_map = {
        "client": UserRole.CLIENT,
        "owner": UserRole.BANYA_OWNER,
        "master": UserRole.BATH_MASTER,
    }

    role = role_map.get(role_str)
    if not role:
        await callback.answer("Неизвестная роль", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.role = role
            await session.commit()

    role_names = {
        UserRole.CLIENT: "👤 Клиент",
        UserRole.BANYA_OWNER: "🏢 Владелец бани",
        UserRole.BATH_MASTER: "👨‍🍳 Пар-мастер",
    }

    await callback.message.edit_text(
        f"✅ Отлично! Вы зарегистрированы как: <b>{role_names[role]}</b>\n\n"
        f"🏙 Теперь выберите ваш город:"
    )

    keyboard = await get_city_selection_keyboard(back_button=True)
    await callback.message.answer(
        "👇 Нажмите на ваш город:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data == "back_to_role_selection")
async def handle_back_to_role(callback: CallbackQuery):
    """Go back to role selection."""
    await callback.message.edit_text(
        "🎯 <b>Кто вы?</b>",
        reply_markup=get_role_selection_keyboard()
    )
    await callback.answer()


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


@router.callback_query(F.data.startswith("select_city_"))
async def handle_city_selection(callback: CallbackQuery):
    """Handle city selection."""
    city_id = int(callback.data.split("_")[-1])

    async with async_session() as session:
        # Get city name
        result = await session.execute(select(City).where(City.id == city_id))
        city = result.scalar_one_or_none()

        if not city:
            await callback.answer("Город не найден", show_alert=True)
            return

        # Update user's city
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.city_id = city_id
            await session.commit()

    await callback.message.edit_text(
        f"✅ Город выбран: <b>{city.name}</b>\n\n"
        f"Теперь вы будете видеть бани и пар-мастеров в этом городе."
    )

    # Show main menu
    await callback.message.answer(
        "📋 Главное меню — выберите действие:",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "change_city")
async def handle_change_city(callback: CallbackQuery):
    """Handle city change request."""
    keyboard = await get_city_selection_keyboard()
    await callback.message.edit_text(
        "🏙 <b>Выберите город:</b>",
        reply_markup=keyboard
    )
    await callback.answer()
