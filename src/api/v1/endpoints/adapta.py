import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.core.security import get_current_active_user, verify_adapta_api_key
from src.db.postgres import get_db
from src.models.postgres import User, UserPreference
from src.models.schemas import (
    AdaptaRequest,
    AdaptaResponse,
    SyllabusParseRequest,
    TTSRequest,
    UserPreferenceResponse,
    UserPreferenceUpdate,
    VisualTaskBreakdownResponse,
)
from src.services.adapta_service import (
    AdaptaEngine,
    apply_bionic_formatting,
    scrub_html_content,
)

router = APIRouter()
engine = AdaptaEngine()


@router.post("/transform", response_model=AdaptaResponse)
async def transform_content(
    request: AdaptaRequest, api_key: str = Depends(verify_adapta_api_key)
) -> AdaptaResponse:
    """
    Transforms text or HTML content using the AdaptaLearn engine.
    Applies Bionic Reading formatting and simplifies complex jargon via LLM analogies.
    """
    try:
        content_to_process = ""

        # Determine source (Raw Text vs URL)
        if request.url:
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(request.url)
                response.raise_for_status()
                # Extract and scrub main content from the DOM
                content_to_process = scrub_html_content(response.text)
        elif request.text:
            content_to_process = request.text
        else:
            raise HTTPException(
                status_code=400, detail="Must provide either text or a url."
            )

        # 1. Bionic Formatting
        bionic_text = apply_bionic_formatting(content_to_process)

        # 2. NLP Jargon Identification
        jargon_words = engine.identify_jargon(content_to_process)

        # 3. Plain Language Generation via LangChain
        analogies = await engine.generate_analogies(jargon_words, content_to_process)

        return AdaptaResponse(
            original_text=content_to_process,
            bionic_text=bionic_text,
            analogies=analogies,
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL content: {e}")
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Transformation engine failed: {str(e)}"
        )


@router.get("/preferences", response_model=UserPreferenceResponse)
async def get_user_preferences(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserPreferenceResponse:
    """
    Retrieves the currently authenticated user's sensory-sensitive preferences.
    """
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    pref = result.scalars().first()
    if not pref:
        pref = UserPreference(
            user_id=current_user.id,
            animations_enabled=True,
            high_contrast_mode=False,
            reading_speed_default=1.0,
        )
        db.add(pref)
        await db.commit()
        await db.refresh(pref)
    return UserPreferenceResponse(
        animations_enabled=pref.animations_enabled,
        high_contrast_mode=pref.high_contrast_mode,
        reading_speed_default=pref.reading_speed_default,
    )


@router.put("/preferences", response_model=UserPreferenceResponse)
async def update_user_preferences(
    update_data: UserPreferenceUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UserPreferenceResponse:
    """
    Updates the authenticated user's sensory-sensitive preferences.
    """
    stmt = select(UserPreference).where(UserPreference.user_id == current_user.id)
    result = await db.execute(stmt)
    pref = result.scalars().first()
    if not pref:
        pref = UserPreference(
            user_id=current_user.id,
            animations_enabled=True,
            high_contrast_mode=False,
            reading_speed_default=1.0,
        )
        db.add(pref)

    if update_data.animations_enabled is not None:
        pref.animations_enabled = update_data.animations_enabled
    if update_data.high_contrast_mode is not None:
        pref.high_contrast_mode = update_data.high_contrast_mode
    if update_data.reading_speed_default is not None:
        pref.reading_speed_default = update_data.reading_speed_default

    await db.commit()
    await db.refresh(pref)

    return UserPreferenceResponse(
        animations_enabled=pref.animations_enabled,
        high_contrast_mode=pref.high_contrast_mode,
        reading_speed_default=pref.reading_speed_default,
    )


@router.post("/tts")
async def generate_tts(
    request: TTSRequest, api_key: str = Depends(verify_adapta_api_key)
) -> dict:
    """
    Generates an audio representation of text via an AI TTS API,
    supporting varied reading speeds for cognitive load adjustment.
    """
    audio_url = await engine.generate_tts_audio(request.text, request.reading_speed)
    return {"audio_url": audio_url}


@router.post("/parse_syllabus", response_model=VisualTaskBreakdownResponse)
async def parse_syllabus(
    request: SyllabusParseRequest, api_key: str = Depends(verify_adapta_api_key)
) -> VisualTaskBreakdownResponse:
    """
    Identifies topics and deadlines within raw syllabus text
    and returns a visual task breakdown json array payload.
    """
    tasks = await engine.parse_syllabus_tasks(request.text)
    return VisualTaskBreakdownResponse(tasks=tasks)
