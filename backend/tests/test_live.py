"""Exercise authenticated Live connections without credentials or calls to Gemini."""
import asyncio
import base64
import json
import sqlite3
from threading import Event
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect
from uuid import uuid4
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosedError, InvalidStatus
from websockets.frames import Close
from websockets.http11 import Response

from app.api.v1.endpoints import live
from app.models.agent_run import AgentRun
from app.models.product_draft import ProductDraft
from app.services.advisor import forget_memory
from app.services.live_actions import LiveActions
from app.services.live_history import LiveHistory
from app.services.live_language import LIVE_GREETINGS, merge_transcript, spoken_listing_name, unclear_vietnamese
from app.services.live_shop import inspect_shop, strategy_summary
from app.services.product_drafts import publish_product_draft
from app.services.product_archive_chat import is_product_archive_request
from test_auth import secured, sign_in  # noqa: F401 - pytest fixture import
from test_listing_semantics import SemanticProvider


class GeminiFixture:
    def __init__(self, calls=None):
        self.sent = []
        self.events = asyncio.Queue()
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        pass

    async def recv(self):
        return '{"setupComplete":{}}'

    async def send(self, value):
        packet = json.loads(value)
        self.sent.append(packet)
        audio = packet.get('realtimeInput', {}).get('audio')
        if audio:
            await self.events.put(json.dumps({'toolCall': {'functionCalls': self.calls or [
                {'id': 'tool-1', 'name': 'publish_product', 'args': {}},
                {'id': 'tool-2', 'name': 'prepare_listing', 'args': {'name': 'Bàn phím', 'price_vnd': 500_000, 'stock': 0}},
                {'id': 'tool-3', 'name': 'prepare_listing', 'args': {'name': 'Sai giá', 'price_vnd': '500000'}},
            ]}}))
        if 'toolResponse' in packet:
            await self.events.put(json.dumps({'serverContent': {
                'outputTranscription': {'text': 'Mình đã chuẩn bị thông tin.'},
                'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': 'AAAAAA=='}}]},
                'generationComplete': True, 'turnComplete': True,
            }}))
        if packet.get('realtimeInput', {}).get('audioStreamEnd'):
            await self.events.put('{"serverContent":{"interrupted":true}}')

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.events.get()


def live_token(client):
    response = sign_in(client)
    assert response.status_code == 200
    return response.json()['data']['token']


@pytest.mark.parametrize('language', ['vi', 'en'])
def test_live_greeting_plays_once_per_connection_without_saving_a_chat_turn(secured, monkeypatch, language):
    client, _ = secured
    conversation_id = str(uuid4())

    class GreetingVoice(GeminiFixture):
        async def send(self, value):
            packet = json.loads(value)
            self.sent.append(packet)
            if 'text' in packet.get('realtimeInput', {}):
                await self.events.put(json.dumps({'serverContent': {
                    'outputTranscription': {'text': 'Greeting'},
                    'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm', 'data': 'AAABAA=='}}]},
                    'generationComplete': True, 'turnComplete': True,
                }}))

    upstream = GreetingVoice()
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: upstream)
    token = live_token(client)
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token, 'turn_protocol': 1,
                          'conversation_id': conversation_id, 'preferences': {'language': language}})
        ready = socket.receive_json()
        assert ready['greeting_count'] == len(set(LIVE_GREETINGS[language])) >= 4
        socket.send_json({'type': 'greet', 'variant': True})
        socket.send_json({'type': 'greet', 'variant': 2})
        socket.send_json({'type': 'greet', 'variant': 3})
        assert socket.receive_json() == {'type': 'audio', 'data': 'AAABAA=='}
        assert socket.receive_json() == {'type': 'audio_end'}
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'finished'
    texts = [packet['realtimeInput']['text'] for packet in upstream.sent if 'text' in packet.get('realtimeInput', {})]
    assert len(texts) == 1 and texts[0].endswith(LIVE_GREETINGS[language][2])
    assert client.get(f'/api/v1/conversations/{conversation_id}',
                      headers={'Authorization': f'Bearer {token}'}).status_code == 404


@pytest.mark.parametrize('speech, asked, expected', [
    ('Tiêu đề là HONDA Wave Alpha – Đỏ Đen 110cc.', False, ('HONDA Wave Alpha – Đỏ Đen 110cc', True)),
    ('HONDA Wave Alpha – Đỏ Đen 110cc.', True, ('HONDA Wave Alpha – Đỏ Đen 110cc', True)),
    ('Này là bán xe máy', True, ('xe máy', False)),
    ('Mình muốn đăng bán một chiếc xe máy', False, ('xe máy', False)),
    ('Xác nhận đăng', True, None),
])
def test_live_distinguishes_a_dictated_title_from_a_product_hint(speech, asked, expected):
    assert spoken_listing_name(speech, expecting_title=asked) == expected


def test_live_copy_choice_survives_reconnect_and_only_rewrites_after_acceptance(secured):
    client, _ = secured
    token = live_token(client)
    history = LiveHistory(client.app.state, token, uuid4(), 'fixture')
    events = []

    async def send(event):
        events.append(event)

    async def scenario(history):
        socket = SimpleNamespace(app=client.app, send_json=send)
        actions = LiveActions(socket, history)
        traffic = {'manual_turns': True, 'speech_finished': True, 'turn_signals': 1, 'awaiting_turn': True}
        history.user = 'Này là bán xe máy, giá 5 xị, tồn kho 20 cái.'
        result = await live.shop_tool(socket, token, 'prepare_listing', {'name': 'Tiêu đề AI đoán'}, history, actions, traffic)
        assert 'bắt mắt hơn' in result['answer'] and not events and not actions.load_draft()
        history.save(history.take())
        resumed = LiveHistory(client.app.state, token, history.conversation_id, 'fixture')
        resumed.initial_context()
        actions = LiveActions(socket, resumed)
        assert resumed.copy_subject == 'xe máy'
        resumed.user = 'Giữ nguyên.'
        await live.shop_tool(socket, token, 'prepare_listing', {}, resumed, actions, traffic)
        assert actions.load_draft()['name'] == 'xe máy'
        assert actions.load_draft()['description'] is None
        assert actions.load_draft()['price_vnd'] == 500000 and actions.load_draft()['stock'] == 20

        history = LiveHistory(client.app.state, token, uuid4(), 'fixture')
        actions = LiveActions(socket, history)
        history.user = 'Tiêu đề là HONDA Wave Alpha – Đỏ Đen 110cc.'
        result = await live.shop_tool(socket, token, 'prepare_listing', {'name': 'Tên khác'}, history, actions, traffic)
        assert result['accepted']
        assert actions.load_draft()['name'] == 'HONDA Wave Alpha – Đỏ Đen 110cc'

        client.app.state.ai_provider = SemanticProvider({
            'name': 'Xe máy màu đỏ', 'description': 'Xe máy màu đỏ do shop giới thiệu.',
        })
        history = LiveHistory(client.app.state, token, uuid4(), 'fixture')
        history.copy_subject = 'xe máy'
        actions = LiveActions(socket, history)
        history.user = 'Viết đẹp hơn nhé.'
        await live.shop_tool(socket, token, 'prepare_listing', {}, history, actions, traffic)
        assert actions.load_draft()['description']
        assert history.copy_subject is None

    asyncio.run(scenario(history))


