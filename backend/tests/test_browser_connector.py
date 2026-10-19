import copy
import asyncio
import json
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.ai.client import response_prompt
from app.ai.contracts import AIProviderError

TOKEN = 'qa-pairing-token-' + 'x' * 48
HEADERS = {'Authorization': 'Bearer ' + TOKEN, 'Origin': 'chrome-extension://' + 'a' * 32}


class BrowserAI:
    provider = 'gemini'
    model = 'qa-only'

    def __init__(self):
        self.facts = []
        self.error = None

    async def respond(self, message, *, history, facts):
        self.facts.append(copy.deepcopy(facts))
        if self.error:
            raise AIProviderError(self.error)
        return 'Mình chỉ thấy số liệu trên trang đang mở, chưa phải toàn shop.'

    async def compose_listing(self, *, facts, history, images):
        self.facts.append(copy.deepcopy(facts))
        return json.dumps({'name': 'Bàn phím trắng', 'description': 'Bàn phím màu trắng.',
                           'price_vnd': 500000, 'price_evidence': '5 xị',
                           'stock': 12, 'stock_evidence': '12 cái'}, ensure_ascii=False)


@pytest.fixture
def browser(client):
    client.app.state.settings.browser_connector_token = SecretStr(TOKEN)
    provider = BrowserAI()
    client.app.state.ai_provider = provider
    return client, provider


def payload(**updates):
    return {'request_id': str(uuid4()), 'connection_id': str(uuid4()),
            'message': 'Tư vấn kế hoạch cho shop', 'snapshot': {
                'url': 'https://banhang.shopee.vn/?is_from_login=true', 'title': 'Kênh Người Bán',
                'captured_at': datetime.now(timezone.utc).isoformat(), 'text': 'Đơn hàng hôm nay: 2'}, **updates}


def finish(client, request):
    result = client.post('/api/v1/browser-connector/requests', json=request, headers=HEADERS)
    assert result.status_code == 202, result.text
    path = '/api/v1/browser-connector/requests/' + request['connection_id'] + '/' + request['request_id']
    for _ in range(100):
        result = client.get(path, headers=HEADERS)
        assert result.status_code == 200
        if result.json()['data']['status'] != 'running':
            return result.json()['data']
        time.sleep(.005)
    pytest.fail('Inference job did not complete')


def test_disabled_and_pairing_auth_do_not_spend_tokens(client):
    assert client.get('/api/v1/browser-connector/health').status_code == 503
    client.app.state.settings.browser_connector_token = SecretStr(TOKEN)
    assert client.get('/api/v1/browser-connector/health').status_code == 401
    assert client.get('/api/v1/browser-connector/health', headers={**HEADERS, 'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/api/v1/browser-connector/health', headers=HEADERS).status_code == 200


def test_browser_chat_has_only_browser_facts_and_isolated_prompt(browser):
    client, provider = browser
    result = finish(client, payload())
    assert result['status'] == 'completed'
    assert result['result']['provider'] == 'gemini'
    assert provider.facts[0]['integration_mode'] == 'shopee_browser'
    assert provider.facts[0]['operations_executed'] == []
    assert 'today' not in provider.facts[0]
    assert 'UTech' not in response_prompt(provider.facts[0])
    assert 'chưa phải toàn bộ shop' in response_prompt(provider.facts[0])


@pytest.mark.parametrize('url', ['https://banhang.shopee.vn.evil.example/', 'http://banhang.shopee.vn/',
                                    'https://user:pass@banhang.shopee.vn/', 'https://shopee.vn/',
                                    'https://banhang.shopee.vn:443/', 'file:///tmp/shop'])
def test_wrong_origin_is_rejected(browser, url):
    client, provider = browser
    request = payload(); request['snapshot']['url'] = url
    assert client.post('/api/v1/browser-connector/requests', json=request, headers=HEADERS).status_code == 422
    assert provider.facts == []


def test_stale_snapshot_and_cross_connection_job_cannot_be_used(browser):
    client, _ = browser
    request = payload()
    request['snapshot']['captured_at'] = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    assert client.post('/api/v1/browser-connector/requests', json=request, headers=HEADERS).status_code == 422
    request = payload(); finish(client, request)
    assert client.get(f'/api/v1/browser-connector/requests/{uuid4()}/{request["request_id"]}', headers=HEADERS).status_code == 404
    assert client.post('/api/v1/browser-connector/requests', json=request, headers=HEADERS).status_code == 202
    request['message'] = 'Different content'
    assert client.post('/api/v1/browser-connector/requests', json=request, headers=HEADERS).status_code == 409


def test_listing_understands_slang_and_never_creates_shop_category(browser):
    client, _ = browser
    result = finish(client, payload(mode='listing', message='Bàn phím trắng bán 5 xị, còn 12 cái, đăng giúp mình.'))
    assert result['status'] == 'completed'
    assert result['result']['draft']['price_vnd'] == 500000
    assert result['result']['draft']['stock'] == 12
    assert result['result']['missing_fields'] == []
    assert 'category_id' not in result['result']['draft']


def test_unproven_price_and_stock_are_not_applied(browser):
    client, _ = browser
    result = finish(client, payload(mode='listing', message='Đây là bàn phím trắng.'))
    assert result['result']['draft']['price_vnd'] is None
    assert result['result']['draft']['stock'] is None
    assert set(result['result']['missing_fields']) == {'price_vnd', 'stock'}


def test_gateway_failure_reports_failure_instead_of_fabricated_data(browser):
    client, provider = browser
    provider.error = 'provider_rate_limited'
    result = finish(client, payload())
    assert result['status'] == 'failed'
    assert result['reason'] == 'provider_rate_limited'
    assert 'result' not in result


def test_invalid_image_is_rejected_before_vision_call(browser):
    client, provider = browser
    result = finish(client, payload(mode='listing', images=['data:image/png;base64,aGVsbG8=']))
    assert result['status'] == 'failed'
    assert provider.facts == []


def test_cancelling_running_inference_returns_no_answer_and_releases_capacity(browser):
    client, provider = browser

    async def slow(*_args, **_kwargs):
        await asyncio.sleep(60)
        return 'Should not be saved'

    provider.respond = slow
    requests = [payload() for _ in range(5)]
    for request in requests[:4]:
        assert client.post('/api/v1/browser-connector/requests', json=request, headers=HEADERS).status_code == 202
    assert client.post('/api/v1/browser-connector/requests', json=requests[4], headers=HEADERS).status_code == 429
    request = requests[0]
    path = f'/api/v1/browser-connector/requests/{request["connection_id"]}/{request["request_id"]}'
    assert client.post(path + '/cancel', headers=HEADERS).status_code == 200
    for _ in range(100):
        result = client.get(path, headers=HEADERS).json()['data']
        if result['status'] == 'cancelled':
            break
        time.sleep(.005)
    assert result == {'status': 'cancelled'}
    assert client.post('/api/v1/browser-connector/requests', json=requests[4], headers=HEADERS).status_code == 202
