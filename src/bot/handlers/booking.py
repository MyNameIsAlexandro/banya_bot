from datetime import datetime, timedelta
from decimal import Decimal
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import async_session, User, Banya, Booking, BathMaster, BookingStatus, BookingType

router = Router(name="booking")


class BookingStates(StatesGroup):
    """States for booking process."""

    selecting_date = State()
    selecting_time = State()
    selecting_duration = State()
    asking_master = State()
    selecting_master = State()
    entering_address = State()  # For home visits
    confirming = State()


class MasterBookingStates(StatesGroup):
    """States for master-first booking process."""

    selecting_location = State()  # Home or banya
    selecting_city = State()
    selecting_banya = State()
    selecting_date = State()
    selecting_time = State()
    entering_address = State()
    confirming = State()


def generate_time_slots(opening: str, closing: str, duration_hours: int = 2) -> list[str]:
    """Generate available time slots."""
    slots = []
    open_hour = int(opening.split(":")[0])
    close_hour = int(closing.split(":")[0])

    for hour in range(open_hour, close_hour - duration_hours + 1):
        slots.append(f"{hour:02d}:00")

    return slots


# ==================== BANYA BOOKING FLOW ====================

@router.callback_query(F.data.startswith("book_"))
async def start_booking(callback: CallbackQuery, state: FSMContext):
    """Start booking process for a banya."""
    banya_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        banya = await session.get(Banya, banya_id)
        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

    await state.update_data(
        banya_id=banya_id,
        banya_name=banya.name,
        booking_flow="banya"  # Mark as banya-first flow
    )

    # Generate next 7 days
    buttons = []
    today = datetime.now().date()

    for i in range(7):
        date = today + timedelta(days=i)
        day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date.weekday()]
        text = f"{day_name}, {date.day}.{date.month:02d}"
        buttons.append([
            InlineKeyboardButton(
                text=text, callback_data=f"date_{banya_id}_{date.isoformat()}"
            )
        ])

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

    buttons = []
    row = []
    for slot in slots:
        row.append(InlineKeyboardButton(
            text=slot, callback_data=f"slot_{banya_id}_{selected_date}_{slot}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"book_{banya_id}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

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

    # Duration buttons
    buttons = []
    for duration in [banya.min_hours, banya.min_hours + 1, banya.min_hours + 2, banya.min_hours + 3]:
        buttons.append([InlineKeyboardButton(
            text=f"{duration} ч. — {int(banya.price_per_hour * duration)} ₽",
            callback_data=f"duration_{banya_id}_{duration}"
        )])

    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data=f"book_{banya_id}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

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
    """Handle duration selection - then ask about master."""
    parts = callback.data.split("_")
    banya_id = int(parts[1])
    duration = int(parts[2])

    await state.update_data(duration=duration)

    async with async_session() as session:
        # Check if banya has masters
        result = await session.execute(
            select(Banya)
            .options(selectinload(Banya.bath_masters).selectinload(BathMaster.user))
            .where(Banya.id == banya_id)
        )
        banya = result.scalar_one_or_none()

        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

        await state.update_data(banya_price=float(banya.price_per_hour * duration))

        # If banya has available masters, ask user
        available_masters = [m for m in banya.bath_masters if m.is_available]

        if available_masters:
            buttons = [
                [InlineKeyboardButton(
                    text="👨‍🍳 Да, выбрать мастера",
                    callback_data=f"add_master_{banya_id}"
                )],
                [InlineKeyboardButton(
                    text="➖ Нет, без мастера",
                    callback_data=f"no_master_{banya_id}"
                )],
            ]
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

            await callback.message.edit_text(
                f"👨‍🍳 <b>Добавить пар-мастера?</b>\n\n"
                f"В этой бане работают {len(available_masters)} мастер(а).\n"
                "Хотите заказать услуги профессионального парильщика?",
                reply_markup=keyboard,
            )
            await state.set_state(BookingStates.asking_master)
        else:
            # No masters - go to confirmation
            await finish_banya_booking(callback, state, banya_id, with_master=False)

    await callback.answer()


@router.callback_query(F.data.startswith("add_master_"), BookingStates.asking_master)
async def show_masters_for_booking(callback: CallbackQuery, state: FSMContext):
    """Show available masters for selection."""
    banya_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        result = await session.execute(
            select(Banya)
            .options(selectinload(Banya.bath_masters).selectinload(BathMaster.user))
            .where(Banya.id == banya_id)
        )
        banya = result.scalar_one_or_none()

        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

    buttons = []
    for master in banya.bath_masters:
        if not master.is_available:
            continue
        rating_stars = "⭐" * int(master.rating)
        text = f"{master.user.first_name} {rating_stars} — {master.price_per_session}₽"
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"select_master_{master.id}"
        )])

    buttons.append([InlineKeyboardButton(
        text="➖ Передумал, без мастера",
        callback_data=f"no_master_{banya_id}"
    )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "👨‍🍳 <b>Выберите пар-мастера:</b>\n\n"
        "Цена указана за сеанс.",
        reply_markup=keyboard,
    )
    await state.set_state(BookingStates.selecting_master)
    await callback.answer()


@router.callback_query(F.data.startswith("select_master_"), BookingStates.selecting_master)
async def select_master_for_banya(callback: CallbackQuery, state: FSMContext):
    """Handle master selection for banya booking."""
    master_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        master = await session.get(BathMaster, master_id)
        if not master:
            await callback.answer("Мастер не найден", show_alert=True)
            return

    await state.update_data(
        master_id=master_id,
        master_price=float(master.price_per_session)
    )

    data = await state.get_data()
    await finish_banya_booking(callback, state, data["banya_id"], with_master=True)
    await callback.answer()


@router.callback_query(F.data.startswith("no_master_"), BookingStates.asking_master)
async def skip_master(callback: CallbackQuery, state: FSMContext):
    """Skip master selection."""
    banya_id = int(callback.data.split("_")[2])
    await finish_banya_booking(callback, state, banya_id, with_master=False)
    await callback.answer()


async def finish_banya_booking(callback: CallbackQuery, state: FSMContext, banya_id: int, with_master: bool):
    """Create booking and show confirmation."""
    data = await state.get_data()

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

        # Calculate prices
        banya_price = Decimal(str(data["banya_price"]))
        master_price = Decimal(str(data.get("master_price", 0))) if with_master else None
        total_price = banya_price + (master_price or Decimal("0"))

        # Determine booking type
        booking_type = BookingType.BANYA_WITH_MASTER if with_master else BookingType.BANYA_ONLY

        # Create booking
        booking = Booking(
            user_id=user.id,
            banya_id=banya_id,
            bath_master_id=data.get("master_id") if with_master else None,
            booking_type=booking_type,
            date=datetime.fromisoformat(data["selected_date"]),
            start_time=data["selected_time"],
            duration_hours=data["duration"],
            guests_count=1,
            banya_price=banya_price,
            master_price=master_price,
            total_price=total_price,
            status=BookingStatus.PENDING,
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)

        # Get master info if selected
        master_text = ""
        if with_master and data.get("master_id"):
            master = await session.get(BathMaster, data["master_id"])
            if master:
                master_user = await session.get(User, master.user_id)
                master_text = f"\n👨‍🍳 Мастер: {master_user.first_name} (+{master_price} ₽)"

    await state.update_data(booking_id=booking.id)

    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"confirm_booking_{booking.id}"
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"cancel_booking_{booking.id}"
            ),
        ],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"✅ <b>Подтверждение бронирования</b>\n\n"
        f"🔥 <b>{banya.name}</b>\n"
        f"📅 Дата: {data['selected_date']}\n"
        f"🕐 Время: {data['selected_time']}\n"
        f"⏱ Длительность: {data['duration']} ч.\n"
        f"👥 Гостей: 1"
        f"{master_text}\n\n"
        f"💰 <b>Итого: {total_price} ₽</b>\n\n"
        "Подтвердите бронирование:",
        reply_markup=keyboard,
    )
    await state.set_state(BookingStates.confirming)


