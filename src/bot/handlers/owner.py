"""Handlers for banya owners."""

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

from src.database import async_session, User, Banya, Booking, City
from src.database.models import UserRole, BookingStatus

router = Router(name="owner")


class AddBanyaStates(StatesGroup):
    """States for adding a new banya."""

    entering_name = State()
    entering_description = State()
    entering_address = State()
    entering_price = State()
    selecting_features = State()
    confirming = State()


def get_owner_keyboard() -> ReplyKeyboardMarkup:
    """Get keyboard for banya owner."""
    buttons = [
        [KeyboardButton(text="🏠 Мои бани"), KeyboardButton(text="📅 Бронирования")],
        [KeyboardButton(text="➕ Добавить баню"), KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="⚙️ Настройки")],
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


async def get_owner_stats(user_id: int) -> dict:
    """Get statistics for banya owner."""
    async with async_session() as session:
        # Count banyas
        result = await session.execute(
            select(func.count(Banya.id)).where(Banya.owner_id == user_id)
        )
        banyas_count = result.scalar() or 0

        # Get banya IDs
        result = await session.execute(
            select(Banya.id).where(Banya.owner_id == user_id)
        )
        banya_ids = [b for b in result.scalars().all()]

        # Count bookings
        if banya_ids:
            result = await session.execute(
                select(func.count(Booking.id)).where(
                    Booking.banya_id.in_(banya_ids),
                    Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
                )
            )
            active_bookings = result.scalar() or 0

            result = await session.execute(
                select(func.count(Booking.id)).where(Booking.banya_id.in_(banya_ids))
            )
            total_bookings = result.scalar() or 0
        else:
            active_bookings = 0
            total_bookings = 0

    return {
        "banyas_count": banyas_count,
        "active_bookings": active_bookings,
        "total_bookings": total_bookings,
    }


# ==================== KEYBOARD HANDLERS ====================