def test_live_strategy_summary_points_to_the_written_plan():
    summary = strategy_summary({'mode': 'business_plan', 'execution': {
        'first_action': 'Kiểm tra tồn kho của món bán chạy nhất trước khi chạy ưu đãi.'}})
    assert 'Kiểm tra tồn kho' in summary and 'cuộc trò chuyện' in summary
    assert len(summary.split()) < 36


def test_live_generates_requested_title_and_waits_before_rewriting_dictated_description(secured):
    client, _ = secured
    token = live_token(client)
    history = LiveHistory(client.app.state, token, uuid4(), 'fixture')
    provider = client.app.state.ai_provider = SemanticProvider({
        'name': 'Bàn phím cơ màu đen Nova K75',
        'description': 'Bàn phím cơ màu đen kết nối qua cổng USB.',
    })

    async def scenario():
        async def send(_event):
            pass

        actions = LiveActions(SimpleNamespace(app=client.app, send_json=send), history)
        history.copy_subject = 'Bàn phím cơ Nova K75 màu đen'
        history.user = 'Bạn tự gợi ý tiêu đề cho hay.'
        await actions.listing_copy()
        draft = actions.load_draft()
        assert draft['name'] == provider.result['name'] and draft['description'] is None
        history.save(history.take())

        history.user = 'Mô tả là Bàn phím USB màu đen'
        answer = await actions.listing_copy()
        assert 'gợi ý mô tả bắt mắt hơn' in answer['answer'] and len(provider.calls) == 1
        assert actions.load_draft()['description'] == 'Bàn phím USB màu đen'
        history.save(history.take())

        history.user = 'Đồng ý'
        await actions.listing_copy()
        draft = actions.load_draft()
        assert draft['description'] == provider.result['description']
        assert draft['name'] == provider.result['name']
        assert len(provider.calls) == 2

    asyncio.run(scenario())


def test_goaway_drains_late_audio_and_saves_before_reopening_same_conversation(secured, monkeypatch):
    client, _ = secured
    token = live_token(client)
    conversation = str(uuid4())

    class TailAudio(GeminiFixture):
        async def send(self, value):
            packet = json.loads(value)
            self.sent.append(packet)
            if 'activityEnd' not in packet.get('realtimeInput', {}):
                return
            for event in (
                {'goAway': {'timeLeft': '20s'}},
                {'serverContent': {'inputTranscription': {'text': 'Chào bạn', 'finished': True},
                                   'generationComplete': True, 'turnComplete': True}},
            ):
                await self.events.put(json.dumps(event))
            await self.events.put(json.dumps({'serverContent': {
                'outputTranscription': {'text': 'Chào bạn nhé.'},
                'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm;rate=24000', 'data': 'AAAAAA=='}}]},
            }}))

    first, second = TailAudio(), TailAudio()
    connections = iter((first, second))
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: next(connections))
    auth = {'type': 'auth', 'token': token, 'conversation_id': conversation, 'turn_protocol': 1}
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json(auth)
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'speech_start'})
        socket.send_json({'type': 'audio', 'rate': 16000, 'data': 'AAA='})
        assert socket.receive_json()['type'] == 'audio_received'
        socket.send_json({'type': 'turn'})
        assert [socket.receive_json()['type'] for _ in range(7)] == [
            'transcript', 'transcript', 'audio', 'audio_end', 'turn_end', 'turn_saved', 'reconnecting',
        ]
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json(auth)
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'finished'
    assert 'Chào bạn nhé.' in json.dumps(second.sent[1], ensure_ascii=False)
    assert all('audio' not in event.get('realtimeInput', {}) for event in second.sent)

def test_live_speech_clarification_keeps_short_commerce_phrases_and_transcript_boundaries():
    assert unclear_vietnamese('Ế o que ế o cu de Hoàng Bá Đù?')
    assert not unclear_vietnamese('Cái áo kia năm xị, tồn kho hai cái')
    assert not unclear_vietnamese('Năm xị')
    assert not unclear_vietnamese('Mình nhờ Hoàng Bá Đù lấy đơn giúp')
    assert merge_transcript('Giá bán', 'Giá bán năm xị.') == 'Giá bán năm xị.'
    assert merge_transcript('Năm x', 'ị') == 'Năm xị'
    assert merge_transcript('cho mình xem biểu đồ', 'xem biểu đồ đơn hàng') == 'cho mình xem biểu đồ đơn hàng'
    assert merge_transcript('rất', ' rất đẹp') == 'rất rất đẹp'
    assert merge_transcript('Shop có ba đơn', 'Shop có') == 'Shop có ba đơn'


def test_manual_live_turn_waits_for_the_final_provider_transcription(secured, monkeypatch):
    client, _ = secured

    class DelayedTranscript(GeminiFixture):
        async def send(self, value):
            packet = json.loads(value)
            self.sent.append(packet)
            if 'activityEnd' in packet.get('realtimeInput', {}):
                for content in (
                    {'outputTranscription': {'text': 'Shop có'}},
                    {'turnComplete': True, 'interactionStatus': 'IN_PROGRESS'},
                    {'turnComplete': True},
                    {'inputTranscription': {'text': 'Shop có bao nhiêu'}},
                    {'outputTranscription': {'text': 'Shop có ba'},
                     'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm', 'data': 'AAM='}}]}},
                    {'generationComplete': True},
                    {'inputTranscription': {'text': 'Shop có bao nhiêu đơn?', 'finished': True}},
                    {'outputTranscription': {'text': ' đơn.'}},
                ):
                    await self.events.put(json.dumps({'serverContent': content}))
            if 'text' in packet.get('realtimeInput', {}):
                answer = packet['realtimeInput']['text'].split('nội dung khác. ', 1)[1]
                await self.events.put(json.dumps({'serverContent': {
                    'outputTranscription': {'text': answer, 'finished': True},
                    'generationComplete': True, 'turnComplete': True,
                }}))

    upstream = DelayedTranscript()
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: upstream)
    token = live_token(client)
    audio = {'type': 'audio', 'rate': 16000, 'data': 'AAA='}
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token, 'turn_protocol': 1})
        assert socket.receive_json()['turn_protocol'] == 1
        socket.send_json(audio)
        socket.send_json({'type': 'speech_start'})
        socket.send_json({'type': 'speech_start'})
        socket.send_json(audio)
        assert socket.receive_json()['type'] == 'audio_received'
        socket.send_json({'type': 'turn'})
        socket.send_json({'type': 'turn'})
        partial = socket.receive_json()
        assert partial['text'] == 'Shop có bao nhiêu'
        question = socket.receive_json()
        assert question['text'] == 'Shop có bao nhiêu đơn?'
        report = socket.receive_json()
        assert report['type'] == 'shop_result'
        assert report['report']['metrics'][1]['label'] == 'Đơn hợp lệ'
        answer = socket.receive_json()
        assert answer['text'] == report['spoken_summary']
        assert socket.receive_json()['type'] == 'audio_end'
        turn_end = socket.receive_json()
        assert turn_end['type'] == 'turn_end'
        saved = socket.receive_json()
        assert saved['type'] == 'turn_saved'
        facts = saved['turn']['response']['facts']
        assert {question['turn_id'], partial['turn_id'], answer['turn_id'], turn_end['turn_id']} == {facts['live_turn_id']}
        assert saved['turn']['response']['answer'] == answer['text']
        assert saved['turn']['message'] == question['text']
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'finished'
    setup = upstream.sent[0]['setup']['realtimeInputConfig']['automaticActivityDetection']
    assert setup == {'disabled': True}
    assert [next(iter(packet['realtimeInput'])) for packet in upstream.sent[1:]] == [
        'activityStart', 'audio', 'activityEnd', 'text',
    ]


