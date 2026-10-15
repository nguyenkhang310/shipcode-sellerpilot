import asyncio
import json
from datetime import date

import httpx
import pytest

from app.ai.contracts import AIProviderError
from app.ai.factory import create_provider, opencode_config
from app.ai.opencode import FREE_MODEL, OpenCodeClient
from app.core.config import Settings


def free_provider_payload():
    return {
        "all": [{
            "id": "opencode",
            "models": {
                FREE_MODEL: {
                    "id": FREE_MODEL,
                    "status": "active",
                    "cost": {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}},
                }
            },
        }]
    }


def completed_payload(text, *, cost=0, model=FREE_MODEL, parts=None):
    return {
        "info": {
            "role": "assistant", "providerID": "opencode", "modelID": model,
            "finish": "stop", "cost": cost, "time": {"completed": 1},
        },
        "parts": parts if parts is not None else [{"type": "text", "text": text}],
    }


def test_opencode_classifier_uses_only_free_model_and_validates_json():
    requests = []
    command = {
        "intent": "change_price", "sku": "A001", "new_price_vnd": 120000,
        "inventory_scope": None, "day": None, "low_stock_threshold": None,
        "query": None, "days": None,
    }

    def respond(request):
        requests.append(request)
        if request.url.path == "/provider":
            return httpx.Response(200, json=free_provider_payload())
        if request.url.path == "/session":
            payload = json.loads(request.content)
            assert payload["model"] == {"providerID": "opencode", "id": FREE_MODEL}
            assert payload["permission"] == [{"permission": "*", "pattern": "*", "action": "ask"}]
            return httpx.Response(200, json={"id": "ses_test"})
        if request.url.path == "/session/ses_test/message":
            payload = json.loads(request.content)
            assert payload["model"] == {"providerID": "opencode", "modelID": FREE_MODEL}
            assert payload["agent"] == "sellerpilot-classifier"
            return httpx.Response(200, json=completed_payload(json.dumps(command)))
        if request.url.path in ("/session/ses_test/abort", "/session/ses_test"):
            return httpx.Response(200, json=True)
        raise AssertionError(request.url.path)

    async def run():
        async with httpx.AsyncClient(
            base_url="http://opencode.test", transport=httpx.MockTransport(respond)
        ) as http:
            return await OpenCodeClient(http).classify(
                "Đổi giá SKU A001 thành 120k", today=date(2026, 10, 15)
            )

    result = asyncio.run(run())
    assert result.provider == "opencode"
    assert result.model == FREE_MODEL
    assert result.command.sku == "A001"
    assert result.command.new_price_vnd == 120000
    assert any(request.method == "DELETE" for request in requests)


@pytest.mark.parametrize("payload,reason", [
    (completed_payload("ok", cost=0.01), "invalid_response"),
    (completed_payload("ok", model="paid-model"), "invalid_response"),
    (completed_payload("", parts=[{"type": "tool", "tool": "bash"}]), "tool_not_allowed"),
])
def test_opencode_rejects_paid_wrong_model_and_tools(payload, reason):
    with pytest.raises(AIProviderError) as caught:
        OpenCodeClient._answer(payload)
    assert caught.value.reason == reason


def test_opencode_health_requires_active_zero_cost_model():
    paid = free_provider_payload()
    paid["all"][0]["models"][FREE_MODEL]["cost"]["output"] = 1

    def respond(request):
        if request.url.path == "/global/health":
            return httpx.Response(200, json={"healthy": True})
        return httpx.Response(200, json=paid)

    async def run():
        async with httpx.AsyncClient(
            base_url="http://opencode.test", transport=httpx.MockTransport(respond)
        ) as http:
            return await OpenCodeClient(http).check_health()

    result = asyncio.run(run())
    assert result.availability == "available"
    assert result.model_available is False


