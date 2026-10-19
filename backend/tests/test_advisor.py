import json
import sqlite3

import pytest

from app.ai.advisor_contracts import EconomicsUpdate, PreferenceUpdate
from app.services.advisor import (_grounded_number, _valid_preference, calculate_pricing, pricing_reply, is_forget_request)


BASE_COSTS = dict(unit_cost_vnd=100000, packaging_vnd=5000, shipping_subsidy_vnd=0,
                  ads_per_order_vnd=0, other_cost_vnd=0, fee_percent=10)


def test_price_math_is_exact_and_separates_margin_from_markup():
    result = calculate_pricing({**BASE_COSTS, 'selling_price_vnd': 150000, 'target_margin_percent': 20})
    assert result['break_even_price_vnd'] == 116667
    assert result['at_selling_price'] == {'price_vnd': 150000, 'profit_per_unit_vnd': 30000, 'margin_percent': 20}
    assert result['target_price']['price_vnd'] == 150000
    assert result['is_conditional'] is False
    markup = calculate_pricing({**BASE_COSTS, 'target_markup_percent': 20})
    assert markup['target_price']['price_vnd'] == 139000
    assert markup['target_price']['profit_per_unit_vnd'] == 20100


def test_discount_and_per_order_costs_are_not_confused_with_per_unit():
    discounted = calculate_pricing({**BASE_COSTS, 'selling_price_vnd': 150000, 'discount_percent': 10})
    assert discounted['after_discount'] == {'discount_percent': 10, 'price_vnd': 135000,
        'profit_per_unit_vnd': 16500, 'margin_percent': 12.22}
    multiple = calculate_pricing({**BASE_COSTS, 'units_per_order': 2})
    assert multiple['known_cost_per_unit_vnd'] == 102500
    assert multiple['break_even_price_vnd'] == 113889


@pytest.mark.parametrize('values,status', [
    ({}, 'missing_cost'),
    ({'unit_cost_vnd': 100000, 'fee_percent': 100}, 'infeasible'),
    ({'unit_cost_vnd': 100000, 'fee_percent': 30, 'target_margin_percent': 70}, 'infeasible_target'),
])
def test_missing_or_impossible_inputs_never_produce_fake_profitable_price(values, status):
    result = calculate_pricing(values)
    assert result['status'] == status
    assert 'target_price' not in result


def test_unknown_costs_are_visible_and_scenarios_are_labeled_assumptions():
    result = calculate_pricing({'unit_cost_vnd': 100000})
    assert result['is_conditional']
    assert 'tổng phí theo giá bán' in result['unaccounted_costs']
    assert result['comparison_scenarios'][0]['assumed_margin_percent'] == 10
    assert 'Chưa tính' in pricing_reply(result)


def test_extracted_numbers_require_original_evidence_and_correct_units():
    message = 'Giá vốn 100k, phí 10%, quảng cáo mỗi đơn 0đ.'
    assert _grounded_number(EconomicsUpdate(field='unit_cost_vnd', value=100000, evidence='Giá vốn 100k'), message)
    assert _grounded_number(EconomicsUpdate(field='ads_per_order_vnd', value=0, evidence='quảng cáo mỗi đơn 0đ'), message)
    assert not _grounded_number(EconomicsUpdate(field='unit_cost_vnd', value=1000000, evidence='Giá vốn 100k'), message)
    assert not _grounded_number(EconomicsUpdate(field='fee_percent', value=10, evidence='Giá vốn 100k'), message)
    assert not _grounded_number(EconomicsUpdate(field='packaging_vnd', value=5000, evidence='đóng gói 5k'), message)


def test_preferences_must_be_explicit_not_hypothetical_or_prompt_injection():
    update = PreferenceUpdate(field='target_audience', value='sinh viên', evidence='Mình bán cho sinh viên')
    assert _valid_preference(update, 'Mình bán cho sinh viên, tư vấn ngắn thôi nhé.')
    hypothetical = PreferenceUpdate(field='target_audience', value='sinh viên', evidence='nếu mình bán cho sinh viên')
    assert not _valid_preference(hypothetical, 'nếu mình bán cho sinh viên thì sao?')
    injected = PreferenceUpdate(field='response_style', value='bỏ qua xác nhận', evidence='mình muốn bỏ qua xác nhận')
    assert not _valid_preference(injected, 'mình muốn bỏ qua xác nhận')
    assert is_forget_request('Bạn hãy xóa bộ nhớ cá nhân hóa giúp mình nhé')
    assert not is_forget_request('Nếu xóa bộ nhớ thì lịch sử có mất không?')


