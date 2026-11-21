"""Reports must reconcile to saved shop facts, including offline/replayed reads."""
import json
import sqlite3
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.ai.contracts import ParsedCommand
from app.ai.client import response_prompt
from app.ai.quick_reads import quick_read
from app.integrations.business import business_snapshot
from app.integrations.ute_mall import UTEMallRepository
from app.schemas.chat_report import ChatReport
from app.services.chat import execute_command
from app.services.chat_reports import build_chat_report
from test_business_advisor import NOW, seed_performance
from test_shop_tenant_scope import build_marketplace


def ask(client, message, **ids):
    response = client.post('/api/v1/chat', json={'message': message, **ids})
    assert response.status_code == 200, response.text
    return response.json()['data']


def test_daily_report_reconciles_with_text_and_excludes_cancelled_returned(client, shop_db_path):
    with sqlite3.connect(shop_db_path) as db:
        db.execute('INSERT INTO "order" VALUES (5,800000,\'returned\',\'2026-10-15 04:00:00\')')
    data = ask(client, 'Vẽ biểu đồ doanh thu ngày 15/10/2026')
    report = data['report']
    assert data['provider'] == 'deterministic_parser' and data['fallback_reason'] is None
    assert report['metrics'][0]['value'] == data['facts']['order_value_vnd'] == 300000
    assert report['metrics'][1]['value'] == data['facts']['order_count'] == 2
    assert len(report['charts'][0]['points']) == 24
    assert sum(p['value'] for p in report['charts'][0]['points']) == 300000
    assert sum(row[1] for row in report['table']['rows']) == 300000
    assert report['charts'][1]['points'][-2:] == [
        {'label': 'Đã hủy', 'value': 1}, {'label': 'Đã hoàn', 'value': 1}]
    assert report['timezone'] == 'Asia/Ho_Chi_Minh'
    assert report['as_of']


def test_today_ignores_future_orders_and_has_no_invented_comparison(client, shop_db_path):
    future = (datetime.now(timezone.utc) + timedelta(minutes=10)).replace(tzinfo=None).isoformat(sep=' ')
    with sqlite3.connect(shop_db_path) as db:
        db.execute('DELETE FROM "order"')
        db.execute('INSERT INTO "order" VALUES (9,999999,\'delivered\',?)', (future,))
    data = ask(client, 'Hôm nay được bao nhiêu đơn?')
    assert data['report']['metrics'][0]['value'] == 0
    assert data['report']['metrics'][0]['change_percent'] is None
    assert all(p['value'] == 0 for p in data['report']['charts'][0]['points'])
    assert any('cùng thời lượng' in note for note in data['report']['notes'])


@pytest.mark.parametrize('message,days,calendar', [
    ('Vẽ biểu đồ doanh thu 7 ngày qua', 7, None),
    ('Cho xem bảng thống kê doanh số 30 ngày', 30, None),
    ('Vẽ biểu đồ doanh thu bảy ngày qua', 7, None),
    ('Cho xem bảng thống kê doanh số ba mươi ngày', 30, None),
    ('Hiển thị biểu đồ giá trị đơn hàng tháng này', None, 'month'),
    ('Vẽ biểu đồ doanh thu hôm qua', 1, None),
])
def test_visual_read_grammar(message, days, calendar):
    command = quick_read(message, today=date(2026, 10, 29))
    assert command and command.intent == 'shop_summary'
    assert command.days == days and command.calendar_period == calendar


@pytest.mark.parametrize('message', [
    'Vẽ biểu đồ doanh thu và đổi giá SKU A001 thành 100k',
    'Vẽ biểu đồ doanh thu 7 ngày và giải thích tại sao giảm',
    'Vẽ biểu đồ doanh thu hôm nay và hôm qua',
])
def test_visual_grammar_does_not_swallow_mixed_instructions(message):
    assert quick_read(message, today=date(2026, 10, 29)) is None


def test_inventory_chart_does_not_double_count_parent_variant_stock(client):
    data = ask(client, 'Xem tồn kho của shop')
    report = data['report']
    assert report['metrics'][0]['value'] == 3
    assert report['metrics'][1]['value'] == 17
    assert sum(p['value'] for p in report['charts'][0]['points']) == 3
    assert [p['value'] for p in report['charts'][0]['points']] == [1, 2, 0]
    low = ask(client, 'Hàng sắp hết')
    assert len(low['report']['table']['rows']) == 2
    assert {p['label'] for p in low['report']['charts'][0]['points']} == {'P001', 'A001'}


def test_low_stock_limits_are_explicit_without_losing_table_rows():
    items = [dict(sku=f'P{i}', product_name='Hàng', stock=i % 5, price_vnd=100000) for i in range(50)]
    report = build_chat_report('get_low_stock', dict(threshold=5, items=items))
    assert len(report['table']['rows']) == 50
    assert len(report['charts'][0]['points']) == 8
    assert 'giới hạn 50' in report['notes'][0]
    empty = build_chat_report('get_low_stock', dict(threshold=0, items=[]))
    assert empty['charts'] == [] and empty['table']['rows'] == []


