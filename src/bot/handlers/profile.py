from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from src.database import async_session, User, Booking
from src.database.models import BookingStatus

router = Router(name="profile")


@router.message(Command("profile"))
async def show_profile(message: Message):
    """Show user profile."""
    async with async_session() as session:
        # Get user with city
        result = await session.execute(
            select(User).options(selectinload(User.city)).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала запустите бота командой /start")
            return

        # Get booking stats
        result = await session.execute(
            select(func.count(Booking.id)).where(
                Booking.user_id == user.id,
                Booking.status == BookingStatus.COMPLETED,
            )
        )
        completed_bookings = result.scalar() or 0

        result = await session.execute(
            select(func.count(Booking.id)).where(
                Booking.user_id == user.id,
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
            )
        )
        active_bookings = result.scalar() or 0

    rating_stars = "⭐" * int(user.rating)
    premium_badge = "👑 Premium" if user.is_premium else ""
    city_name = user.city.name if user.city else "Не выбран"

    text = f"""
👤 <b>Мой профиль</b> {premium_badge}

📛 <b>Имя:</b> {user.first_name} {user.last_name or ''}
🏙 <b>Город:</b> {city_name}
📱 <b>Телефон:</b> {user.phone or 'Не указан'}
🔗 <b>Username:</b> @{user.username or 'Не указан'}

{rating_stars} <b>Рейтинг:</b> {user.rating:.1f} ({user.rating_count} оценок)

📊 <b>Статистика:</b>
✅ Завершённых визитов: {completed_bookings}
📅 Активных броней: {active_bookings}

🗓 <b>С нами с:</b> {user.created_at.strftime('%d.%m.%Y')}
"""

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏙 Сменить город", callback_data="change_city"),
            ],
            [
                InlineKeyboardButton(text="📱 Изменить телефон", callback_data="edit_phone"),
            ],
            [
                InlineKeyboardButton(
                    text="👑 Подключить Premium" if not user.is_premium else "👑 Управление подпиской",
                    callback_data="premium_info",
                ),
            ],
            [
                InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu"),
            ],
        ]
    )

    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery):
    """Handle profile callback."""
    await show_profile(callback.message)
    await callback.answer()


@router.callback_query(F.data == "premium_info")
async def show_premium_info(callback: CallbackQuery):
    """Show premium subscription info."""
    text = """
👑 <b>Premium подписка</b>

Получите максимум от Banya Bot!

<b>Преимущества:</b>
• 💰 Скидка 10% на все бронирования
• ⚡ Приоритетное бронирование в популярных банях
• 🔔 Уведомления о горячих предложениях
• 🎁 Эксклюзивные акции от партнёров
• 👑 Премиум-бейдж в профиле
• 📞 Приоритетная поддержка

<b>Стоимость:</b>
• 299 ₽/месяц
• 2499 ₽/год (экономия 17%)

<i>Скоро будет доступно!</i>
"""

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data="profile"),
            ],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "edit_phone")
async def edit_phone(callback: CallbackQuery):
    """Start phone edit process."""
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup

    text = (
        "📱 <b>Изменение номера телефона</b>\n\n"
        "Отправьте ваш номер телефона или нажмите кнопку ниже "
        "для автоматической отправки."
    )

    # Reply keyboard with contact request
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить номер", request_contact=True)],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


@router.message(F.contact)
async def handle_contact(message: Message):
    """Handle received contact."""
    phone = message.contact.phone_number

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if user:
            user.phone = phone
            await session.commit()

    from src.bot.keyboards import get_main_keyboard

    await message.answer(
        f"✅ Номер телефона обновлён: {phone}",
        reply_markup=get_main_keyboard(),
    )