def test_end_of_microphone_audio_does_not_authorize_a_partial_confirmation():
    speech = {'manual_turns': True, 'awaiting_turn': True, 'turn_signals': 2, 'review_turn': 1}
    assert not live.voice_finished(speech)
    assert live.voice_finished({**speech, 'speech_finished': True})
    assert not live.voice_finished({**speech, 'speech_finished': True, 'awaiting_turn': False})


def test_late_completion_cannot_close_the_next_turn_while_the_mic_is_active(secured, monkeypatch):
    client, _ = secured

    class DelayedCompletion(GeminiFixture):
        turns = 0

        async def send(self, raw):
            packet = json.loads(raw).get('realtimeInput', {})
            if 'activityStart' in packet and self.turns == 1:
                await self.events.put('{"serverContent":{"turnComplete":true}}')
            if 'activityEnd' in packet:
                self.turns += 1
                message = 'Hôm nay shop thế nào?' if self.turns == 1 else 'Còn hôm qua thì sao?'
                await self.events.put(json.dumps({'serverContent': {'inputTranscription': {
                    'text': message, 'finished': True,
                }}}))
            if 'text' in packet:
                await self.events.put(json.dumps({'serverContent': {
                    'modelTurn': {'parts': [{'inlineData': {'mimeType': 'audio/pcm', 'data': 'AAABAA=='}}]},
                    'generationComplete': True, 'turnComplete': True,
                }}))

    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: DelayedCompletion())
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': live_token(client), 'turn_protocol': 1})
        assert socket.receive_json()['type'] == 'ready'
        reports = []
        for index in range(2):
            socket.send_json({'type': 'speech_start'})
            if index:
                # More than the previous relay's completion tail, while the seller is still speaking.
                Event().wait(1.6)
            socket.send_json({'type': 'turn'})
            assert socket.receive_json()['role'] == 'user'
            reports.append(socket.receive_json())
            assert socket.receive_json()['type'] == 'audio'
            assert socket.receive_json()['type'] == 'audio_end'
            assert socket.receive_json()['type'] == 'turn_end'
            assert socket.receive_json()['type'] == 'turn_saved'
        assert reports[0]['sales_context']['to_date'] > reports[1]['sales_context']['to_date']
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'finished'