# ==================== MASTER BOOKING FLOW ====================

@router.callback_query(F.data.startswith("book_master_"))
async def start_master_booking(callback: CallbackQuery, state: FSMContext):
    """Start booking process starting from a master."""
    master_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        result = await session.execute(
            select(BathMaster)
            .options(selectinload(BathMaster.user), selectinload(BathMaster.banyas))
            .where(BathMaster.id == master_id)
        )
        master = result.scalar_one_or_none()

        if not master:
            await callback.answer("Мастер не найден", show_alert=True)
            return

    await state.update_data(
        master_id=master_id,
        master_name=master.user.first_name,
        master_price=float(master.price_per_session),
        master_home_price=float(master.home_visit_price) if master.home_visit_price else None,
        can_visit_home=master.can_visit_home,
        booking_flow="master"  # Mark as master-first flow
    )

    # Ask where to have the session
    buttons = []

    if master.can_visit_home:
        buttons.append([InlineKeyboardButton(
            text=f"🏠 Ко мне ({master.home_visit_price} ₽)",
            callback_data=f"master_home_{master_id}"
        )])

    if master.banyas:
        buttons.append([InlineKeyboardButton(
            text=f"🧖 В баню ({master.price_per_session} ₽)",
            callback_data=f"master_banya_{master_id}"
        )])

    buttons.append([InlineKeyboardButton(
        text="❌ Отмена",
        callback_data=f"view_master_{master_id}"
    )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    location_text = ""
    if master.can_visit_home and master.banyas:
        location_text = "Мастер работает в банях и выезжает на дом."
    elif master.can_visit_home:
        location_text = "Мастер выезжает на дом."
    elif master.banyas:
        location_text = "Мастер работает в банях."

    await callback.message.edit_text(
        f"📍 <b>Куда пригласить {master.user.first_name}?</b>\n\n"
        f"{location_text}",
        reply_markup=keyboard,
    )
    await state.set_state(MasterBookingStates.selecting_location)
    await callback.answer()


@router.callback_query(F.data.startswith("master_home_"), MasterBookingStates.selecting_location)
async def master_home_visit(callback: CallbackQuery, state: FSMContext):
    """Handle home visit selection."""
    master_id = int(callback.data.split("_")[2])

    await state.update_data(location="home")

    # Generate next 7 days
    buttons = []
    today = datetime.now().date()

    for i in range(7):
        date = today + timedelta(days=i)
        day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date.weekday()]
        text = f"{day_name}, {date.day}.{date.month:02d}"
        buttons.append([
            InlineKeyboardButton(
                text=text, callback_data=f"mdate_{master_id}_{date.isoformat()}"
            )
        ])

    buttons.append([InlineKeyboardButton(
        text="🔙 Назад",
        callback_data=f"book_master_{master_id}"
    )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "📅 <b>Выберите дату:</b>\n\n"
        "Мастер приедет к вам.",
        reply_markup=keyboard,
    )
    await state.set_state(MasterBookingStates.selecting_date)
    await callback.answer()


@router.callback_query(F.data.startswith("master_banya_"), MasterBookingStates.selecting_location)
async def master_select_banya(callback: CallbackQuery, state: FSMContext):
    """Show banyas where master works."""
    master_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        result = await session.execute(
            select(BathMaster)
            .options(selectinload(BathMaster.banyas))
            .where(BathMaster.id == master_id)
        )
        master = result.scalar_one_or_none()

        if not master or not master.banyas:
            await callback.answer("Бани не найдены", show_alert=True)
            return

    buttons = []
    for banya in master.banyas:
        if not banya.is_active:
            continue
        rating_stars = "⭐" * int(banya.rating)
        text = f"{banya.name} {rating_stars}"
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"mbanya_{master_id}_{banya.id}"
        )])

    buttons.append([InlineKeyboardButton(
        text="🔙 Назад",
        callback_data=f"book_master_{master_id}"
    )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"🧖 <b>Выберите баню:</b>\n\n"
        f"Где вы хотите встретиться с мастером?",
        reply_markup=keyboard,
    )
    await state.set_state(MasterBookingStates.selecting_banya)
    await callback.answer()


@router.callback_query(F.data.startswith("mbanya_"), MasterBookingStates.selecting_banya)
async def master_banya_selected(callback: CallbackQuery, state: FSMContext):
    """Handle banya selection for master booking."""
    parts = callback.data.split("_")
    master_id = int(parts[1])
    banya_id = int(parts[2])

    async with async_session() as session:
        banya = await session.get(Banya, banya_id)
        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

    await state.update_data(
        location="banya",
        banya_id=banya_id,
        banya_name=banya.name,
        banya_price_per_hour=float(banya.price_per_hour),
        banya_min_hours=banya.min_hours
    )

    # Generate next 7 days
    buttons = []
    today = datetime.now().date()

    for i in range(7):
        date = today + timedelta(days=i)
        day_name = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][date.weekday()]
        text = f"{day_name}, {date.day}.{date.month:02d}"
        buttons.append([
            InlineKeyboardButton(
                text=text, callback_data=f"mdate_{master_id}_{date.isoformat()}"
            )
        ])

    buttons.append([InlineKeyboardButton(
        text="🔙 Назад",
        callback_data=f"master_banya_{master_id}"
    )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"📅 <b>Бронирование в {banya.name}</b>\n\n"
        "Выберите дату:",
        reply_markup=keyboard,
    )
    await state.set_state(MasterBookingStates.selecting_date)
    await callback.answer()


@router.callback_query(F.data.startswith("mdate_"), MasterBookingStates.selecting_date)
async def master_select_date(callback: CallbackQuery, state: FSMContext):
    """Handle date selection for master booking."""
    parts = callback.data.split("_")
    master_id = int(parts[1])
    selected_date = parts[2]

    data = await state.get_data()
    await state.update_data(selected_date=selected_date)

    # Generate time slots (10:00 - 22:00 for home, banya hours for banya)
    if data.get("location") == "home":
        slots = generate_time_slots("10:00", "22:00", 2)
    else:
        async with async_session() as session:
            banya = await session.get(Banya, data["banya_id"])
            slots = generate_time_slots(banya.opening_time, banya.closing_time, banya.min_hours)

    buttons = []
    row = []
    for slot in slots:
        row.append(InlineKeyboardButton(
            text=slot, callback_data=f"mslot_{master_id}_{selected_date}_{slot}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(
        text="🔙 Назад",
        callback_data=f"book_master_{master_id}"
    )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"🕐 <b>Выберите время:</b>\n\n"
        f"📅 Дата: {selected_date}",
        reply_markup=keyboard,
    )
    await state.set_state(MasterBookingStates.selecting_time)
    await callback.answer()


@router.callback_query(F.data.startswith("mslot_"), MasterBookingStates.selecting_time)
async def master_select_time(callback: CallbackQuery, state: FSMContext):
    """Handle time selection for master booking."""
    parts = callback.data.split("_")
    master_id = int(parts[1])
    selected_time = parts[3]

    data = await state.get_data()
    await state.update_data(selected_time=selected_time)

    if data.get("location") == "home":
        # Ask for address
        await callback.message.edit_text(
            "📍 <b>Укажите адрес:</b>\n\n"
            "Напишите адрес, куда приехать мастеру.",
        )
        await state.set_state(MasterBookingStates.entering_address)
    else:
        # Go to confirmation with banya duration selection
        await master_select_duration(callback, state, master_id)

    await callback.answer()


async def master_select_duration(callback: CallbackQuery, state: FSMContext, master_id: int):
    """Show duration selection for banya booking with master."""
    data = await state.get_data()

    min_hours = data.get("banya_min_hours", 2)
    price_per_hour = data.get("banya_price_per_hour", 3000)

    buttons = []
    for duration in [min_hours, min_hours + 1, min_hours + 2]:
        total = int(price_per_hour * duration + data["master_price"])
        buttons.append([InlineKeyboardButton(
            text=f"{duration} ч. — {total} ₽ (баня + мастер)",
            callback_data=f"mdur_{master_id}_{duration}"
        )])

    buttons.append([InlineKeyboardButton(
        text="🔙 Назад",
        callback_data=f"book_master_{master_id}"
    )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"⏱ <b>Выберите продолжительность:</b>\n\n"
        f"🧖 Баня: {price_per_hour} ₽/час\n"
        f"👨‍🍳 Мастер: {int(data['master_price'])} ₽",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("mdur_"))
async def master_duration_selected(callback: CallbackQuery, state: FSMContext):
    """Handle duration selection for master+banya booking."""
    parts = callback.data.split("_")
    master_id = int(parts[1])
    duration = int(parts[2])

    data = await state.get_data()

    banya_price = Decimal(str(data["banya_price_per_hour"])) * duration
    await state.update_data(
        duration=duration,
        banya_price=float(banya_price)
    )

    await finish_master_booking(callback, state)
    await callback.answer()


@router.message(MasterBookingStates.entering_address)
async def master_address_entered(message: Message, state: FSMContext):
    """Handle address input for home visit."""
    address = message.text

    if len(address) < 10:
        await message.answer("Пожалуйста, укажите более подробный адрес.")
        return

    await state.update_data(
        client_address=address,
        duration=1  # Home visits are typically 1 session
    )

    await finish_master_booking_message(message, state)


async def finish_master_booking(callback: CallbackQuery, state: FSMContext):
    """Finish master booking and show confirmation (callback version)."""
    data = await state.get_data()

    async with async_session() as session:
        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        # Get master
        master = await session.get(BathMaster, data["master_id"])
        master_user = await session.get(User, master.user_id)

        # Calculate prices
        if data.get("location") == "home":
            master_price = Decimal(str(data.get("master_home_price", data["master_price"])))
            banya_price = None
            total_price = master_price
            booking_type = BookingType.MASTER_HOME_VISIT
            banya_id = None
        else:
            banya_price = Decimal(str(data["banya_price"]))
            master_price = Decimal(str(data["master_price"]))
            total_price = banya_price + master_price
            booking_type = BookingType.MASTER_AT_BANYA
            banya_id = data["banya_id"]

        # Create booking
        booking = Booking(
            user_id=user.id,
            banya_id=banya_id,
            bath_master_id=data["master_id"],
            booking_type=booking_type,
            date=datetime.fromisoformat(data["selected_date"]),
            start_time=data["selected_time"],
            duration_hours=data.get("duration", 1),
            guests_count=1,
            client_address=data.get("client_address"),
            banya_price=banya_price,
            master_price=master_price,
            total_price=total_price,
            status=BookingStatus.PENDING,
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)

    # Build confirmation text
    location_text = ""
    if data.get("location") == "home":
        location_text = f"📍 Адрес: {data['client_address']}"
    else:
        location_text = f"🧖 Баня: {data['banya_name']}"

    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"confirm_booking_{booking.id}"
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"cancel_booking_{booking.id}"
            ),
        ],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"✅ <b>Подтверждение бронирования</b>\n\n"
        f"👨‍🍳 <b>Мастер: {master_user.first_name}</b>\n"
        f"{location_text}\n"
        f"📅 Дата: {data['selected_date']}\n"
        f"🕐 Время: {data['selected_time']}\n"
        f"⏱ Длительность: {data.get('duration', 1)} ч.\n\n"
        f"💰 <b>Итого: {total_price} ₽</b>\n\n"
        "Подтвердите бронирование:",
        reply_markup=keyboard,
    )
    await state.set_state(BookingStates.confirming)


