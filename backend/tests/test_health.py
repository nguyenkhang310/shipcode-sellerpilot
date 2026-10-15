import asyncio

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.ai.client import OllamaClient
from app.ai.contracts import ProviderHealth
from app.db.session import get_session


def test_health_works_without_ollama(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["data"] == {
        "status": "degraded", "database": "ok", "shop_database": "ok",
        "ollama": "unavailable",
        "provider": "ollama", "ai_availability": "unavailable",
        "model": "qwen3:4b-instruct", "model_available": False,
        "demo_mode": True, "integration_mode": "local_store",
    }


def test_health_ready_when_model_is_available(client):
    class ReadyProvider:
        async def check_health(self):
            return ProviderHealth(availability="available", model_available=True)

    client.app.state.ai_provider = ReadyProvider()
    assert client.get("/api/v1/health").json()["data"]["status"] == "ok"


def test_database_failure_is_unavailable(client):
    class BrokenSession:
        def execute(self, _statement):
            raise SQLAlchemyError("private connection details")

    client.app.dependency_overrides[get_session] = lambda: BrokenSession()
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json()["data"]["database"] == "unavailable"
    assert "private" not in response.text


def test_swagger_and_openapi(client):
    assert client.get("/docs").status_code == 200
    assert "/api/v1/health" in client.get("/openapi.json").json()["paths"]


def test_cors_allows_local_frontend_only(client):
    for origin, expected in [("http://localhost:5173", 200), ("https://example.com", 400)]:
        response = client.options("/api/v1/health", headers={
            "Origin": origin, "Access-Control-Request-Method": "GET",
        })
        assert response.status_code == expected


@pytest.mark.parametrize("payload,availability,model_available", [
    ({"models": [{"name": "qwen3:4b-instruct"}]}, "available", True),
    ({"models": []}, "available", False),
    ({"unexpected": True}, "unavailable", False),
    (None, "unavailable", False),
])
def test_ollama_probe_validates_model(payload, availability, model_available):
    async def run():
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
        async with httpx.AsyncClient(base_url="http://ollama.test", transport=transport) as http:
            return await OllamaClient(http, "qwen3:4b-instruct").check_health()

    result = asyncio.run(run())
    assert result.availability == availability
    assert result.model_available is model_available


def test_ollama_timeout_is_degraded():
    def timeout(_request):
        raise httpx.ReadTimeout("slow provider")

    async def run():
        async with httpx.AsyncClient(base_url="http://ollama.test", transport=httpx.MockTransport(timeout)) as http:
            return await OllamaClient(http, "qwen3:4b-instruct").check_health()

    assert asyncio.run(run()).availability == "unavailable"
