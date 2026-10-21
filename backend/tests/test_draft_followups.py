import base64
import sqlite3
from uuid import uuid4

import pytest

from test_product_drafts import make_client, upload_and_reply


@pytest.mark.parametrize('message', ['Hủy bản nháp này đi', 'Thôi không đăng nữa', 'Đừng đăng sản phẩm này nữa nhé'])
def test_natural_cancellation_never_becomes_listing_content(tmp_path, message):
    client, shop_path, uploads = make_client(tmp_path)
    with client:
        _, reply = upload_and_reply(client)
        result = reply(message)
        assert result['product_draft']['status'] == 'cancelled'
        assert not list(uploads.iterdir())
        with sqlite3.connect(shop_path) as db:
            assert db.execute('SELECT COUNT(*) FROM product').fetchone()[0] == 2


@pytest.mark.parametrize('message', ['Để sau', 'Để lát làm tiếp nhé'])
def test_postponing_retains_the_draft_and_its_photos(tmp_path, message):
    client, _, uploads = make_client(tmp_path)
    with client:
        first, reply = upload_and_reply(client)
        result = reply(message)
        assert result['product_draft']['id'] == first['product_draft']['id']
        assert result['product_draft']['status'] == 'collecting'
        assert result['fallback_reason'] is None
        assert len(list(uploads.iterdir())) == 1
        assert result['product_draft']['name'] is None


def gallery(client, conversation, photos, request=None):
    return client.post('/api/v1/product-drafts/images-data', json={
        'conversation_id': conversation, 'request_id': request or str(uuid4()),
        'images_base64': [base64.b64encode(photo).decode() for photo in photos],
    })


def test_append_gallery_preserves_facts_and_retry_never_adds_twice(tmp_path):
    client, _, uploads = make_client(tmp_path)
    with client:
        first, reply = upload_and_reply(client)
        details = reply('Tên: Bàn phím Nova; giá: 500k; tồn: 8; mô tả: Bàn phím gọn nhẹ.')['product_draft']
        request = str(uuid4())
        photos = [b'\x89PNG\r\n\x1a\nside', b'RIFF0000WEBPdetail']
        response = gallery(client, first['conversation_id'], photos, request)
        assert response.status_code == 201, response.text
        draft = response.json()['data']['product_draft']
        assert draft['id'] == details['id'] and draft['image_count'] == 3
        assert (draft['name'], draft['price_vnd'], draft['stock']) == (details['name'], 500000, 8)
        assert gallery(client, first['conversation_id'], photos, request).json() == response.json()
        assert len(list(uploads.iterdir())) == 3
        for path in draft['preview_urls']:
            assert client.get('/api/v1' + path).status_code == 200


def test_gallery_limit_and_bad_append_leave_existing_images_untouched(tmp_path):
    client, _, uploads = make_client(tmp_path)
    with client:
        first, _ = upload_and_reply(client)
        original_files = set(uploads.iterdir())
        for photos in ([b'\xff\xd8\xffextra'] * 6, [b'\xff\xd8\xffvalid', b'bad image']):
            response = gallery(client, first['conversation_id'], photos)
            assert response.status_code == 422, response.text
            assert set(uploads.iterdir()) == original_files
        assert client.get('/api/v1' + first['product_draft']['preview_url']).status_code == 200


def test_published_chat_product_is_first_in_app_even_after_a_full_page_of_bestsellers(tmp_path):
    client, shop_path, _ = make_client(tmp_path)
    with sqlite3.connect(shop_path) as db:
        db.execute('UPDATE product SET sold_count=100')
        for index in range(25):
            db.execute('INSERT INTO product (name,price,category_id,stock,sku,status,shop_id,sold_count) VALUES (?,100000,4,50,?,\'active\',1,100)',
                       (f'Bán chạy {index}', f'OLD-{index}'))
    with client:
        _, reply = upload_and_reply(client)
        prepared = reply('Tên: Bàn phím mới Nova; giá: 500k; tồn: 8; mô tả: Bàn phím gọn nhẹ.')['product_draft']
        published = reply('Đăng sản phẩm')['product_draft']
        assert published['id'] == prepared['id'] and published['status'] == 'published'
        first = client.get('/api/v1/management/products?sort=newest&limit=20').json()['data']
        assert first['total'] == 28
        assert first['items'][0]['id'] == published['published_product_id']
        assert first['items'][0]['stock'] == 8 and first['items'][0]['price_vnd'] == 500000
        second = client.get('/api/v1/management/products?sort=newest&limit=20&offset=20').json()['data']
        assert not {row['id'] for row in first['items']} & {row['id'] for row in second['items']}
        best = client.get('/api/v1/management/products?sort=bestselling&limit=1').json()['data']['items'][0]
        assert best['sold_count'] == 100 and best['id'] != published['published_product_id']
        assert client.get('/api/v1/management/products?sort=invalid').status_code == 422


