import asyncio
import json

import httpx
import pytest

from app.ai.contracts import AIProviderError
from app.ai.gemini import GeminiClient, MODEL
from app.ai.key_pool import GeminiKeyPool
from test_gemini_client import completed


def test_pool_deduplicates_secrets_and_does_not_log_them():
    pool=GeminiKeyPool([('secret-a','project-a'),('secret-a','project-a'),('secret-b','project-b')])
    assert len(pool.credentials)==2
    assert 'secret-' not in repr(pool.credentials)
    with pytest.raises(ValueError,match='conflicting project'):
        GeminiKeyPool([('secret-a','project-a'),('secret-a','project-b')])


def test_unknown_project_ids_share_one_quota_instead_of_claiming_separate_buckets():
    pool=GeminiKeyPool([('key-a',''),('key-b','')],rpm=1)
    assert pool.available(reserve=True).slot==1
    assert pool.available(reserve=True) is None


def test_project_rate_limit_skips_other_keys_in_same_project_and_recovers(monkeypatch):
    clock=[100.0]
    monkeypatch.setattr('app.ai.key_pool.monotonic',lambda:clock[0])
    pool=GeminiKeyPool([('a','one'),('b','one'),('c','two')])
    first=pool.available(reserve=True)
    pool.rate_limited(first,120)
    assert pool.available(reserve=True).slot==3
    clock[0]=221
    assert pool.available(reserve=True).slot==1


def test_disabled_key_does_not_disable_a_valid_key_in_same_project():
    pool=GeminiKeyPool([('a','one'),('b','one')])
    pool.disable(pool.available(reserve=True))
    assert pool.available(reserve=True).slot==2


def test_live_request_rotation_and_project_cooldown_are_bounded(caplog):
    calls=[]
    def handler(request):
        key=request.headers['x-goog-api-key']
        calls.append(key)
        if key=='synthetic-a':
            return httpx.Response(429,headers={'retry-after':'120'})
        return httpx.Response(200,json=completed('Mình đã nhận dữ liệu shop.'))
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            p=GeminiClient(http,'',credentials=[('synthetic-a','same'),('synthetic-b','same'),('synthetic-c','other')])
            assert await p.respond('Tư vấn',history=[],facts={})=='Mình đã nhận dữ liệu shop.'
            assert p.response_provider=='gemini'
            await p.respond('Tư vấn tiếp',history=[],facts={})
    asyncio.run(run())
    assert calls==['synthetic-a','synthetic-c','synthetic-c']
    assert all(secret not in caplog.text for secret in calls)


def test_three_authorized_projects_rotate_successful_calls():
    calls=[]
    def handler(request):
        calls.append(request.headers['x-goog-api-key'])
        return httpx.Response(200,json=completed())
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            p=GeminiClient(http,'',credentials=[('a','one'),('b','two'),('c','three')])
            for _ in range(4):
                await p.respond('Tư vấn',history=[],facts={})
    asyncio.run(run())
    assert calls==['a','b','c','a']


@pytest.mark.parametrize('status,expected',[(401,['a','b']),(400,['a'])])
def test_auth_failure_moves_to_valid_key_but_bad_payload_does_not(status,expected):
    calls=[]
    def handler(request):
        key=request.headers['x-goog-api-key'];calls.append(key)
        return httpx.Response(status) if key=='a' else httpx.Response(200,json=completed())
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            p=GeminiClient(http,'',credentials=[('a','one'),('b','two')])
            if status==400:
                with pytest.raises(AIProviderError,match='provider_rejected'):
                    await p.respond('Tư vấn',history=[],facts={})
            else:
                await p.respond('Tư vấn',history=[],facts={})
    asyncio.run(run())
    assert calls==expected


def test_health_can_use_second_key_when_first_key_is_invalid():
    calls=[]
    def handler(request):
        key=request.headers['x-goog-api-key'];calls.append(key)
        return httpx.Response(401) if key=='a' else httpx.Response(200,json={
            'name':'models/'+MODEL,'supportedGenerationMethods':['generateContent']})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            p=GeminiClient(http,'',credentials=[('a','one'),('b','two')])
            assert (await p.check_health()).model_available
            assert (await p.check_health()).model_available
    asyncio.run(run())
    assert calls==['a','b']
