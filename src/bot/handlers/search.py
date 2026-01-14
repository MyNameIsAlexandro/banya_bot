from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.database import async_session, City, Banya, BathMaster, User
from src.bot.keyboards.booking import (
    get_cities_keyboard,
    get_banya_list_keyboard,
    get_banya_detail_keyboard,
)

router = Router(name="search")

ITEMS_PER_PAGE = 5


async def get_user_city(telegram_id: int) -> tuple[int | None, str | None]:
    """Get user's city id and name."""
    async with async_session() as session:
        result = await session.execute(
            select(User).options(selectinload(User.city)).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        if user and user.city:
            return user.city_id, user.city.name
        return None, None


@router.message(Command("search"))
async def start_search(message: Message):
    """Start banya search."""
    city_id, city_name = await get_user_city(message.from_user.id)

    if not city_id:
        # User has no city selected - ask to select
        await message.answer(
            "🏙 Сначала выберите ваш город в настройках профиля или через /start"
        )
        return

    async with async_session() as session:
        # Get banyas in user's city
        result = await session.execute(
            select(Banya)
            .where(Banya.city_id == city_id, Banya.is_active == True)
            .order_by(Banya.rating.desc())
            .limit(ITEMS_PER_PAGE)
        )
        banyas = result.scalars().all()

        # Count total
        count_result = await session.execute(
            select(Banya)
            .where(Banya.city_id == city_id, Banya.is_active == True)
        )
        total = len(count_result.scalars().all())

    if not banyas:
        await message.answer(
            f"🏙 <b>{city_name}</b>\n\n"
            "😔 К сожалению, в вашем городе пока нет доступных бань.\n"
            "Попробуйте сменить город в профиле.",
        )
        return

    total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    await message.answer(
        f"🏙 <b>{city_name}</b>\n\n"
        f"🔥 Найдено бань: {total}\n"
        "Выберите баню для подробностей:",
        reply_markup=get_banya_list_keyboard(banyas, page=0, total_pages=total_pages),
    )


@router.callback_query(F.data == "search_banya")
async def search_banya_callback(callback: CallbackQuery):
    """Handle search banya callback."""
    city_id, city_name = await get_user_city(callback.from_user.id)

    if not city_id:
        await callback.message.edit_text(
            "🏙 Сначала выберите ваш город в настройках профиля или через /start"
        )
        await callback.answer()
        return

    async with async_session() as session:
        # Get banyas in user's city
        result = await session.execute(
            select(Banya)
            .where(Banya.city_id == city_id, Banya.is_active == True)
            .order_by(Banya.rating.desc())
            .limit(ITEMS_PER_PAGE)
        )
        banyas = result.scalars().all()

        # Count total
        count_result = await session.execute(
            select(Banya)
            .where(Banya.city_id == city_id, Banya.is_active == True)
        )
        total = len(count_result.scalars().all())

    if not banyas:
        await callback.message.edit_text(
            f"🏙 <b>{city_name}</b>\n\n"
            "😔 К сожалению, в вашем городе пока нет доступных бань.\n"
            "Попробуйте сменить город в профиле.",
        )
        await callback.answer()
        return

    total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    await callback.message.edit_text(
        f"🏙 <b>{city_name}</b>\n\n"
        f"🔥 Найдено бань: {total}\n"
        "Выберите баню для подробностей:",
        reply_markup=get_banya_list_keyboard(banyas, page=0, total_pages=total_pages),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("city_"))
async def handle_city_selection(callback: CallbackQuery):
    """Handle city selection."""
    city_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        # Get city name
        city = await session.get(City, city_id)
        if not city:
            await callback.answer("Город не найден", show_alert=True)
            return

        # Get banyas in city
        result = await session.execute(
            select(Banya)
            .where(Banya.city_id == city_id, Banya.is_active == True)
            .order_by(Banya.rating.desc())
            .limit(ITEMS_PER_PAGE)
        )
        banyas = result.scalars().all()

        # Count total
        count_result = await session.execute(
            select(Banya)
            .where(Banya.city_id == city_id, Banya.is_active == True)
        )
        total = len(count_result.scalars().all())

    if not banyas:
        await callback.message.edit_text(
            f"🏙 <b>{city.name}</b>\n\n"
            "😔 К сожалению, в этом городе пока нет доступных бань.\n"
            "Попробуйте выбрать другой город.",
            reply_markup=get_cities_keyboard([]),
        )
        await callback.answer()
        return

    total_pages = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    await callback.message.edit_text(
        f"🏙 <b>{city.name}</b>\n\n"
        f"🔥 Найдено бань: {total}\n"
        "Выберите баню для подробностей:",
        reply_markup=get_banya_list_keyboard(banyas, page=0, total_pages=total_pages),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("banya_"))
async def handle_banya_selection(callback: CallbackQuery):
    """Handle banya selection - show details."""
    banya_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        result = await session.execute(
            select(Banya)
            .options(selectinload(Banya.city), selectinload(Banya.bath_masters))
            .where(Banya.id == banya_id)
        )
        banya = result.scalar_one_or_none()

    if not banya:
        await callback.answer("Баня не найдена", show_alert=True)
        return

    # Build features text
    features = []
    if banya.has_russian_banya:
        features.append("🇷🇺 Русская баня")
    if banya.has_finnish_sauna:
        features.append("🇫🇮 Финская сауна")
    if banya.has_hammam:
        features.append("🇹🇷 Хаммам")
    if banya.has_pool:
        features.append("🏊 Бассейн")
    if banya.has_jacuzzi:
        features.append("🛁 Джакузи")
    if banya.has_cold_plunge:
        features.append("❄️ Купель")
    if banya.has_rest_room:
        features.append("🛋 Комната отдыха")
    if banya.has_billiards:
        features.append("🎱 Бильярд")
    if banya.has_karaoke:
        features.append("🎤 Караоке")
    if banya.has_bbq:
        features.append("🍖 Мангал")
    if banya.has_parking:
        features.append("🅿️ Парковка")

    # Build services text
    services = []
    if banya.provides_veniks:
        services.append("🌿 Веники")
    if banya.provides_towels:
        services.append("🧺 Полотенца")
    if banya.provides_robes:
        services.append("🥋 Халаты")
    if banya.provides_food:
        services.append("🍽 Еда")
    if banya.provides_drinks:
        services.append("🍺 Напитки")

    rating_stars = "⭐" * int(banya.rating)

    text = f"""
🔥 <b>{banya.name}</b>

{rating_stars} <b>{banya.rating:.1f}</b> ({banya.rating_count} отзывов)

📍 <b>Адрес:</b> {banya.address}
🕐 <b>Время работы:</b> {banya.opening_time} - {banya.closing_time}
👥 <b>Вместимость:</b> до {banya.max_guests} гостей

💰 <b>Цена:</b> {banya.price_per_hour} ₽/час (мин. {banya.min_hours} ч.)

✨ <b>Удобства:</b>
{chr(10).join(features) if features else "Не указаны"}

🎁 <b>Услуги:</b>
{chr(10).join(services) if services else "Не указаны"}
"""

    if banya.description:
        text += f"\n📝 {banya.description}"

    has_masters = len(banya.bath_masters) > 0

    await callback.message.edit_text(
        text,
        reply_markup=get_banya_detail_keyboard(banya_id, has_masters=has_masters),
    )
    await callback.answer()


@router.message(Command("masters"))
async def search_masters(message: Message):
    """Search for bath masters in user's city."""
    city_id, city_name = await get_user_city(message.from_user.id)

    if not city_id:
        await message.answer(
            "🏙 Сначала выберите ваш город в настройках профиля или через /start"
        )
        return

    async with async_session() as session:
        # Get masters who work in banyas in user's city OR can visit home
        # First get all banya IDs in user's city
        banyas_result = await session.execute(
            select(Banya.id).where(Banya.city_id == city_id, Banya.is_active == True)
        )
        banya_ids = [b for b in banyas_result.scalars().all()]

        # Get masters who work in these banyas
        from src.database.models import BanyaBathMaster
        masters_in_city_result = await session.execute(
            select(BanyaBathMaster.bath_master_id).where(BanyaBathMaster.banya_id.in_(banya_ids))
        )
        master_ids_in_city = set(masters_in_city_result.scalars().all())

        # Get all masters who work in city banyas or can visit home
        result = await session.execute(
            select(BathMaster)
            .options(selectinload(BathMaster.user))
            .where(
                BathMaster.is_available == True,
                (BathMaster.id.in_(master_ids_in_city) | (BathMaster.can_visit_home == True))
            )
            .order_by(BathMaster.rating.desc())
            .limit(10)
        )
        masters = result.scalars().all()

    if not masters:
        await message.answer(
            f"👨‍🍳 <b>Пар-мастера в г. {city_name}</b>\n\n"
            "Пока нет доступных мастеров в вашем городе.\n"
            "Попробуйте сменить город в профиле."
        )
        return

    buttons = []
    for master in masters:
        rating_stars = "⭐" * int(master.rating)
        specializations = []
        if master.specializes_russian:
            specializations.append("🇷🇺")
        if master.specializes_finnish:
            specializations.append("🇫🇮")
        if master.specializes_hammam:
            specializations.append("🇹🇷")
        if master.specializes_massage:
            specializations.append("💆")

        specs_text = " ".join(specializations) if specializations else ""
        home_badge = "🏠" if master.can_visit_home else ""
        text = f"{master.user.first_name} {specs_text} {home_badge} {rating_stars}"

        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"view_master_{master.id}"
        )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        f"👨‍🍳 <b>Пар-мастера в г. {city_name}:</b>\n\n"
        "🏠 — выезжает на дом\n\n"
        "Выберите мастера для подробностей:",
        reply_markup=keyboard
    )


