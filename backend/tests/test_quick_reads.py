from datetime import date

import pytest

from app.ai.fallback import parse_fallback
from app.ai.quick_reads import quick_read, simple_pricing_read
from app.services.chat import is_exact_fact_question
from test_advisor import chat

TODAY = date(2026, 10, 20)


@pytest.mark.parametrize('message,intent', [
    ('Nay shop sao rồi?', 'shop_summary'),
    ('Bạn ơi, cho mình xem doanh thu hôm nay với nhé', 'shop_summary'),
    ('Hom nay chot duoc may don?', 'shop_summary'),
    ('Giúp mình xem tổng doanh số 7 ngày qua đi', 'shop_summary'),
    ('Shop mình bán được bao nhiêu tiền hôm qua?', 'shop_summary'),
    ('Shop mình còn bao nhiêu sản phẩm?', 'inventory_query'),
    ('Bạn ơi, kiểm tra kho giúp mình nhé', 'inventory_query'),
    ('Món nào gần hết hàng?', 'inventory_query'),
    ('Xem các mặt hàng hết hàng đi', 'inventory_query'),
    ('SKU A001 còn mấy cái?', 'inventory_query'),
    ('SKU SEED-PHONE còn mấy cái?', 'inventory_query'),
    ('Kiểm tra mã A001 tồn bao nhiêu chiếc với', 'inventory_query'),
])
def test_read_paraphrases_are_normalized_and_complete(message, intent):
    direct = quick_read(message, today=TODAY)
    assert direct is not None and direct.intent == intent
    parsed = parse_fallback(message, today=TODAY)
    assert parsed == direct and is_exact_fact_question(message, parsed)


@pytest.mark.parametrize('message', [
    'Doanh thu hôm nay thấp, phân tích vì sao',
    'Xem kho rồi đăng sản phẩm này cho mình',
    'Hôm nay shop sao rồi và nên làm gì?',
    'Giả sử doanh thu hôm nay là 5 triệu thì sao?',
    'Đừng xem doanh thu hôm nay',
    'Doanh thu hôm qua so với hôm nay',
    'Tồn kho hôm qua',
    'Sửa giá SKU A001 còn 5 xị',
    'Viết mô tả cho SKU A001',
    'Đăng sản phẩm này lên shop',
])
def test_analysis_writes_negation_comparison_and_history_are_not_quick_reads(message):
    assert quick_read(message, today=TODAY) is None


@pytest.mark.parametrize('message,threshold', [
    ('Sản phẩm còn dưới 5 cái', 4), ('Sản phẩm còn không quá 5 cái', 5), ('Hết hàng', 0),
])
def test_stock_threshold_preserves_strict_and_inclusive_meaning(message, threshold):
    assert quick_read(message, today=TODAY).low_stock_threshold == threshold


def test_date_slots_are_explicit():
    assert quick_read('Chốt được mấy đơn hôm qua?', today=TODAY).day == date(2026, 10, 19)
    assert quick_read('Doanh số 7 ngày qua', today=TODAY).days == 7
    assert quick_read('Doanh số 30 ngày qua', today=TODAY).days == 30


class NoNetwork:
    provider = 'gemini'
    model = 'fixture'
    natural_responses = True
    prefer_direct_facts = True

    async def classify(self, *args, **kwargs):
        raise AssertionError('Simple Vietnamese read must not classify remotely')

    async def respond(self, *args, **kwargs):
        raise AssertionError('Simple Vietnamese read must not generate remotely')

    async def prepare_advice(self, *args, **kwargs):
        raise AssertionError('Simple Vietnamese read must not extract remotely')


@pytest.mark.parametrize('message', [
    'Nay shop sao rồi?', 'Hom nay chot duoc may don?', 'Bạn ơi, kiểm tra kho giúp mình nhé',
    'Món nào gần hết hàng?', 'SKU A001 còn mấy cái?', 'chao ban', 'cam on nha',
])
def test_api_answers_quick_reads_with_zero_inference(client, message):
    client.app.state.ai_provider = NoNetwork()
    data = chat(client, message)
    assert data['provider'] == 'deterministic_parser' and data['fallback_reason'] is None
    assert data['answer'] and data['mode'] == 'ai'


def test_selected_sku_is_not_inherited_by_general_report(client):
    client.app.state.ai_provider = NoNetwork()
    selected = chat(client, 'SKU A001 còn mấy cái?')
    result = chat(client, 'Nay shop sao rồi?', selected['conversation_id'])
    assert result['intent'] == 'shop_summary' and result['tool'] == 'get_shop_summary'
    assert 'sku' not in result['facts']


@pytest.mark.parametrize('message,expected', [
    ('Giá vốn 5 xị, đóng gói 20k mỗi đơn, phí sàn 10%. Nếu bán 1 củ thì còn lời bao nhiêu?', True),
    ('Giá vốn 100k, bán 150k thì lời bao nhiêu?', True),
    ('Giá vốn 100k, bán 150k thì lời bao nhiêu và nên quay video thế nào?', False),
    ('Giá vốn 100k, so sánh bán 150k và 200k', False),
])
def test_pure_profit_question_is_separate_from_strategy(message, expected):
    assert simple_pricing_read(message) == expected


def test_exact_pricing_after_validated_extraction_does_not_call_model_again(client):
    from test_chat_context import PreparedAI
    class ExactPricing(PreparedAI):
        prefer_direct_pricing = True
        async def respond(self, *args, **kwargs):
            raise AssertionError('The verified calculation already contains the answer')
    provider = ExactPricing({'topic': 'pricing', 'economics': [
        {'field': 'unit_cost_vnd', 'value': 500000, 'evidence': 'Giá vốn 5 xị'},
        {'field': 'selling_price_vnd', 'value': 1000000, 'evidence': 'bán 1 củ'},
    ]})
    client.app.state.ai_provider = provider
    result = chat(client, 'Giá vốn 5 xị, bán 1 củ thì lời bao nhiêu?')
    assert len(provider.preparations) == 1 and result['tool'] == 'calculate_pricing'
    assert result['facts']['pricing_analysis']['at_selling_price']['profit_per_unit_vnd'] == 500000
    assert '500.000đ' in result['answer']
