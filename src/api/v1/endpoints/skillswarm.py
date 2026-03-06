from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import get_current_active_user
from src.db.postgres import get_db
from src.models.postgres import User
from src.models.schemas import UserResponse
from src.models.skillswarm_schemas import (
    SessionCompleteRequest,
    SessionFeedbackRequest,
    TutorRequest,
)
from src.services.feedback_service import process_session_feedback
from src.services.matching_service import find_tutor_match, process_credit_transfer

router = APIRouter()


@router.post(
    "/request_tutor",
    response_model=UserResponse,
    summary="Request a Peer Mentor Match",
    description=(
        "Initiates the 'Compatibility Matching' algorithm. Scans the active WebSocket registry "
        "to find online tutors who possess the requested skill. It then ranks them based on "
        "teaching credits, learning style compatibility, and historical feedback scores (especially "
        "previous successful pairings)."
    ),
)
async def request_tutor(
    request: TutorRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    POST route to request a matched tutor.
    Retrieves online users from the sockets registry to find an online tutor with the requested skill.
    """
    from src.sockets import user_sockets

    online_user_ids = set(user_sockets.keys())

    if current_user.id in online_user_ids:
        online_user_ids.discard(current_user.id)

    if not online_user_ids:
        raise HTTPException(status_code=404, detail="No online tutors available.")

    tutor = await find_tutor_match(
        db, request.student_id, request.skill_name, online_user_ids
    )
    if not tutor:
        raise HTTPException(
            status_code=404,
            detail=f"No suitable tutor found for skill '{request.skill_name}'.",
        )

    return tutor


@router.post(
    "/complete_session",
    summary="Complete Session & Transfer Credits",
    description=(
        "Concludes a live SkillSwarm tutoring session. Triggers the credit ledger securely, "
        "deducting 1 'EduCoin/Teaching Credit' from the Student and rewarding it to the Tutor. "
        "Behind the scenes, this transaction is also logged onto the blockchain via automated workers."
    ),
)
async def finish_tutoring_session(
    request: SessionCompleteRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Marks the SkillSwarm session as complete and processes the credit transaction,
    deducting from the Student and rewarding the Tutor.
    """
    result = await process_credit_transfer(
        db, student_id=request.student_id, tutor_id=request.tutor_id
    )

    return result


@router.post(
    "/feedback",
    summary="Submit Session Feedback & Generate AI Summary",
    description=(
        "Accepts a JSON payload containing the session transcript and the student's rating (1-5). "
        "It writes the rating to PostgreSQL, uses LangChain to generate an 'Actionable Summary' with "
        "3 targeted practice recommendations from the transcript. If the tutor reaches five '5-star' ratings, "
        "it fires an asynchronous blockchain webhook to mint a 'Verified Peer Mentor' micro-credential."
    ),
)
async def submit_session_feedback(
    request: SessionFeedbackRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Submits feedback for a finished session and processes an actionable AI summary.
    """
    result = await process_session_feedback(
        db,
        student_id=request.student_id,
        tutor_id=request.tutor_id,
        skill_name=request.skill_name,
        rating=request.rating,
        transcript=request.transcript,
    )

    return result