def test_local_product_archive_preview_is_scoped_versioned_and_preserves_orders(secured):
    client, path = secured
    token = live_token(client)
    headers = {'Authorization': 'Bearer ' + token}
    conversation_id = str(uuid4())
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO \"order\" (id,shop_id,total_amount,status,created_at) VALUES (77,1,1000000,'pending','2026-11-21')")
        db.execute('INSERT INTO order_item VALUES (1,77,1,1,1000000)')
        db.execute('CREATE TABLE cart_item(id INTEGER PRIMARY KEY, product_id INTEGER)')
        db.execute('INSERT INTO cart_item VALUES (1,1),(2,2)')
    url = '/api/v1/management/products/1'
    original = client.get(url, headers=headers).json()['data']
    assert is_product_archive_request('Xóa sản phẩm này giúp mình')
    for message in ('Có nên xóa sản phẩm này?', 'Đừng xóa sản phẩm', 'Xóa tất cả sản phẩm', 'Xóa SKU A và xóa SKU B'):
        assert not is_product_archive_request(message)
    preview = client.post('/api/v1/chat', headers=headers, json={'message': 'Xóa SKU SEED-PHONE',
        'conversation_id': conversation_id})
    assert preview.status_code == 200, preview.text
    proposal = preview.json()['data']['product_edit_proposal']
    assert proposal['action'] == 'archive' and proposal['status'] == 'pending'
    assert client.get(url, headers=headers).json()['data']['status'] == 'active'
    payload = {'expected_version': original['version'], 'request_id': str(uuid4())}
    assert client.post(url + '/archive', json=payload).status_code == 401
    response = client.post(url + '/archive', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['data']['status'] == 'archived'
    assert client.post(url + '/archive', headers=headers, json=payload).json()['data']['replayed']
    assert client.post(f"/api/v1/product-edits/{proposal['id']}/confirm", headers=headers).status_code == 409
    assert client.get('/api/v1/management/products?q=SEED-PHONE', headers=headers).json()['data']['items'] == []
    assert client.get('/api/v1/management/orders/77', headers=headers).status_code == 200
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT product_id,quantity,price FROM order_item').fetchone() == (1,1,1000000)
        assert db.execute('SELECT stock,is_active FROM product_variant WHERE product_id=1').fetchone() == (0,0)
        assert db.execute('SELECT product_id FROM cart_item').fetchall() == [(2,)]


def test_live_archive_only_uses_spoken_identity_and_a_new_confirmation(secured):
    client, _ = secured
    token = live_token(client)
    history = LiveHistory(client.app.state, token, uuid4(), 'fixture')
    sent = []

    async def send(event):
        sent.append(event)

    socket = SimpleNamespace(app=client.app, send_json=send)
    actions = LiveActions(socket, history)

    async def scenario():
        model_proposal = {'message': 'Xóa SKU SEED-LAPTOP'}
        history.user = 'Xóa SKU SEED-PHONE'
        traffic = {'manual_turns': True, 'awaiting_turn': True, 'turn_signals': 1}
        denied = await live.shop_tool(socket, token, 'prepare_chat_request', model_proposal, history, actions,
            {**traffic, 'awaiting_turn': False})
        assert not denied['accepted']
        review = await live.shop_tool(socket, token, 'prepare_chat_request', model_proposal, history, actions,
            {**traffic, 'speech_finished': True})
        assert review['accepted'] and actions.pending.value['sku'] == 'SEED-PHONE'
        assert sent[-1]['type'] == 'archive_review'
        assert not (await actions.decide('Xác nhận xóa sản phẩm.', finished=True))['accepted']
        actions.pending.armed = True
        assert not (await actions.decide('Xác nhận xóa sản phẩm?', finished=True))['accepted']
        assert (await actions.decide('Xác nhận xóa sản phẩm.', finished=True))['accepted']
        assert not (await actions.decide('Xác nhận xóa sản phẩm.', finished=True))['accepted']

    asyncio.run(scenario())
    headers = {'Authorization': 'Bearer ' + token}
    assert client.get('/api/v1/management/products/1', headers=headers).json()['data']['status'] == 'archived'
    assert client.get('/api/v1/management/products/2', headers=headers).json()['data']['status'] == 'active'


def test_live_keeps_the_spoken_answer_after_a_tool_phase_reports_completion(secured, monkeypatch):
    client, _ = secured

    class LateSpokenAnswer(GeminiFixture):
        async def send(self, raw):
            packet = json.loads(raw)
            if 'activityEnd' in packet.get('realtimeInput', {}):
                await self.events.put(json.dumps({'serverContent': {
                    'inputTranscription': {'text': 'Hôm nay shop có bao nhiêu đơn?', 'finished': True},
                }}))
                await self.events.put(json.dumps({'toolCall': {'functionCalls': [{
                    'id': 'read', 'name': 'inspect_shop', 'args': {'question': 'Hôm nay shop có bao nhiêu đơn?'},
                }]}}))
            if 'toolResponse' in packet:
                await self.events.put('{"serverContent":{"generationComplete":true}}')
                await self.events.put('{"serverContent":{"turnComplete":true}}')

                async def speak():
                    await asyncio.sleep(1.3)
                    for content in (
                        {'outputTranscription': {'text': 'Mình đã xem số liệu'}},
                        {'outputTranscription': {'text': ' của shop hôm nay.'}},
                        {'generationComplete': True},
                    ):
                        await self.events.put(json.dumps({'serverContent': content}))

                asyncio.create_task(speak())

    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: LateSpokenAnswer())
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': live_token(client), 'turn_protocol': 1})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'speech_start'})
        socket.send_json({'type': 'audio', 'rate': 16000, 'data': 'AAA='})
        assert socket.receive_json()['type'] == 'audio_received'
        socket.send_json({'type': 'turn'})
        question = socket.receive_json()
        report = socket.receive_json()
        assert report['type'] == 'shop_result'
        assert socket.receive_json()['role'] == 'assistant'
        answer = socket.receive_json()
        assert answer['text'] == 'Mình đã xem số liệu của shop hôm nay.'
        assert question['turn_id'] == answer['turn_id']
        assert socket.receive_json()['type'] == 'audio_end'
        assert socket.receive_json()['type'] == 'turn_end'
        saved = socket.receive_json()
        assert saved['type'] == 'turn_saved'
        assert saved['turn']['response']['answer'] == report['spoken_summary']
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'finished'


@pytest.mark.parametrize('projects, expected', [
    (('one', 'one', 'other'), ['fixture-key-a', 'fixture-key-c', 'fixture-key-c']),
    (('', '', ''), ['fixture-key-a', 'fixture-key-b', 'fixture-key-c']),
])
def test_live_rotates_on_quota_failures_with_or_without_project_ids(secured, monkeypatch, caplog, projects, expected):
    client, _ = secured
    settings = client.app.state.settings
    for suffix, letter, project in zip(('', '_2', '_3'), 'abc', projects):
        key = 'fixture-key-' + letter
        monkeypatch.setattr(settings, 'gemini_api_key' + suffix, SecretStr(key))
        monkeypatch.setattr(settings, 'gemini_project_id' + suffix, project)
    calls = []

    class SlowClose(GeminiFixture):
        async def __aexit__(self, *_):
            await asyncio.sleep(.05)

    def connect(_url, *, additional_headers, **_):
        key = additional_headers['x-goog-api-key']
        calls.append(key)
        if key == 'fixture-key-a':
            raise InvalidStatus(Response(429, 'Too Many Requests', Headers({'Retry-After': '120'})))
        return SlowClose()

    monkeypatch.setattr(live, 'connect', connect)
    token = live_token(client)
    for _ in range(2):
        with client.websocket_connect('/api/v1/live') as socket:
            socket.send_json({'type': 'auth', 'token': token, 'turn_protocol': 1})
            assert socket.receive_json()['type'] == 'ready'
            socket.send_json({'type': 'finish'})
            assert socket.receive_json()['type'] == 'finished'
    assert calls == expected
    assert not any(key in caplog.text for key in calls)


def test_live_rotates_when_a_key_is_rejected_during_websocket_setup(secured, monkeypatch):
    client, _ = secured
    settings = client.app.state.settings
    monkeypatch.setattr(settings, 'gemini_api_key', SecretStr('fixture-invalid'))
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('fixture-valid'))
    calls = []

    class Rejected(GeminiFixture):
        async def recv(self):
            raise ConnectionClosedError(Close(1008, 'API key not valid. Please pass a valid API key.'), None)

    def connect(_url, *, additional_headers, **_):
        key = additional_headers['x-goog-api-key']
        calls.append(key)
        return Rejected() if key == 'fixture-invalid' else GeminiFixture()

    monkeypatch.setattr(live, 'connect', connect)
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': live_token(client), 'turn_protocol': 1})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'finished'
    assert calls == ['fixture-invalid', 'fixture-valid']


def test_live_does_not_replay_an_active_conversation_on_another_key(secured, monkeypatch):
    client, _ = secured
    settings = client.app.state.settings
    monkeypatch.setattr(settings, 'gemini_api_key', SecretStr('fixture-key-a'))
    monkeypatch.setattr(settings, 'gemini_api_key_2', SecretStr('fixture-key-b'))
    monkeypatch.setattr(settings, 'gemini_project_id', 'one')
    monkeypatch.setattr(settings, 'gemini_project_id_2', 'other')
    calls = []

    class EndedByQuota(GeminiFixture):
        async def send(self, raw):
            if 'audio' in json.loads(raw).get('realtimeInput', {}):
                await self.events.put(json.dumps({'error': {'status': 'RESOURCE_EXHAUSTED'}}))

    def connect(_url, *, additional_headers, **_):
        key = additional_headers['x-goog-api-key']
        calls.append(key)
        return EndedByQuota() if key == 'fixture-key-a' else GeminiFixture()

    monkeypatch.setattr(live, 'connect', connect)
    token = live_token(client)
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'audio', 'rate': 16000, 'data': 'AAA='})
        assert socket.receive_json()['type'] == 'audio_received'
        assert 'giới hạn' in socket.receive_json()['message']
        assert calls == ['fixture-key-a']
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token, 'turn_protocol': 1})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'finished'
    assert calls == ['fixture-key-a', 'fixture-key-b']


