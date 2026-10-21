import json
from datetime import date
from types import SimpleNamespace

import pytest

from app.ai.context import bounded_history
from app.ai.fallback import parse_fallback, reporting_days
from app.services.chat import reply_issue
from app.services.conversations import history_messages
from test_advisor import AdvisorAI, chat


@pytest.mark.parametrize('answer', ['', '   ', '{"answer": ""}', '{"answer": null}'])
def test_empty_answers_are_rejected_before_display(answer):
    assert reply_issue(answer) in {'empty_answer', 'invalid_answer_envelope'}


@pytest.mark.parametrize('message', ['Sao vậy, ko kết nối được à?', 'Có kết nối được không?'])
def test_empty_answer_is_corrected_with_the_same_shop_facts(client, message):
    class EmptyFirst(AdvisorAI):
        async def respond(self, message, *, history, facts):
            self.answers.append(facts)
            return ' ' if len(self.answers) == 1 else 'Mình vẫn đọc được số liệu shop.'
    provider = EmptyFirst([])
    client.app.state.ai_provider = provider
    result = chat(client, message)
    assert len(provider.answers) == 2
    assert provider.answers[1]['reply_correction']['reason'] == 'empty_answer'
    assert result['answer'] == 'Mình vẫn đọc được số liệu shop.'


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


def test_internal_step_limit_messages_do_not_reach_the_seller():
    assert reply_issue('Đã đạt giới hạn số bước cho agent này.') == 'internal_agent_message'
    assert reply_issue('Việc chưa hoàn thành do hết bước xử lý: ...') == 'internal_agent_message'
    assert reply_issue('Mình đề xuất 3 bước để cải thiện doanh số.') is None


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


class PreparedAI(AdvisorAI):
    def __init__(self, extraction=None, answer='Đề xuất: kiểm tra đơn chờ trước, sau đó thử cải thiện nội dung sản phẩm.'):
        super().__init__([])
        self.extraction = extraction or {'topic': 'strategy'}
        self.prepared_answer = answer
        self.preparations = []

    async def prepare_advice(self, message, *, history, context, facts):
        self.preparations.append({'message':message,'history':history,'context':context,'facts':facts})
        return {'extraction':self.extraction, 'answer':self.prepared_answer}

    async def analyze_advice(self, *args, **kwargs):
        raise AssertionError('Do not run extraction again after a prepared turn')


def test_strategy_preparation_answers_in_one_model_turn_with_actual_shop_facts(client):
    provider = PreparedAI()
    client.app.state.ai_provider = provider
    result = chat(client, 'Tư vấn việc cần ưu tiên hôm nay')
    assert len(provider.preparations) == 1 and not provider.answers
    assert provider.preparations[0]['facts']['today']
    assert result['answer'] == provider.prepared_answer and result['mode'] == 'ai'
    assert '_prepared_answer' not in result['facts']


def test_bad_prepared_reply_is_corrected_before_display(client):
    provider = PreparedAI(answer='Mình đã đổi giá sản phẩm cho bạn.')
    client.app.state.ai_provider = provider
    result = chat(client, 'Tư vấn chiến lược bán hàng')
    assert len(provider.preparations) == len(provider.answers) == 1
    assert 'đã đổi giá' not in result['answer'] and result['mode'] == 'ai'
    assert provider.answers[0]['facts']['reply_correction']['reason'] == 'unexecuted_write_claim'


def test_prepared_pricing_still_runs_exact_backend_math_before_final_reply(client):
    provider = PreparedAI({'topic':'pricing','economics':[
        {'field':'unit_cost_vnd','value':500000,'evidence':'Giá vốn 5 xị'},
        {'field':'selling_price_vnd','value':1000000,'evidence':'bán 1 củ'}]}, answer='Lời 999 triệu.')
    client.app.state.ai_provider = provider
    result = chat(client, 'Giá vốn 5 xị, bán 1 củ thì lời bao nhiêu?')
    assert len(provider.preparations) == len(provider.answers) == 1
    assert result['facts']['pricing_analysis']['at_selling_price']['profit_per_unit_vnd'] == 500000
    assert '999 triệu' not in result['answer'] and '500.000đ' in result['answer']


def test_prepared_preferences_are_checked_and_saved_before_final_reply(client):
    provider = PreparedAI({'topic':'strategy','preferences':[
        {'field':'target_audience','value':'sinh viên','evidence':'Mình bán cho sinh viên'}]})
    client.app.state.ai_provider = provider
    result = chat(client, 'Mình bán cho sinh viên, tư vấn hướng bán hàng nhé')
    assert len(provider.preparations) == len(provider.answers) == 1
    assert result['facts']['seller_preferences']['target_audience'] == 'sinh viên'
    assert 'target_audience' in result['facts']['memory_updates_saved']


def test_preparation_reply_is_never_reused_in_another_conversation(client):
    provider = PreparedAI(answer='Đề xuất của lượt đầu.')
    client.app.state.ai_provider = provider
    first = chat(client, 'Tư vấn chiến lược bán hàng')
    provider.prepared_answer = 'Đề xuất riêng cho lượt sau.'
    second = chat(client, 'Tư vấn chiến lược bán hàng')
    assert first['conversation_id'] != second['conversation_id']
    assert first['answer'] == 'Đề xuất của lượt đầu.' and second['answer'] == provider.prepared_answer


@pytest.mark.parametrize('message', ['Xin chào', 'Doanh thu hôm nay bao nhiêu?',
    'Hôm nay shop có bao nhiêu đơn?', 'Xem tồn kho của shop', 'Shop có sản phẩm nào sắp hết?'])