@router.callback_query(F.data == "search_masters")
async def search_masters_callback(callback: CallbackQuery):
    """Handle search masters callback."""
    city_id, city_name = await get_user_city(callback.from_user.id)

    if not city_id:
        await callback.message.edit_text(
            "🏙 Сначала выберите ваш город в настройках профиля или через /start"
        )
        await callback.answer()
        return

    async with async_session() as session:
        # Get masters who work in banyas in user's city OR can visit home
        banyas_result = await session.execute(
            select(Banya.id).where(Banya.city_id == city_id, Banya.is_active == True)
        )
        banya_ids = [b for b in banyas_result.scalars().all()]

        from src.database.models import BanyaBathMaster
        masters_in_city_result = await session.execute(
            select(BanyaBathMaster.bath_master_id).where(BanyaBathMaster.banya_id.in_(banya_ids))
        )
        master_ids_in_city = set(masters_in_city_result.scalars().all())

        result = await session.execute(
            select(BathMaster)
            .options(selectinload(BathMaster.user))
            .where(
                BathMaster.is_available == True,
                (BathMaster.id.in_(master_ids_in_city) | (BathMaster.can_visit_home == True))
            )
            .order_by(BathMaster.rating.desc())
            .limit(10)
        )
        masters = result.scalars().all()

    if not masters:
        await callback.message.edit_text(
            f"👨‍🍳 <b>Пар-мастера в г. {city_name}</b>\n\n"
            "Пока нет доступных мастеров в вашем городе.\n"
            "Попробуйте сменить город в профиле."
        )
        await callback.answer()
        return

    buttons = []
    for master in masters:
        rating_stars = "⭐" * int(master.rating)
        specializations = []
        if master.specializes_russian:
            specializations.append("🇷🇺")
        if master.specializes_finnish:
            specializations.append("🇫🇮")
        if master.specializes_hammam:
            specializations.append("🇹🇷")
        if master.specializes_massage:
            specializations.append("💆")

        specs_text = " ".join(specializations) if specializations else ""
        home_badge = "🏠" if master.can_visit_home else ""
        text = f"{master.user.first_name} {specs_text} {home_badge} {rating_stars}"

        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"view_master_{master.id}"
        )])

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        f"👨‍🍳 <b>Пар-мастера в г. {city_name}:</b>\n\n"
        "🏠 — выезжает на дом\n\n"
        "Выберите мастера для подробностей:",
        reply_markup=keyboard
    )
    await callback.answer()


