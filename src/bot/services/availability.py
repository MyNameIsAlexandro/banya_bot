"""Service for checking booking slot availability."""

from datetime import datetime, date
from typing import List, Set
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Booking, BookingStatus


async def get_occupied_banya_slots(
    session: AsyncSession,
    banya_id: int,
    booking_date: date,
    duration_hours: int = 2
) -> Set[str]:
    """
    Get set of time slots that are already booked for a banya on a specific date.
    Returns set of start times that should NOT be offered.
    """
    # Active statuses - bookings that block slots
    active_statuses = [
        BookingStatus.PENDING,
        BookingStatus.AWAITING_CONFIRMATIONS,
        BookingStatus.CONFIRMED,
    ]

    result = await session.execute(
        select(Booking)
        .where(
            and_(
                Booking.banya_id == banya_id,
                Booking.date == datetime.combine(booking_date, datetime.min.time()),
                Booking.status.in_(active_statuses)
            )
        )
    )
    bookings = result.scalars().all()

    occupied_slots = set()
    for booking in bookings:
        # Calculate all slots blocked by this booking
        start_hour = int(booking.start_time.split(":")[0])
        for hour_offset in range(booking.duration_hours):
            # Block the hour itself
            occupied_slots.add(f"{start_hour + hour_offset:02d}:00")

        # Also block slots that would overlap with this booking
        # If someone wants to book for duration_hours, they can't start
        # within (duration_hours - 1) hours before an existing booking
        for hour_offset in range(1, duration_hours):
            prev_hour = start_hour - hour_offset
            if prev_hour >= 0:
                occupied_slots.add(f"{prev_hour:02d}:00")

    return occupied_slots


async def get_occupied_master_slots(
    session: AsyncSession,
    master_id: int,
    booking_date: date,
    duration_hours: int = 2
) -> Set[str]:
    """
    Get set of time slots that are already booked for a master on a specific date.
    This checks across ALL banyas and home visits.
    """
    active_statuses = [
        BookingStatus.PENDING,
        BookingStatus.AWAITING_CONFIRMATIONS,
        BookingStatus.CONFIRMED,
    ]

    result = await session.execute(
        select(Booking)
        .where(
            and_(
                Booking.bath_master_id == master_id,
                Booking.date == datetime.combine(booking_date, datetime.min.time()),
                Booking.status.in_(active_statuses)
            )
        )
    )
    bookings = result.scalars().all()

    occupied_slots = set()
    for booking in bookings:
        start_hour = int(booking.start_time.split(":")[0])
        for hour_offset in range(booking.duration_hours):
            occupied_slots.add(f"{start_hour + hour_offset:02d}:00")

        # Block overlapping slots
        for hour_offset in range(1, duration_hours):
            prev_hour = start_hour - hour_offset
            if prev_hour >= 0:
                occupied_slots.add(f"{prev_hour:02d}:00")

    return occupied_slots


async def get_available_slots(
    session: AsyncSession,
    all_slots: List[str],
    banya_id: int | None,
    master_id: int | None,
    booking_date: date,
    duration_hours: int = 2
) -> List[str]:
    """
    Filter available slots based on existing bookings.
    Returns list of slots that are still available.
    """
    occupied = set()

    if banya_id:
        banya_occupied = await get_occupied_banya_slots(
            session, banya_id, booking_date, duration_hours
        )
        occupied.update(banya_occupied)

    if master_id:
        master_occupied = await get_occupied_master_slots(
            session, master_id, booking_date, duration_hours
        )
        occupied.update(master_occupied)

    return [slot for slot in all_slots if slot not in occupied]


def filter_available_slots(all_slots: List[str], occupied_slots: Set[str]) -> List[str]:
    """Simple helper to filter slots based on occupied set."""
    return [slot for slot in all_slots if slot not in occupied_slots]
