from typing import List
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from src.database.models import City, Banya


def get_cities_keyboard(cities: List[City]) -> InlineKeyboardMarkup:
    """Get keyboard with cities."""
    buttons = []
    row = []
    for i, city in enumerate(cities):
        row.append(InlineKeyboardButton(text=city.name, callback_data=f"city_{city.id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_banya_list_keyboard(
    banyas: List[Banya], page: int = 0, total_pages: int = 1
) -> InlineKeyboardMarkup:
    """Get keyboard with banyas list."""
    buttons = []

    for banya in banyas:
        rating_stars = "⭐" * int(banya.rating)
        text = f"{banya.name} {rating_stars} ({banya.rating:.1f})"
        buttons.append([InlineKeyboardButton(text=text, callback_data=f"banya_{banya.id}")])

    # Pagination
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"page_{page - 1}"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton(text="Вперёд ▶️", callback_data=f"page_{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="🔙 К городам", callback_data="search_banya")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_banya_detail_keyboard(banya_id: int, has_masters: bool = False) -> InlineKeyboardMarkup:
    """Get keyboard for banya detail view."""
    buttons = [
        [InlineKeyboardButton(text="📅 Забронировать", callback_data=f"book_{banya_id}")],
        [
            InlineKeyboardButton(text="📸 Фото", callback_data=f"photos_{banya_id}"),
            InlineKeyboardButton(text="📍 На карте", callback_data=f"map_{banya_id}"),
        ],
        [InlineKeyboardButton(text="⭐ Отзывы", callback_data=f"reviews_{banya_id}")],
    ]

    if has_masters:
        buttons.insert(
            1,
            [
                InlineKeyboardButton(
                    text="👨‍🍳 Пар-мастера", callback_data=f"masters_{banya_id}"
                )
            ],
        )

    buttons.append([InlineKeyboardButton(text="🔙 К списку", callback_data="back_to_list")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_booking_confirm_keyboard(booking_id: int) -> InlineKeyboardMarkup:
    """Get confirmation keyboard for booking."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить", callback_data=f"confirm_booking_{booking_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отменить", callback_data=f"cancel_booking_{booking_id}"
                ),
            ],
        ]
    )


def get_time_slots_keyboard(
    banya_id: int, available_slots: List[str], selected_date: str
) -> InlineKeyboardMarkup:
    """Get keyboard with available time slots."""
    buttons = []
    row = []

    for slot in available_slots:
        row.append(
            InlineKeyboardButton(
                text=slot, callback_data=f"slot_{banya_id}_{selected_date}_{slot}"
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"banya_{banya_id}")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_duration_keyboard(banya_id: int, min_hours: int = 2) -> InlineKeyboardMarkup:
    """Get keyboard for selecting booking duration."""
    buttons = []
    durations = [min_hours, min_hours + 1, min_hours + 2, min_hours + 3]

    for duration in durations:
        text = f"{duration} ч."
        buttons.append(
            [InlineKeyboardButton(text=text, callback_data=f"duration_{banya_id}_{duration}")]
        )

    buttons.append(
        [InlineKeyboardButton(text="🔙 Назад", callback_data=f"banya_{banya_id}")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)
