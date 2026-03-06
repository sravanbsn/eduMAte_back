from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import get_current_active_user, verify_adapta_api_key
from src.db.postgres import get_db
from src.models.postgres import User
from src.models.schemas import SocraticRequest, SocraticResponse, TeacherExportResponse
from src.services.socratic_service import (
    process_socratic_inquiry,
    produce_teacher_export,
)

router = APIRouter()


@router.post(
    "/ask",
    response_model=SocraticResponse,
    summary="Ask the Socratic Tutor a Single Question",
    description=(
        "Executes a one-off query to the SocraticBridge AI Tutor. Demands a strict instructional "
        "persona that guides students to the answer without revealing it, actively logging distinct "
        "logical fallacies dynamically detected during the interaction."
    ),
)
async def ask_socratic_tutor(
    request: SocraticRequest,
    current_user: User = Depends(get_current_active_user),
    api_key: str = Depends(verify_adapta_api_key),
    db: AsyncSession = Depends(get_db),
) -> SocraticResponse:
    """
    Endpoint for querying the SocraticBridge AI Tutor.
    Requires a valid AdaptaLearn API Key and User JWT.
    Provides an AI-guided response devoid of direct answers, while logging logical fallacies.
    """

    reply_text = await process_socratic_inquiry(
        db=db,
        user_id=current_user.id,
        question=request.question,
        concept_name=request.concept_name,
        persona=request.persona,
    )

    return SocraticResponse(reply=reply_text)


@router.post(
    "/chat",
    response_model=SocraticResponse,
    summary="Converse with the Socratic AI",
    description=(
        "Used for a seamless ongoing dialogue loop. Internally loads conversation history and "
        "modifies the pedagogical prompt based on continuous input."
    ),
)
async def chat_socratic_tutor(
    request: SocraticRequest,
    current_user: User = Depends(get_current_active_user),
    api_key: str = Depends(verify_adapta_api_key),
    db: AsyncSession = Depends(get_db),
) -> SocraticResponse:
    """
    Endpoint for querying the SocraticBridge AI Tutor in a seamless conversation log manner.
    Requires a valid AdaptaLearn API Key and User JWT.
    """

    reply_text = await process_socratic_inquiry(
        db=db,
        user_id=current_user.id,
        question=request.question,
        concept_name=request.concept_name,
        persona=request.persona,
    )

    return SocraticResponse(reply=reply_text)


@router.get(
    "/export/{user_id}/{concept_name}",
    response_model=TeacherExportResponse,
    summary="Export Student Reasoning Dashboard",
    description=(
        "Admin only endpoint for Teachers. Returns a comprehensive JSON object detailing a student's "
        "strengths, weaknesses, and a structured map of logical fallacies they committed while covering "
        "a specific concept module."
    ),
)
async def export_teacher_report(
    user_id: int,
    concept_name: str,
    current_user: User = Depends(get_current_active_user),
) -> TeacherExportResponse:
    """
    Endpoint for teachers to retrieve a summarized JSON report of a student's reasoning map.
    """
    if current_user.id != user_id and not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=403, detail="Not authorized to view this summary."
        )

    report = await produce_teacher_export(user_id, concept_name)
    return TeacherExportResponse(**report)
