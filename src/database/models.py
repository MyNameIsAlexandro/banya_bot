from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List
from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    Enum as SQLEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class BookingStatus(str, Enum):
    """Booking status enumeration."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class BookingType(str, Enum):
    """Booking type enumeration."""

    BANYA_ONLY = "banya_only"           # Только баня, без мастера
    BANYA_WITH_MASTER = "banya_with_master"  # Баня + пар-мастер
    MASTER_AT_BANYA = "master_at_banya"      # Мастер в бане (выбор начался с мастера)
    MASTER_HOME_VISIT = "master_home_visit"  # Мастер выезжает к клиенту


class UserRole(str, Enum):
    """User role enumeration."""

    CLIENT = "client"
    BATH_MASTER = "bath_master"
    BANYA_OWNER = "banya_owner"
    ADMIN = "admin"


class User(Base):
    """User model - clients, bath masters, banya owners."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole), default=UserRole.CLIENT)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    rating: Mapped[float] = mapped_column(Float, default=5.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    bookings: Mapped[List["Booking"]] = relationship(
        "Booking", back_populates="user", foreign_keys="Booking.user_id"
    )
    reviews_given: Mapped[List["Review"]] = relationship(
        "Review", back_populates="user", foreign_keys="Review.user_id"
    )
    owned_banyas: Mapped[List["Banya"]] = relationship("Banya", back_populates="owner")
    bath_master_profile: Mapped[Optional["BathMaster"]] = relationship(
        "BathMaster", back_populates="user", uselist=False
    )


class City(Base):
    """City model for filtering banyas by location."""

    __tablename__ = "cities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    region: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    banyas: Mapped[List["Banya"]] = relationship("Banya", back_populates="city")


class Banya(Base):
    """Banya (sauna) model."""

    __tablename__ = "banyas"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    city_id: Mapped[int] = mapped_column(ForeignKey("cities.id"))

    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address: Mapped[str] = mapped_column(String(500))
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Pricing
    price_per_hour: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    min_hours: Mapped[int] = mapped_column(Integer, default=2)

    # Capacity
    max_guests: Mapped[int] = mapped_column(Integer, default=10)

    # Features (amenities)
    has_pool: Mapped[bool] = mapped_column(Boolean, default=False)
    has_jacuzzi: Mapped[bool] = mapped_column(Boolean, default=False)
    has_russian_banya: Mapped[bool] = mapped_column(Boolean, default=True)
    has_finnish_sauna: Mapped[bool] = mapped_column(Boolean, default=False)
    has_hammam: Mapped[bool] = mapped_column(Boolean, default=False)
    has_infrared_sauna: Mapped[bool] = mapped_column(Boolean, default=False)
    has_salt_room: Mapped[bool] = mapped_column(Boolean, default=False)
    has_cold_plunge: Mapped[bool] = mapped_column(Boolean, default=False)
    has_rest_room: Mapped[bool] = mapped_column(Boolean, default=False)
    has_billiards: Mapped[bool] = mapped_column(Boolean, default=False)
    has_karaoke: Mapped[bool] = mapped_column(Boolean, default=False)
    has_bbq: Mapped[bool] = mapped_column(Boolean, default=False)
    has_parking: Mapped[bool] = mapped_column(Boolean, default=False)

    # Additional services
    provides_veniks: Mapped[bool] = mapped_column(Boolean, default=False)
    provides_towels: Mapped[bool] = mapped_column(Boolean, default=False)
    provides_robes: Mapped[bool] = mapped_column(Boolean, default=False)
    provides_food: Mapped[bool] = mapped_column(Boolean, default=False)
    provides_drinks: Mapped[bool] = mapped_column(Boolean, default=False)

    # Working hours (stored as "HH:MM" format)
    opening_time: Mapped[str] = mapped_column(String(5), default="10:00")
    closing_time: Mapped[str] = mapped_column(String(5), default="23:00")

    # Status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Ratings
    rating: Mapped[float] = mapped_column(Float, default=5.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="owned_banyas")
    city: Mapped["City"] = relationship("City", back_populates="banyas")
    photos: Mapped[List["BanyaPhoto"]] = relationship("BanyaPhoto", back_populates="banya")
    bookings: Mapped[List["Booking"]] = relationship("Booking", back_populates="banya")
    reviews: Mapped[List["Review"]] = relationship(
        "Review", back_populates="banya", foreign_keys="Review.banya_id"
    )
    bath_masters: Mapped[List["BathMaster"]] = relationship(
        "BathMaster", secondary="banya_bath_masters", back_populates="banyas"
    )


