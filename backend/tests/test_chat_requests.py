import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import func, select

from app.models.action import ActionProposal
from app.models.agent_run import AgentRun
from app.models.chat_request import ChatRequestRecord


class WaitingProvider:
    provider = 'opencode'
    model = 'muse-spark-1.3-contributor-free'
    natural_responses = True
    prefer_model_intent = True

    def __init__(self):
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def analyze_advice(self, *_args, **_kwargs):
        return json.dumps({'topic': 'strategy', 'preferences': [
            {'field': 'target_audience', 'value': 'sinh viên', 'evidence': 'Mình bán cho sinh viên'}]})

    async def respond(self, *_args, **_kwargs):
        self.calls += 1
        self.started.set()
        try:
            await self.release.wait()
            return 'Mình sẽ tư vấn theo số liệu thực tế của shop.'
        finally:
            self.stopped.set()


def payload(message='Mình bán cho sinh viên, tư vấn chiến lược giúp mình.'):
    return {'request_id': str(uuid4()), 'conversation_id': str(uuid4()), 'message': message}


def status(client, data):
    return client.get('/api/v1/chat/requests/' + data['request_id']).json()['data']


def count(client, model):
    with client.app.state.session_factory() as session:
        return session.scalar(select(func.count()).select_from(model))


def unblock(client, provider):
    async def release():
        provider.release.set()
    client.portal.call(release)


def test_concurrent_duplicate_requests_run_once_and_replay_exact_response(client):
    provider = WaitingProvider()
    client.app.state.ai_provider = provider
    data = payload()
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, '/api/v1/chat', json=data)
        assert provider.started.wait(3)
        second = pool.submit(client.post, '/api/v1/chat', json=data)
        assert status(client, data)['status'] == 'running'
        # Pending personalization has not locked or modified the database.
        assert client.get('/api/v1/assistant/memory').json()['data']['items'] == []
        unblock(client, provider)
        one, two = first.result(3), second.result(3)
    assert one.status_code == two.status_code == 200
    assert one.json() == two.json()
    assert provider.calls == count(client, AgentRun) == 1
    assert client.post('/api/v1/chat', json=data).json() == one.json()
    assert status(client, data)['response'] == one.json()
    assert len(client.get('/api/v1/assistant/memory').json()['data']['items']) == 1


def test_cancel_stops_inference_and_rolls_back_history_and_memory(client):
    provider = WaitingProvider()
    client.app.state.ai_provider = provider
    data = payload()
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(client.post, '/api/v1/chat', json=data)
        assert provider.started.wait(3)
        cancelled = client.post('/api/v1/chat/requests/' + data['request_id'] + '/cancel')
        assert cancelled.status_code == 200
        assert cancelled.json()['data']['status'] == 'cancelled'
        assert pending.result(3).status_code == 409
    assert provider.stopped.is_set()
    assert count(client, AgentRun) == 0
    assert client.get('/api/v1/assistant/memory').json()['data']['items'] == []
    assert client.post('/api/v1/chat', json=data).json()['detail']['code'] == 'chat_cancelled'
    assert provider.calls == 1
    # Cancellation also releases the conversation and inference locks.
    unblock(client, provider)
    followup = {**data, 'request_id': str(uuid4())}
    assert client.post('/api/v1/chat', json=followup).status_code == 200


def test_cancel_before_post_leaves_tombstone_preventing_late_generation(client):
    provider = WaitingProvider()
    client.app.state.ai_provider = provider
    data = payload()
    url = '/api/v1/chat/requests/' + data['request_id'] + '/cancel'
    assert client.post(url).json()['data']['status'] == 'cancelled'
    assert client.post(url).json()['data']['status'] == 'cancelled'
    assert client.post('/api/v1/chat', json=data).status_code == 409
    assert provider.calls == count(client, AgentRun) == 0


def test_cancel_after_completion_keeps_real_result_and_no_duplicate_proposals(client):
    data = payload('Đổi giá SKU A001 thành 125k')
    first = client.post('/api/v1/chat', json=data)
    assert first.status_code == 200
    cancelled = client.post('/api/v1/chat/requests/' + data['request_id'] + '/cancel').json()['data']
    assert cancelled['status'] == 'completed'
    assert cancelled['response'] == first.json()
    assert client.post('/api/v1/chat', json=data).json() == first.json()
    assert count(client, AgentRun) == count(client, ActionProposal) == 1


