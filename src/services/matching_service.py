import asyncio
import logging

import redis.asyncio as redis
from fastapi import HTTPException, status
from sqlalchemy import case, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.models.postgres import SkillTag, TutorFeedback, User

logger = logging.getLogger(__name__)

# Cache connection setup
redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
)


async def find_tutor_match(
    db: AsyncSession, student_id: int, skill_name: str, online_tutor_ids: set
) -> User | None:
    """
    Searches the PostgreSQL Users and SkillTags tables for a tutor who has 'mastered' the specific sub-topic requested.
    Calculates a 'Compatibility Score' factoring in learning styles and previous feedback ratings.

    Inputs:
        - db (AsyncSession): Active database session.
        - student_id (int): Searching student.
        - skill_name (str): The requested subject/skill.
        - online_tutor_ids (set): A set of user IDs currently connected to the WebSocket.
    Output:
        - User | None: The matched tutor user object, or None if none found.
    EduMate Module: SkillSwarm Matching
    """
    if not online_tutor_ids:
        return None

    # Check cache first for available matches for this skill
    cache_key = f"tutor_match:{skill_name}"
    cached_tutor_id_str = await redis_client.get(cache_key)

    if cached_tutor_id_str and int(cached_tutor_id_str) in online_tutor_ids:
        # Cache Hit - Fetch minimal user data from DB quickly, assumes they still have credits
        try:
            stmt = select(User).where(User.id == int(cached_tutor_id_str))
            result = await db.execute(stmt)
            user = result.scalars().first()
            if user:
                logger.info(f"Cache Hit: Found tutor {user.id} for skill {skill_name}")
                return user
        except Exception as e:
            logger.warning(f"Failed to retrieve cached tutor: {e}")

    try:
        # Get Student for learning style
        student_stmt = select(User).where(User.id == student_id)
        student_res = await db.execute(student_stmt)
        student = student_res.scalars().first()
        student_style = student.learning_style if student else "visual"

        # 1. Subquery for Direct Previous Feedback (Highly Rated)
        direct_avg = (
            select(
                TutorFeedback.tutor_id,
                func.coalesce(func.avg(TutorFeedback.rating), 0).label("direct_avg"),
            )
            .where(
                TutorFeedback.student_id == student_id,
                TutorFeedback.skill_tag == skill_name,
            )
            .group_by(TutorFeedback.tutor_id)
            .subquery()
        )

        # 2. Subquery for General Feedback Average
        general_avg = (
            select(
                TutorFeedback.tutor_id,
                func.coalesce(func.avg(TutorFeedback.rating), 0).label("gen_avg"),
            )
            .group_by(TutorFeedback.tutor_id)
            .subquery()
        )

        # 3. Calculate optimized score on the DB level to execute < 150ms
        score_expr = (
            User.teaching_credits * 0.1
            + case((User.learning_style == student_style, 5.0), else_=0.0)
            + case(
                (direct_avg.c.direct_avg > 0, direct_avg.c.direct_avg * 2.0),
                else_=func.coalesce(general_avg.c.gen_avg, 0) * 1.0,
            )
        )

        stmt = (
            select(User, score_expr.label("compatibility_score"))
            .join(User.skills)
            .options(selectinload(User.skills))
            .outerjoin(direct_avg, User.id == direct_avg.c.tutor_id)
            .outerjoin(general_avg, User.id == general_avg.c.tutor_id)
            .where(SkillTag.name == skill_name)
            .where(User.id.in_(online_tutor_ids))
            .where(User.teaching_credits >= 0)
            .order_by(score_expr.desc())
            .limit(1)
        )

        result = await db.execute(stmt)
        match = result.first()

        if not match:
            return None

        best_tutor = match[0]
        best_score = match[1]

        # Write to Cache with 5 min TTL
        if best_tutor:
            await redis_client.setex(cache_key, 300, str(best_tutor.id))
            logger.info(
                f"Cache Miss: Found and cached tutor {best_tutor.id} for skill {skill_name} with score {best_score}"
            )

        return best_tutor

    except Exception as e:
        logger.error(f"Error finding tutor match for skill {skill_name}: {e}")
        return None


async def process_credit_transfer(
    db: AsyncSession, student_id: int, tutor_id: int
) -> dict:
    """
    Deducts 1 credit from the student and adds it to the tutor's balance once a session is successfully verified.

    Inputs:
        - db (AsyncSession): Active database session.
        - student_id (int): ID of the student spending a credit.
        - tutor_id (int): ID of the tutor receiving the credit.
    Output:
        - dict: A dictionary confirming the successful transaction amount.
    EduMate Module: SkillSwarm Transacting
    """
    if student_id == tutor_id:
        raise HTTPException(
            status_code=400, detail="Student and Tutor cannot be the same user."
        )

    cost = 1

    try:
        # Lock the rows for update to prevent race conditions (lost updates)
        student_stmt = select(User).where(User.id == student_id).with_for_update()
        tutor_stmt = select(User).where(User.id == tutor_id).with_for_update()

        student_result = await db.execute(student_stmt)
        student = student_result.scalars().first()

        tutor_result = await db.execute(tutor_stmt)
        tutor = tutor_result.scalars().first()

        if not student:
            raise HTTPException(
                status_code=404, detail=f"Student ID {student_id} not found."
            )
        if not tutor:
            raise HTTPException(
                status_code=404, detail=f"Tutor ID {tutor_id} not found."
            )

        # Validate Balance
        if student.teaching_credits < cost:
            raise HTTPException(
                status_code=400, detail="Insufficient teaching credits."
            )

        # Execute the transfer
        student.teaching_credits -= cost
        tutor.teaching_credits += cost

        # Commit the transaction to persist the changes
        await db.commit()

        # Fire off the blockchain logging in the background
        try:
            from src.services.blockchain_service import transfer_credits

            asyncio.create_task(
                transfer_credits(
                    sender_id=student_id, receiver_id=tutor_id, amount=cost
                )
            )
        except ImportError:
            pass

        logger.info(
            f"Credit transfer successful: User {student_id} paid User {tutor_id} {cost} credits."
        )
        return {"message": "Session complete. Transaction successful.", "cost": cost}

    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Credit transfer failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transaction failed due to an internal error.",
        )
