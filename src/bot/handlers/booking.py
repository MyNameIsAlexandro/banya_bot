from datetime import datetime, timedelta
from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import async_session, User, Banya, Booking, BathMaster
from src.database.models import BookingStatus
from src.bot.keyboards.booking import (
    get_booking_confirm_keyboard,
    get_time_slots_keyboard,
    get_duration_keyboard,
)

router = Router(name="booking")


class BookingStates(StatesGroup):
    """States for booking process."""

    selecting_date = State()
    selecting_time = State()
    selecting_duration = State()
    selecting_master = State()
    selecting_guests = State()
    confirming = State()


def generate_time_slots(opening: str, closing: str, duration_hours: int = 2) -> list[str]:
    """Generate available time slots."""
    slots = []
    open_hour = int(opening.split(":")[0])
    close_hour = int(closing.split(":")[0])

    for hour in range(open_hour, close_hour - duration_hours + 1):
        slots.append(f"{hour:02d}:00")

    return slots


@router.callback_query(F.data.startswith("book_"))
async def start_booking(callback: CallbackQuery, state: FSMContext):
    """Start booking process."""
    banya_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        banya = await session.get(Banya, banya_id)
        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

    await state.update_data(banya_id=banya_id, banya_name=banya.name)

    # Generate next 7 days
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = []
    today = datetime.now().date()

    for i in range(7):
        date = today + timedelta(days=i)
        day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date.weekday()]
        text = f"{day_name}, {date.day}.{date.month:02d}"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=text, callback_data=f"date_{banya_id}_{date.isoformat()}"
                )
            ]
        )

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data=f"banya_{banya_id}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"📅 <b>Бронирование: {banya.name}</b>\n\n"
        "Выберите дату:",
        reply_markup=keyboard,
    )
    await state.set_state(BookingStates.selecting_date)
    await callback.answer()


@router.callback_query(F.data.startswith("date_"), BookingStates.selecting_date)
async def select_date(callback: CallbackQuery, state: FSMContext):
    """Handle date selection."""
    parts = callback.data.split("_")
    banya_id = int(parts[1])
    selected_date = parts[2]

    await state.update_data(selected_date=selected_date)

    async with async_session() as session:
        banya = await session.get(Banya, banya_id)
        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

    # Generate time slots
    slots = generate_time_slots(banya.opening_time, banya.closing_time, banya.min_hours)

    keyboard = get_time_slots_keyboard(banya_id, slots, selected_date)

    await callback.message.edit_text(
        f"🕐 <b>Выберите время:</b>\n\n"
        f"📅 Дата: {selected_date}\n"
        f"⏰ Работаем: {banya.opening_time} - {banya.closing_time}",
        reply_markup=keyboard,
    )
    await state.set_state(BookingStates.selecting_time)
    await callback.answer()


@router.callback_query(F.data.startswith("slot_"), BookingStates.selecting_time)
async def select_time(callback: CallbackQuery, state: FSMContext):
    """Handle time slot selection."""
    parts = callback.data.split("_")
    banya_id = int(parts[1])
    selected_time = parts[3]

    await state.update_data(selected_time=selected_time)

    async with async_session() as session:
        banya = await session.get(Banya, banya_id)
        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

    keyboard = get_duration_keyboard(banya_id, banya.min_hours)

    await callback.message.edit_text(
        f"⏱ <b>Выберите продолжительность:</b>\n\n"
        f"💰 Цена: {banya.price_per_hour} ₽/час\n"
        f"⏰ Минимум: {banya.min_hours} часа",
        reply_markup=keyboard,
    )
    await state.set_state(BookingStates.selecting_duration)
    await callback.answer()


