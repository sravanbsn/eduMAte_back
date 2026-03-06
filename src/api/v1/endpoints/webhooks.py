import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.postgres import get_db
from src.models.postgres import CreditTransferLog, MasteryTokenLog

router = APIRouter()
logger = logging.getLogger(__name__)


class MasteryTokenWebhookPayload(BaseModel):
    user_id: int
    skill_tag: str
    transaction_hash: str
    security_hash: str


def verify_security_hash(payload: MasteryTokenWebhookPayload) -> bool:
    """Verifies that the incoming webhook is genuinely from our own internal service via HMAC SHA256."""
    message = (
        f"{payload.user_id}:{payload.skill_tag}:{payload.transaction_hash}".encode(
            "utf-8"
        )
    )
    secret = settings.WEBHOOK_SECRET_KEY.encode("utf-8")
    expected_hash = hmac.new(secret, message, hashlib.sha256).hexdigest()
    # Use hmac.compare_digest to prevent timing attacks
    return hmac.compare_digest(expected_hash, payload.security_hash)


@router.post("/blockchain/mastery_token")
async def log_mastery_token(
    payload: MasteryTokenWebhookPayload, db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Internal Webhook to log successfully minted Mastery Tokens.
    This guarantees that the transaction is saved back to PostgreSQL for the user.
    """
    if not verify_security_hash(payload):
        logger.warning(
            f"Invalid security hash received for Mastery Token webhook: User {payload.user_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid security signature"
        )

    try:
        new_log = MasteryTokenLog(
            user_id=payload.user_id,
            skill_tag=payload.skill_tag,
            transaction_hash=payload.transaction_hash,
        )
        db.add(new_log)
        await db.commit()
        logger.info(
            f"Successfully saved Mastery Token log for User {payload.user_id} with hash {payload.transaction_hash}"
        )
        return {"status": "success", "message": "Mastery token logged successfully."}
    except Exception as e:
        logger.error(f"Failed to save Mastery Token log: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed")


class CreditTransferWebhookPayload(BaseModel):
    sender_id: int
    receiver_id: int
    amount: int
    transaction_hash: str
    security_hash: str


def verify_credit_transfer_security_hash(payload: CreditTransferWebhookPayload) -> bool:
    message = f"{payload.sender_id}:{payload.receiver_id}:{payload.amount}:{payload.transaction_hash}".encode(
        "utf-8"
    )
    secret = settings.WEBHOOK_SECRET_KEY.encode("utf-8")
    expected_hash = hmac.new(secret, message, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected_hash, payload.security_hash)


@router.post("/blockchain/credit_transfer")
async def log_credit_transfer(
    payload: CreditTransferWebhookPayload, db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Internal Webhook to log successfully transferred EduCoins.
    """
    if not verify_credit_transfer_security_hash(payload):
        logger.warning(
            f"Invalid security hash received for Credit Transfer: Sender {payload.sender_id}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid security signature"
        )

    try:
        new_log = CreditTransferLog(
            sender_id=payload.sender_id,
            receiver_id=payload.receiver_id,
            amount=payload.amount,
            transaction_hash=payload.transaction_hash,
        )
        db.add(new_log)
        await db.commit()
        logger.info(
            f"Successfully saved Credit Transfer log: {payload.sender_id} -> {payload.receiver_id} with hash {payload.transaction_hash}"
        )
        return {"status": "success", "message": "Credit transfer logged successfully."}
    except Exception as e:
        logger.error(f"Failed to save Credit Transfer log: {e}")
        await db.rollback()
        raise HTTPException(status_code=500, detail="Database operation failed")
