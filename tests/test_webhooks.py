import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from src.core.config import settings
from src.db.postgres import get_db
from src.main import app

client = TestClient(app)


# Helper function to generate a valid hash
def generate_valid_hash(user_id: int, skill_tag: str, tx_hash: str) -> str:
    message = f"{user_id}:{skill_tag}:{tx_hash}".encode("utf-8")
    secret = settings.WEBHOOK_SECRET_KEY.encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


# Mock mock db session
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


# Override the FastAPI dependency
app.dependency_overrides[get_db] = override_get_db


def test_mastery_token_webhook_success():
    """Test successful mastery token log with valid security hash."""
    user_id = 1
    skill_tag = "Python_Expertise"
    tx_hash = "0x123abc456def"

    valid_hash = generate_valid_hash(user_id, skill_tag, tx_hash)

    payload = {
        "user_id": user_id,
        "skill_tag": skill_tag,
        "transaction_hash": tx_hash,
        "security_hash": valid_hash,
    }

    response = client.post("/api/v1/webhooks/blockchain/mastery_token", json=payload)
    assert response.status_code == 200
    assert response.json() == {
        "status": "success",
        "message": "Mastery token logged successfully.",
    }


def test_mastery_token_webhook_invalid_hash():
    """Test that the webhook rejects requests with invalid security hashes."""
    payload = {
        "user_id": 1,
        "skill_tag": "Python_Expertise",
        "transaction_hash": "0x123abc456def",
        "security_hash": "invalid_hash_string",
    }

    response = client.post("/api/v1/webhooks/blockchain/mastery_token", json=payload)
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid security signature"


def test_mastery_token_webhook_missing_fields():
    """Test that the webhook returns 422 for missing required fields."""
    payload = {
        "user_id": 1,
        # missing skill_tag
        "transaction_hash": "0x123abc456def",
        "security_hash": "some_hash",
    }

    response = client.post("/api/v1/webhooks/blockchain/mastery_token", json=payload)
    assert response.status_code == 422
