from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db, Banya, City, BanyaPhoto
from src.api.schemas import BanyaResponse, BanyaListResponse, CityResponse

router = APIRouter()


@router.get("/cities", response_model=List[CityResponse])
async def get_cities(db: AsyncSession = Depends(get_db)):
    """Get all available cities."""
    result = await db.execute(select(City).order_by(City.name))
    cities = result.scalars().all()
    return cities


@router.get("", response_model=List[BanyaListResponse])
async def get_banyas(
    city_id: Optional[int] = Query(None),
    min_price: Optional[float] = Query(None),
    max_price: Optional[float] = Query(None),
    min_rating: Optional[float] = Query(None),
    has_pool: Optional[bool] = Query(None),
    has_russian_banya: Optional[bool] = Query(None),
    has_finnish_sauna: Optional[bool] = Query(None),
    has_hammam: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get banyas with filters."""
    query = select(Banya).where(Banya.is_active == True)

    if city_id:
        query = query.where(Banya.city_id == city_id)
    if min_price:
        query = query.where(Banya.price_per_hour >= min_price)
    if max_price:
        query = query.where(Banya.price_per_hour <= max_price)
    if min_rating:
        query = query.where(Banya.rating >= min_rating)
    if has_pool is not None:
        query = query.where(Banya.has_pool == has_pool)
    if has_russian_banya is not None:
        query = query.where(Banya.has_russian_banya == has_russian_banya)
    if has_finnish_sauna is not None:
        query = query.where(Banya.has_finnish_sauna == has_finnish_sauna)
    if has_hammam is not None:
        query = query.where(Banya.has_hammam == has_hammam)

    query = query.order_by(Banya.rating.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    banyas = result.scalars().all()

    # Get main photos
    response = []
    for banya in banyas:
        photo_result = await db.execute(
            select(BanyaPhoto)
            .where(BanyaPhoto.banya_id == banya.id, BanyaPhoto.is_main == True)
            .limit(1)
        )
        main_photo = photo_result.scalar_one_or_none()

        response.append(
            BanyaListResponse(
                id=banya.id,
                name=banya.name,
                address=banya.address,
                price_per_hour=banya.price_per_hour,
                rating=banya.rating,
                rating_count=banya.rating_count,
                has_russian_banya=banya.has_russian_banya,
                has_finnish_sauna=banya.has_finnish_sauna,
                has_hammam=banya.has_hammam,
                main_photo_url=main_photo.url if main_photo else None,
            )
        )

    return response


@router.get("/{banya_id}", response_model=BanyaResponse)
async def get_banya(banya_id: int, db: AsyncSession = Depends(get_db)):
    """Get banya details by ID."""
    result = await db.execute(
        select(Banya)
        .options(selectinload(Banya.photos), selectinload(Banya.bath_masters))
        .where(Banya.id == banya_id)
    )
    banya = result.scalar_one_or_none()

    if not banya:
        raise HTTPException(status_code=404, detail="Banya not found")

    return banya


@router.get("/{banya_id}/photos")
async def get_banya_photos(banya_id: int, db: AsyncSession = Depends(get_db)):
    """Get banya photos."""
    result = await db.execute(
        select(BanyaPhoto)
        .where(BanyaPhoto.banya_id == banya_id)
        .order_by(BanyaPhoto.order)
    )
    photos = result.scalars().all()
    return [{"id": p.id, "url": p.url, "is_main": p.is_main} for p in photos]


@router.get("/{banya_id}/available-slots")
async def get_available_slots(
    banya_id: int,
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db),
):
    """Get available time slots for a specific date."""
    from datetime import datetime

    banya = await db.get(Banya, banya_id)
    if not banya:
        raise HTTPException(status_code=404, detail="Banya not found")

    # Parse date
    try:
        selected_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    # Generate all possible slots
    open_hour = int(banya.opening_time.split(":")[0])
    close_hour = int(banya.closing_time.split(":")[0])
    all_slots = [f"{h:02d}:00" for h in range(open_hour, close_hour - banya.min_hours + 1)]

    # Get existing bookings for this date
    from src.database import Booking
    from src.database.models import BookingStatus

    result = await db.execute(
        select(Booking).where(
            Booking.banya_id == banya_id,
            Booking.date == datetime.combine(selected_date, datetime.min.time()),
            Booking.status.in_([BookingStatus.PENDING, BookingStatus.CONFIRMED]),
        )
    )
    bookings = result.scalars().all()

    # Filter out booked slots
    booked_hours = set()
    for booking in bookings:
        start_hour = int(booking.start_time.split(":")[0])
        for h in range(start_hour, start_hour + booking.duration_hours):
            booked_hours.add(h)

    available_slots = []
    for slot in all_slots:
        hour = int(slot.split(":")[0])
        # Check if all hours for min_duration are available
        is_available = all(
            h not in booked_hours for h in range(hour, hour + banya.min_hours)
        )
        if is_available:
            available_slots.append(slot)

    return {
        "date": date,
        "slots": available_slots,
        "min_hours": banya.min_hours,
        "price_per_hour": float(banya.price_per_hour),
    }