@router.callback_query(F.data.startswith("duration_"), BookingStates.selecting_duration)
async def select_duration(callback: CallbackQuery, state: FSMContext):
    """Handle duration selection."""
    parts = callback.data.split("_")
    banya_id = int(parts[1])
    duration = int(parts[2])

    data = await state.get_data()
    await state.update_data(duration=duration)

    async with async_session() as session:
        banya = await session.get(Banya, banya_id)
        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        # Calculate price
        total_price = banya.price_per_hour * duration

        # Create booking
        booking = Booking(
            user_id=user.id,
            banya_id=banya_id,
            date=datetime.fromisoformat(data["selected_date"]),
            start_time=data["selected_time"],
            duration_hours=duration,
            guests_count=1,
            banya_price=banya.price_per_hour * duration,
            total_price=total_price,
            status=BookingStatus.PENDING,
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)

    await state.update_data(booking_id=booking.id)

    await callback.message.edit_text(
        f"✅ <b>Подтверждение бронирования</b>\n\n"
        f"🔥 <b>{banya.name}</b>\n"
        f"📅 Дата: {data['selected_date']}\n"
        f"🕐 Время: {data['selected_time']}\n"
        f"⏱ Длительность: {duration} ч.\n"
        f"👥 Гостей: 1\n\n"
        f"💰 <b>Итого: {total_price} ₽</b>\n\n"
        "Подтвердите бронирование:",
        reply_markup=get_booking_confirm_keyboard(booking.id),
    )
    await state.set_state(BookingStates.confirming)
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_booking_"), BookingStates.confirming)
async def confirm_booking(callback: CallbackQuery, state: FSMContext):
    """Confirm the booking."""
    booking_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        if not booking:
            await callback.answer("Бронирование не найдено", show_alert=True)
            return

        booking.status = BookingStatus.CONFIRMED
        await session.commit()

    await callback.message.edit_text(
        "🎉 <b>Бронирование подтверждено!</b>\n\n"
        f"Номер брони: #{booking_id}\n\n"
        "Мы отправим напоминание за день до визита.\n"
        "Хорошего отдыха! 🔥"
    )
    await state.clear()
    await callback.answer("Бронирование подтверждено!")


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: CallbackQuery, state: FSMContext):
    """Cancel the booking."""
    booking_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        booking = await session.get(Booking, booking_id)
        if booking:
            booking.status = BookingStatus.CANCELLED
            await session.commit()

    await callback.message.edit_text("❌ Бронирование отменено.")
    await state.clear()
    await callback.answer()


@router.message(Command("bookings"))
async def show_my_bookings(message: Message):
    """Show user's bookings."""
    async with async_session() as session:
        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала запустите бота командой /start")
            return

        # Get bookings
        result = await session.execute(
            select(Booking)
            .options(selectinload(Booking.banya))
            .where(Booking.user_id == user.id)
            .order_by(Booking.date.desc())
            .limit(10)
        )
        bookings = result.scalars().all()

    if not bookings:
        await message.answer(
            "📅 <b>Мои бронирования</b>\n\n"
            "У вас пока нет бронирований.\n"
            "Найдите баню и забронируйте! 🔥"
        )
        return

    text = "📅 <b>Мои бронирования:</b>\n\n"

    status_emoji = {
        BookingStatus.PENDING: "⏳",
        BookingStatus.CONFIRMED: "✅",
        BookingStatus.CANCELLED: "❌",
        BookingStatus.COMPLETED: "✔️",
    }

    for booking in bookings:
        emoji = status_emoji.get(booking.status, "❓")
        date_str = booking.date.strftime("%d.%m.%Y")
        text += (
            f"{emoji} <b>#{booking.id}</b> - {booking.banya.name}\n"
            f"   📅 {date_str} в {booking.start_time}\n"
            f"   ⏱ {booking.duration_hours} ч. • 💰 {booking.total_price} ₽\n\n"
        )

    await message.answer(text)


@router.callback_query(F.data == "my_bookings")
async def my_bookings_callback(callback: CallbackQuery):
    """Handle my bookings callback."""
    await show_my_bookings(callback.message)
    await callback.answer()
