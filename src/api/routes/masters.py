from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db, BathMaster
from src.api.schemas import BathMasterResponse

router = APIRouter()


@router.get("", response_model=List[BathMasterResponse])
async def get_masters(
    min_rating: float | None = Query(None),
    specializes_russian: bool | None = Query(None),
    specializes_finnish: bool | None = Query(None),
    specializes_hammam: bool | None = Query(None),
    specializes_massage: bool | None = Query(None),
    banya_id: int | None = Query(None, description="Filter by banya"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get bath masters with filters."""
    query = (
        select(BathMaster)
        .options(selectinload(BathMaster.user))
        .where(BathMaster.is_available == True)
    )

    if min_rating:
        query = query.where(BathMaster.rating >= min_rating)
    if specializes_russian is not None:
        query = query.where(BathMaster.specializes_russian == specializes_russian)
    if specializes_finnish is not None:
        query = query.where(BathMaster.specializes_finnish == specializes_finnish)
    if specializes_hammam is not None:
        query = query.where(BathMaster.specializes_hammam == specializes_hammam)
    if specializes_massage is not None:
        query = query.where(BathMaster.specializes_massage == specializes_massage)

    if banya_id:
        from src.database.models import BanyaBathMaster

        query = query.join(BanyaBathMaster).where(BanyaBathMaster.banya_id == banya_id)

    query = query.order_by(BathMaster.rating.desc()).offset(skip).limit(limit)

    result = await db.execute(query)
    masters = result.scalars().all()

    return masters


@router.get("/{master_id}", response_model=BathMasterResponse)
async def get_master(master_id: int, db: AsyncSession = Depends(get_db)):
    """Get bath master by ID."""
    result = await db.execute(
        select(BathMaster)
        .options(selectinload(BathMaster.user), selectinload(BathMaster.reviews))
        .where(BathMaster.id == master_id)
    )
    master = result.scalar_one_or_none()

    if not master:
        raise HTTPException(status_code=404, detail="Bath master not found")

    return master