def test_live_english_voice_and_transcription_are_applied_to_the_same_session(secured, monkeypatch):
    client, _ = secured
    upstream = GeminiFixture()
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: upstream)
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': live_token(client),
                          'preferences': {'language': 'en', 'voice': 'female'}})
        assert socket.receive_json()['type'] == 'ready'
        setup = upstream.sent[0]['setup']
        assert setup['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'] == 'Kore'
        assert setup['inputAudioTranscription']['languageCodes'] == ['en-US']
        assert 'confirm publish' in setup['systemInstruction']['parts'][0]['text']
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'interrupted'
        assert socket.receive_json()['type'] == 'finished'


def test_live_asks_to_repeat_an_unclear_turn_before_using_listing_tools(secured, monkeypatch):
    client, _ = secured

    class UnclearInput(GeminiFixture):
        async def send(self, value):
            packet = json.loads(value)
            if packet.get('realtimeInput', {}).get('audio'):
                await self.events.put(json.dumps({'serverContent': {'inputTranscription': {
                    'text': 'Ế o que ế o cu de Hoàng Bá Đù?', 'finished': True,
                }}}))
            if packet.get('realtimeInput', {}).get('text'):
                self.sent.append(packet)
                return
            await super().send(value)

    upstream = UnclearInput()
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: upstream)
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': live_token(client)})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'audio', 'rate': 16000, 'data': 'AAA='})
        assert socket.receive_json()['type'] == 'audio_received'
        assert socket.receive_json()['type'] == 'interrupted'
        marker = socket.receive_json()
        assert marker['unclear'] and marker['text'] == 'Lời nói chưa rõ'
        while (saved := socket.receive_json())['type'] != 'turn_saved':
            assert saved['type'] in ('audio_end', 'turn_end')
        assert 'nói lại' in saved['turn']['response']['answer']
        assert saved['turn']['response']['product_draft'] is None
        tool = next(packet for packet in upstream.sent if 'toolResponse' in packet)
        assert not any(reply['response']['accepted'] for reply in tool['toolResponse']['functionResponses'])


def test_live_report_uses_the_spoken_period(secured):
    client, _ = secured
    state = client.app.state
    with state.session_factory() as session:
        result = inspect_shop(session, state.shop_repository,
            'Vẽ biểu đồ giá trị đơn hàng 30 ngày qua',
            'Hôm nay shop có bao nhiêu đơn và tổng giá trị đơn hàng là bao nhiêu?')
    assert result['facts']['days'] == 1
    assert ' → ' not in result['report']['subtitle']


def test_live_report_preserves_spoken_seven_days_followed_by_chart_request(secured):
    client, _ = secured
    state = client.app.state
    with state.session_factory() as session:
        result = inspect_shop(session, state.shop_repository, 'Doanh thu hôm nay',
            'Bảy ngày qua shop có bao nhiêu đơn hàng và tổng giá trị đơn là bao nhiêu? Bạn cho mình xem biểu đồ nhé.')
    assert result['facts']['days'] == 7
    assert len(result['report']['charts'][0]['points']) == 7


def test_live_report_uses_the_spoken_inventory_threshold(secured):
    client, _ = secured
    state = client.app.state
    with state.session_factory() as session:
        result = inspect_shop(session, state.shop_repository,
            'Hàng sắp hết', 'Sản phẩm nào còn dưới ba cái?')
    assert result['facts']['threshold'] == 2
    assert result['report']['subtitle'] == 'Tồn kho không quá 2'


@pytest.mark.parametrize('language,gender,expected', [
    ('vi', 'male', 'Iapetus'), ('vi', 'female', 'Erinome'), ('en', 'male', 'Puck'), ('en', 'female', 'Kore'),
])
def test_live_voice_preferences_reach_gemini_and_idle_finish(secured, monkeypatch, language, gender, expected):
    client, _ = secured
    token = live_token(client)
    upstream = GeminiFixture()
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: upstream)
    with client.websocket_connect('/api/v1/live', headers={'Origin': 'http://localhost:8081'}) as socket:
        socket.send_json({'type': 'auth', 'token': token, 'turn_protocol': 1,
                          'preferences': {'language': language, 'voice': gender}})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'finished'
        assert len(upstream.sent) == 1
        assert upstream.sent[0]['setup']['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'] == expected


def test_cancel_before_gemini_ready_releases_the_connection(secured, monkeypatch):
    client, _ = secured
    token = live_token(client)
    starting, cancelled = Event(), Event()

    class DelayedGemini(GeminiFixture):
        async def recv(self):
            starting.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

    connections = iter((DelayedGemini(), GeminiFixture()))
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: next(connections))
    auth = {'type': 'auth', 'token': token, 'turn_protocol': 1}
    headers = {'Origin': 'http://localhost:8081'}
    with client.websocket_connect('/api/v1/live', headers=headers) as socket:
        socket.send_json(auth)
        assert starting.wait(2)
        socket.close()
        assert cancelled.wait(2)
    with client.websocket_connect('/api/v1/live', headers=headers) as socket:
        socket.send_json(auth)
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'finished'