@router.callback_query(F.data.startswith("view_master_"))
async def view_master_detail(callback: CallbackQuery):
    """Show detailed info about a bath master."""
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

    # Build specializations text
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

    rating_stars = "⭐" * int(master.rating)

    # Build banyas list
    banyas_text = ""
    if master.banyas:
        banya_names = [b.name for b in master.banyas if b.is_active]
        banyas_text = f"\n\n🧖 <b>Работает в:</b>\n" + "\n".join(f"• {name}" for name in banya_names)

    # Home visit info
    home_visit_text = ""
    if master.can_visit_home:
        home_visit_text = f"\n🏠 <b>Выезд на дом:</b> {master.home_visit_price} ₽"

    text = f"""
👨‍🍳 <b>{master.user.first_name}</b>

{rating_stars} <b>{master.rating:.1f}</b> ({master.rating_count} отзывов)
📅 Опыт: {master.experience_years} лет

💰 <b>В бане:</b> {master.price_per_session} ₽ / {master.session_duration_minutes} мин{home_visit_text}

✨ <b>Специализации:</b>
{chr(10).join(specs) if specs else "Не указаны"}{banyas_text}
"""

    if master.bio:
        text += f"\n\n📝 {master.bio}"

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    buttons = [
        [InlineKeyboardButton(
            text="📅 Забронировать мастера",
            callback_data=f"book_master_{master_id}"
        )],
        [InlineKeyboardButton(
            text="🔙 К списку мастеров",
            callback_data="search_masters"
        )],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("masters_"))
async def show_banya_masters(callback: CallbackQuery):
    """Show bath masters available at a specific banya."""
    banya_id = int(callback.data.split("_")[1])

    async with async_session() as session:
        result = await session.execute(
            select(Banya)
            .options(
                selectinload(Banya.bath_masters).selectinload(BathMaster.user)
            )
            .where(Banya.id == banya_id)
        )
        banya = result.scalar_one_or_none()

    if not banya or not banya.bath_masters:
        await callback.answer("Мастера не найдены", show_alert=True)
        return

    text = f"👨‍🍳 <b>Пар-мастера в {banya.name}:</b>\n\n"

    for master in banya.bath_masters:
        if not master.is_available:
            continue

        rating_stars = "⭐" * int(master.rating)
        text += (
            f"<b>{master.user.first_name}</b>\n"
            f"{rating_stars} {master.rating:.1f} • {master.experience_years} лет опыта\n"
            f"💰 {master.price_per_session} ₽ / {master.session_duration_minutes} мин\n\n"
        )

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"banya_{banya_id}")]
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()
