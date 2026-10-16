import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.ai.context import bounded_history
from app.ai.fallback import parse_fallback, reporting_days
from app.services.chat import reply_issue
from app.services.conversations import history_messages
from test_advisor import AdvisorAI, chat


def test_history_preserves_information_at_end_of_long_seller_message():
    message = 'Mô tả sản phẩm. ' * 150 + '\nGiá bán 990k, tồn kho 20, màu trắng.'
    runs = [SimpleNamespace(tool_name=None, message=message, answer='Mình đã nhận thông tin.',
                            intent='sales_advice', mode='ai', fallback_reason=None)]
    rows = history_messages(runs)
    assert rows[0]['content'] == message
    assert 'Giá bán 990k, tồn kho 20, màu trắng.' in rows[0]['content']


def test_history_budget_keeps_recent_complete_messages_and_discards_error_boilerplate():
    rows = [{'role': 'user', 'content': str(i) * 4000} for i in range(9)]
    result = bounded_history(rows, budget=18000)
    assert len(result) == 4 and result[-1] == rows[-1]
    assert all(len(row['content']) == 4000 for row in result)
    failed = SimpleNamespace(tool_name=None, message='Sao không kết nối?',
        answer='Mình chưa kết nối được Muse Spark.', intent='unknown', mode='fallback', fallback_reason='invalid_response')
    assert history_messages([failed]) == [{'role': 'user', 'content': failed.message}]


@pytest.mark.parametrize('message,expected', [
    ('Phân tích doanh số trong 30 ngày qua', 30),
    ('Phân tích 14 ngày gần đây rồi lập kế hoạch 7 ngày tới', 14),
    ('Tư vấn việc nên ưu tiên hôm nay', 1),
    ('Lập kế hoạch 7 ngày tới', None),
])
def test_reporting_period_does_not_confuse_future_plan_horizon(message, expected):
    assert reporting_days(message) == expected
    assert parse_fallback(message, today=date(2026, 10, 17)).days == expected


def test_advice_followup_keeps_period_until_seller_explicitly_changes_it(client):
    client.app.state.ai_provider = AdvisorAI([{'topic': 'strategy'}] * 3)
    first = chat(client, 'Phân tích 30 ngày qua và tư vấn chiến lược')
    assert first['facts']['period']['days'] == 30
    second = chat(client, 'Vậy nên ưu tiên bước nào trước?', first['conversation_id'])
    assert second['facts']['period']['days'] == 30
    third = chat(client, 'Còn hôm nay thì sao?', first['conversation_id'])
    assert third['facts']['period']['days'] == 1


def test_connection_question_uses_one_generation_with_current_shop_facts(client):
    class AI(AdvisorAI):
        async def analyze_advice(self, *_args, **_kwargs):
            raise AssertionError('A connection question does not require price/preference extraction')
        async def respond(self, message, *, history, facts):
            assert facts['inventory'] and facts['today']
            return 'Mình vẫn đang đọc được số liệu shop.'
    client.app.state.ai_provider = AI([])
    result = chat(client, 'Sao vậy, ko kết nối được à?')
    assert result['mode'] == 'ai' and result['fallback_reason'] is None


def test_conditional_advice_is_allowed_but_actual_unexecuted_write_stays_blocked():
    assert reply_issue('Nếu bạn đã đăng sản phẩm, hãy kiểm tra lại ảnh.') is None
    assert reply_issue('Khi đã cập nhật giá, bạn nên theo dõi số đơn.') is None
    assert reply_issue('Nếu bạn muốn, mình đã cập nhật giá cho bạn.') == 'unexecuted_write_claim'
    assert reply_issue('Mình đã đăng sản phẩm lên shop.') == 'unexecuted_write_claim'


def test_zero_orders_are_not_evidence_that_the_shop_is_new():
    assert reply_issue('Shop mới nên chưa có đơn là bình thường.', {'shop': {}, 'today': {'order_count': 0}}) == 'unsupported_shop_age'
    assert reply_issue('Shop mới nên cần ưu tiên nội dung.', {'shop': {}}, seller_context='Mình mới mở shop.') is None
    assert reply_issue('Nếu shop mới mở, bạn có thể bắt đầu từ nội dung.', {'shop': {}}) is None


def test_pricing_rewrite_cannot_invent_a_currency_amount_or_change_thousands_to_millions():
    facts = {'pricing_analysis': {'inputs': {'selling_price_vnd': 900000},
        'at_selling_price': {'profit_per_unit_vnd': 290000}}}
    assert reply_issue('Bán **900.000đ**, lời **290k**.', facts) is None
    assert reply_issue('Bán 900k, lời 290 triệu.', facts) == 'unsupported_pricing_amount'
    assert reply_issue('Bạn có thể lời 400k.', facts) == 'unsupported_pricing_amount'


def test_incorrect_profit_copy_falls_back_to_the_exact_backend_calculation(client):
    class WrongProfit(AdvisorAI):
        calls = 0
        async def respond(self, *_args, **_kwargs):
            self.calls += 1
            return 'Bạn sẽ lời 50 triệu mỗi sản phẩm.'
    provider = WrongProfit([{'topic': 'pricing', 'economics': [
        {'field': 'unit_cost_vnd', 'value': 100000, 'evidence': 'Giá vốn 100k'},
        {'field': 'selling_price_vnd', 'value': 150000, 'evidence': 'bán 150k'},
    ]}])
    client.app.state.ai_provider = provider
    result = chat(client, 'Giá vốn 100k, bán 150k thì lời bao nhiêu?')
    assert provider.calls == 2 and result['mode'] == 'fallback'
    assert result['facts']['pricing_analysis']['at_selling_price']['profit_per_unit_vnd'] == 50000
    assert '50.000đ' in result['answer'] and '50 triệu' not in result['answer']


def test_opencode_does_not_truncate_seller_history_again():
    import asyncio
    import httpx
    from app.ai.opencode import OpenCodeClient
    from test_opencode_client import completed_payload, free_provider_payload
    long_message = 'Đặc điểm sản phẩm. ' * 100 + '\nMàu trắng; giá bán 990k.'
    def transport(request):
        if request.url.path == '/provider':
            return httpx.Response(200, json=free_provider_payload())
        if request.url.path == '/session':
            return httpx.Response(200, json={'id': 'ses_context'})
        if request.url.path.endswith('/message'):
            context = json.loads(json.loads(request.content)['parts'][0]['text'])
            assert context['history'][0]['content'] == long_message
            return httpx.Response(200, json=completed_payload('Mình đã nhận đủ thông tin.'))
        return httpx.Response(200, json=True)
    async def run():
        async with httpx.AsyncClient(base_url='http://opencode.test', transport=httpx.MockTransport(transport)) as http:
            return await OpenCodeClient(http).respond('Tiếp tục nhé', history=[{'role': 'user', 'content': long_message}], facts={})
    asyncio.run(run())
