import asyncio
import logging
from unittest.mock import patch

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.models.postgres import Base, User, SkillTag
from src.services.feedback_service import process_session_feedback, FeedbackEngine
import src.services.blockchain_service as blockchain_service

# Setup simpler DB config for test
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_loop")

async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
async def verify():
    # Mocking out external LLM and Blockchain dependencies
    async def mock_generate_summaries(*args, **kwargs):
        return {
            "summary": "This is a mock summary for testing.",
            "recommendations": ["Practice 1", "Practice 2", "Practice 3"]
        }

    mock_badge_call_count = 0
    async def mock_mint_badge(user_id):
        nonlocal mock_badge_call_count
        mock_badge_call_count += 1
        logger.info(f"MOCKED EVENT: Minted badge for user {user_id}")
    
    # Patch the engine directly
    FeedbackEngine.generate_actionable_summaries = mock_generate_summaries
    blockchain_service.mint_verified_peer_mentor_badge = mock_mint_badge

    await setup_db()

    async with AsyncSessionLocal() as session:
        # Create users
        student = User(username="student1", email="student1@example.com", teaching_credits=5)
        tutor = User(username="tutor_expert", email="tutor@example.com", teaching_credits=0)
        session.add_all([student, tutor])
        await session.flush()
        
        # Test 5 feedback loops
        skill = "Calculus"
        for i in range(1, 6):
            logger.info(f"--- Submitting 'Excellent' (5) rating #{i} ---")
            # process_session_feedback internally fetches/counts ratings and can trigger mint
            result = await process_session_feedback(
                db=session,
                student_id=student.id,
                tutor_id=tutor.id,
                skill_name=skill,
                rating=5,
                transcript="Mock transcript text"
            )
            
            logger.info(f"Analysis Output: {result['ai_analysis']['summary']}")
            
            # Need to sleep slightly if async tasks were dispatched
            # Though in this implementation create_task runs without await, so we yield control let it run
            await asyncio.sleep(0.1)

        if mock_badge_call_count > 0:
            logger.info("VERIFICATION SUCCESS: The blockchain badge was minted!")
        else:
            logger.info("VERIFICATION FAILED: The badge was NOT minted.")


if __name__ == "__main__":
    asyncio.run(verify())
