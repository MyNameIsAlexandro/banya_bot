"""Handlers for bath masters (пар-мастеров)."""

from decimal import Decimal
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from src.database import async_session, User, Banya, Booking, BathMaster
from src.database.models import UserRole, BookingStatus, BookingType

router = Router(name="master_dashboard")


class SetupMasterStates(StatesGroup):
    """States for setting up master profile."""

    entering_bio = State()
    entering_experience = State()
    entering_price = State()
    selecting_specializations = State()
    entering_home_visit_price = State()
    confirming = State()


def get_master_keyboard() -> ReplyKeyboardMarkup:
    """Get keyboard for bath master."""
    buttons = [
        [KeyboardButton(text="📅 Мои заказы"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="👤 Мой профиль"), KeyboardButton(text="⚙️ Настройки")],
        [KeyboardButton(text="🏠 Выезд на дом"), KeyboardButton(text="🧖 Мои бани")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


async def get_master_stats(user_id: int) -> dict:
    """Get statistics for bath master."""
    async with async_session() as session:
        # Get master profile
        result = await session.execute(
            select(BathMaster).where(BathMaster.user_id == user_id)
        )
        master = result.scalar_one_or_none()

        if not master:
            return {
                "active_bookings": 0,
                "completed_bookings": 0,
                "rating": 5.0,
                "rating_count": 0,
                "has_profile": False,
            }

        # Count bookings
        result = await session.execute(
            select(func.count(Booking.id)).where(
                Booking.bath_master_id == master.id,
                Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
            )
        )
        active_bookings = result.scalar() or 0

        result = await session.execute(
            select(func.count(Booking.id)).where(
                Booking.bath_master_id == master.id,
                Booking.status == BookingStatus.COMPLETED,
            )
        )
        completed_bookings = result.scalar() or 0

    return {
        "active_bookings": active_bookings,
        "completed_bookings": completed_bookings,
        "rating": master.rating,
        "rating_count": master.rating_count,
        "has_profile": True,
    }


async def get_or_create_master_profile(user_id: int) -> BathMaster | None:
    """Get or create master profile."""
    async with async_session() as session:
        result = await session.execute(
            select(BathMaster).where(BathMaster.user_id == user_id)
        )
        return result.scalar_one_or_none()


# ==================== KEYBOARD HANDLERS ====================


@router.message(F.text == "📅 Мои заказы")
async def show_master_orders(message: Message):
    """Show master's bookings/orders."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BATH_MASTER:
            await message.answer("Эта функция доступна только пар-мастерам.")
            return

        # Get master profile
        master = await get_or_create_master_profile(user.id)

        if not master:
            await message.answer(
                "📅 <b>Мои заказы</b>\n\n"
                "Сначала заполните профиль мастера.\n"
                "Нажмите «👤 Мой профиль» для настройки."
            )
            return

        # Get bookings
        result = await session.execute(
            select(Booking)
            .options(
                selectinload(Booking.user),
                selectinload(Booking.banya),
            )
            .where(Booking.bath_master_id == master.id)
            .order_by(Booking.date.desc())
            .limit(20)
        )
        bookings = result.scalars().all()

    if not bookings:
        await message.answer(
            "📅 <b>Мои заказы</b>\n\n"
            "Пока нет заказов. Они появятся здесь, когда клиенты начнут бронировать!"
        )
        return

    # Group by status
    pending = [b for b in bookings if b.status == BookingStatus.PENDING]
    confirmed = [b for b in bookings if b.status == BookingStatus.CONFIRMED]

    text = "📅 <b>Мои заказы:</b>\n\n"

    if pending:
        text += "⏳ <b>Ожидают подтверждения:</b>\n"
        for b in pending[:5]:
            date_str = b.date.strftime("%d.%m.%Y")
            location = b.banya.name if b.banya else f"Выезд: {b.client_address[:20]}..."
            text += (
                f"  #{b.id} • {date_str} {b.start_time}\n"
                f"  👤 {b.user.first_name}\n"
                f"  📍 {location}\n"
                f"  💰 {b.master_price or b.total_price} ₽\n\n"
            )

    if confirmed:
        text += "✅ <b>Подтверждённые:</b>\n"
        for b in confirmed[:5]:
            date_str = b.date.strftime("%d.%m.%Y")
            location = b.banya.name if b.banya else f"Выезд: {b.client_address[:20]}..."
            text += (
                f"  #{b.id} • {date_str} {b.start_time}\n"
                f"  👤 {b.user.first_name} • {location}\n\n"
            )

    buttons = []
    for b in pending[:5]:
        buttons.append([
            InlineKeyboardButton(
                text=f"✅ #{b.id}",
                callback_data=f"master_confirm_{b.id}"
            ),
            InlineKeyboardButton(
                text=f"❌ #{b.id}",
                callback_data=f"master_reject_{b.id}"
            ),
            InlineKeyboardButton(
                text=f"💬 Написать",
                callback_data=f"master_contact_{b.id}"
            ),
        ])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "👤 Мой профиль")
async def show_master_profile(message: Message, state: FSMContext):
    """Show or setup master profile."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BATH_MASTER:
            await message.answer("Эта функция доступна только пар-мастерам.")
            return

        master = await get_or_create_master_profile(user.id)

    if not master:
        # No profile - start setup
        await message.answer(
            "👨‍🍳 <b>Настройка профиля пар-мастера</b>\n\n"
            "Давайте заполним ваш профиль!\n\n"
            "Расскажите о себе (опыт, навыки, особенности работы):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_master_setup")]
            ])
        )
        await state.update_data(user_id=user.id)
        await state.set_state(SetupMasterStates.entering_bio)
        return

    # Show existing profile
    specs = []
    if master.specializes_russian:
        specs.append("🇷🇺 Русская баня")
    if master.specializes_finnish:
        specs.append("🇫🇮 Финская сауна")
    if master.specializes_hammam:
        specs.append("🇹🇷 Хаммам")
    if master.specializes_scrub:
        specs.append("🧴 Скрабирование")
    if master.specializes_massage:
        specs.append("💆 Массаж")
    if master.specializes_aromatherapy:
        specs.append("🌿 Ароматерапия")

    home_visit = "✅ Да" if master.can_visit_home else "❌ Нет"
    home_price = f" ({master.home_visit_price} ₽)" if master.home_visit_price else ""

    text = f"""
👨‍🍳 <b>Мой профиль</b>

📝 <b>О себе:</b>
{master.bio or "Не указано"}

📅 <b>Опыт:</b> {master.experience_years} лет
💰 <b>Цена в бане:</b> {master.price_per_session} ₽ / {master.session_duration_minutes} мин
🏠 <b>Выезд на дом:</b> {home_visit}{home_price}

⭐ <b>Рейтинг:</b> {master.rating:.1f} ({master.rating_count} отзывов)

✨ <b>Специализации:</b>
{chr(10).join(specs) if specs else "Не указаны"}
"""

    buttons = [
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data="edit_master_profile")],
        [InlineKeyboardButton(text="🏠 Настроить выезд", callback_data="setup_home_visit")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "📊 Статистика")
