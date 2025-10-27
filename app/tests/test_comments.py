import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_create_valid_comment(monkeypatch):
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/comments/",
            json={"project_id": 1, "author_id": 2, "text": "Great project!"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["text"] == "Great project!"
        assert not data["is_deleted"]

@pytest.mark.asyncio
async def test_invalid_text_too_short():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/comments/",
            json={"project_id": 1, "author_id": 2, "text": "ok"}
        )
        assert response.status_code == 422  # validation error
