import asyncio
import base64
import json
from datetime import date

import httpx
import pytest

from app.ai.contracts import AIProviderError
from app.ai.gemini import GeminiClient, GroqBackup, MODEL, groq_strict_schema
from app.ai.advisor_contracts import AdvicePreparation
from app.ai.listing_contracts import ListingCopy
from app.ai.text import assistant_text
from app.core.config import Settings
from app.scripts.check_ai import synthetic_keyboard_png


def completed(text='Chào bạn. Mình có thể hỗ trợ shop hôm nay.'):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': text}]}}]}


def image():
    return {'mime':'image/png', 'url':'data:image/png;base64,' + base64.b64encode(synthetic_keyboard_png()).decode()}


def run_call(handler, call, *, key='synthetic-gemini-key', backup=False, model=MODEL):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            spare = GroqBackup(http, 'synthetic-groq-key') if backup else None
            return await call(GeminiClient(http, key, model, backup=spare))
    return asyncio.run(run())


def test_direct_chat_uses_header_and_plain_text_without_cli_or_tools():
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers['x-goog-api-key'] == 'synthetic-gemini-key'
        assert not request.url.query and 'synthetic-gemini-key' not in str(request.url)
        body = json.loads(request.content)
        assert 'tools' not in body and 'systemInstruction' in body
        assert body['generationConfig']['thinkingConfig']['thinkingLevel'] == 'MINIMAL'
        assert 'responseFormat' not in body['generationConfig']
        return httpx.Response(200, json=completed(json.dumps({'answer':'Còn 8 chiếc.\n\nBạn muốn xem SKU nào?'}, ensure_ascii=False)))
    answer = run_call(handler, lambda p:p.respond('Xem hàng', history=[], facts={'stock':8}))
    assert len(calls) == 1 and answer == 'Còn 8 chiếc.\n\nBạn muốn xem SKU nào?'


def test_missing_key_never_sends_a_request_or_silently_uses_backup():
    def handler(_request):
        raise AssertionError('No key must not send inference')
    async def call(provider):
        assert not (await provider.check_health()).model_available
        with pytest.raises(AIProviderError) as caught:
            await provider.respond('Xin chào', history=[], facts={})
        assert caught.value.stage == 'api_key_missing'
    run_call(handler, call, key='', backup=True)


def test_requested_product_rewrite_cannot_silently_return_empty_fields():
    calls=[]
    def handler(request):
        body=json.loads(request.content)
        payload=json.loads(body['contents'][0]['parts'][0]['text'])
        calls.append(payload)
        assert payload['fields_to_rewrite']==['name','description']
        return httpx.Response(200,json=completed('{}' if len(calls)==1 else
            json.dumps({'name':'Nova K75 màu trắng','description':'Bàn phím Nova K75 màu trắng.'})))
    result=run_call(handler,lambda p:p.compose_product_edit('Tối ưu tiêu đề và mô tả SKU A001',history=[],
        product={'name':'Bàn phím Nova K75 màu trắng','description':None}))
    assert len(calls)==2 and calls[1]['format_correction']
    assert result.name=='Nova K75 màu trắng'


def test_settings_keep_api_keys_out_of_repr():
    settings = Settings(_env_file=None, gemini_api_key='synthetic-secret-one', groq_api_key='synthetic-secret-two')
    assert 'synthetic-secret' not in repr(settings)


def test_six_inline_images_and_listing_schema_are_sent_in_one_request():
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        parts = body['contents'][0]['parts']
        assert len(parts) == 7
        assert all(p['inlineData']['mimeType'] == 'image/png' for p in parts[1:])
        assert all(base64.b64decode(p['inlineData']['data']) == synthetic_keyboard_png() for p in parts[1:])
        schema = body['generationConfig']['responseFormat']['text']
        assert schema['mimeType'] == 'APPLICATION_JSON' and 'name' in schema['schema']['properties']
        return httpx.Response(200, json=completed(json.dumps({'name':'Bàn phím máy tính',
            'description':'Bàn phím màu đen với các phím màu sáng.', 'category_id':4,
            'price_vnd':500000,'stock':8,'price_evidence':'5 xị','stock_evidence':'8 chiếc'})))
    result = run_call(handler, lambda p:p.compose_listing(
        facts={'current_message':'Bán 5 xị, kho 8 chiếc'}, history=[], images=[image()]*6))
    assert json.loads(result)['price_vnd'] == 500000 and len(calls) == 1