async def show_master_statistics(message: Message):
    """Show statistics for master."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BATH_MASTER:
            await message.answer("Эта функция доступна только пар-мастерам.")
            return

    stats = await get_master_stats(user.id)

    if not stats["has_profile"]:
        await message.answer(
            "📊 <b>Статистика</b>\n\n"
            "Сначала заполните профиль мастера.\n"
            "Нажмите «👤 Мой профиль» для настройки."
        )
        return

    async with async_session() as session:
        # Get master
        result = await session.execute(
            select(BathMaster).where(BathMaster.user_id == user.id)
        )
        master = result.scalar_one_or_none()

        # Total revenue
        if master:
            result = await session.execute(
                select(func.sum(Booking.master_price)).where(
                    Booking.bath_master_id == master.id,
                    Booking.status == BookingStatus.COMPLETED,
                )
            )
            total_revenue = result.scalar() or 0
        else:
            total_revenue = 0

    text = f"""
📊 <b>Статистика</b>

📅 <b>Активных заказов:</b> {stats['active_bookings']}
✅ <b>Завершённых:</b> {stats['completed_bookings']}
⭐ <b>Рейтинг:</b> {stats['rating']:.1f} ({stats['rating_count']} отзывов)
💰 <b>Общий заработок:</b> {total_revenue} ₽

