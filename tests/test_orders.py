import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


async def get_token(
    client: AsyncClient, email: str, password: str, role: str = "customer"
) -> str:
    name = "Test Customer" if role == "customer" else "Test Manager"
    payload = {"name": name, "email": email, "password": password, "role": role}
    if role == "manager":
        payload["manager_code"] = "0000"
    await client.post("/auth/register", json=payload)
    res = await client.post("/auth/login", json={"email": email, "password": password})
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_create_and_track_order():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        token = await get_token(client, "customer_order_test@example.com", "pass1234")
        headers = {"Authorization": f"Bearer {token}"}

        res = await client.post(
            "/orders",
            json={
                "service_type": "normal",
                "cart": [
                    {"name": "shirt", "quantity": 1, "unit_price": 200},
                    {"name": "trousers", "quantity": 1, "unit_price": 250},
                ],
                "notes": "Handle with care",
            },
            headers=headers,
        )
        assert res.status_code == 201
        order = res.json()
        tracking_id = order["tracking_id"]
        assert tracking_id.startswith("GPRON-")

        res = await client.get(f"/track/{tracking_id}")
        assert res.status_code == 200
        assert res.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_manager_can_update_status():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        cust_token = await get_token(
            client, "cust_status_test@example.com", "pass1234", "customer"
        )
        mgr_token = await get_token(
            client, "mgr_status_test@example.com", "pass1234", "manager"
        )

        res = await client.post(
            "/orders",
            json={
                "service_type": "express",
                "cart": [{"name": "dress", "quantity": 1, "unit_price": 300}],
            },
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        tracking_id = res.json()["tracking_id"]

        res = await client.patch(
            "/orders/status",
            json={
                "tracking_id": tracking_id,
                "status": "picked_up",
            },
            headers={"Authorization": f"Bearer {mgr_token}"},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "picked_up"