async def finish_master_booking_message(message: Message, state: FSMContext):
    """Finish master booking and show confirmation (message version for address input)."""
    data = await state.get_data()

    async with async_session() as session:
        # Get user
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("Пользователь не найден. Начните сначала /start")
            return

        # Get master
        master = await session.get(BathMaster, data["master_id"])
        master_user = await session.get(User, master.user_id)

        # Home visit pricing
        master_price = Decimal(str(data.get("master_home_price", data["master_price"])))
        total_price = master_price

        # Create booking
        booking = Booking(
            user_id=user.id,
            banya_id=None,
            bath_master_id=data["master_id"],
            booking_type=BookingType.MASTER_HOME_VISIT,
            date=datetime.fromisoformat(data["selected_date"]),
            start_time=data["selected_time"],
            duration_hours=1,
            guests_count=1,
            client_address=data["client_address"],
            banya_price=None,
            master_price=master_price,
            total_price=total_price,
            status=BookingStatus.PENDING,
        )
        session.add(booking)
        await session.commit()
        await session.refresh(booking)

    buttons = [
        [
            InlineKeyboardButton(
                text="✅ Подтвердить",
                callback_data=f"confirm_booking_{booking.id}"
            ),
            InlineKeyboardButton(
                text="❌ Отменить",
                callback_data=f"cancel_booking_{booking.id}"
            ),
        ],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        f"✅ <b>Подтверждение бронирования</b>\n\n"
        f"👨‍🍳 <b>Мастер: {master_user.first_name}</b>\n"
        f"📍 Адрес: {data['client_address']}\n"
        f"📅 Дата: {data['selected_date']}\n"
        f"🕐 Время: {data['selected_time']}\n\n"
        f"💰 <b>Итого: {total_price} ₽</b>\n\n"
        "Подтвердите бронирование:",
        reply_markup=keyboard,
    )
    await state.set_state(BookingStates.confirming)


