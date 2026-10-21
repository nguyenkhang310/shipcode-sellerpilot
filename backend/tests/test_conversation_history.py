import base64
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from sqlalchemy import select

from app.models.action import ActionProposal
from app.models.agent_run import AgentRun
from app.models.conversation_state import ConversationState
from app.models.product_draft import ProductDraft
from app.models.product_edit import ProductEditProposal
from test_chat_requests import WaitingProvider, count, payload, status
from test_product_drafts import CopyProvider, make_client, upload_and_reply


def history(client):
    return client.get('/api/v1/conversations').json()['data']['items']


def test_pin_order_persistence_unpin_and_strict_payload(client):
    first, second = payload('SKU A001 còn bao nhiêu?'), payload('SKU A002 còn bao nhiêu?')
    for data in (first, second):
        assert client.post('/api/v1/chat', json=data).status_code == 200
    url = '/api/v1/conversations/' + first['conversation_id']
    assert [row['id'] for row in history(client)] == [second['conversation_id'], first['conversation_id']]
    assert client.patch(url, json={'is_pinned': True}).status_code == 200
    rows = history(client)
    assert rows[0]['id'] == first['conversation_id'] and rows[0]['is_pinned']
    with client.app.state.session_factory() as session:
        tenant = client.app.state.shop_repository.seller_shop_slug or 'local'
        assert session.get(ConversationState, (tenant, first['conversation_id'])).pinned_at
    assert client.patch(url, json={'is_pinned': 'false'}).status_code == 422
    assert client.patch(url, json={'is_pinned': False}).status_code == 200
    assert history(client)[0]['id'] == second['conversation_id']
    assert not any(row['is_pinned'] for row in history(client))


def test_deleted_chat_is_removed_and_late_replays_cannot_restore_it(client):
    data = payload('Đổi giá SKU A001 thành 125k')
    response = client.post('/api/v1/chat', json=data)
    assert response.status_code == 200
    url = '/api/v1/conversations/' + data['conversation_id']
    assert client.delete(url).status_code == 200
    assert client.delete(url).status_code == 200  # idempotent retry after lost HTTP response
    assert history(client) == []
    assert count(client, AgentRun) == 0
    assert client.get(url).status_code == client.patch(url, json={'is_pinned': True}).status_code == 410
    assert status(client, data)['response'] is None
    assert status(client, data)['error']['status'] == 410
    for new_id in (data['request_id'], str(uuid4())):
        assert client.post('/api/v1/chat', json={**data, 'request_id': new_id}).status_code == 410
    with client.app.state.session_factory() as session:
        assert session.scalar(select(ActionProposal)).status == 'rejected'
    assert client.post('/api/v1/chat', json=payload('SKU A001 còn bao nhiêu?')).status_code == 200


def test_delete_rejects_pending_content_edits_but_keeps_confirmed_changes(tmp_path):
    import sqlite3
    client, shop_path, _ = make_client(tmp_path)
    with client:
        first = client.post('/api/v1/chat', json={
            'message': 'Sửa tiêu đề SKU SEED-PHONE thành "Điện thoại gọn nhẹ"',
        }).json()['data']
        proposal_id = first['product_edit_proposal']['id']
        assert client.delete('/api/v1/conversations/' + first['conversation_id']).status_code == 200
        assert client.post(f'/api/v1/product-edits/{proposal_id}/confirm').status_code == 409
        with client.app.state.session_factory() as session:
            assert session.get(ProductEditProposal, proposal_id).status == 'rejected'
        with sqlite3.connect(shop_path) as db:
            assert db.execute('SELECT name FROM product WHERE id=1').fetchone()[0] == 'Điện thoại mẫu'
        second = client.post('/api/v1/chat', json={
            'message': 'Sửa tiêu đề SKU SEED-PHONE thành "Điện thoại gọn nhẹ"',
        }).json()['data']
        approved_id = second['product_edit_proposal']['id']
        assert client.post(f'/api/v1/product-edits/{approved_id}/confirm').status_code == 200
        assert client.delete('/api/v1/conversations/' + second['conversation_id']).status_code == 200
        assert client.post(f'/api/v1/product-edits/{approved_id}/confirm').json()['data']['idempotent']
        with sqlite3.connect(shop_path) as db:
            assert db.execute('SELECT name FROM product WHERE id=1').fetchone()[0] == 'Điện thoại gọn nhẹ'