def test_voice_relays_audio_and_saves_a_real_draft(secured, monkeypatch):
    client, _ = secured
    token = live_token(client)
    upstream = GeminiFixture()
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))

    def connect(url, *, additional_headers, **_):
        assert url == live.GEMINI_LIVE_URL
        assert additional_headers == {'x-goog-api-key': 'fixture-key'}
        return upstream

    monkeypatch.setattr(live, 'connect', connect)
    with client.websocket_connect('/api/v1/live', headers={'Origin': 'http://localhost:8081'}) as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'audio', 'rate': 16000, 'data': base64.b64encode(bytes(1280)).decode()})
        assert socket.receive_json()['type'] == 'audio_received'
        event = socket.receive_json()
        assert event['type'] == 'draft'
        assert event['draft']['name'] == 'Bàn phím'
        assert event['draft']['price_vnd'] == 500_000 and event['draft']['stock'] == 0
        assert socket.receive_json()['type'] == 'transcript'
        assert socket.receive_json() == {'type': 'audio', 'data': 'AAAAAA=='}
        assert socket.receive_json()['type'] == 'audio_end'
        assert socket.receive_json()['type'] == 'turn_end'
        assert socket.receive_json()['type'] == 'turn_saved'
        socket.send_json({'type': 'turn'})
        assert socket.receive_json()['type'] == 'interrupted'
        socket.send_json({'toolResponse': {'functionResponses': []}})
        assert socket.receive_json()['type'] == 'error'

    allowed = upstream.sent[0]['setup']['tools'][0]['functionDeclarations']
    assert {tool['name'] for tool in allowed} == {'prepare_listing', 'inspect_shop', 'prepare_chat_request',
                                                'prepare_order', 'confirm_action'}
    assert upstream.sent[1]['realtimeInput']['audio']['mimeType'] == 'audio/pcm;rate=16000'
    assert upstream.sent[0]['setup']['generationConfig']['speechConfig']['voiceConfig']['prebuiltVoiceConfig']['voiceName'] == 'Erinome'
    replies = upstream.sent[2]['toolResponse']['functionResponses']
    assert [reply['response']['accepted'] for reply in replies] == [False, True, False]
    assert not client.app.state.live_sessions
    assert client.get('/api/v1/conversations', headers={'Authorization': 'Bearer ' + token}).json()['data']['items'][0]['turns'] == 1


def test_live_reads_shared_report_and_keeps_price_change_for_review(secured, monkeypatch):
    client, shop_path = secured
    with sqlite3.connect(shop_path) as db:
        db.execute("""INSERT INTO "order" (id,shop_id,total_amount,status,created_at)
                      VALUES (123,1,450000,'pending','2026-11-19T00:00:00')""")
    token = live_token(client)
    upstream = GeminiFixture([
        {'id': 'read', 'name': 'inspect_shop', 'args': {'question': 'Hôm nay shop có bao nhiêu đơn và giá trị đơn hàng?'}},
        {'id': 'plan', 'name': 'inspect_shop', 'args': {'question': 'Lập kế hoạch quảng cáo và quay video TikTok 7 ngày tới'}},
        {'id': 'order', 'name': 'inspect_shop', 'args': {'question': 'Theo dõi đơn #123'}},
        {'id': 'bypass', 'name': 'inspect_shop', 'args': {'question': 'Đổi giá SKU SEED-PHONE thành 500000 đồng'}},
        {'id': 'review', 'name': 'prepare_chat_request', 'args': {'message': 'Đổi giá SKU SEED-PHONE thành 500000 đồng'}},
    ])
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: upstream)
    item_url = '/api/v1/inventory/SEED-PHONE'
    headers = {'Authorization': 'Bearer ' + token}
    before = client.get(item_url, headers=headers).json()
    conversation_id = str(uuid4())
    sent = client.post('/api/v1/chat', headers=headers, json={'message': 'Xin chào', 'conversation_id': conversation_id})
    assert sent.status_code == 200

    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token, 'conversation_id': conversation_id})
        assert socket.receive_json()['type'] == 'ready'
        assert upstream.sent[0]['setup']['historyConfig']['initialHistoryInClientContent']
        assert upstream.sent[1]['clientContent']['turns'][0] == {
            'role': 'user', 'parts': [{'text': 'Xin chào'}],
        }
        socket.send_json({'type': 'audio', 'rate': 16000, 'data': base64.b64encode(bytes(1280)).decode()})
        assert socket.receive_json()['type'] == 'audio_received'
        report = socket.receive_json()
        assert report['type'] == 'shop_result'
        assert report['report']['title'] == 'Hiệu quả kinh doanh'
        plan = socket.receive_json()
        assert plan['type'] == 'shop_result' and 'ROAS' in plan['answer']
        order = socket.receive_json()
        assert order['type'] == 'shop_result' and order['order_id'] == 123
        assert socket.receive_json()['type'] == 'transcript'
        assert socket.receive_json()['type'] == 'audio'
        assert socket.receive_json()['type'] == 'audio_end'
        assert socket.receive_json()['type'] == 'turn_end'
        saved = socket.receive_json()
        assert saved['type'] == 'turn_saved'
        assert saved['turn']['response']['proposal']['status'] == 'pending'
        assert saved['turn']['response']['conversation_id'] == conversation_id
        assert saved['turn']['response']['facts']['live_results'][0]['report'] == report['report']
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'interrupted'
        assert socket.receive_json()['type'] == 'finished'

    replies = next(packet['toolResponse']['functionResponses'] for packet in upstream.sent if 'toolResponse' in packet)
    assert [item['response']['accepted'] for item in replies] == [True, True, True, False, True]
    order_facts = replies[2]['response']['facts']['order_lookup'][0]
    assert order_facts['id'] == 123 and 'tracking_number' not in order_facts
    assert client.get(item_url, headers=headers).json() == before
    listing = client.get('/api/v1/conversations', headers=headers).json()['data']['items']
    assert len(listing) == 1 and listing[0]['turns'] == 2
    restored = client.get('/api/v1/conversations/' + conversation_id, headers=headers).json()['data']['turns']
    assert restored[-1] == saved['turn']


def test_ending_live_preserves_unanswered_speech_and_final_snapshot(secured, monkeypatch):
    client, _ = secured
    token = live_token(client)

    class PendingSpeech(GeminiFixture):
        async def send(self, value):
            block = json.loads(value).get('realtimeInput', {})
            for key, text, finished in [('audio', 'Hôm nay', False), ('audioStreamEnd', 'Hôm nay shop thế nào?', True)]:
                if key in block:
                    await self.events.put(json.dumps({'serverContent': {
                        'inputTranscription': {'text': text, 'finished': finished}
                    }}))

    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: PendingSpeech())
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'audio', 'rate': 16000, 'data': 'AAA='})
        assert socket.receive_json()['type'] == 'audio_received'
        assert socket.receive_json()['text'] == 'Hôm nay'
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['final'] is True
        saved = socket.receive_json()
        assert saved['type'] == 'turn_saved'
        assert saved['turn']['message'] == 'Hôm nay shop thế nào?'
        assert socket.receive_json()['type'] == 'finished'

    history_id = saved['turn']['response']['conversation_id']
    assert client.get('/api/v1/conversations/' + history_id, headers={'Authorization': 'Bearer ' + token}).json()['data']['turns'] == [saved['turn']]


def test_empty_live_closes_without_creating_a_conversation(secured, monkeypatch):
    client, _ = secured
    token = live_token(client)
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: GeminiFixture())
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'finish'})
        assert socket.receive_json()['type'] == 'interrupted'
        assert socket.receive_json()['type'] == 'finished'
    assert client.get('/api/v1/conversations', headers={'Authorization': 'Bearer ' + token}).json()['data']['items'] == []


