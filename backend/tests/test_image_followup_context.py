from uuid import uuid4

import pytest

from test_product_drafts import make_client
from test_draft_followups import gallery
from test_listing_semantics import SemanticProvider


@pytest.mark.parametrize('message', ['đây nha', 'đây nè', 'ảnh này nha', 'Bổ sung một góc khác'])
def test_new_photo_is_actually_sent_to_ai_after_the_first_photo_was_understood(tmp_path, message):
    client, _, _ = make_client(tmp_path)
    with client:
        provider = SemanticProvider({'name': 'Bàn phím Nova màu trắng', 'description': 'Bàn phím Nova màu trắng.', 'category_id': 4})
        client.app.state.ai_provider = provider
        first = gallery(client, None, [b'\xff\xd8\xfffront']).json()['data']
        conversation = first['conversation_id']
        def say(text):
            result = client.post('/api/v1/chat', json={'message': text, 'conversation_id': conversation})
            assert result.status_code == 200, result.text
            return result.json()['data']
        initial = say('Bàn phím Nova màu trắng; giá: 500k; tồn: 8; tự viết mô tả')
        assert len(provider.calls[0]['images']) == 1
        assert initial['facts']['ai_image_count'] == 1
        assert gallery(client, conversation, [b'\xff\xd8\xffback']).status_code == 201
        result = say(message)
        assert result['product_draft']['id'] == first['product_draft']['id']
        assert result['product_draft']['name'] not in {'đây nha', 'đây nè', 'ảnh này nha'}
        assert result['product_draft']['price_vnd'] == 500000 and result['product_draft']['stock'] == 8
        assert len(provider.calls[-1]['images']) == 2
        assert result['facts']['ai_image_count'] == 2 and result['fallback_reason'] is None


def test_same_photo_with_new_request_ids_is_reused_without_filling_gallery(tmp_path):
    client, _, uploads = make_client(tmp_path)
    with client:
        photo = b'\xff\xd8\xfffront'
        first = gallery(client, None, [photo, photo]).json()['data']
        assert first['product_draft']['image_count'] == 1
        for _ in range(7):
            repeated = gallery(client, first['conversation_id'], [photo]).json()['data']
            assert repeated['product_draft']['id'] == first['product_draft']['id']
            assert repeated['product_draft']['image_count'] == 1
            assert repeated['facts']['new_image_count'] == 0
            assert repeated['facts']['image_indices'] == [0]
            assert repeated['facts']['duplicate_image_count'] == 1
        assert len(list(uploads.iterdir())) == 1


def test_duplicates_can_be_resent_when_gallery_is_full_and_keep_input_order(tmp_path):
    client, _, uploads = make_client(tmp_path)
    with client:
        photos = [b'\xff\xd8\xffphoto' + bytes([i]) for i in range(6)]
        first = gallery(client, None, photos).json()['data']
        request_id = str(uuid4())
        repeated = gallery(client, first['conversation_id'], [photos[4], photos[1], photos[4]], request_id)
        assert repeated.status_code == 201
        assert repeated.json()['data']['facts']['image_indices'] == [4, 1]
        assert repeated.json()['data']['product_draft']['image_count'] == 6
        assert len(list(uploads.iterdir())) == 6
        assert gallery(client, first['conversation_id'], [photos[4], photos[1], photos[4]], request_id).json() == repeated.json()