def test_same_id_cannot_change_message_or_conversation(client):
    data = payload('SKU A001 còn bao nhiêu?')
    assert client.post('/api/v1/chat', json=data).status_code == 200
    for update in ({'message': 'Đổi giá SKU A001 thành 120k'}, {'conversation_id': str(uuid4())}):
        response = client.post('/api/v1/chat', json={**data, **update})
        assert response.status_code == 409
        assert response.json()['detail']['code'] == 'request_id_conflict'
    assert count(client, AgentRun) == 1


def test_new_turn_in_busy_conversation_is_rejected_without_side_effects(client):
    provider = WaitingProvider()
    client.app.state.ai_provider = provider
    data = payload()
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(client.post, '/api/v1/chat', json=data)
        assert provider.started.wait(3)
        second = client.post('/api/v1/chat', json={**data, 'request_id': str(uuid4()), 'message': 'SKU A001 còn bao nhiêu?'})
        assert second.status_code == 409
        assert second.json()['detail']['code'] == 'conversation_busy'
        unblock(client, provider)
        assert first.result(3).status_code == 200
    assert provider.calls == count(client, AgentRun) == 1


def test_durable_status_is_shop_scoped(client):
    data = payload('SKU A001 còn bao nhiêu?')
    assert client.post('/api/v1/chat', json=data).status_code == 200
    shop = client.app.state.shop_repository
    original = shop.seller_shop_slug
    shop.seller_shop_slug = 'another-shop'
    try:
        assert client.get('/api/v1/chat/requests/' + data['request_id']).status_code == 404
        assert client.post('/api/v1/chat/requests/' + data['request_id'] + '/cancel').json()['data']['status'] == 'cancelled'
    finally:
        shop.seller_shop_slug = original
    assert status(client, data)['status'] == 'completed'


def test_recovery_marks_interrupted_work_and_does_not_repeat_it(client):
    data = payload()
    manager = client.app.state.chat_requests
    with manager.sessions() as session:
        session.add(ChatRequestRecord(shop_slug=client.app.state.shop_repository.seller_shop_slug,
            request_id=data['request_id'], conversation_id=data['conversation_id'], status='running'))
        session.commit()
    manager.recover()
    assert status(client, data)['error']['detail']['code'] == 'chat_interrupted'
    assert client.post('/api/v1/chat', json=data).status_code == 409
    assert count(client, AgentRun) == 0


def test_http_waiter_cancellation_does_not_cancel_durable_job(client):
    from app.schemas.chat import ChatRequest
    provider = WaitingProvider()
    client.app.state.ai_provider = provider
    manager = client.app.state.chat_requests
    data = payload()

    async def disconnect_waiter():
        key = manager.submit(ChatRequest(**data), client.app.state.shop_repository)
        waiter = asyncio.create_task(manager.wait(key))
        await asyncio.sleep(0)
        waiter.cancel()
        try:
            await waiter
        except asyncio.CancelledError:
            pass
        assert not manager.tasks[key].cancelled()

    client.portal.call(disconnect_waiter)
    assert provider.started.wait(3)
    unblock(client, provider)
    assert client.post('/api/v1/chat', json=data).status_code == 200
    assert count(client, AgentRun) == provider.calls == 1


def test_cancel_rolls_back_intermediate_service_commit(client, monkeypatch):
    from app.services.seller_tools import create_price_proposal
    provider = WaitingProvider()

    async def staged_write(payload, session, shop, *_args):
        create_price_proposal(session, shop, sku='A001', new_price_vnd=125000)
        await provider.respond()

    monkeypatch.setattr('app.services.chat_requests.dispatch_chat', staged_write)
    data = payload()
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(client.post, '/api/v1/chat', json=data)
        assert provider.started.wait(3)
        response = client.post('/api/v1/chat/requests/' + data['request_id'] + '/cancel')
        assert response.json()['data']['status'] == 'cancelled'
        assert pending.result(3).status_code == 409
    assert count(client, ActionProposal) == count(client, AgentRun) == 0