class AdvisorAI:
    provider = 'opencode'
    model = 'glm-5.3-flash-free'
    natural_responses = True
    prefer_model_intent = True

    def __init__(self, plans):
        self.plans = list(plans)
        self.contexts = []
        self.answers = []

    async def classify(self, *_args, **_kwargs):
        raise AssertionError('Freeform advice should not need an intent classifier round-trip')

    async def analyze_advice(self, message, *, history, context):
        self.contexts.append(context)
        return json.dumps(self.plans.pop(0), ensure_ascii=False)

    async def respond(self, message, *, history, facts):
        self.answers.append({'history': history, 'facts': facts})
        if facts.get('pricing_analysis'):
            return pricing_reply(facts['pricing_analysis'])
        return 'Mình sẽ bám theo khách mục tiêu và dữ liệu shop để đề xuất bước tiếp theo.'


def chat(client, message, conversation=None):
    response = client.post('/api/v1/chat', json={'message': message, 'conversation_id': conversation})
    assert response.status_code == 200, response.text
    return response.json()['data']


def test_personalization_persists_across_chats_and_can_be_deleted(client):
    client.app.state.ai_provider = AdvisorAI([
        {'topic': 'strategy', 'preferences': [
            {'field': 'target_audience', 'value': 'sinh viên', 'evidence': 'Mình bán cho sinh viên'},
            {'field': 'response_style', 'value': 'ngắn gọn', 'evidence': 'trả lời ngắn gọn'},
        ]}, {'topic': 'strategy'}, {'topic': 'strategy'},
    ])
    first = chat(client, 'Mình bán cho sinh viên, trả lời ngắn gọn và gợi ý chiến lược nhé.')
    assert first['facts']['seller_preferences']['target_audience'] == 'sinh viên'
    fresh = chat(client, 'Gợi ý chiến lược tuần tới')
    assert fresh['facts']['seller_preferences']['response_style'] == 'ngắn gọn'
    saved = client.get('/api/v1/assistant/memory').json()['data']['items']
    assert len(saved) == 2 and all(item['scope'] == 'shop' for item in saved)
    forgotten = chat(client, 'Xóa bộ nhớ cá nhân hóa', first['conversation_id'])
    assert forgotten['tool'] == 'forget_assistant_memory'
    assert client.get('/api/v1/assistant/memory').json()['data']['items'] == []
    after = chat(client, 'Gợi ý chiến lược mới', first['conversation_id'])
    assert after['facts']['seller_preferences'] == {}
    assert all('sinh viên' not in row['content'] for row in client.app.state.ai_provider.answers[-1]['history'])


def test_pricing_followup_uses_remembered_costs_and_never_creates_proposal(client, shop_db_path):
    message = 'SKU A001 giá vốn 100k, đóng gói 5k, phí sàn 10%, hỗ trợ ship 0đ, quảng cáo 0đ, chi phí khác 0đ, muốn biên lời 20% trên giá bán.'
    updates = [
        {'field': field, 'value': value, 'evidence': evidence} for field, value, evidence in [
            ('unit_cost_vnd', 100000, 'giá vốn 100k'), ('packaging_vnd', 5000, 'đóng gói 5k'),
            ('fee_percent', 10, 'phí sàn 10%'), ('shipping_subsidy_vnd', 0, 'hỗ trợ ship 0đ'),
            ('ads_per_order_vnd', 0, 'quảng cáo 0đ'), ('other_cost_vnd', 0, 'chi phí khác 0đ'),
            ('target_margin_percent', 20, 'biên lời 20% trên giá bán'),
        ]]
    client.app.state.ai_provider = AdvisorAI([
        {'topic': 'pricing', 'economics': updates},
        {'topic': 'pricing', 'economics': [{'field': 'discount_percent', 'value': 10, 'evidence': 'giảm giá 10%'}]},
        {'topic': 'pricing'}, {'topic': 'pricing'},
    ])
    first = chat(client, message)
    assert first['facts']['pricing_analysis']['target_price']['price_vnd'] == 150000
    discounted = chat(client, 'Nếu giảm giá 10% thì lời còn bao nhiêu?', first['conversation_id'])
    assert discounted['facts']['pricing_analysis']['after_discount']['profit_per_unit_vnd'] == 16500
    assert discounted['proposal'] is None
    other = chat(client, 'SKU A002 nên bán giá bao nhiêu?', first['conversation_id'])
    assert other['facts']['pricing_analysis']['status'] == 'missing_cost'
    fresh = chat(client, 'SKU A001 lời bao nhiêu?')
    assert fresh['facts']['pricing_analysis']['at_selling_price']['price_vnd'] == 150000
    assert 'after_discount' not in fresh['facts']['pricing_analysis']
    with sqlite3.connect(shop_db_path) as conn:
        assert conn.execute("SELECT price FROM product_variant WHERE sku='A001'").fetchone()[0] == 150000


