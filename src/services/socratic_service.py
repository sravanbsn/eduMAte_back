import asyncio
import logging
from typing import Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, stop_after_attempt, wait_exponential

from src.db.neo4j import neo4j_db
from src.db.postgres import SessionLocal
from src.models.postgres import LogicalFallacyLog

logger = logging.getLogger(__name__)


class SocraticEngine:
    """
    SocraticEngine utilizes LangChain to manage conversational guidance
    acting as a pedagogical mentor.
    """

    def __init__(self, persona: Optional[str] = None):
        self.llm = ChatOpenAI(temperature=0.4, model="gpt-4o-mini")
        self.persona = persona

        persona_str = f" Adopt the persona of {self.persona}." if self.persona else ""

        # System Prompt defining Socratic behavior
        self.system_prompt_base = f"""You are a pedagogical mentor embedded in the SocraticBridge platform.{persona_str}

YOUR DIRECTIVES:
1. NEVER provide a direct answer to a question. STRICTLY enforce the 'Refuses direct answers' rule. Immediately refuse if you catch yourself giving a final solution.
2. Analyze the student's query to identify missing prerequisite concepts.
3. Respond ONLY with hints, leading questions, or analogies that guide the student to discover the answer themselves.
4. Use the provided Knowledge Graph context to inform your questions.
5. Keep your responses encouraging, brief, and incredibly focused on the student's current conceptual disconnect.

Knowledge Graph Context regarding the student's concept:
{{concept_context}}
"""

    async def get_knowledge_map(self, concept_name: str) -> str:
        """
        Fetch context from Neo4j Knowledge Graph.

        Inputs:
            - concept_name (str): The learning concept to search for.
        Output:
            - str: A formatted list of connected concepts to append to the LLM context.
        EduMate Module: SocraticBridge engine
        """
        query = """
        MATCH (c:Concept {name: $name})-[r]-(connected)
        RETURN c.name as name, type(r) as relation, connected.name as related_concept
        LIMIT 5
        """
        context_lines = []
        try:
            session = await neo4j_db.get_session()
            async with session:
                results = await session.run(query, name=concept_name)
                async for record in results:
                    context_lines.append(
                        f"- {record['name']} {record['relation']} {record['related_concept']}"
                    )
        except Exception as e:
            logger.error(f"Failed fetching Neo4j context for '{concept_name}': {e}")

        if not context_lines:
            return f"No specific graph context found for '{concept_name}'. Rely on general knowledge."

        return "\n".join(context_lines)

    def detect_frustration(self, question: str, recent_steps: list[dict]) -> bool:
        """
        Heuristic check: If the student shows frustration in 3 consecutive turns, return True for hint escalation.
        """
        frustration_keywords = [
            "don't get it",
            "confused",
            "help",
            "stuck",
            "frustrated",
            "dont understand",
            "lost",
        ]

        current_frustrated = any(kw in question.lower() for kw in frustration_keywords)
        if not current_frustrated:
            return False

        frustrated_turns = 1  # Counting the current one
        # recent_steps is chronological, so we iterate backwards
        for step in reversed(recent_steps):
            q_lower = step["question"].lower()
            if any(kw in q_lower for kw in frustration_keywords):
                frustrated_turns += 1
            else:
                break

        return frustrated_turns >= 3

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def generate_response(
        self, question: str, concept_name: str, recent_steps: Optional[list[dict]] = None
    ) -> str:
        recent_steps = recent_steps or []
        context = await self.get_knowledge_map(concept_name)

        is_frustrated = self.detect_frustration(question, recent_steps)

        escalation_directive = ""
        if is_frustrated:
            escalation_directive = "\n🚨 URGENT: The student is highly frustrated. Escalate to LAYERED HINTS: Provide a direct, clarifying clue or partial answer before asking your next leading question to lower their cognitive load."

        system_prompt = self.system_prompt_base + escalation_directive

        prompt = ChatPromptTemplate.from_messages(
            [("system", system_prompt), ("human", "{question}")]
        )

        chain = prompt | self.llm

        try:
            response = await chain.ainvoke(
                {"concept_context": context, "question": question}
            )
            return response.content
        except Exception as e:
            logger.error(f"Socratic engine error: {e}")
            raise  # Let tenacity handle retries


