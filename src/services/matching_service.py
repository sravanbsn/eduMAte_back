import asyncio
import logging

import redis.asyncio as redis
from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from src.core.config import settings
from src.models.postgres import SkillTag, TutorFeedback, User

logger = logging.getLogger(__name__)

# Cache connection setup
redis_client = redis.from_url(
    settings.REDIS_URL if hasattr(settings, "REDIS_URL") else "redis://localhost:6379",
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

        stmt = (
            select(User)
            .join(User.skills)
            .options(selectinload(User.skills))
            .where(SkillTag.name == skill_name)
            .where(User.id.in_(online_tutor_ids))
            .where(User.teaching_credits >= 0)
        )

        result = await db.execute(stmt)
        tutors = result.scalars().all()

        if not tutors:
            return None

        best_tutor = None
        best_score = -1

        for tutor in tutors:
            # 1. Base Score (Teaching Credits)
            score = tutor.teaching_credits * 0.1

            # 2. Learning Styles Match
            if tutor.learning_style == student_style:
                score += 5.0  # Compatibility bonus

            # 3. Previous Feedback Ratings Average for this Mentor from this student
            avg_feedback_stmt = select(func.avg(TutorFeedback.rating)).where(
                TutorFeedback.tutor_id == tutor.id,
                TutorFeedback.student_id == student_id,
                TutorFeedback.skill_tag == skill_name,
            )
            feedback_res = await db.execute(avg_feedback_stmt)
            avg_rating = feedback_res.scalar()

            if avg_rating:
                # Highly rate return matches
                score += avg_rating * 2.0
            else:
                # General success rate bonus lookup
                general_feedback_stmt = select(func.avg(TutorFeedback.rating)).where(
                    TutorFeedback.tutor_id == tutor.id
                )
                gen_res = await db.execute(general_feedback_stmt)
                gen_rating = gen_res.scalar()
                if gen_rating:
                    score += gen_rating * 1.0

            if score > best_score:
                best_score = score
                best_tutor = tutor

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