def test_opencode_config_disables_sharing_and_paid_fallback():
    config = opencode_config(FREE_MODEL)
    assert config["model"] == f"opencode/{FREE_MODEL}"
    assert config["small_model"] == f"opencode/{FREE_MODEL}"
    assert config["enabled_providers"] == ["opencode"]
    assert config["share"] == "disabled"
    assert config["autoupdate"] is False
    assert config["snapshot"] is False
    assert set(config["agent"]) == {"sellerpilot-classifier", "sellerpilot-chat", "sellerpilot-listing", "sellerpilot-advisor"}
    assert 'JSON' in config['agent']['sellerpilot-listing']['prompt']


def test_only_verified_free_model_can_be_constructed():
    with pytest.raises(ValueError):
        OpenCodeClient(None, "muse-spark-1.3")


def test_missing_opencode_binary_keeps_backend_provider_available_for_fallback():
    settings = Settings(
        _env_file=None, ai_provider="opencode",
        opencode_binary="sellerpilot-opencode-does-not-exist",
    )

    async def run():
        async with create_provider(settings) as provider:
            health = await provider.check_health()
            with pytest.raises(AIProviderError) as caught:
                await provider.classify("Tình hình shop", today=date(2026, 10, 15))
            return provider, health, caught.value.reason

    provider, health, reason = asyncio.run(run())
    assert provider.provider == "opencode"
    assert provider.model == FREE_MODEL
    assert health.availability == "unavailable"
    assert health.model_available is False
    assert reason == "provider_unavailable"


@pytest.mark.parametrize('vision', [True, False])
def test_listing_uses_dedicated_agent_and_attaches_images_only_when_supported(vision):
    sent = []
    image = {'type': 'file', 'mime': 'image/jpeg', 'url': 'data:image/jpeg;base64,/9j/'}

    def respond(request):
        if request.url.path == '/provider':
            payload = free_provider_payload()
            payload['all'][0]['models'][FREE_MODEL]['capabilities'] = {'input': {'image': vision}}
            return httpx.Response(200, json=payload)
        if request.url.path == '/session':
            return httpx.Response(200, json={'id': 'ses_listing'})
        if request.url.path == '/session/ses_listing/message':
            body = json.loads(request.content)
            sent.append(body)
            return httpx.Response(200, json=completed_payload('{"name":null}'))
        if request.url.path in ('/session/ses_listing/abort', '/session/ses_listing'):
            return httpx.Response(200, json=True)
        raise AssertionError(request.url.path)

    async def run():
        async with httpx.AsyncClient(base_url='http://opencode.test', transport=httpx.MockTransport(respond)) as http:
            return await OpenCodeClient(http).compose_listing(facts={'name': None}, history=[], images=[image])
    asyncio.run(run())
    assert sent[0]['agent'] == 'sellerpilot-listing'
    assert sent[0]['parts'][1:] == ([image] if vision else [])
    assert json.loads(sent[0]['parts'][0]['text'])['images_attached'] is vision


def test_cancelling_generation_aborts_and_deletes_only_its_opencode_session():
    async def run():
        started = asyncio.Event()
        calls = []

        async def respond(request):
            calls.append((request.method, request.url.path))
            if request.url.path == '/provider':
                return httpx.Response(200, json=free_provider_payload())
            if request.url.path == '/session':
                return httpx.Response(200, json={'id': 'ses_cancel_test'})
            if request.url.path == '/session/ses_cancel_test/message':
                started.set()
                await asyncio.Event().wait()
            if request.url.path in ('/session/ses_cancel_test/abort', '/session/ses_cancel_test'):
                return httpx.Response(200, json=True)
            raise AssertionError(request.url.path)

        async with httpx.AsyncClient(base_url='http://opencode.test', transport=httpx.MockTransport(respond)) as http:
            provider = OpenCodeClient(http)
            task = asyncio.create_task(provider.respond('Chào', history=[], facts={}))
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert ('POST', '/session/ses_cancel_test/abort') in calls
            assert ('DELETE', '/session/ses_cancel_test') in calls
            assert not provider._generation_lock.locked()

    asyncio.run(run())