def test_history_actions_are_shop_scoped_and_do_not_create_unknown_conversations(client):
    data = payload('SKU A001 còn bao nhiêu?')
    client.post('/api/v1/chat', json=data)
    shop = client.app.state.shop_repository
    original = shop.seller_shop_slug
    shop.seller_shop_slug = 'other-shop'
    url = '/api/v1/conversations/' + data['conversation_id']
    try:
        assert history(client) == []
        assert client.delete(url).status_code == 404
        assert client.patch(url, json={'is_pinned': True}).status_code == 404
    finally:
        shop.seller_shop_slug = original
    assert len(history(client)) == 1
    assert client.delete('/api/v1/conversations/' + str(uuid4())).status_code == 404
    assert count(client, ConversationState) == 0


def test_delete_cancels_inference_even_when_transaction_has_staged_writes(client, monkeypatch):
    from app.services.seller_tools import create_price_proposal
    provider = WaitingProvider()

    async def staged_write(_payload, session, shop, *_args):
        create_price_proposal(session, shop, sku='A001', new_price_vnd=125000)
        await provider.respond()

    monkeypatch.setattr('app.services.chat_requests.dispatch_chat', staged_write)
    data = payload()
    with ThreadPoolExecutor(1) as pool:
        pending = pool.submit(client.post, '/api/v1/chat', json=data)
        assert provider.started.wait(3)
        deleted = client.delete('/api/v1/conversations/' + data['conversation_id'])
        assert deleted.status_code == 200, deleted.text
        assert pending.result(3).status_code in (409, 410)
    assert provider.stopped.is_set()
    assert not client.app.state.chat_requests.tasks and not client.app.state.chat_requests.conversations
    assert count(client, AgentRun) == count(client, ActionProposal) == 0
    assert client.post('/api/v1/chat', json=data).status_code == 410


def test_delete_draft_removes_private_images_and_blocks_all_upload_retries(tmp_path):
    client, _, uploads = make_client(tmp_path)
    with client:
        data = {'request_id': str(uuid4()), 'conversation_id': str(uuid4()),
                'images_base64': [base64.b64encode(b'\xff\xd8\xffphoto').decode()] * 2}
        uploaded = client.post('/api/v1/product-drafts/images-data', json=data).json()['data']
        draft_id = uploaded['product_draft']['id']
        assert len(list(uploads.iterdir())) == 2
        assert client.delete('/api/v1/conversations/' + data['conversation_id']).status_code == 200
        assert not list(uploads.iterdir())
        assert client.get(f'/api/v1/product-drafts/{draft_id}/image').status_code == 410
        for change in ({}, {'request_id': str(uuid4())}):
            assert client.post('/api/v1/product-drafts/images-data', json={**data, **change}).status_code == 410
        assert client.post('/api/v1/product-drafts/image-data', json={
            'image_base64': data['images_base64'][0], 'conversation_id': data['conversation_id']}).status_code == 410
        assert client.post('/api/v1/product-drafts', data={'conversation_id': data['conversation_id']},
            files={'image': ('photo.jpg', b'\xff\xd8\xffphoto', 'image/jpeg')}).status_code == 410
        assert count(client, ProductDraft) == 1 and count(client, AgentRun) == 0


def test_delete_history_keeps_published_product_and_public_images(tmp_path):
    import sqlite3
    client, shop_db, uploads = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CopyProvider()
        uploaded, reply = upload_and_reply(client)
        result = reply('Tên: Bàn phím Nova, giá: 990k, tồn kho: 20, AI tự viết nội dung')
        draft = result['product_draft']
        published = client.post(f"/api/v1/product-drafts/{draft['id']}/publish")
        assert published.status_code == 200, published.text
        images = list(uploads.iterdir())
        assert client.delete('/api/v1/conversations/' + uploaded['conversation_id']).status_code == 200
        assert list(uploads.iterdir()) == images
        with sqlite3.connect(shop_db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM product WHERE name='Bàn phím Nova'").fetchone()[0] == 1
        with client.app.state.session_factory() as session:
            assert session.get(ProductDraft, draft['id']).status == 'published'


def test_cors_allows_history_mutations(client):
    origin = client.app.state.settings.cors_origins[0]
    for method in ('PATCH', 'DELETE'):
        response = client.options('/api/v1/conversations/' + str(uuid4()), headers={
            'Origin': origin, 'Access-Control-Request-Method': method,
            'Access-Control-Request-Headers': 'Content-Type'})
        assert response.status_code == 200 and response.headers['access-control-allow-origin'] == origin
