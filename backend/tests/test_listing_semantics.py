import json
import sqlite3

import pytest

from test_product_drafts import CopyProvider, OfflineProvider, make_client, upload_and_reply


class SemanticProvider(CopyProvider):
    provider = 'opencode'
    model = 'semantic-test'

    def __init__(self, result):
        super().__init__()
        self.result = result

    async def compose_listing(self, *, facts, history, images):
        self.calls.append({'facts': facts, 'history': history, 'images': images})
        return json.dumps(self.result, ensure_ascii=False)


def test_natural_listing_collects_all_details_before_asking(tmp_path):
    message = 'Mình có bàn phím Nova K75 màu trắng, bán 990k, kho còn 20 cái, đăng giúp mình.'
    client, shop_path, _ = make_client(tmp_path)
    provider = SemanticProvider({
        'name': 'Bàn phím Nova K75 màu trắng', 'name_evidence': 'bàn phím Nova K75 màu trắng',
        'description': 'Bàn phím Nova K75 màu trắng, phù hợp góc làm việc của bạn.',
        'category_id': 4, 'price_vnd': 990000, 'price_evidence': '990k',
        'stock': 20, 'stock_evidence': '20 cái',
    })
    with client:
        client.app.state.ai_provider = provider
        _, reply = upload_and_reply(client)
        response = reply(message)
        draft = response['product_draft']
        assert provider.calls[0]['facts']['current_message'] == message
        assert draft['status'] == 'ready'
        assert draft['price_vnd'] == 990000 and draft['stock'] == 20
        assert draft['name'] == 'Bàn phím Nova K75 màu trắng'
        assert draft['missing_fields'] == []
        assert draft['published_product_id'] is None
        assert 'bao nhiêu' not in response['answer']
        with sqlite3.connect(shop_path) as connection:
            assert connection.execute('SELECT count(*) FROM product').fetchone()[0] == 2


