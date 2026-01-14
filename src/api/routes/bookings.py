from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db, Booking, Banya, User, BathMaster
from src.database.models import BookingStatus
from src.api.schemas import BookingCreate, BookingResponse

router = APIRouter()


@router.post("", response_model=BookingResponse)
async def create_booking(
    booking_data: BookingCreate,
    telegram_id: int = Query(..., description="User's Telegram ID"),
    db: AsyncSession = Depends(get_db),
):
    """Create a new booking."""
    # Get user
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get banya
    banya = await db.get(Banya, booking_data.banya_id)
    if not banya:
        raise HTTPException(status_code=404, detail="Banya not found")

    if not banya.is_active:
        raise HTTPException(status_code=400, detail="Banya is not available")

    # Calculate prices
    banya_price = banya.price_per_hour * booking_data.duration_hours
    master_price = None
    total_price = banya_price

    # Get bath master if specified
    if booking_data.bath_master_id:
        master = await db.get(BathMaster, booking_data.bath_master_id)
        if not master:
            raise HTTPException(status_code=404, detail="Bath master not found")
        if not master.is_available:
            raise HTTPException(status_code=400, detail="Bath master is not available")
        master_price = master.price_per_session
        total_price += master_price

    # Create booking
    booking = Booking(
        user_id=user.id,
        banya_id=booking_data.banya_id,
        bath_master_id=booking_data.bath_master_id,
        date=booking_data.date,
        start_time=booking_data.start_time,
        duration_hours=booking_data.duration_hours,
        guests_count=booking_data.guests_count,
        banya_price=banya_price,
        master_price=master_price,
        total_price=total_price,
        user_notes=booking_data.user_notes,
        status=BookingStatus.PENDING,
    )

    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    return booking


@router.get("", response_model=List[BookingResponse])
async def get_user_bookings(
    telegram_id: int = Query(..., description="User's Telegram ID"),
    status: BookingStatus | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get user's bookings."""
    # Get user
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    query = (
        select(Booking)
        .options(selectinload(Booking.banya), selectinload(Booking.bath_master))
        .where(Booking.user_id == user.id)
    )

    if status:
        query = query.where(Booking.status == status)

    query = query.order_by(Booking.date.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    bookings = result.scalars().all()

    return bookings


@router.get("/{booking_id}", response_model=BookingResponse)
async def get_booking(booking_id: int, db: AsyncSession = Depends(get_db)):
    """Get booking by ID."""
    result = await db.execute(
        select(Booking)
        .options(selectinload(Booking.banya), selectinload(Booking.bath_master))
        .where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    return booking


@router.patch("/{booking_id}/confirm", response_model=BookingResponse)
async def confirm_booking(
    booking_id: int,
    telegram_id: int = Query(..., description="User's Telegram ID"),
    db: AsyncSession = Depends(get_db),
):
    """Confirm a pending booking."""
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Verify user owns this booking
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user or booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=400, detail="Booking cannot be confirmed")

    booking.status = BookingStatus.CONFIRMED
    await db.commit()
    await db.refresh(booking)

    return booking


@router.patch("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: int,
    telegram_id: int = Query(..., description="User's Telegram ID"),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a booking."""
    booking = await db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Verify user owns this booking
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user or booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if booking.status in [BookingStatus.CANCELLED, BookingStatus.COMPLETED]:
        raise HTTPException(status_code=400, detail="Booking cannot be cancelled")

    booking.status = BookingStatus.CANCELLED
    await db.commit()
    await db.refresh(booking)

    return booking