def test_unclear_photo_asks_for_the_item_and_keeps_commercial_facts(tmp_path):
    import sqlite3
    client, shop_path, _ = make_client(tmp_path)
    with client:
        provider = SemanticProvider({'clarification': 'Bạn muốn bán áo hay kính trong ảnh này?'})
        client.app.state.ai_provider = provider
        first = gallery(client, None, [b'\xff\xd8\xffunclear']).json()['data']
        conversation = first['conversation_id']
        initial = client.post('/api/v1/chat', json={'message': 'Giá: 5 xị; tồn: 8', 'conversation_id': conversation})
        assert initial.status_code == 200
        for _ in range(7):
            assert gallery(client, conversation, [b'\xff\xd8\xffunclear']).status_code == 201
        assert gallery(client, conversation, [b'\xff\xd8\xffanother-angle']).status_code == 201
        response = client.post('/api/v1/chat', json={'message': 'đây nha', 'conversation_id': conversation})
        assert response.status_code == 200
        result = response.json()['data']
        draft = result['product_draft']
        assert 'áo hay kính' in result['answer'] and result['fallback_reason'] is None
        assert draft['name'] is None and draft['status'] == 'collecting'
        assert draft['price_vnd'] == 500000 and draft['stock'] == 8
        assert len(provider.calls[-1]['images']) == 2
        assert provider.calls[-1]['facts']['last_question'] == initial.json()['data']['answer']
        assert client.post(f"/api/v1/product-drafts/{draft['id']}/publish").status_code == 409
        with sqlite3.connect(shop_path) as db:
            assert db.execute('SELECT count(*) FROM product').fetchone()[0] == 2


def test_failed_vision_attempt_does_not_mark_new_images_as_already_understood(tmp_path):
    from app.ai.contracts import AIProviderError

    class InterruptedVision(SemanticProvider):
        fail_next = False

        async def compose_listing(self, **kwargs):
            if self.fail_next:
                self.fail_next = False
                raise AIProviderError('provider_timeout', stage='generation')
            return await super().compose_listing(**kwargs)

    client, _, uploads = make_client(tmp_path)
    with client:
        provider = InterruptedVision({'name': 'Bàn phím Nova màu trắng',
            'description': 'Bàn phím Nova màu trắng.', 'category_id': 4})
        client.app.state.ai_provider = provider
        first = gallery(client, None, [b'\xff\xd8\xfffront']).json()['data']
        conversation = first['conversation_id']
        def say(message):
            response = client.post('/api/v1/chat', json={'message': message, 'conversation_id': conversation})
            assert response.status_code == 200
            return response.json()['data']
        say('Bàn phím Nova; giá: 500k; tồn: 8; tự viết mô tả')
        assert gallery(client, conversation, [b'\xff\xd8\xffback']).status_code == 201
        provider.fail_next = True
        failed = say('Bổ sung một góc khác')
        assert failed['fallback_reason'] == 'provider_timeout'
        assert 'ai_image_count' not in failed['facts']
        recovered = say('soạn lại bản nháp')
        assert recovered['fallback_reason'] is None
        assert recovered['facts']['ai_image_count'] == 2
        assert len(provider.calls[-1]['images']) == 2
        assert recovered['product_draft']['id'] == first['product_draft']['id']
        assert recovered['product_draft']['price_vnd'] == 500000 and recovered['product_draft']['stock'] == 8
        assert len(list(uploads.iterdir())) == 2


def test_adding_a_photo_preserves_unresolved_price_and_requires_a_clear_answer(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        provider = SemanticProvider({'name': 'Bàn phím Nova màu trắng',
            'description': 'Bàn phím Nova màu trắng.', 'category_id': 4})
        client.app.state.ai_provider = provider
        first = gallery(client, None, [b'\xff\xd8\xfffront']).json()['data']
        conversation = first['conversation_id']
        def say(message):
            response = client.post('/api/v1/chat', json={'message': message, 'conversation_id': conversation})
            assert response.status_code == 200
            return response.json()['data']
        assert say('Bàn phím Nova; giá: 990k; tồn: 8; tự viết mô tả')['product_draft']['status'] == 'ready'
        ambiguous = say('Giá bán để 500–600k nhé')
        assert ambiguous['facts']['pending_fields'] == ['price_vnd']
        uploaded = gallery(client, conversation, [b'\xff\xd8\xffback']).json()['data']
        assert uploaded['product_draft']['missing_fields'] == ['price_vnd']
        followup = say('đây nha')
        assert provider.calls[-1]['facts']['last_question'] == ambiguous['answer']
        assert followup['product_draft']['status'] == 'collecting'
        assert followup['product_draft']['price_vnd'] == 990000
        assert client.post(f"/api/v1/product-drafts/{first['product_draft']['id']}/publish").status_code == 409
        resolved = say('5 xị')
        assert resolved['product_draft']['status'] == 'ready'
        assert resolved['product_draft']['price_vnd'] == 500000