@router.message(F.text == "🏠 Мои бани")
async def show_my_banyas(message: Message):
    """Show owner's banyas."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BANYA_OWNER:
            await message.answer("Эта функция доступна только владельцам бань.")
            return

        result = await session.execute(
            select(Banya)
            .options(selectinload(Banya.city))
            .where(Banya.owner_id == user.id)
            .order_by(Banya.created_at.desc())
        )
        banyas = result.scalars().all()

    if not banyas:
        await message.answer(
            "🏠 <b>Мои бани</b>\n\n"
            "У вас пока нет добавленных бань.\n"
            "Нажмите «➕ Добавить баню» чтобы создать первую!",
        )
        return

    text = "🏠 <b>Мои бани:</b>\n\n"
    buttons = []

    for banya in banyas:
        status = "✅" if banya.is_active else "❌"
        verified = "✓" if banya.is_verified else ""
        text += (
            f"{status} <b>{banya.name}</b> {verified}\n"
            f"   📍 {banya.city.name if banya.city else 'Город не указан'}\n"
            f"   💰 {banya.price_per_hour} ₽/час\n"
            f"   ⭐ {banya.rating:.1f} ({banya.rating_count})\n\n"
        )
        buttons.append([InlineKeyboardButton(
            text=f"⚙️ {banya.name}",
            callback_data=f"manage_banya_{banya.id}"
        )])

    buttons.append([InlineKeyboardButton(
        text="➕ Добавить баню",
        callback_data="add_banya"
    )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "📅 Бронирования")
async def show_owner_bookings(message: Message):
    """Show bookings for owner's banyas."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BANYA_OWNER:
            await message.answer("Эта функция доступна только владельцам бань.")
            return

        # Get banya IDs
        result = await session.execute(
            select(Banya.id).where(Banya.owner_id == user.id)
        )
        banya_ids = [b for b in result.scalars().all()]

        if not banya_ids:
            await message.answer(
                "📅 <b>Бронирования</b>\n\n"
                "У вас пока нет бань. Добавьте баню, чтобы получать бронирования."
            )
            return

        # Get bookings
        result = await session.execute(
            select(Booking)
            .options(
                selectinload(Booking.user),
                selectinload(Booking.banya),
                selectinload(Booking.bath_master).selectinload(User)
            )
            .where(Booking.banya_id.in_(banya_ids))
            .order_by(Booking.date.desc())
            .limit(20)
        )
        bookings = result.scalars().all()

    if not bookings:
        await message.answer(
            "📅 <b>Бронирования</b>\n\n"
            "Пока нет бронирований. Они появятся здесь, когда клиенты начнут бронировать!"
        )
        return

    status_emoji = {
        BookingStatus.PENDING: "⏳",
        BookingStatus.AWAITING_CONFIRMATIONS: "🔄",
        BookingStatus.CONFIRMED: "✅",
        BookingStatus.CANCELLED: "❌",
        BookingStatus.COMPLETED: "✔️",
    }

    # Group by status
    pending = [b for b in bookings if b.status == BookingStatus.PENDING]
    awaiting = [b for b in bookings if b.status == BookingStatus.AWAITING_CONFIRMATIONS]
    confirmed = [b for b in bookings if b.status == BookingStatus.CONFIRMED]
    other = [b for b in bookings if b.status not in [BookingStatus.PENDING, BookingStatus.AWAITING_CONFIRMATIONS, BookingStatus.CONFIRMED]]

    text = "📅 <b>Бронирования:</b>\n\n"

    if awaiting:
        text += "🔄 <b>Ожидают вашего подтверждения:</b>\n"
        for b in awaiting[:5]:
            date_str = b.date.strftime("%d.%m.%Y")
            confirmed_status = "✅" if b.banya_confirmed else "⏳"
            text += (
                f"  #{b.id} {b.banya.name} {confirmed_status}\n"
                f"  👤 {b.user.first_name} • {date_str} {b.start_time}\n"
                f"  💰 {b.total_price} ₽\n\n"
            )

    if pending:
        text += "⏳ <b>Ожидают подтверждения клиента:</b>\n"
        for b in pending[:5]:
            date_str = b.date.strftime("%d.%m.%Y")
            text += (
                f"  #{b.id} {b.banya.name}\n"
                f"  👤 {b.user.first_name} • {date_str} {b.start_time}\n"
                f"  💰 {b.total_price} ₽\n\n"
            )

    if confirmed:
        text += "✅ <b>Подтверждённые:</b>\n"
        for b in confirmed[:5]:
            date_str = b.date.strftime("%d.%m.%Y")
            text += (
                f"  #{b.id} {b.banya.name}\n"
                f"  👤 {b.user.first_name} • {date_str} {b.start_time}\n\n"
            )

    buttons = []
    # Show confirm/reject buttons for awaiting bookings (not yet confirmed by this banya)
    for b in awaiting[:5]:
        if not b.banya_confirmed:
            buttons.append([
                InlineKeyboardButton(
                    text=f"✅ Подтвердить #{b.id}",
                    callback_data=f"banya_confirm_{b.id}"
                ),
                InlineKeyboardButton(
                    text=f"❌ Отклонить",
                    callback_data=f"banya_reject_{b.id}"
                ),
            ])

    if awaiting:
        buttons.append([InlineKeyboardButton(
            text="📋 Все ожидающие",
            callback_data="owner_pending_bookings"
        )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await message.answer(text, reply_markup=keyboard)


@router.message(F.text == "📊 Статистика")
async def show_owner_statistics(message: Message):
    """Show statistics for owner."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BANYA_OWNER:
            await message.answer("Эта функция доступна только владельцам бань.")
            return

    stats = await get_owner_stats(user.id)

    async with async_session() as session:
        # Get banya IDs
        result = await session.execute(
            select(Banya.id).where(Banya.owner_id == user.id)
        )
        banya_ids = [b for b in result.scalars().all()]

        # Total revenue
        if banya_ids:
            result = await session.execute(
                select(func.sum(Booking.total_price)).where(
                    Booking.banya_id.in_(banya_ids),
                    Booking.status == BookingStatus.COMPLETED,
                )
            )
            total_revenue = result.scalar() or 0
        else:
            total_revenue = 0

    text = f"""
📊 <b>Статистика</b>

🏠 <b>Бани:</b> {stats['banyas_count']}
📅 <b>Активных броней:</b> {stats['active_bookings']}
✅ <b>Всего бронирований:</b> {stats['total_bookings']}
💰 <b>Общий доход:</b> {total_revenue} ₽

<i>Статистика обновляется в реальном времени</i>
"""
    await message.answer(text)


@router.message(F.text == "👤 Профиль")
async def show_owner_profile(message: Message):
    """Show profile for owner (redirect to profile handler)."""
    from src.bot.handlers.profile import show_profile
    await show_profile(message)


@router.message(F.text == "⚙️ Настройки")
async def show_owner_settings(message: Message):
    """Show settings for owner (redirect to profile with role switching)."""
    from src.bot.handlers.profile import show_profile
    await show_profile(message)


@router.message(F.text == "➕ Добавить баню")
async def start_add_banya(message: Message, state: FSMContext):
    """Start adding a new banya."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BANYA_OWNER:
            await message.answer("Эта функция доступна только владельцам бань.")
            return

    await state.update_data(owner_id=user.id)

    await message.answer(
        "➕ <b>Добавление бани</b>\n\n"
        "Введите название вашей бани:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_banya")]
        ])
    )
    await state.set_state(AddBanyaStates.entering_name)