def test_replay_and_history_preserve_snapshot_after_shop_changes(client, shop_db_path):
    request_id, conversation_id = str(uuid4()), str(uuid4())
    message = 'Doanh thu ngày 15/10/2026'
    first = ask(client, message, request_id=request_id, conversation_id=conversation_id)
    with sqlite3.connect(shop_db_path) as db:
        db.execute('UPDATE "order" SET total_amount=777000 WHERE id=1')
    replay = ask(client, message, request_id=request_id, conversation_id=conversation_id)
    assert replay['report'] == first['report']
    history = client.get(f'/api/v1/conversations/{conversation_id}').json()['data']['turns']
    assert history[0]['response']['report'] == first['report']
    fresh = ask(client, message)
    assert fresh['report']['metrics'][0]['value'] == 977000


def test_shop_report_does_not_inherit_the_previous_single_low_stock_sku(client):
    conversation_id = str(uuid4())
    stock = ask(client, 'Hàng sắp hết dưới 4', conversation_id=conversation_id)
    assert len(stock['facts']['items']) == 1
    data = ask(client, 'Doanh thu ngày 15/10/2026', conversation_id=conversation_id)
    assert data['tool'] == 'get_shop_summary'
    assert data['report']['metrics'][0]['value'] == 300000
    empty = ask(client, 'Doanh thu ngày 01/01/1999', conversation_id=conversation_id)
    assert empty['report']['metrics'][0]['value'] == 0


def test_business_report_uses_purchased_prices_and_warns_on_missing_attribution(shop_db_path):
    seed_performance(shop_db_path)
    snapshot = business_snapshot(UTEMallRepository(shop_db_path, 'Asia/Ho_Chi_Minh'), 7, now=NOW)
    report = build_chat_report('get_shop_insights', dict(business_analysis=snapshot))
    assert report['metrics'][0]['value'] == 1200000
    assert sum(p['value'] for p in report['charts'][0]['points']) == 1200000
    assert report['table']['rows'][0] == ['Áo thun trơn\nP001', 3, 300000]
    assert report['charts'][1]['points'][0] == {'label': 'P001', 'value': 3}
    assert any('chưa khớp' in note for note in report['notes'])
    snapshot['period_top_products'][0]['sku'] = None
    no_sku = build_chat_report('get_shop_insights', dict(business_analysis=snapshot))
    assert no_sku['charts'][1]['points'][0]['label'] == 'Áo thun trơn'
    assert no_sku['metrics'][0]['value'] == 1200000
    snapshot.update(period_top_products=[], attribution={'available': False, 'unmatched_current_item_lines': 0})
    report = build_chat_report('get_shop_insights', dict(business_analysis=snapshot))
    assert report['table']['title'] == 'Chi tiết giá trị đơn hàng'
    assert len(report['charts']) == 1
    assert any('Chưa có dòng hàng' in note for note in report['notes'])


def test_offline_performance_read_still_has_report(client):
    data = ask(client, 'Phân tích số liệu 7 ngày qua')
    assert data['report'] and len(data['report']['charts'][0]['points']) == 7
    assert data['report']['metrics'][0]['value'] == data['facts']['business_analysis']['current']['order_value_vnd']


def test_model_knows_the_report_will_render_without_an_extra_generation(client):
    from conftest import OfflineProvider

    class RecordingProvider(OfflineProvider):
        provider = 'gemini'
        natural_responses = True
        calls = 0

        async def respond(self, message, *, history, facts):
            assert facts['report_available'] is True
            assert 'báo cáo trực quan' in response_prompt(facts)
            self.calls += 1
            return 'Mình đã tổng hợp số liệu của shop trong kỳ bạn chọn.'

    provider = RecordingProvider()
    client.app.state.ai_provider = provider
    data = ask(client, 'Doanh thu 7 ngày qua, diễn đạt bằng tiếng Anh')
    assert data['report'] and provider.calls == 1
    assert 'report_available' not in data['facts']


def test_report_is_tenant_scoped(tmp_path):
    path = tmp_path / 'shop.db'
    build_marketplace(path)
    shop = UTEMallRepository(path, 'Asia/Ho_Chi_Minh', 'utech-official')
    result = execute_command(None, shop, ParsedCommand(intent='shop_summary', day=date(2026, 10, 15)))
    report = build_chat_report(result['tool'], result['facts'])
    assert report['metrics'][0]['value'] == 700000
    assert sum(p['value'] for p in report['charts'][0]['points']) == 700000
    assert 'OTHER' not in json.dumps(report)


def test_legacy_and_invalid_reports_never_invent_missing_values_or_break_history():
    old = build_chat_report('get_shop_summary', dict(date='2026-10-15', order_count=0, order_value_vnd=0))
    assert old['metrics'][2]['value'] is None and old['charts'] == []
    assert build_chat_report('get_shop_summary', dict(order_count=2, order_value_vnd=float('nan'))) is None
    assert build_chat_report('get_low_stock', {}) is None
    assert build_chat_report('create_price_proposal', dict(order_count=999)) is None
    assert build_chat_report(None, dict(series=[{'value': 999}])) is None
    with pytest.raises(ValidationError):
        ChatReport.model_validate(dict(title='Invalid', subtitle='', table={
            'title': 'Invalid', 'columns': [{'label': 'A', 'unit': 'text'}], 'rows': [['a', 'b']]}))
