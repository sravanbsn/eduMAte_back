import logging

from fastapi import HTTPException
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from tenacity import retry, stop_after_attempt, wait_exponential

from src.models.postgres import TutorFeedback

logger = logging.getLogger(__name__)


class FeedbackEngine:
    def __init__(self):
        self.llm = ChatOpenAI(temperature=0.3, model="gpt-4o-mini")

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_actionable_summaries(self, transcript: str) -> dict:
        """
        Summarize transcript and generate 3 Targeted Practice recommendations based on weak points.
        """
        prompt_text = """Analyze the following tutoring session transcript.
Provide a short summary and exactly 3 'Targeted Practice' recommendations based on the student's weak points.

Format restrictions:
Return a JSON object with:
"summary": a short string summarizing the session.
"recommendations": a list of 3 strings containing the practice recommendations.

Transcript:
{transcript}
"""
        prompt = ChatPromptTemplate.from_messages([("system", prompt_text)])

        chain = prompt | self.llm | JsonOutputParser()
        try:
            return await chain.ainvoke({"transcript": transcript})
        except Exception as e:
            logger.error(f"Error parsing feedback transcript: {e}")
            raise


async def process_session_feedback(
    db: AsyncSession,
    student_id: int,
    tutor_id: int,
    skill_name: str,
    rating: int,
    transcript: str,
) -> dict:
    feedback = TutorFeedback(
        student_id=student_id,
        tutor_id=tutor_id,
        skill_tag=skill_name,
        rating=rating,
        comment="Auto-processed session feedback",
    )
    db.add(feedback)
    await db.commit()
    await db.refresh(feedback)

    # Check for verified peer mentor badge
    if rating == 5:  # 5 is 'Excellent'
        stmt = select(func.count(TutorFeedback.id)).where(
            TutorFeedback.tutor_id == tutor_id,
            TutorFeedback.skill_tag == skill_name,
            TutorFeedback.rating == 5,
        )
        result = await db.execute(stmt)
        excellent_count = result.scalar()

        if excellent_count == 5:
            logger.info(
                f"Tutor {tutor_id} reached 5 excellent feedback ratings in {skill_name}. Minting verified badge."
            )
            try:
                import asyncio

                from src.services.blockchain_service import (
                    mint_verified_peer_mentor_badge,
                )

                asyncio.create_task(mint_verified_peer_mentor_badge(tutor_id))
            except ImportError:
                pass

    # Generate Actionable Summaries
    engine = FeedbackEngine()
    try:
        ai_analysis = await engine.generate_actionable_summaries(transcript)
    except Exception:
        ai_analysis = {"summary": "Transcript analysis failed.", "recommendations": []}

    return {"message": "Feedback submitted successfully.", "ai_analysis": ai_analysis}