# ==================== COMMON HANDLERS ====================

@router.callback_query(F.data.startswith("confirm_booking_"))
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

    # Different messages based on booking type
    type_emoji = {
        BookingType.BANYA_ONLY: "🧖",
        BookingType.BANYA_WITH_MASTER: "🧖👨‍🍳",
        BookingType.MASTER_AT_BANYA: "👨‍🍳🧖",
        BookingType.MASTER_HOME_VISIT: "👨‍🍳🏠",
    }

    emoji = type_emoji.get(booking.booking_type, "✅")

    await callback.message.edit_text(
        f"🎉 <b>Бронирование подтверждено!</b>\n\n"
        f"{emoji} Номер брони: #{booking_id}\n\n"
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
            .options(
                selectinload(Booking.banya),
                selectinload(Booking.bath_master).selectinload(BathMaster.user)
            )
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

    type_emoji = {
        BookingType.BANYA_ONLY: "🧖",
        BookingType.BANYA_WITH_MASTER: "🧖👨‍🍳",
        BookingType.MASTER_AT_BANYA: "👨‍🍳🧖",
        BookingType.MASTER_HOME_VISIT: "👨‍🍳🏠",
    }

    for booking in bookings:
        s_emoji = status_emoji.get(booking.status, "❓")
        t_emoji = type_emoji.get(booking.booking_type, "")
        date_str = booking.date.strftime("%d.%m.%Y")

        location = ""
        if booking.banya:
            location = booking.banya.name
        elif booking.client_address:
            location = f"Выезд: {booking.client_address[:30]}..."

        master_info = ""
        if booking.bath_master:
            master_info = f" + {booking.bath_master.user.first_name}"

        text += (
            f"{s_emoji} {t_emoji} <b>#{booking.id}</b> - {location}{master_info}\n"
            f"   📅 {date_str} в {booking.start_time}\n"
            f"   ⏱ {booking.duration_hours} ч. • 💰 {booking.total_price} ₽\n\n"
        )

    await message.answer(text)


@router.callback_query(F.data == "my_bookings")
async def my_bookings_callback(callback: CallbackQuery):
    """Handle my bookings callback."""
    await show_my_bookings(callback.message)
    await callback.answer()