def test_live_accepts_jpeg_frames_and_keeps_session_open_on_invalid_image(secured, monkeypatch):
    client, _ = secured
    token = live_token(client)
    upstream = GeminiFixture()
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: upstream)
    frame = base64.b64encode(bytes.fromhex('ffd8ffe00001ffd9')).decode()

    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'image', 'data': 'not an image'})
        assert socket.receive_json()['type'] == 'image_rejected'
        socket.send_json({'type': 'image', 'data': frame})
        assert socket.receive_json()['type'] == 'image_sent'
        socket.send_json({'type': 'image', 'data': frame})
        assert socket.receive_json()['type'] == 'image_rejected'
        socket.send_json({'type': 'mute'})
        assert socket.receive_json()['type'] == 'interrupted'

    assert upstream.sent[1] == {'realtimeInput': {'video': {'mimeType': 'image/jpeg', 'data': frame}}}
    assert len(upstream.sent) == 3


def test_live_blocks_foreign_origin_revoked_session_and_missing_key(secured, monkeypatch):
    client, _ = secured
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr(''))
    with pytest.raises(WebSocketDisconnect) as disconnected:
        with client.websocket_connect('/api/v1/live', headers={'Origin': 'https://foreign.example'}):
            pass
    assert disconnected.value.code == 1008

    token = live_token(client)
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert 'GEMINI_API_KEY' in socket.receive_json()['message']

    assert client.post('/api/v1/auth/logout', headers={'Authorization': 'Bearer ' + token}).status_code == 200
    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token})
        assert 'hết hạn' in socket.receive_json()['message']
    assert not client.app.state.live_sessions