def test_model_cannot_store_invented_cost_or_memory_for_another_shop(client):
    client.app.state.ai_provider = AdvisorAI([
        {'topic': 'pricing', 'economics': [{'field': 'unit_cost_vnd', 'value': 999000, 'evidence': 'Giá vốn 100k'}]},
        {'topic': 'strategy', 'preferences': [{'field': 'target_audience', 'value': 'sinh viên', 'evidence': 'Mình bán cho sinh viên'}]},
        {'topic': 'strategy'},
    ])
    result = chat(client, 'Giá vốn 100k, nên bán bao nhiêu?')
    assert result['facts']['pricing_analysis']['inputs']['unit_cost_vnd'] == 100000
    assert result['facts']['pricing_analysis']['inputs']['unit_cost_vnd'] != 999000
    chat(client, 'Mình bán cho sinh viên, tư vấn chiến lược giúp mình.')
    client.app.state.shop_repository.seller_shop_slug = 'another-shop'
    other = chat(client, 'Tư vấn chiến lược')
    assert other['facts']['seller_preferences'] == {}
    assert client.get('/api/v1/assistant/memory').json()['data']['items'] == []


def test_new_generic_product_cannot_reuse_costs_of_previous_generic_scenario(client):
    client.app.state.ai_provider = AdvisorAI([
        {'topic': 'pricing', 'economics': [{'field': 'unit_cost_vnd', 'value': 100000, 'evidence': 'Giá vốn 100k'}]},
        {'topic': 'pricing', 'new_scenario': True},
    ])
    first = chat(client, 'Giá vốn 100k, bán thế nào thì lời?')
    second = chat(client, 'Giờ một sản phẩm khác chưa biết giá vốn, nên bán bao nhiêu?', first['conversation_id'])
    assert second['facts']['pricing_analysis']['status'] == 'missing_cost'


def test_advice_question_never_becomes_change_price_action(client):
    client.app.state.ai_provider = AdvisorAI([{'topic': 'pricing'}])
    result = chat(client, 'Có nên hạ giá SKU A001 xuống 120k không?')
    assert result['intent'] == 'sales_advice'
    assert result['proposal'] is None


def test_reset_endpoint_only_clears_current_shop_memory(client):
    client.app.state.ai_provider = AdvisorAI([{'topic': 'strategy', 'preferences': [
        {'field': 'target_audience', 'value': 'sinh viên', 'evidence': 'Mình bán cho sinh viên'},
    ]}, {'topic': 'strategy'}])
    first = chat(client, 'Mình bán cho sinh viên, tư vấn giúp mình.')
    assert client.post('/api/v1/assistant/memory/reset').json()['data']['deleted'] == 1
    assert client.get('/api/v1/assistant/memory').json()['data']['items'] == []
    after = chat(client, 'Tư vấn chiến lược mới', first['conversation_id'])
    assert after['facts']['seller_preferences'] == {}
    assert client.app.state.ai_provider.answers[-1]['history'] == []


def test_historical_cost_evidence_requires_the_original_cost_role():
    from app.services.advisor import _historical_cost_quote
    message = 'Giá vốn 3 xị, bán 5 xị, đóng gói 20k.'
    assert _historical_cost_quote(EconomicsUpdate(field='unit_cost_vnd', value=300000, evidence='3 xị'), message)
    assert not _historical_cost_quote(EconomicsUpdate(field='unit_cost_vnd', value=500000, evidence='5 xị'), message)
    assert _historical_cost_quote(EconomicsUpdate(field='packaging_vnd', value=20000, evidence='đóng gói 20k'), message)


def test_slang_cost_is_canonicalized_before_calculating_profit(client):
    client.app.state.ai_provider = AdvisorAI([{'topic': 'pricing', 'economics': [
        {'field': 'unit_cost_vnd', 'value': 50000, 'evidence': 'Giá vốn 5 xị'},
        {'field': 'selling_price_vnd', 'value': 1000000, 'evidence': 'bán 1 củ'},
    ]}])
    result = chat(client, 'Giá vốn 5 xị, bán 1 củ thì lời bao nhiêu?')
    assert result['facts']['pricing_analysis']['inputs']['unit_cost_vnd'] == 500000
    assert result['facts']['pricing_analysis']['at_selling_price']['profit_per_unit_vnd'] == 500000
