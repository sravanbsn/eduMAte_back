import os

import pytest

os.environ["OPENAI_API_KEY"] = "fake-api-key"
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.core.security import get_current_active_user, verify_adapta_api_key
from src.db.postgres import get_db
from src.main import app
from src.models.postgres import User

client = TestClient(app)

# --- Mock Dependencies to bypass real DB/Auth during test ---


class MockAsyncSession:
    def add(self, instance):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass

    async def refresh(self, instance):
        pass

    async def execute(self, stmt):
        class MockResult:
            def scalars(self):
                class MockScalars:
                    def first(self):
                        return None

                return MockScalars()

        return MockResult()


async def override_get_db():
    yield MockAsyncSession()


async def override_get_user():
    return User(id=1, username="test_student", email="test@example.com")


async def override_verify_api_key():
    return "valid-api-key"


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_active_user] = override_get_user
app.dependency_overrides[verify_adapta_api_key] = override_verify_api_key


@patch("src.services.socratic_service.log_reasoning_step_neo4j", new_callable=AsyncMock)
@patch("src.services.socratic_service.get_reasoning_map_neo4j", new_callable=AsyncMock)
@patch(
    "src.services.socratic_service.SocraticEngine.generate_response",
    new_callable=AsyncMock,
)
def test_socratic_chat_hint_response(
    mock_generate_response, mock_get_reasoning_map, mock_log_reasoning
):
    """
    Simulates a student asking 'What is the answer to 2+2?'
    and verifies the AI responds with a hint.
    """
    mock_get_reasoning_map.return_value = []
    # Mocking the AI so it strictly follows the hint protocol!
    mock_generate_response.return_value = (
        "If you have two apples and get two more, how many do you have?"
    )

    payload = {
        "question": "What is the answer to 2+2?",
        "concept_name": "Basic Addition",
        "persona": "Socrates",
    }

    # We call the new /chat route
    response = client.post("/api/v1/socratic/chat", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert "reply" in data

    reply = data["reply"]

    # Verify the AI gives a hint instead of the number 4
    assert "4" not in reply
    assert "two apples" in reply
    assert "how many do you have" in reply

    # Verify our SocraticEngine generate_response was actually called with correct args
    mock_generate_response.assert_called_once_with(
        "What is the answer to 2+2?", "Basic Addition", []
    )


@patch("src.api.v1.endpoints.socratic.produce_teacher_export", new_callable=AsyncMock)
def test_socratic_export_endpoint(mock_produce_export):
    mock_produce_export.return_value = {
        "user_id": 1,
        "concept_name": "Basic Addition",
        "summary_report": "The student learned addition.",
    }

    response = client.get("/api/v1/socratic/export/1/Basic%20Addition")
    assert response.status_code == 200
    assert response.json()["summary_report"] == "The student learned addition."


@pytest.mark.asyncio
@patch("src.services.socratic_service.neo4j_db.get_session", new_callable=AsyncMock)
async def test_draft_trail_logs_three_steps(mock_get_session):
    """
    Verification: Create a test to ensure the 'Draft Trail' correctly logs
    three distinct steps of a student's reasoning.
    """
    mock_session = AsyncMock()
    mock_get_session.return_value = mock_session
    mock_session.__aenter__.return_value = mock_session

    class MockRecord:
        def __init__(self, data):
            self.data = data

        def __getitem__(self, key):
            return self.data[key]

    class MockResult:
        def __init__(self, records):
            self.records = records

        async def __aiter__(self):
            for r in self.records:
                yield MockRecord(r)

    mock_session.run.return_value = MockResult(
        [
            {
                "question": "Step 1: I am confused.",
                "response": "Think about it.",
                "persona": "Socrates",
                "timestamp": "T1",
            },
            {
                "question": "Step 2: Is it related to variables?",
                "response": "Yes, keep going.",
                "persona": "Socrates",
                "timestamp": "T2",
            },
            {
                "question": "Step 3: Ah I get it now!",
                "response": "Great job.",
                "persona": "Socrates",
                "timestamp": "T3",
            },
        ]
    )

    from src.services.socratic_service import get_reasoning_map_neo4j

    steps = await get_reasoning_map_neo4j(1, "Algebra")

    assert len(steps) == 3
    assert "Step 1" in steps[0]["question"]
    assert "Step 2" in steps[1]["question"]
    assert "Step 3" in steps[2]["question"]
