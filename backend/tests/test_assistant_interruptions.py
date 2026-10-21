"""Short conversation turns must not overwrite work in progress."""
import pytest

from test_product_drafts import CopyProvider, make_client
from app.models.product_draft import ProductDraft


def draft_values(client, identifier):
    with client.app.state.session_factory() as session:
        draft = session.get(ProductDraft, identifier)
        return {field: getattr(draft, field) for field in ('name', 'description', 'price_vnd', 'stock', 'status')}


@pytest.mark.parametrize('message', ['Xin chào!', 'cảm ơn nhé', 'ok', 'bạn là ai'])
def test_small_talk_preserves_active_listing_and_can_resume(tmp_path, message):
    client, _, _ = make_client(tmp_path)
    with client:
        provider = CopyProvider()
        client.app.state.ai_provider = provider
        first = client.post('/api/v1/chat', json={'message': 'Đăng sản phẩm mới lên shop'}).json()['data']
        conversation = first['conversation_id']
        draft_id = first['product_draft']['id']
        before = draft_values(client, draft_id)
        reply = client.post('/api/v1/chat', json={'message': message, 'conversation_id': conversation})
        assert reply.status_code == 200
        assert reply.json()['data']['tool'] not in {'update_product_draft', 'publish_product'}
        assert draft_values(client, draft_id) == before
        resumed = client.post('/api/v1/chat', json={
            'message': 'Tên: Bàn phím Nova K75; giá: 500k; tồn: 10', 'conversation_id': conversation,
        }).json()['data']
        assert resumed['product_draft']['id'] == draft_id
        assert resumed['product_draft']['price_vnd'] == 500000


def test_thanks_does_not_answer_pending_product_edit_target(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        first = client.post('/api/v1/chat', json={'message': 'Sửa tiêu đề thành "Điện thoại nhỏ gọn"'}).json()['data']
        assert first['facts']['missing_fields'] == ['sku']
        reply = client.post('/api/v1/chat', json={
            'message': 'cảm ơn', 'conversation_id': first['conversation_id'],
        }).json()['data']
        assert reply['intent'] == 'unknown'
        assert reply['fallback_reason'] is None
        assert 'sản phẩm nào' not in reply['answer']
        resumed = client.post('/api/v1/chat', json={
            'message': 'SKU SEED-PHONE', 'conversation_id': first['conversation_id'],
        }).json()['data']
        assert resumed['product_edit_proposal']['changes'][0]['after'] == 'Điện thoại nhỏ gọn'


def test_casual_change_of_topic_cannot_become_a_draft_title(tmp_path):
    from test_advisor import AdvisorAI
    client, _, _ = make_client(tmp_path)
    with client:
        first = client.post('/api/v1/chat', json={'message': 'Đăng sản phẩm mới'}).json()['data']
        before = draft_values(client, first['product_draft']['id'])
        client.app.state.ai_provider = AdvisorAI([])
        reply = client.post('/api/v1/chat', json={
            'message': 'Hôm nay mình hơi mệt, nói chuyện chút đi', 'conversation_id': first['conversation_id'],
        }).json()['data']
        assert reply['mode'] == 'ai' and reply['product_draft'] is None
        assert draft_values(client, first['product_draft']['id']) == before