async def log_fallacy(user_id: int, student_text: str) -> None:
    """
    Analyzes the student's text for logical fallacies and logs it.

    Inputs:
        - user_id (int): Student ID.
        - student_text (str): The prompt that was submitted.
    Output:
        - None
    EduMate Module: SocraticBridge telemetry
    """
    detected_fallacy = None
    text_lower = student_text.lower()

    if "always" in text_lower and "never" in text_lower:
        detected_fallacy = "Black-or-White Fallacy"
    elif "everyone knows" in text_lower:
        detected_fallacy = "Bandwagon Fallacy"
    elif "because you said so" in text_lower:
        detected_fallacy = "Appeal to Authority"

    if detected_fallacy:
        try:
            async with SessionLocal() as db:
                new_log = LogicalFallacyLog(
                    user_id=user_id, fallacy_type=detected_fallacy, context=student_text
                )
                db.add(new_log)
                await db.commit()
                logger.info(f"Logged fallacy '{detected_fallacy}' for user {user_id}")
        except Exception as e:
            logger.error(f"Error logging fallacy: {e}")


async def log_reasoning_step_neo4j(
    user_id: int, concept_name: str, question: str, response: str, persona: str
) -> None:
    """
    Logs every conversational turn as a ReasoningStep node in Neo4j to form a Draft Trail.
    """
    query = """
    CREATE (s:ReasoningStep {
        user_id: $user_id, 
        concept: $concept_name, 
        timestamp: datetime(), 
        question: $question, 
        response: $response, 
        persona: $persona
    })
    """
    try:
        session = await neo4j_db.get_session()
        async with session:
            await session.run(
                query,
                user_id=user_id,
                concept_name=concept_name,
                question=question,
                response=response,
                persona=persona or "None",
            )
    except Exception as e:
        logger.error(f"Failed to log reasoning step to Neo4j: {e}")


async def get_reasoning_map_neo4j(user_id: int, concept_name: str) -> list[dict]:
    """
    Retrieves the chronological Draft Trail from Neo4j for a given user and concept.
    """
    query = """
    MATCH (s:ReasoningStep {user_id: $user_id, concept: $concept_name})
    RETURN s.question AS question, s.response AS response, s.persona AS persona, s.timestamp AS timestamp
    ORDER BY s.timestamp ASC
    """
    steps = []
    try:
        session = await neo4j_db.get_session()
        async with session:
            results = await session.run(
                query, user_id=user_id, concept_name=concept_name
            )
            async for record in results:
                steps.append(
                    {
                        "question": record["question"],
                        "response": record["response"],
                        "persona": record["persona"],
                        "timestamp": str(record["timestamp"]),
                    }
                )
    except Exception as e:
        logger.error(f"Failed fetching Neo4j reasoning map: {e}")
    return steps


async def log_failing_subconcept_neo4j(user_id: int, concept_name: str, question: str) -> None:
    """
    Use an LLM to quickly extract the failing sub-concept from the user's question,
    then log it to Neo4j to visualize 'sub-concepts failing' in real-time.
    """
    llm = ChatOpenAI(temperature=0.0, model="gpt-4o-mini")
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an AI extracting a concise 1-3 word sub-concept that a student is struggling with, based on their question and the main concept. Return ONLY the sub-concept string without quotes."),
        ("human", "Main Concept: {concept_name}\nQuestion: {question}")
    ])
    chain = prompt | llm
    try:
        extraction = await chain.ainvoke({"concept_name": concept_name, "question": question})
        failed_subconcept = extraction.content.strip()
    except Exception as e:
        logger.error(f"Failed to extract sub-concept: {e}")
        failed_subconcept = concept_name + " Basics"

    query = """
    MERGE (u:User {id: toInteger($user_id)})
    MERGE (c:Concept {name: $concept_name})
    MERGE (s:SubConcept {name: $failed_subconcept})
    MERGE (c)-[:CONTAINS]->(s)
    MERGE (u)-[r:FAILING_SUBCONCEPT]->(s)
    ON CREATE SET r.timestamp = datetime(), r.count = 1
    ON MATCH SET r.timestamp = datetime(), r.count = r.count + 1
    """
    try:
        session = await neo4j_db.get_session()
        async with session:
            await session.run(query, user_id=user_id, concept_name=concept_name, failed_subconcept=failed_subconcept)
    except Exception as e:
        logger.error(f"Failed to log failing subconcept to Neo4j: {e}")


