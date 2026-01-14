from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db, User
from src.database.models import UserRole
from src.api.schemas import UserResponse, UserCreate

router = APIRouter()


@router.post("", response_model=UserResponse)
async def create_or_get_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new user or return existing one."""
    result = await db.execute(
        select(User).where(User.telegram_id == user_data.telegram_id)
    )
    user = result.scalar_one_or_none()

    if user:
        # Update user info
        user.username = user_data.username
        user.first_name = user_data.first_name
        user.last_name = user_data.last_name
        if user_data.phone:
            user.phone = user_data.phone
        await db.commit()
        await db.refresh(user)
        return user

    # Create new user
    user = User(
        telegram_id=user_data.telegram_id,
        username=user_data.username,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        phone=user_data.phone,
        role=UserRole.CLIENT,
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    return user


@router.get("/me", response_model=UserResponse)
async def get_current_user(
    telegram_id: int = Query(..., description="User's Telegram ID"),
    db: AsyncSession = Depends(get_db),
):
    """Get current user by Telegram ID."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.patch("/me/phone", response_model=UserResponse)
async def update_phone(
    phone: str = Query(..., description="New phone number"),
    telegram_id: int = Query(..., description="User's Telegram ID"),
    db: AsyncSession = Depends(get_db),
):
    """Update user's phone number."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.phone = phone
    await db.commit()
    await db.refresh(user)

    return user