<i>Статистика обновляется в реальном времени</i>
"""
    await message.answer(text)


@router.message(F.text == "🏠 Выезд на дом")
async def show_home_visit_settings(message: Message):
    """Show home visit settings."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BATH_MASTER:
            await message.answer("Эта функция доступна только пар-мастерам.")
            return

        master = await get_or_create_master_profile(user.id)

    if not master:
        await message.answer(
            "🏠 <b>Выезд на дом</b>\n\n"
            "Сначала заполните профиль мастера.\n"
            "Нажмите «👤 Мой профиль» для настройки."
        )
        return

    status = "✅ Включён" if master.can_visit_home else "❌ Выключен"
    price = f"{master.home_visit_price} ₽" if master.home_visit_price else "Не указана"

    text = f"""
🏠 <b>Выезд на дом</b>

📊 <b>Статус:</b> {status}
💰 <b>Цена выезда:</b> {price}

Когда выезд включён, клиенты могут заказать вас к себе домой.
"""

    toggle_text = "❌ Выключить выезд" if master.can_visit_home else "✅ Включить выезд"

    buttons = [
        [InlineKeyboardButton(text=toggle_text, callback_data="toggle_home_visit")],
        [InlineKeyboardButton(text="💰 Изменить цену", callback_data="change_home_price")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "🧖 Мои бани")
async def show_master_banyas(message: Message):
    """Show banyas where master works."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BATH_MASTER:
            await message.answer("Эта функция доступна только пар-мастерам.")
            return

        result = await session.execute(
            select(BathMaster)
            .options(selectinload(BathMaster.banyas))
            .where(BathMaster.user_id == user.id)
        )
        master = result.scalar_one_or_none()

    if not master:
        await message.answer(
            "🧖 <b>Мои бани</b>\n\n"
            "Сначала заполните профиль мастера.\n"
            "Нажмите «👤 Мой профиль» для настройки."
        )
        return

    if not master.banyas:
        await message.answer(
            "🧖 <b>Мои бани</b>\n\n"
            "Вы пока не привязаны ни к одной бане.\n"
            "Владельцы бань могут пригласить вас работать у них."
        )
        return

    text = "🧖 <b>Бани, где я работаю:</b>\n\n"

    for banya in master.banyas:
        status = "✅" if banya.is_active else "❌"
        text += (
            f"{status} <b>{banya.name}</b>\n"
            f"   📍 {banya.address}\n"
            f"   ⭐ {banya.rating:.1f}\n\n"
        )

    await message.answer(text)


# ==================== PROFILE SETUP ====================


@router.message(SetupMasterStates.entering_bio)
async def process_master_bio(message: Message, state: FSMContext):
    """Process master bio."""
    bio = message.text.strip()

    if len(bio) < 20:
        await message.answer("Опишите себя подробнее (минимум 20 символов):")
        return

    await state.update_data(bio=bio)

    await message.answer(
        "✅ Отлично!\n\n"
        "Сколько лет у вас опыта работы пар-мастером? (число):"
    )
    await state.set_state(SetupMasterStates.entering_experience)


@router.message(SetupMasterStates.entering_experience)
async def process_master_experience(message: Message, state: FSMContext):
    """Process master experience."""
    try:
        experience = int(message.text.strip())
        if experience < 0 or experience > 50:
            raise ValueError()
    except ValueError:
        await message.answer("Введите корректное число лет опыта (0-50):")
        return

    await state.update_data(experience_years=experience)

    await message.answer(
        "✅ Записано!\n\n"
        "Какая ваша цена за сеанс в бане? (в рублях):"
    )
    await state.set_state(SetupMasterStates.entering_price)


@router.message(SetupMasterStates.entering_price)
async def process_master_price(message: Message, state: FSMContext):
    """Process master price."""
    try:
        price = int(message.text.strip().replace(" ", "").replace("₽", ""))
        if price < 500 or price > 50000:
            raise ValueError()
    except ValueError:
        await message.answer("Введите корректную цену (от 500 до 50000 ₽):")
        return

    await state.update_data(price_per_session=price)

    # Show specializations selection
    keyboard = get_specializations_keyboard({})
    await message.answer(
        f"✅ Цена: <b>{price} ₽</b>\n\n"
        "Выберите ваши специализации:",
        reply_markup=keyboard
    )
    await state.set_state(SetupMasterStates.selecting_specializations)


def get_specializations_keyboard(selected: dict) -> InlineKeyboardMarkup:
    """Get keyboard for selecting master specializations."""
    specs = [
        ("specializes_russian", "🇷🇺 Русская баня"),
        ("specializes_finnish", "🇫🇮 Финская сауна"),
        ("specializes_hammam", "🇹🇷 Хаммам"),
        ("specializes_scrub", "🧴 Скрабирование"),
        ("specializes_massage", "💆 Массаж"),
        ("specializes_aromatherapy", "🌿 Ароматерапия"),
    ]

    buttons = []
    for key, name in specs:
        check = "✅ " if selected.get(key) else ""
        buttons.append([InlineKeyboardButton(
            text=f"{check}{name}",
            callback_data=f"toggle_spec_{key}"
        )])

    buttons.append([InlineKeyboardButton(
        text="✅ Готово — создать профиль",
        callback_data="finish_master_setup"
    )])
    buttons.append([InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="cancel_master_setup"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("toggle_spec_"), SetupMasterStates.selecting_specializations)
async def toggle_specialization(callback: CallbackQuery, state: FSMContext):
    """Toggle a master specialization."""
    spec = callback.data.replace("toggle_spec_", "")

    data = await state.get_data()
    specs = data.get("specializations", {})
    specs[spec] = not specs.get(spec, False)
    await state.update_data(specializations=specs)

    keyboard = get_specializations_keyboard(specs)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "finish_master_setup", SetupMasterStates.selecting_specializations)
async def finish_master_setup(callback: CallbackQuery, state: FSMContext):
    """Finish master profile setup."""
    data = await state.get_data()
    specs = data.get("specializations", {})

    async with async_session() as session:
        master = BathMaster(
            user_id=data["user_id"],
            bio=data["bio"],
            experience_years=data["experience_years"],
            price_per_session=Decimal(str(data["price_per_session"])),
            session_duration_minutes=60,
            specializes_russian=specs.get("specializes_russian", False),
            specializes_finnish=specs.get("specializes_finnish", False),
            specializes_hammam=specs.get("specializes_hammam", False),
            specializes_scrub=specs.get("specializes_scrub", False),
            specializes_massage=specs.get("specializes_massage", False),
            specializes_aromatherapy=specs.get("specializes_aromatherapy", False),
            is_available=True,
            can_visit_home=False,
        )
        session.add(master)
        await session.commit()

    await state.clear()

    await callback.message.edit_text(
        "🎉 <b>Профиль создан!</b>\n\n"
        "Теперь клиенты смогут бронировать ваши услуги.\n\n"
        "💡 <b>Советы:</b>\n"
        "• Настройте выезд на дом для большего количества заказов\n"
        "• Свяжитесь с владельцами бань для сотрудничества"
    )
    await callback.answer("Профиль создан!")


@router.callback_query(F.data == "cancel_master_setup")
async def cancel_master_setup(callback: CallbackQuery, state: FSMContext):
    """Cancel master profile setup."""
    await state.clear()
    await callback.message.edit_text("❌ Настройка профиля отменена.")
    await callback.answer()


# ==================== BOOKING MANAGEMENT ====================


@router.callback_query(F.data.startswith("master_confirm_"))
async def confirm_booking_master(callback: CallbackQuery):
    """Confirm booking as master."""
    booking_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        booking = await session.get(Booking, booking_id)

        if not booking:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        booking.status = BookingStatus.CONFIRMED
        await session.commit()

    await callback.message.edit_text(
        f"✅ Заказ #{booking_id} подтверждён!\n\n"
        f"Клиент получит уведомление."
    )
    await callback.answer("Подтверждено!")


@router.callback_query(F.data.startswith("master_reject_"))
async def reject_booking_master(callback: CallbackQuery):
    """Reject booking as master."""
    booking_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        booking = await session.get(Booking, booking_id)

        if not booking:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        booking.status = BookingStatus.CANCELLED
        await session.commit()

    await callback.message.edit_text(
        f"❌ Заказ #{booking_id} отклонён.\n\n"
        f"Клиент получит уведомление."
    )
    await callback.answer("Отклонено")


@router.callback_query(F.data.startswith("master_contact_"))
async def contact_client(callback: CallbackQuery):
    """Show contact info for client."""
    booking_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        result = await session.execute(
            select(Booking)
            .options(selectinload(Booking.user))
            .where(Booking.id == booking_id)
        )
        booking = result.scalar_one_or_none()

        if not booking:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        user = booking.user

    contact_text = f"👤 <b>{user.first_name}</b>"
    if user.username:
        contact_text += f"\n📱 @{user.username}"
    if user.phone:
        contact_text += f"\n📞 {user.phone}"

    await callback.message.answer(
        f"💬 <b>Контакт клиента:</b>\n\n{contact_text}\n\n"
        f"Напишите клиенту напрямую в Telegram."
    )
    await callback.answer()


@router.message(F.text == "⚙️ Настройки")
async def show_master_settings(message: Message):
    """Show settings for master (redirect to profile with role switching)."""
    from src.bot.handlers.profile import show_profile
    await show_profile(message)


@router.callback_query(F.data == "toggle_home_visit")
async def toggle_home_visit(callback: CallbackQuery):
    """Toggle home visit availability."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        result = await session.execute(
            select(BathMaster).where(BathMaster.user_id == user.id)
        )
        master = result.scalar_one_or_none()

        if not master:
            await callback.answer("Профиль не найден", show_alert=True)
            return

        master.can_visit_home = not master.can_visit_home
        await session.commit()

        status = "включён" if master.can_visit_home else "выключен"

    await callback.answer(f"Выезд на дом {status}!", show_alert=True)
    # Refresh the view
    await show_home_visit_settings(callback.message)
