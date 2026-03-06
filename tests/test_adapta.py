import os

import pytest

os.environ["OPENAI_API_KEY"] = "fake-api-key"
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from src.core.security import get_current_active_user, verify_adapta_api_key
from src.db.postgres import get_db
from src.main import app
from src.models.postgres import User
from src.services.adapta_service import apply_bionic_formatting, scrub_html_content

client = TestClient(app)


async def override_verify_api_key():
    return "valid-api-key"


class MockAsyncSession:
    def add(self, instance):
        pass

    async def commit(self):
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


app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[get_current_active_user] = override_get_user
app.dependency_overrides[verify_adapta_api_key] = override_verify_api_key


def test_apply_bionic_formatting():
    """Verify that bionic processing correctly formats a sentence based on substring character limits."""
    text = "The mitochondrial matrix facilitates ATP synthesis through chemiosmosis"
    bionic_result = apply_bionic_formatting(text)

    # Check that bolding tags have been injected properly
    assert "<b>T</b>he" in bionic_result
    assert "<b>mit</b>ochondrial" in bionic_result
    assert "<b>mat</b>rix" in bionic_result
    assert "<b>che</b>miosmosis" in bionic_result


def test_scrub_html_content():
    """Verify that undesirable HTML nodes (scripts, ads, navigation) are dumped, leaving only the readable text."""
    dirty_html = """
        <html>
            <head><script>alert('ad');</script><style>body {color: red;}</style></head>
            <body>
                <header>Navigation Bar</header>
                <nav><ul><li>Link</li></ul></nav>
                <aside>Sidebar Ads</aside>
                <main>This is the core educational text that we need to keep.</main>
                <footer>Copyright 2026</footer>
            </body>
        </html>
    """

    clean_text = scrub_html_content(dirty_html)

    # Discarded Elements:
    assert "Navigation Bar" not in clean_text
    assert "Sidebar Ads" not in clean_text
    assert "Link" not in clean_text
    assert "Copyright" not in clean_text
    assert "alert" not in clean_text

    # Retained Elements:
    assert "This is the core educational text that we need to keep." in clean_text


@patch(
    "src.services.adapta_service.AdaptaEngine.generate_analogies",
    new_callable=AsyncMock,
)
@patch("src.services.adapta_service.AdaptaEngine.identify_jargon")
def test_adapta_transform_endpoint(mock_identify_jargon, mock_generate_analogies):
    """
    Test the full transformation endpoint using a complex biology sentence.
    Mocks out LangChain LLM analogy generation to prevent rate limits/delays.
    """
    input_text = (
        "The mitochondrial matrix facilitates ATP synthesis through chemiosmosis"
    )

    # Mock NLP Extraction
    mock_identify_jargon.return_value = [
        "mitochondrial",
        "chemiosmosis",
        "synthesis",
        "facilitates",
        "matrix",
    ]

    # Mock LLM generation
    mock_generate_analogies.return_value = {
        "mitochondrial": "A powerhouse structure inside cells that creates energy.",
        "chemiosmosis": "The movement of ions across a membrane, like water flowing through a dam.",
        "synthesis": "The process of building or putting things together.",
        "matrix": "The inner space where important chemical reactions happen.",
        "facilitates": "Makes an action or process easier.",
    }

    payload = {"text": input_text}

    response = client.post("/api/v1/adapta/transform", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["original_text"] == input_text
    assert "<b>mit</b>ochondrial" in data["bionic_text"]

    # Verify Analogies payload mapping
    assert len(data["analogies"]) == 5
    assert (
        data["analogies"]["chemiosmosis"]
        == "The movement of ions across a membrane, like water flowing through a dam."
    )


def test_user_preferences_endpoints():
    response = client.get("/api/v1/adapta/preferences")
    assert response.status_code == 200
    assert response.json()["animations_enabled"] is True

    put_data = {"animations_enabled": False, "reading_speed_default": 1.5}
    response = client.put("/api/v1/adapta/preferences", json=put_data)
    assert response.status_code == 200
    assert response.json()["animations_enabled"] is False
    assert response.json()["reading_speed_default"] == 1.5


@patch(
    "src.services.adapta_service.AdaptaEngine.parse_syllabus_tasks",
    new_callable=AsyncMock,
)
def test_parse_syllabus(mock_parse):
    mock_parse.return_value = [
        {
            "topic": "Homework 1",
            "deadline": "2026-03-15",
            "description": "Write an essay",
        }
    ]
    payload = {"text": "Complete Homework 1 by March 15th."}
    response = client.post("/api/v1/adapta/parse_syllabus", json=payload)
    assert response.status_code == 200
    assert response.json()["tasks"][0]["topic"] == "Homework 1"


@patch(
    "src.services.adapta_service.AdaptaEngine.generate_tts_audio",
    new_callable=AsyncMock,
)
def test_generate_tts(mock_tts):
    mock_tts.return_value = "https://cdn.skillswarm.edu/mock_audio/tts_abc_1.0.mp3"
    payload = {"text": "hello world", "reading_speed": 1.0}
    response = client.post("/api/v1/adapta/tts", json=payload)
    assert response.status_code == 200
    assert "audio_url" in response.json()

@pytest.mark.asyncio
@patch("langchain_core.runnables.base.RunnableSequence.ainvoke", new_callable=AsyncMock)
async def test_parse_syllabus_engine_logic(mock_ainvoke):
    from src.services.adapta_service import AdaptaEngine
    
    mock_ainvoke.return_value = [
        {"topic": "Midterm Exam", "deadline": "October 15, 2026", "description": "Covers chapters 1-5"},
        {"topic": "Final Project", "deadline": "December 1, 2026", "description": "Submit code and report"}
    ]
    
    engine = AdaptaEngine()
    syllabus_text = "Midterm Exam is on October 15, 2026. The Final Project is due December 1, 2026."
    
    tasks = await engine.parse_syllabus_tasks(syllabus_text)
    
    assert len(tasks) == 2
    assert tasks[0]["topic"] == "Midterm Exam"
    assert tasks[0]["deadline"] == "October 15, 2026"
    assert tasks[1]["topic"] == "Final Project"
    assert tasks[1]["deadline"] == "December 1, 2026"
