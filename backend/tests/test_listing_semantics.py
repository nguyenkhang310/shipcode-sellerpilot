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


@pytest.mark.parametrize('message,expected', [
    ('Đăng bán Camera 4K, tồn kho 10', None),
    ('Giá của nó chưa chốt. Màn hình 4K, còn 20 cái', None),
    ('Giá vốn 100k, phí ship 20k', None),
    ('Giá của nó là 15k/trái và còn khoảng 10 trái', 15000),
    ('Giá mỗi quả là 15k, giá vốn 5k', 15000),
    ('Giá của nó là 15k, giá của món này 20k', None),
])
def test_natural_price_reference_does_not_treat_specs_or_costs_as_sale_price(message, expected):
    from app.services.product_drafts import _extract_labeled_price
    assert _extract_labeled_price(message) == expected


def test_posting_a_4k_camera_still_asks_for_a_real_sale_price(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        _, reply = upload_and_reply(client)
        draft = reply('Đăng bán camera 4K, tồn kho 10, tự viết mô tả giúp mình')['product_draft']
        assert draft['price_vnd'] is None
        assert 'price_vnd' in draft['missing_fields']


def test_gateway_restriction_explains_missing_ai_without_losing_draft_or_publishing(tmp_path):
    from app.ai.contracts import AIProviderError

    class RestrictedProvider(OfflineProvider):
        provider = 'opencode'
        model = 'glm-5.3-flash-free'

        async def compose_listing(self, **kwargs):
            raise AIProviderError('free_tier_restricted', stage='model_gateway')

    client, shop_path, upload_dir = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = RestrictedProvider()
        _, reply = upload_and_reply(client)
        result = reply('Đăng sản phẩm trong ảnh, bán 5 xị, còn 20 cái. Tự viết tên và mô tả.')
        draft = result['product_draft']
        assert result['mode'] == 'fallback'
        assert result['fallback_reason'] == 'free_tier_restricted'
        assert 'OpenCode đang chặn' in result['answer']
        assert 'Ảnh và thông tin bản nháp vẫn được giữ' in result['answer']
        assert 'chưa có sản phẩm nào được đăng' in result['answer']
        assert draft['price_vnd'] == 500000 and draft['stock'] == 20
        assert draft['status'] == 'collecting' and draft['published_product_id'] is None
        assert len(list(upload_dir.iterdir())) == 1
        assert client.get('/api/v1' + draft['preview_url']).status_code == 200
        with sqlite3.connect(shop_path) as connection:
            assert connection.execute('SELECT count(*) FROM product').fetchone()[0] == 2


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
        # The explicit seller phrase "bán 990k" is independently readable;
        # forged model values/evidence must not override it.
        assert result['product_draft']['price_vnd'] == 990000
        assert result['product_draft']['stock'] is None
        assert result['product_draft']['status'] == 'collecting'
        assert result['product_draft']['missing_fields'] == ['stock']
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
        result = reply('Để giá mềm hơn một chút nhé')
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


def test_slang_price_is_normalized_even_when_model_is_wrong_by_a_factor_of_ten(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = SemanticProvider({
            'name': 'Bàn phím Demo K87', 'name_evidence': 'bàn phím Demo K87',
            'description': 'Bàn phím màu đen dùng cho góc làm việc.', 'category_id': 4,
            'price_vnd': 50000, 'price_evidence': '5 xị', 'stock': 20, 'stock_evidence': '20 cái',
        })
        _, reply = upload_and_reply(client)
        result = reply('Đăng bàn phím Demo K87, bán 5 xị, kho còn 20 cái nhé.')
        assert result['product_draft']['price_vnd'] == 500000
        assert result['product_draft']['stock'] == 20
        assert result['product_draft']['status'] == 'ready'


def test_price_range_blocks_publishing_and_next_reply_resolves_the_pending_question(tmp_path):
    client, store, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CopyProvider()
        _, reply = upload_and_reply(client)
        ready = reply('Tên: Bàn phím Nova K75, giá: 990k, tồn kho: 20, mô tả: Bàn phím màu đen dùng cổng USB.')['product_draft']
        assert ready['status'] == 'ready'
        client.app.state.ai_provider = SemanticProvider({'price_vnd': 600000, 'price_evidence': '600k'})
        ambiguous = reply('Giá bán để 500–600k nhé')['product_draft']
        assert ambiguous['status'] == 'collecting'
        assert ambiguous['price_vnd'] == 990000
        assert ambiguous['missing_fields'] == ['price_vnd']
        assert client.post(f"/api/v1/product-drafts/{ready['id']}/publish").status_code == 409
        resolved = reply('5 xị')['product_draft']
        assert resolved['status'] == 'ready' and resolved['price_vnd'] == 500000
        assert resolved['name'] == ready['name'] and resolved['description'] == ready['description']
        with sqlite3.connect(store) as db:
            assert db.execute('SELECT count(*) FROM product').fetchone()[0] == 2


def test_natural_followup_only_asks_the_missing_stock(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = SemanticProvider({
            'name': 'Bàn phím Demo K87', 'description': 'Bàn phím màu đen dùng cho góc làm việc.',
            'category_id': 4, 'price_vnd': 500000, 'price_evidence': '5 xị',
            'next_question': 'Mẫu này bạn còn sẵn mấy cái để mình lên bản nháp?', 'next_question_fields': ['stock'],
        })
        _, reply = upload_and_reply(client)
        result = reply('Đăng bàn phím Demo K87 bán 5 xị nhé')
        assert result['product_draft']['missing_fields'] == ['stock']
        assert 'còn sẵn mấy cái' in result['answer']
        assert 'giá bán' not in result['answer']


def test_model_question_cannot_reask_price_that_was_already_provided(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = SemanticProvider({
            'name': 'Bàn phím Demo K87', 'description': 'Bàn phím màu đen dùng cho góc làm việc.',
            'category_id': 4, 'price_vnd': 500000, 'price_evidence': '5 xị',
            'next_question': 'Bạn bán giá bao nhiêu và còn mấy cái?', 'next_question_fields': ['price_vnd', 'stock'],
        })
        _, reply = upload_and_reply(client)
        result = reply('Đăng bàn phím Demo K87, giá 5 xị')
        assert result['product_draft']['price_vnd'] == 500000
        assert 'tồn kho' in result['answer'] and 'giá bao nhiêu' not in result['answer']


def test_pricing_advice_knows_draft_and_can_reuse_cost_from_its_seller_caption(tmp_path):
    from test_advisor import AdvisorAI
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = CopyProvider()
        _, reply = upload_and_reply(client)
        ready = reply('Tên: Bàn phím Nova K75, giá: 5 xị, tồn: 20, mô tả: Bàn phím màu đen. Giá vốn 3 xị.')['product_draft']
        assert ready['status'] == 'ready'
        advisor = AdvisorAI([{'topic': 'pricing', 'economics': [
            {'field': 'unit_cost_vnd', 'value': 300000, 'evidence': 'Giá vốn 3 xị'},
        ]}])
        client.app.state.ai_provider = advisor
        advice = reply('Mình chưa biết giá nên bán bao nhiêu, tư vấn giúp mình')
        assert advice['product_draft'] is None
        assert advice['facts']['draft_context']['name'] == ready['name']
        assert advice['facts']['pricing_analysis']['inputs']['unit_cost_vnd'] == 300000
        assert advice['facts']['pricing_analysis']['at_selling_price']['price_vnd'] == 500000
        assert advisor.contexts[0]['draft_seller_messages']


def test_slang_currency_reply_is_not_a_product_name(tmp_path):
    client, _, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        _, reply = upload_and_reply(client)
        draft = reply('năm xị')['product_draft']
        assert draft['name'] is None and draft['price_vnd'] == 500000
        assert draft['status'] == 'collecting'


def test_generated_listing_cannot_invent_condition_seals_authenticity_or_warranty():
    from app.ai.listing_contracts import ListingCopy, listing_validation_context
    from pydantic import ValidationError
    for claim in ['Sản phẩm mới', 'Hàng nguyên tem', 'Hàng chính hãng', 'Bảo hành 12 tháng']:
        with pytest.raises(ValidationError):
            ListingCopy.model_validate({'name': 'Bàn phím Demo K87', 'description': claim},
                context=listing_validation_context({'current_message': 'Bàn phím màu đen, bán 5 xị.'},
                    [{'role': 'assistant', 'content': claim}]))
    result = ListingCopy.model_validate({'description': 'Bảo hành 12 tháng'},
        context=listing_validation_context({'current_message': 'Bàn phím, bảo hành 12 tháng.'}, []))
    assert result.description == 'Bảo hành 12 tháng'


def test_seller_supplied_negative_condition_is_preserved_without_becoming_a_positive_claim():
    from app.ai.listing_contracts import ListingCopy, listing_validation_context
    from pydantic import ValidationError
    context = listing_validation_context({'current_message': 'Mô tả: Máy không mới, không bảo hành.'}, [])
    assert ListingCopy.model_validate({'description':'Máy không mới, không bảo hành.'},context=context).description
    with pytest.raises(ValidationError):
        ListingCopy.model_validate({'description':'Máy mới, bảo hành 12 tháng.'},context=context)


def test_text_request_starts_listing_then_images_attach_without_losing_facts(tmp_path):
    import base64
    client, path, _ = make_client(tmp_path)
    provider = SemanticProvider({'name': 'Bàn phím Nova K75 màu trắng', 'description': 'Bàn phím màu trắng dành cho bàn làm việc.',
                                 'category_id': 4, 'price_vnd': 500000, 'price_evidence': '5 xị', 'stock': 20, 'stock_evidence': '20 cái'})
    with client:
        client.app.state.ai_provider = provider
        result = client.post('/api/v1/chat', json={'message': 'Đăng bàn phím Nova K75 lên sàn, bán 5 xị, kho còn 20 cái, tự viết mô tả.'})
        assert result.status_code == 200, result.text
        data = result.json()['data']
        draft = data['product_draft']
        assert draft and draft['status'] == 'collecting'
        assert draft['preview_url'] == '' and draft['image_count'] == 0
        assert draft['missing_fields'] == ['image']
        assert 'ảnh' in data['answer']
        assert client.post(f"/api/v1/product-drafts/{draft['id']}/publish").status_code == 409
        uploaded = client.post('/api/v1/product-drafts/images-data', json={
            'images_base64': [base64.b64encode(b'\xff\xd8\xffphoto').decode()], 'conversation_id': data['conversation_id']})
        assert uploaded.status_code == 201, uploaded.text
        attached = uploaded.json()['data']['product_draft']
        assert attached['id'] == draft['id'] and attached['name'] == draft['name']
        assert attached['price_vnd'] == 500000 and attached['stock'] == 20
        result = client.post('/api/v1/chat', json={'message': 'đúng mẫu này nhé', 'conversation_id': data['conversation_id']})
        assert result.status_code == 200, result.text
        ready = result.json()['data']['product_draft']
        assert ready['status'] == 'ready'
        assert provider.calls[0]['images'] == [] and len(provider.calls[-1]['images']) == 1
        assert provider.calls[-1]['facts']['last_question']
        assert client.post(f"/api/v1/product-drafts/{draft['id']}/publish").status_code == 200
        with sqlite3.connect(path) as db:
            product = db.execute('SELECT name,price,stock,image_url FROM product ORDER BY id DESC LIMIT 1').fetchone()
            assert product[:3] == (draft['name'], 500000, 20)
            assert product[3].startswith('/static/')


def test_short_subject_is_expanded_by_model_and_deictic_reply_uses_image_context(tmp_path):
    client, _, _ = make_client(tmp_path)
    provider = SemanticProvider({'clarification': 'Bạn muốn bán món nào trong ảnh?'})
    with client:
        client.app.state.ai_provider = provider
        _, reply = upload_and_reply(client)
        first = reply('Đăng sản phẩm này lên giúp mình')
        assert first['product_draft']['name'] is None
        provider.result = {'name': 'Xe đạp màu đen', 'description': 'Xe đạp màu đen theo hình sản phẩm của shop.', 'category_id': 7}
        result = reply('xe đó')
        assert result['product_draft']['name'] == 'Xe đạp màu đen'
        assert result['product_draft']['price_vnd'] is None and result['product_draft']['stock'] is None
        assert len(provider.calls[-1]['images']) == 1
        assert 'món nào' in provider.calls[-1]['facts']['last_question']
        assert provider.calls[-1]['history'][-1]['content'] == 'xe đó'


def test_short_product_label_uses_model_to_write_copy_instead_of_just_echoing(tmp_path):
    client, _, _ = make_client(tmp_path)
    provider = SemanticProvider({'name': 'Bàn phím màu trắng cho góc làm việc',
        'description': 'Bàn phím màu trắng theo hình ảnh shop cung cấp.', 'category_id': 4})
    with client:
        client.app.state.ai_provider = provider
        _, reply = upload_and_reply(client)
        draft = reply('bàn phím')['product_draft']
        assert provider.calls and draft['name'] == provider.result['name']
        assert draft['description'] == provider.result['description']


@pytest.mark.parametrize('message', ['xe đó', 'cái này', 'ý mình là xe đó', 'mẫu kia'])
def test_model_cannot_return_a_context_reference_as_product_title(message):
    from app.ai.listing_contracts import ListingCopy
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ListingCopy.model_validate({'name': message})


@pytest.mark.parametrize('message', ['Đừng đăng sản phẩm này', 'Chưa muốn đăng sản phẩm', 'Nếu đăng sản phẩm thì sao?',
    'Hướng dẫn đăng sản phẩm', 'Có nên đăng sản phẩm lúc này không?', 'Lên kế hoạch đăng video TikTok', 'Đăng ký tài khoản'])
def test_advice_and_negation_do_not_create_a_product_draft(message):
    from app.services.chat_dispatch import listing_request
    assert not listing_request(message)