async def process_socratic_inquiry(
    db: AsyncSession,
    user_id: int,
    question: str,
    concept_name: str,
    persona: Optional[str] = None,
) -> str:
    """
    Main orchestrator for Socratic engine requests.

    Inputs:
        - db (AsyncSession): Database session.
        - user_id (int): Student ID seeking help.
        - question (str): The student's input query.
        - concept_name (str): The overarching subject they are learning.
        - persona (str, optional): The persona the LLM should adopt.
    Output:
        - str: The LLM generated Socratic response strings.
    EduMate Module: SocraticBridge
    """
    # 1. Background task to track fallacies
    asyncio.create_task(log_fallacy(user_id, question))

    # 2. Fetch recent reasoning map steps for context and frustration detection
    recent_steps = await get_reasoning_map_neo4j(user_id, concept_name)

    # 3. Process using SocraticEngine
    engine = SocraticEngine(persona=persona)
    is_frustrated = engine.detect_frustration(question, recent_steps)
    if is_frustrated:
        asyncio.create_task(log_failing_subconcept_neo4j(user_id, concept_name, question))

    response_content = await engine.generate_response(
        question, concept_name, recent_steps
    )

    # 4. Detect "Aha!" moment
    aha_keywords = [
        "oh i get it",
        "makes sense now",
        "aha",
        "so that means",
        "i understand",
    ]
    is_aha_moment = any(kw in question.lower() for kw in aha_keywords)

    if is_aha_moment:
        logger.info(
            f"Student {user_id} reached an 'Aha!' moment for {concept_name}. Triggering Mastery NFT minting."
        )
        try:
            from src.services.blockchain_service import mint_mastery_token

            asyncio.create_task(mint_mastery_token(user_id, concept_name))
        except ImportError:
            pass

    # Record the step via background task
    asyncio.create_task(
        log_reasoning_step_neo4j(
            user_id, concept_name, question, response_content, persona or ""
        )
    )

    return response_content


async def produce_teacher_export(user_id: int, concept_name: str) -> dict:
    """
    Summarizes a student's Socratic reasoning map into a Teacher Report.

    Inputs:
        - user_id (int): Student ID to analyze.
        - concept_name (str): Concept mapping to analyze.
    Output:
        - dict: Dictionary payload forming the TeacherExportResponse.
    EduMate Module: Teacher Dashboard
    """
    steps = await get_reasoning_map_neo4j(user_id, concept_name)
    if not steps:
        return {
            "user_id": user_id,
            "concept_name": concept_name,
            "summary_report": "No reasoning data available.",
        }

    trail_text = "\n".join(
        [
            f"Student: {s['question']}\nAI ({s['persona']}): {s['response']}"
            for s in steps
        ]
    )

    llm = ChatOpenAI(temperature=0.2, model="gpt-4o-mini")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an educational analyst. Summarize the following student's learning trail. Highlight their struggles, aha moments, and overall conceptual flow in a concise paragraph.",
            ),
            ("human", "Trail:\n{trail}"),
        ]
    )

    chain = prompt | llm
    try:
        response = await chain.ainvoke({"trail": trail_text})
        summary = response.content
    except Exception as e:
        logger.error(f"Failed to generate teacher export summary: {e}")
        summary = "Error generating summary."

    return {"user_id": user_id, "concept_name": concept_name, "summary_report": summary}