@pytest.mark.parametrize('images', [[image()]*7,
    [{'mime':'image/png','url':'https://example.test/product.png'}],
    [{'mime':'image/png','url':'data:image/png;base64,@@@'}],
    [{'mime':'image/png','url':'data:image/png;base64,YmFk'}]])
def test_invalid_images_fail_before_network_without_dropping_files(images):
    def handler(_request):
        raise AssertionError('Invalid gallery must not reach provider')
    async def call(p):
        with pytest.raises(AIProviderError):
            await p.compose_listing(facts={}, history=[], images=images)
    run_call(handler, call, backup=True)


@pytest.mark.parametrize('code,reason', [(400,'provider_rejected'),(401,'provider_rejected'),
    (403,'provider_rejected'),(404,'model_unavailable'),(429,'provider_rate_limited'),(503,'provider_unavailable')])
def test_http_errors_are_mapped_without_exposing_provider_body(code, reason):
    def handler(_request):
        return httpx.Response(code, json={'error':{'message':'PRIVATE provider details and key'}})
    async def call(p):
        with pytest.raises(AIProviderError) as caught:
            await p.respond('Câu hỏi', history=[], facts={})
        assert caught.value.reason == reason and 'PRIVATE' not in str(caught.value)
    run_call(handler, call)


@pytest.mark.parametrize('payload,reason', [
    ({'promptFeedback':{'blockReason':'SAFETY'}},'provider_rejected'),
    ({'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'partial'}]}}]},'invalid_response'),
    ({'candidates':[]},'invalid_response'),
    (completed(''),'invalid_response'),
    ({'candidates':[{'finishReason':'STOP','content':{'parts':[{'functionCall':{'name':'delete_all'}}]}}]},'tool_not_allowed'),
])
def test_blocked_partial_empty_and_tool_responses_never_reach_seller(payload, reason):
    def handler(request):
        assert request.url.host != 'api.groq.com'
        return httpx.Response(200, json=payload)
    async def call(p):
        with pytest.raises(AIProviderError) as caught:
            await p.respond('Câu hỏi', history=[], facts={})
        assert caught.value.reason == reason
    run_call(handler, call, backup=True)


def test_thought_parts_are_not_displayed():
    payload=completed('Câu trả lời cuối.')
    payload['candidates'][0]['content']['parts'].insert(0,{'thought':True,'text':'INTERNAL THOUGHT'})
    assert run_call(lambda _:httpx.Response(200,json=payload),
        lambda p:p.respond('Tư vấn',history=[],facts={})) == 'Câu trả lời cuối.'


def test_structured_correction_is_bounded_and_bad_sku_does_not_become_500():
    count=0
    def handler(request):
        nonlocal count
        count+=1
        if count==2:
            payload=json.loads(json.loads(request.content)['contents'][0]['parts'][0]['text'])
            assert payload['format_correction']
        return httpx.Response(200,json=completed('{"invalid": true}'))
    async def call(p):
        with pytest.raises(AIProviderError,match='invalid_response'):
            await p.classify('Đổi giá A001 thành 5 xị',today=date(2026,10,19))
    run_call(handler,call)
    assert count==2


@pytest.mark.parametrize('code',[429,503])
def test_transient_error_uses_one_configured_backup_and_records_actual_source(code):
    calls=[]
    def handler(request):
        calls.append(request.url.host)
        if request.url.host=='generativelanguage.googleapis.com':
            assert 'authorization' not in request.headers
            return httpx.Response(code)
        assert request.headers['authorization']=='Bearer synthetic-groq-key'
        assert 'x-goog-api-key' not in request.headers
        body=json.loads(request.content)
        assert body['model']=='qwen/qwen3.8-27b' and body['reasoning_effort']=='none'
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'Đề xuất từ dự phòng.'}}]})
    async def call(p):
        answer=await p.respond('Tư vấn',history=[],facts={})
        assert p.response_provider=='groq' and p.response_model=='qwen/qwen3.8-27b'
        return answer
    assert run_call(handler,call,backup=True)=='Đề xuất từ dự phòng.'
    assert calls==['generativelanguage.googleapis.com','api.groq.com']


def test_six_images_never_fail_over_to_a_three_image_model():
    calls=[]
    def handler(request):
        calls.append(request.url.host)
        return httpx.Response(429)
    async def call(p):
        with pytest.raises(AIProviderError,match='provider_rate_limited'):
            await p.compose_listing(facts={},history=[],images=[image()]*6)
    run_call(handler,call,backup=True)
    assert calls==['generativelanguage.googleapis.com']