def test_cancel_task_before_it_starts_is_terminal_and_releases_conversation(client):
    from app.schemas.chat import ChatRequest
    manager = client.app.state.chat_requests
    data = payload()

    async def cancel_immediately():
        key = manager.submit(ChatRequest(**data), client.app.state.shop_repository)
        result = await manager.cancel(key)
        await manager.wait(key)
        assert key not in manager.tasks
        assert not manager.conversations
        return result

    assert client.portal.call(cancel_immediately)['status'] == 'cancelled'
    assert count(client, AgentRun) == 0


def test_gallery_upload_replays_same_draft_and_files_after_lost_response(tmp_path):
    import base64
    from test_product_drafts import make_client
    from app.models.product_draft import ProductDraft

    client, _, _ = make_client(tmp_path)
    with client:
        data = {'request_id': str(uuid4()), 'conversation_id': str(uuid4()),
            'images_base64': [base64.b64encode(b'\xff\xd8\xffphoto').decode()] * 2}
        first = client.post('/api/v1/product-drafts/images-data', json=data)
        assert first.status_code == 201
        files = sorted(tmp_path.joinpath('uploads').iterdir())
        replay = client.post('/api/v1/product-drafts/images-data', json=data)
        assert replay.status_code == 201
        assert replay.json() == first.json()
        assert sorted(tmp_path.joinpath('uploads').iterdir()) == files
        assert count(client, ProductDraft) == count(client, AgentRun) == 1
        assert status(client, data)['response'] == first.json()
        changed = client.post('/api/v1/product-drafts/images-data', json={**data,
            'images_base64': [base64.b64encode(b'\xff\xd8\xffdifferent').decode()]})
        assert changed.status_code == 409


def test_cancel_gallery_before_upload_never_creates_draft_or_media(tmp_path):
    import base64
    from test_product_drafts import make_client
    from app.models.product_draft import ProductDraft

    client, _, _ = make_client(tmp_path)
    with client:
        data = {'request_id': str(uuid4()), 'conversation_id': str(uuid4()),
            'images_base64': [base64.b64encode(b'\xff\xd8\xffphoto').decode()]}
        client.post('/api/v1/chat/requests/' + data['request_id'] + '/cancel')
        response = client.post('/api/v1/product-drafts/images-data', json=data)
        assert response.status_code == 409
        assert count(client, ProductDraft) == count(client, AgentRun) == 0
        assert not tmp_path.joinpath('uploads').exists()


def test_cancel_listing_generation_preserves_original_draft_fields_and_images(tmp_path):
    import base64
    from test_product_drafts import make_client
    from app.models.product_draft import ProductDraft

    client, _, _ = make_client(tmp_path)
    provider = WaitingProvider()
    # Listing supports respond() on text-only providers too; block it mid-copy.
    with client:
        client.app.state.ai_provider = provider
        uploaded = client.post('/api/v1/product-drafts/images-data', json={
            'images_base64': [base64.b64encode(b'\xff\xd8\xffphoto').decode()]}).json()['data']
        data = {**payload('Tên: Bàn phím Nova, giá: 990k, tồn kho: 20, AI tự viết nội dung'),
            'conversation_id': uploaded['conversation_id']}
        with ThreadPoolExecutor(1) as pool:
            pending = pool.submit(client.post, '/api/v1/chat', json=data)
            assert provider.started.wait(3)
            assert client.post('/api/v1/chat/requests/' + data['request_id'] + '/cancel').status_code == 200
            assert pending.result(3).status_code == 409
        with client.app.state.session_factory() as session:
            draft = session.get(ProductDraft, uploaded['product_draft']['id'])
            assert draft.name is None and draft.price_vnd is None and draft.stock is None
            assert draft.status == 'collecting'
        assert count(client, AgentRun) == 1  # Only the original upload remains.
        assert list(tmp_path.joinpath('uploads').iterdir())


