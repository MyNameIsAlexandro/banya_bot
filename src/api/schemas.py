from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel

from src.database.models import BookingStatus, UserRole


# User schemas
class UserBase(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    first_name: str
    last_name: Optional[str] = None
    phone: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    role: UserRole
    is_premium: bool
    rating: float
    rating_count: int
    created_at: datetime

    class Config:
        from_attributes = True


# City schemas
class CityResponse(BaseModel):
    id: int
    name: str
    region: Optional[str] = None

    class Config:
        from_attributes = True


# Banya schemas
class BanyaBase(BaseModel):
    name: str
    description: Optional[str] = None
    address: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    phone: Optional[str] = None
    price_per_hour: Decimal
    min_hours: int = 2
    max_guests: int = 10
    opening_time: str = "10:00"
    closing_time: str = "23:00"


class BanyaCreate(BanyaBase):
    city_id: int


class BanyaResponse(BanyaBase):
    id: int
    city_id: int
    owner_id: int
    rating: float
    rating_count: int
    is_active: bool
    is_verified: bool
    # Features
    has_pool: bool
    has_jacuzzi: bool
    has_russian_banya: bool
    has_finnish_sauna: bool
    has_hammam: bool
    has_infrared_sauna: bool
    has_salt_room: bool
    has_cold_plunge: bool
    has_rest_room: bool
    has_billiards: bool
    has_karaoke: bool
    has_bbq: bool
    has_parking: bool
    # Services
    provides_veniks: bool
    provides_towels: bool
    provides_robes: bool
    provides_food: bool
    provides_drinks: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BanyaListResponse(BaseModel):
    id: int
    name: str
    address: str
    price_per_hour: Decimal
    rating: float
    rating_count: int
    has_russian_banya: bool
    has_finnish_sauna: bool
    has_hammam: bool
    main_photo_url: Optional[str] = None

    class Config:
        from_attributes = True


# Bath Master schemas
class BathMasterBase(BaseModel):
    bio: Optional[str] = None
    experience_years: int = 0
    price_per_session: Decimal
    session_duration_minutes: int = 60


class BathMasterResponse(BathMasterBase):
    id: int
    user_id: int
    rating: float
    rating_count: int
    is_available: bool
    specializes_russian: bool
    specializes_finnish: bool
    specializes_hammam: bool
    specializes_scrub: bool
    specializes_massage: bool
    specializes_aromatherapy: bool
    user: UserResponse

    class Config:
        from_attributes = True


# Booking schemas
class BookingCreate(BaseModel):
    banya_id: int
    bath_master_id: Optional[int] = None
    date: datetime
    start_time: str
    duration_hours: int
    guests_count: int = 1
    user_notes: Optional[str] = None


class BookingResponse(BaseModel):
    id: int
    user_id: int
    banya_id: int
    bath_master_id: Optional[int]
    date: datetime
    start_time: str
    duration_hours: int
    guests_count: int
    banya_price: Decimal
    master_price: Optional[Decimal]
    total_price: Decimal
    status: BookingStatus
    user_notes: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# Review schemas
class ReviewCreate(BaseModel):
    banya_id: Optional[int] = None
    bath_master_id: Optional[int] = None
    booking_id: Optional[int] = None
    rating: int
    comment: Optional[str] = None


class ReviewResponse(BaseModel):
    id: int
    user_id: int
    banya_id: Optional[int]
    bath_master_id: Optional[int]
    rating: int
    comment: Optional[str]
    created_at: datetime
    user: UserResponse

    class Config:
        from_attributes = True


# Search/Filter schemas
class BanyaSearchParams(BaseModel):
    city_id: Optional[int] = None
    min_price: Optional[Decimal] = None
    max_price: Optional[Decimal] = None
    min_rating: Optional[float] = None
    max_guests: Optional[int] = None
    has_pool: Optional[bool] = None
    has_jacuzzi: Optional[bool] = None
    has_russian_banya: Optional[bool] = None
    has_finnish_sauna: Optional[bool] = None
    has_hammam: Optional[bool] = None
    date: Optional[datetime] = None