@router.callback_query(F.data == "add_banya")
async def start_add_banya_callback(callback: CallbackQuery, state: FSMContext):
    """Start adding a new banya from callback."""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user or user.role != UserRole.BANYA_OWNER:
            await callback.answer("Эта функция доступна только владельцам бань.", show_alert=True)
            return

    await state.update_data(owner_id=user.id)

    await callback.message.edit_text(
        "➕ <b>Добавление бани</b>\n\n"
        "Введите название вашей бани:"
    )
    await callback.message.answer(
        "👇 Напишите название:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_banya")]
        ])
    )
    await state.set_state(AddBanyaStates.entering_name)
    await callback.answer()


@router.message(AddBanyaStates.entering_name)
async def process_banya_name(message: Message, state: FSMContext):
    """Process banya name."""
    name = message.text.strip()

    if len(name) < 3:
        await message.answer("Название должно быть не менее 3 символов. Попробуйте ещё раз:")
        return

    await state.update_data(name=name)

    await message.answer(
        f"✅ Название: <b>{name}</b>\n\n"
        "Теперь введите описание бани (особенности, удобства, атмосфера):"
    )
    await state.set_state(AddBanyaStates.entering_description)


@router.message(AddBanyaStates.entering_description)
async def process_banya_description(message: Message, state: FSMContext):
    """Process banya description."""
    description = message.text.strip()

    await state.update_data(description=description)

    await message.answer(
        "✅ Описание сохранено!\n\n"
        "Введите полный адрес бани (город, улица, дом):"
    )
    await state.set_state(AddBanyaStates.entering_address)


@router.message(AddBanyaStates.entering_address)
async def process_banya_address(message: Message, state: FSMContext):
    """Process banya address."""
    address = message.text.strip()

    if len(address) < 10:
        await message.answer("Укажите более подробный адрес:")
        return

    await state.update_data(address=address)

    await message.answer(
        "✅ Адрес сохранён!\n\n"
        "Введите цену за час аренды (только число, в рублях):"
    )
    await state.set_state(AddBanyaStates.entering_price)


@router.message(AddBanyaStates.entering_price)
async def process_banya_price(message: Message, state: FSMContext):
    """Process banya price."""
    try:
        price = int(message.text.strip().replace(" ", "").replace("₽", ""))
        if price < 100 or price > 100000:
            raise ValueError()
    except ValueError:
        await message.answer("Введите корректную цену (от 100 до 100000 ₽):")
        return

    await state.update_data(price_per_hour=price)

    # Show features selection
    keyboard = get_features_keyboard({})
    await message.answer(
        "✅ Цена: <b>{} ₽/час</b>\n\n"
        "Выберите удобства вашей бани:".format(price),
        reply_markup=keyboard
    )
    await state.set_state(AddBanyaStates.selecting_features)


def get_features_keyboard(selected: dict) -> InlineKeyboardMarkup:
    """Get keyboard for selecting banya features."""
    features = [
        ("has_russian_banya", "🇷🇺 Русская баня"),
        ("has_finnish_sauna", "🇫🇮 Финская сауна"),
        ("has_hammam", "🇹🇷 Хаммам"),
        ("has_pool", "🏊 Бассейн"),
        ("has_jacuzzi", "🛁 Джакузи"),
        ("has_cold_plunge", "❄️ Купель"),
        ("has_rest_room", "🛋 Комната отдыха"),
        ("has_parking", "🅿️ Парковка"),
    ]

    buttons = []
    row = []
    for key, name in features:
        check = "✅ " if selected.get(key) else ""
        row.append(InlineKeyboardButton(
            text=f"{check}{name}",
            callback_data=f"toggle_feature_{key}"
        ))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(
        text="✅ Готово — создать баню",
        callback_data="finish_add_banya"
    )])
    buttons.append([InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="cancel_add_banya"
    )])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data.startswith("toggle_feature_"), AddBanyaStates.selecting_features)
async def toggle_feature(callback: CallbackQuery, state: FSMContext):
    """Toggle a banya feature."""
    feature = callback.data.replace("toggle_feature_", "")

    data = await state.get_data()
    features = data.get("features", {})
    features[feature] = not features.get(feature, False)
    await state.update_data(features=features)

    keyboard = get_features_keyboard(features)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data == "finish_add_banya", AddBanyaStates.selecting_features)