def test_live_gallery_and_confirmation_publish_once_in_the_same_session(secured, monkeypatch):
    client, shop_path = secured
    token = live_token(client)
    headers = {'Authorization': 'Bearer ' + token}
    conversation_id = str(uuid4())
    details = {'name': 'Bàn phím cơ nhỏ gọn', 'price_vnd': 500_000, 'stock': 0,
               'category': 'Máy Tính & Laptop', 'description': 'Bàn phím cơ bố cục nhỏ gọn màu đen.'}
    steps = iter([
        ('Tiêu đề là Bàn phím cơ nhỏ gọn, giá bán 500000 đồng, tồn kho 0 cái, '
         'ngành Máy Tính & Laptop, mô tả Bàn phím cơ bố cục nhỏ gọn màu đen.',
         [{'name': 'prepare_listing', 'args': details}]),
        ('Không xác nhận đăng.', [{'name': 'confirm_action'}]),
        ('Xác nhận đăng.', [{'name': 'confirm_action'}, {'name': 'confirm_action'}]),
        ('Sản phẩm này làm sao để bán tốt và tăng doanh số?', [
            {'name': 'prepare_chat_request', 'args': {'message': 'Tư vấn bán SKU SEED-LAPTOP'}},
        ]),
        ('Món vừa đăng thì quay video sao để ra đơn?', []),
    ])

    class VoiceSeller(GeminiFixture):
        async def send(self, value):
            packet = json.loads(value)
            realtime = packet.get('realtimeInput', {})
            if 'audio' in realtime:
                self.sent.append(packet)
                return
            if realtime.get('audioStreamEnd'):
                self.sent.append(packet)
                try:
                    spoken, calls = next(steps)
                except StopIteration:
                    return
                await self.events.put(json.dumps({'serverContent': {
                    'inputTranscription': {'text': spoken, 'finished': True},
                }}))
                if not calls:
                    await self.events.put(json.dumps({'serverContent': {
                        'outputTranscription': {'text': 'Thử quay một video dùng thử.'},
                        'generationComplete': True, 'turnComplete': True,
                    }}))
                    return
                await self.events.put(json.dumps({'toolCall': {'functionCalls': [
                    {'id': str(index), **call} for index, call in enumerate(calls)
                ]}}))
                return
            if 'text' in realtime:
                assert 'vừa chọn ảnh' in realtime['text']
                await self.events.put(json.dumps({'serverContent': {
                    'outputTranscription': {'text': 'Mình đã nhận ảnh. Bạn nói xác nhận đăng nhé.'},
                    'generationComplete': True, 'turnComplete': True,
                }}))
                return
            await super().send(value)

    upstream = VoiceSeller()
    monkeypatch.setattr(client.app.state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    monkeypatch.setattr(live, 'connect', lambda *_, **__: upstream)

    def events_until(socket, event_type):
        events = []
        for _ in range(12):
            event = socket.receive_json()
            events.append(event)
            if event['type'] == event_type:
                return events
        pytest.fail(f'Missing {event_type}: {events}')

    with client.websocket_connect('/api/v1/live') as socket:
        socket.send_json({'type': 'auth', 'token': token, 'conversation_id': conversation_id})
        assert socket.receive_json()['type'] == 'ready'
        socket.send_json({'type': 'audio', 'rate': 16000, 'data': 'AAA='})
        assert socket.receive_json()['type'] == 'audio_received'
        socket.send_json({'type': 'turn'})
        draft = next(event['draft'] for event in events_until(socket, 'turn_end') if event['type'] == 'draft')
        assert socket.receive_json()['type'] == 'turn_saved'
        assert draft['status'] == 'collecting' and draft['missing_fields'] == ['image']
        assert 'Thêm ảnh' in upstream.sent[-1]['toolResponse']['functionResponses'][0]['response']['instruction']
        # The app saves the selected photo through the same upload as chat.
        upload = client.post('/api/v1/product-drafts/images-data', headers=headers, json={
            'conversation_id': conversation_id,
            'images_base64': [base64.b64encode(bytes.fromhex(f'ffd8ffe000{number:02x}ffd9')).decode()
                              for number in range(6)],
        })
        assert upload.status_code == 201, upload.text
        receipt = upload.json()['data']
        assert receipt['product_draft']['status'] == 'ready'
        socket.send_json({'type': 'images_added', 'draft_id': draft['id'], 'run_id': receipt['run_id']})
        events = events_until(socket, 'turn_end')
        assert events[0]['draft']['image_count'] == 6
        assert sum('video' in event.get('realtimeInput', {}) for event in upstream.sent) == 6

        socket.send_json({'type': 'turn'})
        assert not any(event['type'] == 'action_done' for event in events_until(socket, 'turn_end'))
        rejected = upstream.sent[-1]['toolResponse']['functionResponses'][0]['response']
        assert rejected['accepted'] is False
        assert socket.receive_json()['type'] == 'turn_saved'

        socket.send_json({'type': 'turn'})
        events = events_until(socket, 'turn_saved')
        published = next(event['draft'] for event in events if event['type'] == 'action_done')
        assert published['status'] == 'published' and published['stock'] == 0
        assert sum(event['type'] == 'action_done' for event in events) == 1
        socket.send_json({'type': 'turn'})
        events = events_until(socket, 'turn_saved')
        result = next(event for event in events if event['type'] == 'shop_result')
        assert published['name'] in result['answer']
        assert 'SEED-LAPTOP' not in result['answer']
        advice = upstream.sent[-1]['toolResponse']['functionResponses'][0]['response']
        assert advice['facts']['business_advisory']['focus_product']['sku'] == published['sku']
        socket.send_json({'type': 'turn'})
        events = events_until(socket, 'turn_saved')
        assert sum(event['type'] == 'shop_result' for event in events) == 1
        assert published['name'] in events[-1]['turn']['response']['answer']
        socket.send_json({'type': 'finish'})
        events_until(socket, 'finished')

    with sqlite3.connect(shop_path) as db:
        assert db.execute('SELECT COUNT(*) FROM product WHERE sku=?', (published['sku'],)).fetchone() == (1,)
    history = client.get(f'/api/v1/conversations/{conversation_id}', headers=headers).json()['data']['turns']
    assert history[-3]['message'] == 'Xác nhận đăng.'
    assert history[-3]['response']['product_draft']['status'] == 'published'
    assert history[-1]['response']['facts']['live_product_selection']['selected_product']['sku'] == published['sku']


def test_chat_and_reopened_live_find_a_published_product_beyond_recent_turns(secured, monkeypatch):
    client, shop_path = secured
    state = client.app.state
    token = live_token(client)
    headers = {'Authorization': 'Bearer ' + token}
    conversation = str(uuid4())
    name, sku = 'Bàn phím cơ Sao Khuê', 'FIXTURE-SAO-KHUE'
    with state.session_factory() as session:
        draft = ProductDraft(conversation_id=conversation, shop_slug='utech-official', status='ready',
            name=name, description='Bàn phím cơ màu đen.', category_id=4, category_name='Máy Tính & Laptop',
            price_vnd=500_000, stock=9, sku=sku, image_filename='test.jpg', image_url='/static/test.jpg',
            image_mime='image/jpeg', image_bytes=10)
        session.add(draft)
        session.commit()
        published = publish_product_draft(session, state.shop_repository, draft.id)
        assert published.published_product_id
        session.add_all([
            AgentRun(conversation_id=conversation, shop_slug='utech-official', message=f'Câu trước {index}',
                answer=f'Phản hồi trước {index}', intent='unknown', mode='ai', status='completed',
                provider='gemini', elapsed_ms=0) for index in range(30)
        ])
        session.commit()

    with sqlite3.connect(shop_path) as db:
        db.execute('UPDATE product_variant SET price=550000, stock=7 WHERE sku=?', (sku,))

    question = 'Sản phẩm này làm sao để bán tốt và tăng doanh số?'
    response = client.post('/api/v1/chat', headers=headers, json={'message': question, 'conversation_id': conversation})
    assert response.status_code == 200
    focus = response.json()['data']['facts']['business_advisory']['focus_product']
    assert (focus['sku'], focus['price_vnd'], focus['available_stock']) == (sku, 550_000, 7)

    def turn():
        upstream = GeminiFixture()
        monkeypatch.setattr(live, 'connect', lambda *_, **__: upstream)
        with client.websocket_connect('/api/v1/live') as socket:
            socket.send_json({'type': 'auth', 'token': token, 'conversation_id': conversation, 'turn_protocol': 1})
            assert socket.receive_json()['type'] == 'ready'
            socket.send_json({'type': 'finish'})
            assert socket.receive_json()['type'] == 'finished'
        return upstream

    monkeypatch.setattr(state.settings, 'gemini_api_key', SecretStr('fixture-key'))
    upstream = turn()
    setup = upstream.sent[0]['setup']
    assert setup['inputAudioTranscription']['languageCodes'] == ['vi-VN']
    assert name in setup['inputAudioTranscription']['customVocabulary']
    assert sku in setup['systemInstruction']['parts'][0]['text']
    assert setup['contextWindowCompression']['slidingWindow']['targetTokens'] == 8000
    messages = upstream.sent[1]['clientContent']['turns']
    assert len(messages) <= 8 and any(question in row['parts'][0]['text'] for row in messages)

    with state.session_factory() as session:
        result = inspect_shop(session, state.shop_repository, question, conversation_id=conversation)
        assert result['facts']['business_advisory']['focus_product']['sku'] == sku
        other = inspect_shop(session, state.shop_repository, question, conversation_id=uuid4())
        assert other['facts']['product_reference_missing']
        forget_memory(session, state.shop_repository)
        session.commit()
    upstream = turn()
    assert 'historyConfig' not in upstream.sent[0]['setup']
    assert name not in upstream.sent[0]['setup']['inputAudioTranscription']['customVocabulary']


def test_live_order_and_price_updates_use_shop_rules_and_fresh_approval(secured):
    client, path = secured
    token = live_token(client)
    headers = {'Authorization': 'Bearer ' + token}
    conversation_id = uuid4()
    history = LiveHistory(client.app.state, token, conversation_id, 'qa')
    sent = []

    async def send(event):
        sent.append(event)

    actions = LiveActions(SimpleNamespace(app=client.app, send_json=send), history)
    with sqlite3.connect(path) as db:
        db.execute('ALTER TABLE "order" ADD COLUMN note TEXT')
        db.execute('INSERT INTO "order" VALUES(1,1,1000000,?,?,?)',
                   ('pending', '2026-11-20T00:00:00', ''))
        db.execute('INSERT INTO order_item VALUES(1,1,1,1,1000000)')
    url = '/api/v1/management/orders/1'

    async def review_and_confirm():
        await actions.prepare_order(1, {'status': 'paid', 'note': 'Gọi trước khi giao'})
        assert not (await actions.decide('Xác nhận cập nhật đơn', finished=True))['accepted']
        actions.pending.armed = True
        assert not (await actions.decide('Xác nhận cập nhật đơn?', finished=True))['accepted']
        assert not (await actions.decide('Xác nhận cập nhật đơn', finished=False))['accepted']
        history.language = 'en'
        assert (await actions.decide('Confirm order update.', finished=True))['answer'] == 'I updated order 1.'
        history.language = 'vi'
        price = await actions.ask_chat('Đổi giá SKU SEED-PHONE thành 500000 đồng')
        assert '500000' in price['review']
        actions.pending.armed = True
        assert (await actions.decide('Tôi xác nhận đổi giá.', finished=True))['accepted']

    asyncio.run(review_and_confirm())
    order = client.get(url, headers=headers).json()['data']
    assert order['status'] == 'paid' and order['note'] == 'Gọi trước khi giao'
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT price FROM product_variant WHERE sku='SEED-PHONE'").fetchone() == (500000,)
    assert sum(event['type'] == 'action_done' and event['changed'] for event in sent) == 2
