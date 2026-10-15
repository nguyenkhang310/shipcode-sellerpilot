import asyncio
import json
from datetime import date

import httpx
import pytest

from app.ai.client import OllamaClient
from app.ai.contracts import AIProviderError


def test_ollama_listing_uses_json_prompt_without_claiming_vision():
    captured = {}
    result_text = '{"name":"Bàn phím Nova", "description":"Bàn phím Nova hiện có tại shop.", "category_id":4, "clarification":null}'

    def respond(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={'done': True, 'message': {'content': result_text}})

    async def run():
        async with httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(respond)) as http:
            return await OllamaClient(http, 'qwen3:4b-instruct').compose_listing(
                facts={'name': 'Bàn phím Nova'}, history=[],
                images=[{'type': 'file', 'mime': 'image/jpeg', 'url': 'data:image/jpeg;base64,ignored'}],
            )

    assert asyncio.run(run()) == result_text
    assert captured['format'] == 'json'
    assert 'JSON' in captured['messages'][0]['content']
    assert json.loads(captured['messages'][1]['content'])['images_attached'] is False
    assert 'base64' not in captured['messages'][1]['content']


def test_ollama_classifier_uses_closed_schema_and_validates_result():
    captured = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        content = json.dumps({
            "intent": "change_price",
            "sku": "a001",
            "new_price_vnd": 120000,
            "inventory_scope": None,
            "day": None,
            "low_stock_threshold": None,
        })
        return httpx.Response(200, json={
            "model": "qwen3:4b-instruct",
            "message": {"role": "assistant", "content": content},
            "done": True,
        })

    async def run():
        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(respond),
        ) as http:
            provider = OllamaClient(http, "qwen3:4b-instruct")
            return await provider.classify(
                "Đổi giá SKU A001 thành 120k", today=date(2026, 10, 15)
            )

    result = asyncio.run(run())
    assert result.command.sku == "A001"
    assert result.command.new_price_vnd == 120000
    assert captured["stream"] is False
    assert captured["think"] is False
    assert captured["format"]["additionalProperties"] is False
    assert set(captured["format"]["required"]) == {
        "intent",
        "sku",
        "new_price_vnd",
        "inventory_scope",
        "day",
        "low_stock_threshold",
    }
    assert captured["options"] == {
        "temperature": 0,
        "num_ctx": 4096,
        "num_predict": 256,
    }
    assert captured["keep_alive"] == "30m"


@pytest.mark.parametrize("response_payload", [
    {"done": True, "message": {"content": "not-json"}},
    {"done": False, "message": {"content": "{}"}},
    {"done": True, "message": {"content": '{"intent":"delete_shop"}'}},
    [],
])
def test_ollama_classifier_rejects_invalid_output(response_payload):
    async def run():
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, json=response_payload)
        )
        async with httpx.AsyncClient(
            base_url="http://ollama.test", transport=transport
        ) as http:
            provider = OllamaClient(http, "qwen3:4b-instruct")
            return await provider.classify("test", today=date(2026, 10, 15))

    with pytest.raises(AIProviderError) as caught:
        asyncio.run(run())
    assert caught.value.reason == "invalid_response"


def test_ollama_classifier_maps_timeout_to_safe_fallback_reason():
    def timeout(_request):
        raise httpx.ReadTimeout("slow provider")

    async def run():
        async with httpx.AsyncClient(
            base_url="http://ollama.test",
            transport=httpx.MockTransport(timeout),
        ) as http:
            provider = OllamaClient(http, "qwen3:4b-instruct")
            return await provider.classify("test", today=date(2026, 10, 15))

    with pytest.raises(AIProviderError) as caught:
        asyncio.run(run())
    assert caught.value.reason == "provider_timeout"


@pytest.mark.parametrize("status_code,reason", [
    (404, "model_unavailable"),
    (503, "provider_unavailable"),
])
def test_ollama_classifier_maps_http_failures(status_code, reason):
    async def run():
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(status_code, json={"error": "hidden"})
        )
        async with httpx.AsyncClient(
            base_url="http://ollama.test", transport=transport
        ) as http:
            provider = OllamaClient(http, "qwen3:4b-instruct")
            return await provider.classify("test", today=date(2026, 10, 15))

    with pytest.raises(AIProviderError) as caught:
        asyncio.run(run())
    assert caught.value.reason == reason


def test_conversational_response_uses_history_facts_and_no_tools():
    captured = {}
    def respond(request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={'done': True, 'message': {'content': '<think>internal</think>Kho còn 3 sản phẩm.'}})
    async def run():
        async with httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(respond)) as http:
            return await OllamaClient(http, 'qwen3:4b-instruct').respond(
                'Nên nhập thêm không?', history=[{'role':'user','content':'Kiểm tra mã A001'}], facts={'sku':'A001','stock':3})
    assert asyncio.run(run()) == 'Kho còn 3 sản phẩm.'
    assert captured['messages'][1] == {'role':'user','content':'Kiểm tra mã A001'}
    assert '"stock": 3' in captured['messages'][-1]['content']
    assert 'tools' not in captured
    assert captured['stream'] is False
    assert captured['think'] is False


@pytest.mark.parametrize('payload', [
    {'done':False,'message':{'content':'partial'}},
    {'done':True,'message':{'content':''}},
    {'done':True,'message':{'content':'<think>internal only</think>'}},
    {'done':True,'message':{}},
])
def test_conversational_response_rejects_empty_or_incomplete_output(payload):
    async def run():
        async with httpx.AsyncClient(base_url='http://ollama.test', transport=httpx.MockTransport(lambda _: httpx.Response(200,json=payload))) as http:
            return await OllamaClient(http,'qwen3:4b-instruct').respond('hi',history=[],facts={})
    with pytest.raises(AIProviderError) as error:
        asyncio.run(run())
    assert error.value.reason == 'invalid_response'