def test_groq_schema_conversion_closes_nested_objects_without_changing_nullable_fields():
    original = AdvicePreparation.model_json_schema()
    snapshot = json.dumps(original, sort_keys=True)
    converted = groq_strict_schema(original)
    assert converted['required'] == ['extraction', 'answer']
    assert converted['additionalProperties'] is False
    extraction = converted['$defs']['AdviceExtraction']
    assert set(extraction['required']) == set(extraction['properties'])
    assert {'type': 'null'} in converted['properties']['answer']['anyOf']
    assert 'default' not in converted['properties']['answer']
    assert json.dumps(original, sort_keys=True) == snapshot


def test_groq_listing_uses_strict_fields_and_reasoning_without_losing_images():
    async def check():
        def handler(request):
            body = json.loads(request.content)
            assert body['reasoning_effort'] == 'low'
            contract = body['response_format']['json_schema']
            assert contract['strict'] is True
            assert set(contract['schema']['required']) == set(ListingCopy.model_fields)
            assert len(body['messages'][1]['content']) == 2
            assert body['messages'][1]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
            return httpx.Response(200, json={'choices':[{'finish_reason':'stop',
                'message':{'content':'{}'}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            backup = GroqBackup(http, 'synthetic-groq-key')
            await backup.generate('synthetic listing task', {},
                [{'inlineData': {'mimeType':'image/png','data':image()['url'].split(',')[1]}}],
                ListingCopy.model_json_schema(), timeout=20)
    asyncio.run(check())


def test_cooldown_honors_retry_after_without_sliding_forward_on_each_request(monkeypatch):
    clock=[100.0]
    monkeypatch.setattr('app.ai.gemini.monotonic',lambda:clock[0])
    monkeypatch.setattr('app.ai.key_pool.monotonic',lambda:clock[0])
    count=0
    def handler(_request):
        nonlocal count
        count+=1
        return httpx.Response(429,headers={'retry-after':'120'})
    async def call(p):
        for now in (100,110,219,221):
            clock[0]=now
            with pytest.raises(AIProviderError,match='provider_rate_limited'):
                await p.respond('Tư vấn',history=[],facts={})
    run_call(handler,call)
    assert count==2


def test_cached_health_and_selected_flash_reasoning_level():
    calls=[]
    def handler(request):
        calls.append(request.method)
        if request.method=='GET':
            return httpx.Response(200,json={'name':'models/gemini-3.8-flash','supportedGenerationMethods':['generateContent']})
        assert json.loads(request.content)['generationConfig']['thinkingConfig']['thinkingLevel']=='LOW'
        return httpx.Response(200,json=completed())
    async def call(p):
        assert (await p.check_health()).model_available
        assert (await p.check_health()).model_available
        await p.respond('Tư vấn',history=[],facts={})
    run_call(handler,call,model='gemini-3.8-flash')
    assert calls==['GET','POST']


@pytest.mark.parametrize('value,expected', [
    ('Văn bản có \\n giữ nguyên.','Văn bản có \\n giữ nguyên.'),
    ('{"answer":"Dòng 1.\\n\\nDòng 2."}','Dòng 1.\n\nDòng 2.'),
    ('```json\n{"answer":"Nội dung."}\n```','Nội dung.'),
    (json.dumps({'answer':json.dumps({'answer':'Nội dung.'})}),'Nội dung.'),
    ('{"answer":"Ví dụ", "stock":8}','{"answer":"Ví dụ", "stock":8}'),
    ('Ví dụ: {"answer":"Không phải toàn bộ câu trả lời"}','Ví dụ: {"answer":"Không phải toàn bộ câu trả lời"}'),
])
def test_answer_envelopes_are_decoded_without_corrupting_plain_text(value,expected):
    assert assistant_text(value)==expected


def test_api_chat_reports_groq_when_backup_writes_the_final_answer(client):
    def handler(request):
        if request.url.host=='generativelanguage.googleapis.com':
            return httpx.Response(503)
        prepared={'extraction':{'topic':'strategy'},'answer':'Đề xuất: rà soát các đơn đang chờ trước.'}
        return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':json.dumps(prepared)}}]})
    http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        client.app.state.ai_provider=GeminiClient(http,'synthetic-gemini-key',backup=GroqBackup(http,'synthetic-groq-key'))
        response=client.post('/api/v1/chat',json={'message':'Tư vấn việc cần ưu tiên hôm nay'})
        assert response.status_code==200,response.text
        data=response.json()['data']
        assert data['provider']=='groq' and data['model']=='qwen/qwen3.8-27b' and data['mode']=='ai'
        assert data['answer']=='Đề xuất: rà soát các đơn đang chờ trước.'
    finally:
        asyncio.run(http.aclose())


def test_gemini_health_uses_api_model_and_does_not_label_it_ollama(client):
    def handler(request):
        assert request.method=='GET'
        return httpx.Response(200,json={'name':'models/'+MODEL,'supportedGenerationMethods':['generateContent']})
    http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        client.app.state.settings.ai_provider='gemini'
        client.app.state.ai_provider=GeminiClient(http,'synthetic-key')
        data=client.get('/api/v1/health').json()['data']
        assert data['provider']=='gemini' and data['model']==MODEL
        assert data['status']=='ok' and data['ollama']=='unavailable'
    finally:
        asyncio.run(http.aclose())


def test_six_image_api_flow_asks_only_missing_stock_then_publishes_once(tmp_path):
    import sqlite3
    from test_product_drafts import make_client
    calls=[]
    def handler(request):
        body=json.loads(request.content)
        calls.append(body)
        assert len(body['contents'][0]['parts'])==7
        return httpx.Response(200,json=completed(json.dumps({
            'name':'Bàn phím máy tính','description':'Bàn phím máy tính màu đen với các phím màu sáng.',
            'category_id':4,'price_vnd':500000,'price_evidence':'5 xị','stock':None})))
    http=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    api,shop_path,uploads=make_client(tmp_path)
    try:
        with api:
            api.app.state.ai_provider=GeminiClient(http,'synthetic-key')
            png=base64.b64encode(synthetic_keyboard_png()).decode()
            upload=api.post('/api/v1/product-drafts/images-data',json={'images_base64':[png]*6})
            assert upload.status_code==201,upload.text
            conversation=upload.json()['data']['conversation_id']
            response=api.post('/api/v1/chat',json={'conversation_id':conversation,
                'message':'Đăng bàn phím từ bộ ảnh giúp mình, bán 5 xị. Tự viết tên và mô tả theo ảnh.'})
            assert response.status_code==200,response.text
            data=response.json()['data'];draft=data['product_draft']
            assert data['provider']=='gemini' and data['model']==MODEL
            assert draft['price_vnd']==500000 and draft['image_count']==6
            assert draft['missing_fields']==['stock'] and draft['status']=='collecting'
            with sqlite3.connect(shop_path) as db:
                assert db.execute('SELECT count(*) FROM product').fetchone()[0]==2
            response=api.post('/api/v1/chat',json={'conversation_id':conversation,'message':'Kho còn 12 chiếc nhé.'})
            assert response.status_code==200,response.text
            draft=response.json()['data']['product_draft']
            assert draft['status']=='ready' and draft['stock']==12 and draft['image_count']==6
            published=api.post(f"/api/v1/product-drafts/{draft['id']}/publish")
            assert published.status_code==200,published.text
            again=api.post(f"/api/v1/product-drafts/{draft['id']}/publish")
            assert published.json()['data']['published_product_id']==again.json()['data']['published_product_id']
            with sqlite3.connect(shop_path) as db:
                assert db.execute('SELECT count(*) FROM product').fetchone()[0]==3
                product_id=published.json()['data']['published_product_id']
                row=db.execute('SELECT image_url,extra_images,stock,price FROM product WHERE id=?',(product_id,)).fetchone()
                assert row[2:]==(12,500000.0)
                assert len(set([row[0],*json.loads(row[1])]))==6
            assert len(calls)==1
    finally:
        asyncio.run(http.aclose())


def test_cancel_direct_api_request_does_not_invoke_backup():
    async def run():
        started=asyncio.Event()
        async def handler(request):
            assert request.url.host=='generativelanguage.googleapis.com'
            started.set()
            await asyncio.Event().wait()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            p=GeminiClient(http,'synthetic-key',backup=GroqBackup(http,'synthetic-backup-key'))
            task=asyncio.create_task(p.respond('Tư vấn',history=[],facts={}))
            await asyncio.wait_for(started.wait(),2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
    asyncio.run(run())