def test_migration_adds_request_table_without_changing_existing_memory(tmp_path, monkeypatch):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, inspect, text

    database_url = 'sqlite:///' + str(tmp_path / 'upgrade.db')
    monkeypatch.setenv('DATABASE_URL', database_url)
    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / 'alembic.ini'))
    config.set_main_option('script_location', str(backend / 'alembic'))
    command.upgrade(config, '20261016_08')
    engine = create_engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO assistant_memory (shop_slug,scope,key,value_json,evidence,updated_at) VALUES ('shop','shop','business_goal','\"bền vững\"','mục tiêu bền vững','2026-10-16 00:00:00')"))
        command.upgrade(config, 'head')
        assert 'chat_request' in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT count(*) FROM assistant_memory')) == 1
        command.downgrade(config, '20261016_08')
        assert 'chat_request' not in inspect(engine).get_table_names()
        command.upgrade(config, 'head')
    finally:
        engine.dispose()


def test_memory_reset_cancels_inflight_personalization_instead_of_restoring_it(client):
    provider = WaitingProvider()
    client.app.state.ai_provider = provider
    data = payload()
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(client.post, '/api/v1/chat', json=data)
        assert provider.started.wait(3)
        assert client.post('/api/v1/assistant/memory/reset').status_code == 200
        assert pending.result(3).status_code == 409
    assert provider.stopped.is_set()
    assert status(client, data)['status'] == 'cancelled'
    assert client.get('/api/v1/assistant/memory').json()['data']['items'] == []


def test_queued_request_can_be_cancelled_without_calling_ai(client):
    provider = WaitingProvider()
    client.app.state.ai_provider = provider
    data, queued = payload(), payload()
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(client.post, '/api/v1/chat', json=data)
        assert provider.started.wait(3)

        async def queue():
            from app.schemas.chat import ChatRequest
            return client.app.state.chat_requests.submit(ChatRequest(**queued), client.app.state.shop_repository)

        client.portal.call(queue)
        assert status(client, queued)['status'] == 'queued'
        assert client.post('/api/v1/chat/requests/' + queued['request_id'] + '/cancel').json()['data']['status'] == 'cancelled'
        unblock(client, provider)
        assert first.result(3).status_code == 200
    assert provider.calls == count(client, AgentRun) == 1


def test_unexpected_provider_failure_rolls_back_and_has_stable_error_on_retry(client):
    provider = WaitingProvider()

    async def broken(*_args, **_kwargs):
        raise RuntimeError('simulated connection failure')

    provider.respond = broken
    client.app.state.ai_provider = provider
    data = payload()
    first = client.post('/api/v1/chat', json=data)
    assert first.status_code == 500
    assert first.json()['detail']['code'] == 'chat_failed'
    assert client.post('/api/v1/chat', json=data).json() == first.json()
    assert count(client, AgentRun) == 0
    assert client.get('/api/v1/assistant/memory').json()['data']['items'] == []


def test_completed_response_survives_runner_restart_without_calling_ai(client):
    from app.services.chat_requests import ChatRequestManager
    from app.schemas.chat import ChatRequest

    data = payload('SKU A001 còn bao nhiêu?')
    original = client.post('/api/v1/chat', json=data).json()
    replacement = ChatRequestManager(client.app.state.session_factory,
        lambda: (_ for _ in ()).throw(AssertionError('Replay must not call AI')),
        client.app.state.settings)
    replacement.recover()
    key = replacement.submit(ChatRequest(**data), client.app.state.shop_repository)
    assert not replacement.tasks
    assert replacement.result(key).model_dump(mode='json') == original
    assert count(client, AgentRun) == 1


def test_queue_capacity_rejects_new_work_without_creating_orphan_record(client):
    from fastapi import HTTPException
    from app.schemas.chat import ChatRequest

    manager = client.app.state.chat_requests

    async def fill_queue():
        async with manager.execution:
            for _ in range(16):
                manager.submit(ChatRequest(**payload()), client.app.state.shop_repository)
            try:
                manager.submit(ChatRequest(**payload()), client.app.state.shop_repository)
                raise AssertionError('Queue must be bounded')
            except HTTPException as error:
                assert error.status_code == 429
            for key in list(manager.tasks):
                await manager.cancel(key)

    client.portal.call(fill_queue)
    assert count(client, ChatRequestRecord) == 16
    assert count(client, AgentRun) == 0
    assert not manager.tasks and not manager.conversations