def test_caption_multiline_and_alternate_title_label_work_without_model(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        _, reply = upload_and_reply(client)
        description = 'Thiết kế gọn nhẹ.\nKết nối USB-C.\nĐóng gói kèm dây cáp.'
        result = reply('Tiêu đề: Bàn phím Nova K75\nGiá bán: 990k\nTồn kho: 0\nNgành hàng: Máy Tính & Laptop\nCaption: ' + description)
        draft = result['product_draft']
        assert draft['status'] == 'ready'
        assert draft['description'] == description
        assert draft['price_vnd'] == 990000 and draft['stock'] == 0
        assert result['fallback_reason'] is None


def test_ready_draft_accepts_natural_price_and_stock_correction_together(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        _, reply = upload_and_reply(client)
        original = reply('Tên: Bàn phím Nova K75, giá: 990k, tồn kho: 20, mô tả: Bàn phím màu trắng dành cho bàn làm việc.')['product_draft']
        assert original['status'] == 'ready'
        provider = SemanticProvider({'price_vnd': 850000, 'price_evidence': '850 nghìn',
                                     'stock': 12, 'stock_evidence': '12 chiếc'})
        client.app.state.ai_provider = provider
        corrected = reply('Để 850 nghìn thôi, còn 12 chiếc nhé')['product_draft']
        assert corrected['status'] == 'ready'
        assert (corrected['price_vnd'], corrected['stock']) == (850000, 12)
        assert corrected['name'] == original['name'] and corrected['sku'] == original['sku']
        assert corrected['description'] == original['description']


@pytest.mark.parametrize('price_evidence,stock_evidence', [
    (None, None), ('500k', '80 cái'), ('990k và 20', '20 cái và 990'),
])
def test_model_cannot_invent_or_misquote_commercial_facts(tmp_path, price_evidence, stock_evidence):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = SemanticProvider({
            'name': 'Bàn phím Nova K75', 'description': 'Bàn phím Nova K75 màu trắng trong ảnh.',
            'category_id': 4, 'price_vnd': 500000, 'price_evidence': price_evidence,
            'stock': 80, 'stock_evidence': stock_evidence,
        })
        _, reply = upload_and_reply(client)
        result = reply('Đăng bàn phím Nova K75, bán 990k và 20 cái nhé')
        assert result['product_draft']['price_vnd'] is None
        assert result['product_draft']['stock'] is None
        assert result['product_draft']['status'] == 'collecting'
        assert result['product_draft']['missing_fields'] == ['price_vnd', 'stock']
        assert 'tên' not in result['answer'].lower()


def test_supplied_description_is_preserved_and_only_stock_is_asked(tmp_path):
    description = 'Bàn phím màu trắng.\nKèm dây USB-C, sử dụng qua cổng USB.'
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = SemanticProvider({
            'name': 'Bàn phím Nova K75', 'name_evidence': 'bàn phím Nova K75',
            'description': 'Bàn phím Nova K75 với thiết kế màu trắng.',
            'description_evidence': description, 'price_vnd': 990000,
            'price_evidence': '990k', 'category_id': 4,
        })
        _, reply = upload_and_reply(client)
        result = reply('Đăng bàn phím Nova K75 giúp mình, bán 990k. Nội dung giữ nguyên nhé:\n' + description)
        draft = result['product_draft']
        assert draft['description'] == description
        assert draft['missing_fields'] == ['stock']
        assert 'tồn kho' in result['answer']
        assert 'Giá bán' not in result['answer']


def test_price_quote_cannot_turn_cost_into_selling_price(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = SemanticProvider({
            'name': 'Bàn phím Nova K75', 'description': 'Bàn phím màu trắng dùng qua cổng USB.',
            'category_id': 4, 'price_vnd': 500000, 'price_evidence': '500k',
            'stock': 20, 'stock_evidence': '20 cái',
        })
        _, reply = upload_and_reply(client)
        draft = reply('Mình bán bàn phím Nova K75, giá vốn 500k, kho còn 20 cái. Chưa chốt giá bán.')['product_draft']
        assert draft['price_vnd'] is None
        assert draft['stock'] == 20
        assert draft['missing_fields'] == ['price_vnd']


def test_quantity_reply_does_not_fill_the_next_missing_price(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CopyProvider()
        _, reply = upload_and_reply(client)
        reply('Bàn phím Nova K75')
        client.app.state.ai_provider = SemanticProvider({'stock': 20, 'stock_evidence': '20 cái'})
        draft = reply('Mình còn 20 cái nhé')['product_draft']
        assert draft['stock'] == 20 and draft['price_vnd'] is None


def test_long_caption_is_not_truncated_and_posting_instruction_is_excluded(tmp_path):
    client, _, _ = make_client(tmp_path)
    description = ('Bàn phím màu đen, kết nối USB.\n' * 80).strip()
    with client:
        client.app.state.ai_provider = OfflineProvider()
        _, reply = upload_and_reply(client)
        draft = reply('Tên: Bàn phím Nova K75\nGiá: 990k\nTồn: 20\nNgành: Máy Tính & Laptop\nMô tả: ' + description + '\nĐăng giúp mình nhé.')['product_draft']
        assert draft['status'] == 'ready'
        assert draft['description'] == description


def test_failed_natural_edit_never_claims_the_draft_was_updated(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        _, reply = upload_and_reply(client)
        reply('Tên: Bàn phím Nova K75, giá: 990k, tồn: 20, mô tả: Bàn phím màu đen dùng cổng USB.')
        result = reply('Để 850 nghìn thôi nhé')
        assert result['product_draft']['price_vnd'] == 990000
        assert result['fallback_reason'] == 'provider_unavailable'
        assert 'chưa xử lý được' in result['answer']
        assert 'đã cập nhật' not in result['answer']


def test_fractional_stock_is_not_silently_rounded(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CopyProvider()
        _, reply = upload_and_reply(client)
        reply('Bàn phím Nova K75')
        reply('990k')
        result = reply('20.5')
        assert result['product_draft']['stock'] is None
        assert 'số lượng' in result['answer']