async def finish_add_banya(callback: CallbackQuery, state: FSMContext):
    """Finish adding banya and save to database."""
    data = await state.get_data()

    async with async_session() as session:
        # Get user's city
        result = await session.execute(
            select(User).options(selectinload(User.city)).where(User.id == data["owner_id"])
        )
        user = result.scalar_one_or_none()

        if not user or not user.city_id:
            # Get first city as default
            result = await session.execute(select(City).limit(1))
            city = result.scalar_one_or_none()
            city_id = city.id if city else 1
        else:
            city_id = user.city_id

        features = data.get("features", {})

        banya = Banya(
            owner_id=data["owner_id"],
            city_id=city_id,
            name=data["name"],
            description=data.get("description", ""),
            address=data["address"],
            price_per_hour=Decimal(str(data["price_per_hour"])),
            min_hours=2,
            max_guests=10,
            has_russian_banya=features.get("has_russian_banya", False),
            has_finnish_sauna=features.get("has_finnish_sauna", False),
            has_hammam=features.get("has_hammam", False),
            has_pool=features.get("has_pool", False),
            has_jacuzzi=features.get("has_jacuzzi", False),
            has_cold_plunge=features.get("has_cold_plunge", False),
            has_rest_room=features.get("has_rest_room", False),
            has_parking=features.get("has_parking", False),
            is_active=True,
            is_verified=False,
        )
        session.add(banya)
        await session.commit()
        await session.refresh(banya)

    await state.clear()

    await callback.message.edit_text(
        f"🎉 <b>Баня успешно добавлена!</b>\n\n"
        f"🏠 <b>{data['name']}</b>\n"
        f"📍 {data['address']}\n"
        f"💰 {data['price_per_hour']} ₽/час\n\n"
        f"⏳ Баня будет проверена модератором и станет видна клиентам.\n"
        f"Вы получите уведомление о результате проверки."
    )
    await callback.answer("Баня добавлена!")


@router.callback_query(F.data == "cancel_add_banya")
async def cancel_add_banya(callback: CallbackQuery, state: FSMContext):
    """Cancel adding banya."""
    await state.clear()
    await callback.message.edit_text("❌ Добавление бани отменено.")
    await callback.answer()


# ==================== BOOKING MANAGEMENT ====================


@router.callback_query(F.data.startswith("owner_confirm_"))
async def confirm_booking_owner(callback: CallbackQuery):
    """Confirm booking as owner."""
    booking_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        booking = await session.get(Booking, booking_id)

        if not booking:
            await callback.answer("Бронирование не найдено", show_alert=True)
            return

        booking.status = BookingStatus.CONFIRMED
        await session.commit()

        # Get user to notify
        user = await session.get(User, booking.user_id)

    await callback.message.edit_text(
        f"✅ Бронирование #{booking_id} подтверждено!\n\n"
        f"Клиент получит уведомление."
    )
    await callback.answer("Подтверждено!")

    # TODO: Send notification to user via bot


@router.callback_query(F.data.startswith("owner_reject_"))
async def reject_booking_owner(callback: CallbackQuery):
    """Reject booking as owner."""
    booking_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        booking = await session.get(Booking, booking_id)

        if not booking:
            await callback.answer("Бронирование не найдено", show_alert=True)
            return

        booking.status = BookingStatus.CANCELLED
        await session.commit()

    await callback.message.edit_text(
        f"❌ Бронирование #{booking_id} отклонено.\n\n"
        f"Клиент получит уведомление."
    )
    await callback.answer("Отклонено")


@router.callback_query(F.data.startswith("manage_banya_"))
async def manage_banya(callback: CallbackQuery):
    """Show banya management menu."""
    banya_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        result = await session.execute(
            select(Banya)
            .options(selectinload(Banya.city))
            .where(Banya.id == banya_id)
        )
        banya = result.scalar_one_or_none()

        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

    status = "✅ Активна" if banya.is_active else "❌ Неактивна"
    verified = "✓ Проверена" if banya.is_verified else "⏳ На модерации"

    text = f"""
⚙️ <b>Управление баней</b>

🏠 <b>{banya.name}</b>
📍 {banya.address}
💰 {banya.price_per_hour} ₽/час
⭐ {banya.rating:.1f} ({banya.rating_count} отзывов)

📊 <b>Статус:</b> {status}
🔍 <b>Модерация:</b> {verified}
"""

    toggle_text = "❌ Деактивировать" if banya.is_active else "✅ Активировать"

    buttons = [
        [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_banya_{banya_id}")],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"toggle_banya_{banya_id}")],
        [InlineKeyboardButton(text="📅 Бронирования этой бани", callback_data=f"banya_bookings_{banya_id}")],
        [InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_banyas")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("toggle_banya_"))
async def toggle_banya_status(callback: CallbackQuery):
    """Toggle banya active status."""
    banya_id = int(callback.data.split("_")[2])

    async with async_session() as session:
        banya = await session.get(Banya, banya_id)

        if not banya:
            await callback.answer("Баня не найдена", show_alert=True)
            return

        banya.is_active = not banya.is_active
        await session.commit()

        status = "активирована" if banya.is_active else "деактивирована"

    await callback.answer(f"Баня {status}!", show_alert=True)

    # Refresh the management view
    await manage_banya(callback)


@router.callback_query(F.data == "back_to_banyas")
async def back_to_banyas(callback: CallbackQuery):
    """Go back to banyas list."""
    await show_my_banyas(callback.message)
    await callback.answer()
