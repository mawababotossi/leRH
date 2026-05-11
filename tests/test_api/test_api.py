"""Tests de l'API FastAPI."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient) -> None:
    payload = {"name": "Kossi", "country": "Togo", "city": "Lomé"}
    resp = await client.post("/users/", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Kossi"
    assert data["country"] == "Togo"
    assert data["city"] == "Lomé"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient) -> None:
    resp = await client.get("/users/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_user_by_id(client: AsyncClient) -> None:
    payload = {"name": "Afiwa", "country": "Bénin", "phone": "90123456"}
    create = await client.post("/users/", json=payload)
    user_id = create.json()["id"]

    resp = await client.get(f"/users/{user_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Afiwa"


@pytest.mark.asyncio
async def test_get_user_by_telegram(client: AsyncClient) -> None:
    payload = {"name": "TelegramUser", "telegram_id": 12345, "country": "Ghana"}
    await client.post("/users/", json=payload)

    resp = await client.get("/users/telegram/12345")
    assert resp.status_code == 200
    assert resp.json()["telegram_id"] == 12345
