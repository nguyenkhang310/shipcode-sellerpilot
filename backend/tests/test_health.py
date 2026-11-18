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
        "capabilities": ['draft_image_append', 'draft_image_dedup', 'draft_image_context_v2', 'chat_request_recovery'],
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


@pytest.mark.parametrize('origin', [
    'http://localhost:8081', 'http://127.0.0.1:8081', 'http://[::1]:8081',
    'http://172.16.30.187:8081', 'http://172.31.255.255:5173',
    'http://192.168.1.9:5173', 'http://10.0.2.2:8081',
    'https://192.168.1.9:8081',
])
def test_demo_web_login_preflight_allows_expo_and_private_lan(client, origin):
    response = client.options('/api/v1/auth/login', headers={
        'Origin': origin, 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'Content-Type,Authorization',
    })
    assert response.status_code == 200
    assert response.headers['access-control-allow-origin'] == origin
    assert 'Origin' in response.headers['vary']
    assert 'access-control-allow-credentials' not in response.headers


@pytest.mark.parametrize('origin', [
    'https://example.com:8081', 'http://172.15.30.187:8081',
    'http://172.32.30.187:8081', 'http://192.168.1.999:8081',
    'http://192.168.1.9:8000', 'http://localhost:5000',
    'http://localhost.evil.example:8081', 'http://192.168.1.9.evil.example:8081',
    'http://evil.example@192.168.1.9:8081', 'null',
])
def test_demo_cors_rejects_unrelated_origins_and_ports(client, origin):
    response = client.options('/api/v1/auth/login', headers={
        'Origin': origin, 'Access-Control-Request-Method': 'POST',
    })
    assert response.status_code == 400
    assert 'access-control-allow-origin' not in response.headers


def test_non_demo_cors_uses_only_explicit_origins():
    from fastapi.testclient import TestClient
    from app.core.config import Settings
    from app.main import create_app

    # No lifespan/DB/provider startup is needed to exercise middleware.
    application = create_app(Settings(_env_file=None, demo_mode=False,
                                      cors_origins=['https://seller.example.test']))
    client = TestClient(application)
    for origin, expected in [('http://172.16.30.187:8081', 400),
                             ('http://localhost:8081', 400),
                             ('https://seller.example.test', 200)]:
        response = client.options('/api/v1/auth/login', headers={
            'Origin': origin, 'Access-Control-Request-Method': 'POST',
        })
        assert response.status_code == expected
        assert response.headers.get('access-control-allow-origin') == (origin if expected == 200 else None)


def test_allowed_cors_does_not_bypass_authentication(client):
    client.app.dependency_overrides.clear()
    response = client.get('/api/v1/auth/me', headers={'Origin': 'http://172.16.30.187:8081'})
    assert response.status_code == 401
    assert response.headers['access-control-allow-origin'] == 'http://172.16.30.187:8081'


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