def test_exact_small_requests_do_not_pay_cli_generation_latency(client, message):
    class FastAI(PreparedAI):
        prefer_direct_facts = True
        async def prepare_advice(self, *args, **kwargs):
            raise AssertionError('Exact read request should use current database facts')
        async def respond(self, *args, **kwargs):
            raise AssertionError('No model wording needed for exact facts')
    client.app.state.ai_provider = FastAI()
    result = chat(client, message)
    assert result['provider'] == 'deterministic_parser' and result['model'] is None
    assert result['answer'] and result['fallback_reason'] is None
    assert result['mode'] == 'ai'


@pytest.mark.parametrize('message', ['Doanh thu hôm nay bao nhiêu và nên làm gì tiếp?',
    'Phân tích tại sao doanh thu hôm nay thấp', 'Xem tồn kho của shop rồi gợi ý nên nhập gì',
    'Giả sử doanh thu hôm nay là 5 triệu thì sao?', 'Doanh thu hôm nay, trả lời bằng tiếng Anh'])
def test_extended_questions_keep_semantic_generation_instead_of_read_template(message):
    from app.services.chat import is_exact_fact_question
    command = parse_fallback(message, today=date(2026,10,18))
    assert not is_exact_fact_question(message, command)


@pytest.mark.parametrize('message', [
    'Hôm nay shop có bao nhiêu đơn và giá trị đơn hàng bao nhiêu?',
    'Hôm nay, shop có bao nhiêu đơn và doanh thu bao nhiêu?',
    'Shop mình có bao nhiêu đơn hôm nay và giá trị đơn hàng bao nhiêu?',
])
def test_compound_report_question_is_a_complete_fast_read(message):
    from app.services.chat import is_exact_fact_question
    command=parse_fallback(message,today=date(2026,10,19))
    assert is_exact_fact_question(message,command)


def test_home_quick_read_questions_do_not_invoke_api_and_read_current_numbers(client,shop_db_path):
    import sqlite3
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from time import perf_counter
    class NoInference(PreparedAI):
        prefer_direct_facts=True
        async def respond(self,*args,**kwargs):
            raise AssertionError('Quick read must not call model')
        async def prepare_advice(self,*args,**kwargs):
            raise AssertionError('Quick read must not extract advice')
    client.app.state.ai_provider=NoInference()
    created=datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).replace(hour=0,minute=0,second=0,microsecond=0).astimezone(timezone.utc).replace(tzinfo=None).isoformat(sep=' ')
    with sqlite3.connect(shop_db_path) as db:
        db.execute('DELETE FROM order_item')
        db.execute('DELETE FROM "order"')
        for order_id,total,status in [(1,123000,'pending'),(2,321000,'delivered'),(3,900000,'cancelled')]:
            db.execute('INSERT INTO "order" VALUES (?,?,?,?)',(order_id,total,status,created))
    started=perf_counter()
    result=chat(client,'Hôm nay shop có bao nhiêu đơn và giá trị đơn hàng bao nhiêu?')
    print(f'\nCompound report API on temp DB: {(perf_counter()-started)*1000:.1f} ms; inference calls: 0')
    assert result['provider']=='deterministic_parser' and result['model'] is None
    assert result['facts']['order_count']==2 and result['facts']['order_value_vnd']==444000
    assert '444.000đ' in result['answer'] and not result['answer'].startswith('{')
    for text in ('Những sản phẩm nào sắp hết hàng?','Tìm sản phẩm bàn phím'):
        assert chat(client,text)['provider']=='deterministic_parser'


def test_shop_report_after_selecting_sku_does_not_inherit_product_scope(client):
    class FastAI(PreparedAI):
        prefer_direct_facts=True
        async def respond(self,*args,**kwargs):
            raise AssertionError('Read should not call model')
    client.app.state.ai_provider=FastAI()
    selected=chat(client,'SKU A001 còn bao nhiêu?')
    report=chat(client,'Hôm nay shop có bao nhiêu đơn và giá trị đơn hàng bao nhiêu?',selected['conversation_id'])
    assert report['intent']=='shop_summary' and report['tool']=='get_shop_summary'
    assert report['provider']=='deterministic_parser' and 'sku' not in report['facts']


def test_serialized_prepared_answer_is_decoded_before_guard_and_persistence(client):
    from app.models.agent_run import AgentRun
    provider=PreparedAI(answer=json.dumps({'answer':'Ưu tiên kiểm tra đơn đang chờ.\n\nSau đó rà tồn kho.'},ensure_ascii=False))
    client.app.state.ai_provider=provider
    result=chat(client,'Tư vấn chiến lược bán hàng')
    assert result['answer']=='Ưu tiên kiểm tra đơn đang chờ.\n\nSau đó rà tồn kho.'
    with client.app.state.session_factory() as session:
        assert session.get(AgentRun,result['run_id']).answer==result['answer']


def test_legacy_json_answer_is_clean_in_history_and_context_without_rewriting_audit_row(client):
    from app.models.agent_run import AgentRun
    from app.services.conversations import history_messages
    result=chat(client,'SKU A001 còn bao nhiêu?')
    wrapped=json.dumps({'answer':'Còn 3 chiếc.\n\nBạn cần kiểm tra thêm không?'},ensure_ascii=False)
    with client.app.state.session_factory() as session:
        row=session.get(AgentRun,result['run_id'])
        row.answer=wrapped
        session.commit()
        assert history_messages([row])[-1]['content']=='Còn 3 chiếc.\n\nBạn cần kiểm tra thêm không?'
    history=client.get('/api/v1/conversations/'+result['conversation_id']).json()['data']
    assert history['turns'][0]['response']['answer']=='Còn 3 chiếc.\n\nBạn cần kiểm tra thêm không?'
    with client.app.state.session_factory() as session:
        assert session.get(AgentRun,result['run_id']).answer==wrapped
