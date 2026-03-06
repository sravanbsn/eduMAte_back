from typing import Dict
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from src.db.postgres import get_db
from src.db.neo4j import neo4j_db
from src.models.postgres import LogicalFallacyLog, ReasoningScoreLog

router = APIRouter()

@router.get("/analytics", response_model=Dict)
async def get_teacher_analytics(db: AsyncSession = Depends(get_db)):
    """
    Alerts educators to class-wide misconceptions (from Neo4j sub-concepts failing) 
    and logical fallacies (from Postgres).
    """
    # 1. Fetch class-wide logical fallacies frequency
    fallacy_query = select(LogicalFallacyLog.fallacy_type, func.count(LogicalFallacyLog.id)).group_by(LogicalFallacyLog.fallacy_type)
    result = await db.execute(fallacy_query)
    fallacies_data = [{"fallacy": row[0], "count": row[1]} for row in result.all()]

    # 2. Fetch class-wide misconceptions from Neo4j (subconcepts failing)
    neo4j_query = """
    MATCH (s:SubConcept)<-[r:FAILING_SUBCONCEPT]-()
    RETURN s.name AS failed_subconcept, count(r) AS failing_students
    ORDER BY failing_students DESC
    LIMIT 10
    """
    misconceptions_data = []
    try:
        session = await neo4j_db.get_session()
        async with session:
            neo4j_results = await session.run(neo4j_query)
            async for record in neo4j_results:
                misconceptions_data.append({
                    "subconcept": record["failed_subconcept"],
                    "failing_students": record["failing_students"]
                })
    except Exception as e:
        misconceptions_data = [{"error": str(e)}]

    # 3. Fetch reasoning scores average (optional contextual info for class)
    avg_score_query = select(func.avg(ReasoningScoreLog.reasoning_ability_score))
    avg_score_result = await db.execute(avg_score_query)
    avg_reasoning_score = avg_score_result.scalar() or 0.0

    return {
        "class_wide_fallacies": fallacies_data,
        "class_wide_misconceptions": misconceptions_data,
        "average_reasoning_ability": avg_reasoning_score
    }
