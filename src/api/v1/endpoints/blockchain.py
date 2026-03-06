from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.security import get_current_active_user
from src.db.postgres import get_db
from src.models.postgres import MasteryTokenLog, User

router = APIRouter()


@router.get("/balance/{user_id}")
async def get_user_balance(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Retrieves the teaching credits user balance from the PostgreSQL DB.
    (This mirrors their on-chain balance via our sync logic).
    """
    if current_user.id != user_id and not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=403, detail="Not authorized to view this user's balance."
        )

    stmt = select(User.teaching_credits).where(User.id == user_id)
    result = await db.execute(stmt)
    credits = result.scalars().first()

    if credits is None:
        raise HTTPException(status_code=404, detail="User not found.")

    return {"user_id": user_id, "balance": credits}


@router.get("/certificates/{user_id}")
async def get_mastery_certificates(
    user_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Retrieves the logged Mastery Certificates (SBTs) for a specific user.
    """
    if current_user.id != user_id and not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=403, detail="Not authorized to view this user's certificates."
        )

    stmt = (
        select(MasteryTokenLog)
        .where(MasteryTokenLog.user_id == user_id)
        .order_by(MasteryTokenLog.timestamp.desc())
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    certificates = [
        {
            "skill_tag": log.skill_tag,
            "transaction_hash": log.transaction_hash,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in logs
    ]

    return {"user_id": user_id, "certificates": certificates}
