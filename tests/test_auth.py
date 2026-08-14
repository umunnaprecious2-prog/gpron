import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_register_customer_and_login():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "name": "Test Customer",
            "email": "testcustomer_gpron@example.com",
            "password": "securepass123",
            "role": "customer",
        }
        res = await client.post("/auth/register", json=payload)
        assert res.status_code in (201, 400)

        res = await client.post(
            "/auth/login",
            json={
                "email": payload["email"],
                "password": payload["password"],
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data


@pytest.mark.asyncio
async def test_manager_registration_without_code():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "name": "Test Manager",
            "email": "testmgr_nocode@example.com",
            "password": "securepass123",
            "role": "manager",
        }
        res = await client.post("/auth/register", json=payload)
        assert res.status_code == 403
        assert "Manager code required" in res.json()["detail"]


@pytest.mark.asyncio
async def test_manager_registration_with_wrong_code():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "name": "Test Manager",
            "email": "testmgr_wrongcode@example.com",
            "password": "securepass123",
            "role": "manager",
            "manager_code": "9999",
        }
        res = await client.post("/auth/register", json=payload)
        assert res.status_code == 403
        assert "Invalid manager code" in res.json()["detail"]


@pytest.mark.asyncio
async def test_manager_registration_with_correct_code():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        payload = {
            "name": "Test Manager",
            "email": "testmgr_correctcode@example.com",
            "password": "securepass123",
            "role": "manager",
            "manager_code": "0000",
        }
        res = await client.post("/auth/register", json=payload)
        assert res.status_code == 201
        data = res.json()
        assert "access_token" in data
        assert data["user"]["role"] == "manager"


@pytest.mark.asyncio
async def test_invalid_login():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "wrongpassword",
            },
        )
        assert res.status_code == 401