class BanyaPhoto(Base):
    """Photos for banya."""

    __tablename__ = "banya_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    banya_id: Mapped[int] = mapped_column(ForeignKey("banyas.id"))
    url: Mapped[str] = mapped_column(String(500))
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)
    order: Mapped[int] = mapped_column(Integer, default=0)

    banya: Mapped["Banya"] = relationship("Banya", back_populates="photos")


class BathMaster(Base):
    """Bath master (par-master) profile."""

    __tablename__ = "bath_masters"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)

    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    experience_years: Mapped[int] = mapped_column(Integer, default=0)
    price_per_session: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    session_duration_minutes: Mapped[int] = mapped_column(Integer, default=60)

    # Specializations
    specializes_russian: Mapped[bool] = mapped_column(Boolean, default=True)
    specializes_finnish: Mapped[bool] = mapped_column(Boolean, default=False)
    specializes_hammam: Mapped[bool] = mapped_column(Boolean, default=False)
    specializes_scrub: Mapped[bool] = mapped_column(Boolean, default=False)
    specializes_massage: Mapped[bool] = mapped_column(Boolean, default=False)
    specializes_aromatherapy: Mapped[bool] = mapped_column(Boolean, default=False)

    # Availability
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    can_visit_home: Mapped[bool] = mapped_column(Boolean, default=False)  # Выезд к клиенту
    home_visit_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)  # Цена выезда

    # Ratings
    rating: Mapped[float] = mapped_column(Float, default=5.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="bath_master_profile")
    bookings: Mapped[List["Booking"]] = relationship("Booking", back_populates="bath_master")
    reviews: Mapped[List["Review"]] = relationship(
        "Review", back_populates="bath_master", foreign_keys="Review.bath_master_id"
    )
    banyas: Mapped[List["Banya"]] = relationship(
        "Banya", secondary="banya_bath_masters", back_populates="bath_masters"
    )


class BanyaBathMaster(Base):
    """Association table for banyas and bath masters."""

    __tablename__ = "banya_bath_masters"

    banya_id: Mapped[int] = mapped_column(ForeignKey("banyas.id"), primary_key=True)
    bath_master_id: Mapped[int] = mapped_column(ForeignKey("bath_masters.id"), primary_key=True)


class Booking(Base):
    """Booking model."""

    __tablename__ = "bookings"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    banya_id: Mapped[Optional[int]] = mapped_column(ForeignKey("banyas.id"), nullable=True)  # Nullable для выезда мастера
    bath_master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bath_masters.id"), nullable=True
    )

    # Booking type
    booking_type: Mapped[BookingType] = mapped_column(
        SQLEnum(BookingType), default=BookingType.BANYA_ONLY
    )

    # Booking details
    date: Mapped[datetime] = mapped_column(DateTime)
    start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM"
    duration_hours: Mapped[int] = mapped_column(Integer)
    guests_count: Mapped[int] = mapped_column(Integer, default=1)

    # Client address for home visits
    client_address: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Pricing
    banya_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)  # Nullable для выезда
    master_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    # Status
    status: Mapped[BookingStatus] = mapped_column(
        SQLEnum(BookingStatus), default=BookingStatus.PENDING
    )

    # Notes
    user_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    admin_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="bookings")
    banya: Mapped["Banya"] = relationship("Banya", back_populates="bookings")
    bath_master: Mapped[Optional["BathMaster"]] = relationship(
        "BathMaster", back_populates="bookings"
    )


class Review(Base):
    """Review model for banyas and bath masters."""

    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    banya_id: Mapped[Optional[int]] = mapped_column(ForeignKey("banyas.id"), nullable=True)
    bath_master_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bath_masters.id"), nullable=True
    )
    booking_id: Mapped[Optional[int]] = mapped_column(ForeignKey("bookings.id"), nullable=True)

    rating: Mapped[int] = mapped_column(Integer)  # 1-5
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="reviews_given")
    banya: Mapped[Optional["Banya"]] = relationship("Banya", back_populates="reviews")
    bath_master: Mapped[Optional["BathMaster"]] = relationship(
        "BathMaster", back_populates="reviews"
    )