def test_upload_and_publish_are_blocked_while_the_same_draft_is_being_rewritten(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from test_chat_requests import WaitingProvider
    class WaitingListing(WaitingProvider):
        async def compose_listing(self, **kwargs):
            return await self.respond()
    client, _, uploads = make_client(tmp_path)
    with client:
        first, reply = upload_and_reply(client)
        draft = reply('Tên: Bàn phím Nova; giá: 500k; tồn: 8; mô tả: Bàn phím gọn nhẹ.')['product_draft']
        provider = WaitingListing()
        client.app.state.ai_provider = provider
        request_id = str(uuid4())
        with ThreadPoolExecutor(1) as pool:
            pending = pool.submit(client.post, '/api/v1/chat', json={
                'conversation_id': first['conversation_id'], 'request_id': request_id,
                'message': 'Viết lại nội dung bản nháp',
            })
            try:
                assert provider.started.wait(3)
                response = gallery(client, first['conversation_id'], [b'\xff\xd8\xffextra'])
                assert response.status_code == 409 and response.json()['detail']['code'] == 'conversation_busy'
                assert len(list(uploads.iterdir())) == 1
                for action in ('publish', 'cancel'):
                    result = client.post(f"/api/v1/product-drafts/{draft['id']}/{action}")
                    assert result.status_code == 409 and result.json()['detail']['code'] == 'conversation_busy'
            finally:
                client.post(f'/api/v1/chat/requests/{request_id}/cancel')
            assert pending.result(3).status_code == 409


def test_unrelated_upload_waits_without_blocking_stop_or_leaving_partial_files(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from test_chat_requests import WaitingProvider
    class WaitingListing(WaitingProvider):
        async def compose_listing(self, **kwargs):
            return await self.respond()
    client, _, uploads = make_client(tmp_path)
    with client:
        provider = WaitingListing()
        client.app.state.ai_provider = provider
        request_id, first, second = str(uuid4()), str(uuid4()), str(uuid4())
        with ThreadPoolExecutor(2) as pool:
            chat = pool.submit(client.post, '/api/v1/chat', json={'message': 'Đăng sản phẩm mới',
                'conversation_id': first, 'request_id': request_id})
            assert provider.started.wait(3)
            photo = pool.submit(gallery, client, second, [b'\xff\xd8\xffphoto'])
            try:
                # These endpoints must remain responsive while SQLite has a writer.
                assert client.get(f'/api/v1/chat/requests/{request_id}').json()['data']['status'] == 'running'
                assert client.post(f'/api/v1/chat/requests/{request_id}/cancel').status_code == 200
            finally:
                client.post(f'/api/v1/chat/requests/{request_id}/cancel')
            assert chat.result(3).status_code == 409
            response = photo.result(3)
            assert response.status_code == 201, response.text
            assert response.json()['data']['conversation_id'] == second
            assert len(list(uploads.iterdir())) == 1


def test_new_text_listing_does_not_lock_out_other_sellers_chat_requests(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.schemas.chat import ChatRequest
    from test_chat_requests import WaitingProvider
    class WaitingListing(WaitingProvider):
        prefer_direct_facts = True
        async def compose_listing(self, **kwargs):
            return await self.respond()
    client, _, _ = make_client(tmp_path)
    with client:
        provider = WaitingListing()
        client.app.state.ai_provider = provider
        first_id, second_id = str(uuid4()), str(uuid4())
        with ThreadPoolExecutor(1) as pool:
            first = pool.submit(client.post, '/api/v1/chat', json={'message': 'Đăng sản phẩm mới',
                'conversation_id': str(uuid4()), 'request_id': first_id})
            assert provider.started.wait(3)
            try:
                manager = client.app.state.chat_requests
                second = ChatRequest(message='SKU SEED-PHONE còn bao nhiêu?', conversation_id=uuid4(), request_id=second_id)
                key = client.portal.call(manager.submit, second, client.app.state.shop_repository)
                assert manager.status(key)['status'] == 'queued'
            finally:
                client.post(f'/api/v1/chat/requests/{first_id}/cancel')
            assert first.result(3).status_code == 409
            replay = client.post('/api/v1/chat', json=second.model_dump(mode='json'))
            assert replay.status_code == 200 and replay.json()['data']['facts']['stock'] == 8


def test_unsaved_text_draft_never_inherits_unrelated_chat_history(tmp_path):
    from test_product_drafts import CopyProvider
    client, _, _ = make_client(tmp_path)
    with client:
        client.post('/api/v1/chat', json={'message': 'SKU SEED-PHONE còn bao nhiêu?'})
        provider = CopyProvider()
        client.app.state.ai_provider = provider
        result = client.post('/api/v1/chat', json={'message': 'Đăng sản phẩm mới'}).json()['data']
        assert result['facts']['draft_id'] == result['product_draft']['id']
        assert provider.calls[0]['history'] == [{'role': 'user', 'content': 'Đăng sản phẩm mới'}]
