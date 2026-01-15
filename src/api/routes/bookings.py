from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db, Booking, Banya, User, BathMaster, CancelledBy
from src.database.models import BookingStatus, BookingType
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
    """Client confirms a pending booking - initiates multi-party confirmation."""
    result = await db.execute(
        select(Booking)
        .options(selectinload(Booking.banya), selectinload(Booking.bath_master))
        .where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Verify user owns this booking
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user or booking.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if booking.status != BookingStatus.PENDING:
        raise HTTPException(status_code=400, detail="Booking cannot be confirmed")

    # Mark client as confirmed
    booking.client_confirmed = True

    # Determine required confirmations
    needs_banya = booking.banya_id is not None
    needs_master = booking.bath_master_id is not None

    if needs_banya or needs_master:
        booking.status = BookingStatus.AWAITING_CONFIRMATIONS
        if not needs_banya:
            booking.banya_confirmed = True
        if not needs_master:
            booking.master_confirmed = None
    else:
        booking.status = BookingStatus.CONFIRMED

    await db.commit()
    await db.refresh(booking)

    return booking


@router.patch("/{booking_id}/banya-confirm", response_model=BookingResponse)
async def banya_confirm_booking(
    booking_id: int,
    telegram_id: int = Query(..., description="Banya owner's Telegram ID"),
    db: AsyncSession = Depends(get_db),
):
    """Banya owner confirms their part of the booking."""
    result = await db.execute(
        select(Booking)
        .options(selectinload(Booking.banya).selectinload(Banya.owner))
        .where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Verify caller is banya owner
    if not booking.banya or not booking.banya.owner:
        raise HTTPException(status_code=400, detail="No banya associated with this booking")
    if booking.banya.owner.telegram_id != telegram_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if booking.status != BookingStatus.AWAITING_CONFIRMATIONS:
        raise HTTPException(status_code=400, detail="Booking is not awaiting confirmations")

    booking.banya_confirmed = True

    # Check if all confirmations received
    all_confirmed = booking.banya_confirmed
    if booking.bath_master_id:
        all_confirmed = all_confirmed and booking.master_confirmed

    if all_confirmed:
        booking.status = BookingStatus.CONFIRMED

    await db.commit()
    await db.refresh(booking)

    return booking


@router.patch("/{booking_id}/master-confirm", response_model=BookingResponse)
async def master_confirm_booking(
    booking_id: int,
    telegram_id: int = Query(..., description="Bath master's Telegram ID"),
    db: AsyncSession = Depends(get_db),
):
    """Bath master confirms their part of the booking."""
    result = await db.execute(
        select(Booking)
        .options(selectinload(Booking.bath_master).selectinload(BathMaster.user))
        .where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Verify caller is bath master
    if not booking.bath_master or not booking.bath_master.user:
        raise HTTPException(status_code=400, detail="No bath master associated with this booking")
    if booking.bath_master.user.telegram_id != telegram_id:
        raise HTTPException(status_code=403, detail="Not authorized")

    if booking.status != BookingStatus.AWAITING_CONFIRMATIONS:
        raise HTTPException(status_code=400, detail="Booking is not awaiting confirmations")

    booking.master_confirmed = True

    # Check if all confirmations received
    all_confirmed = booking.master_confirmed
    if booking.banya_id:
        all_confirmed = all_confirmed and booking.banya_confirmed

    if all_confirmed:
        booking.status = BookingStatus.CONFIRMED

    await db.commit()
    await db.refresh(booking)

    return booking


@router.patch("/{booking_id}/cancel", response_model=BookingResponse)
async def cancel_booking(
    booking_id: int,
    telegram_id: int = Query(..., description="User's Telegram ID"),
    reason: str = Query(None, description="Cancellation reason"),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a booking. Works for client, banya owner, or bath master."""
    result = await db.execute(
        select(Booking)
        .options(
            selectinload(Booking.user),
            selectinload(Booking.banya).selectinload(Banya.owner),
            selectinload(Booking.bath_master).selectinload(BathMaster.user)
        )
        .where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if booking.status in [BookingStatus.CANCELLED, BookingStatus.COMPLETED]:
        raise HTTPException(status_code=400, detail="Booking cannot be cancelled")

    # Determine who is cancelling
    cancelled_by = None

    # Check if client
    if booking.user and booking.user.telegram_id == telegram_id:
        cancelled_by = CancelledBy.CLIENT
    # Check if banya owner
    elif booking.banya and booking.banya.owner and booking.banya.owner.telegram_id == telegram_id:
        cancelled_by = CancelledBy.BANYA
    # Check if bath master
    elif booking.bath_master and booking.bath_master.user and booking.bath_master.user.telegram_id == telegram_id:
        cancelled_by = CancelledBy.BATH_MASTER

    if not cancelled_by:
        raise HTTPException(status_code=403, detail="Not authorized to cancel this booking")

    booking.status = BookingStatus.CANCELLED
    booking.cancelled_by = cancelled_by
    booking.cancellation_reason = reason
    await db.commit()
    await db.refresh(booking)

    return booking
