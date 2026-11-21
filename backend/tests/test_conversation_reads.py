"""Use distinctive, time-frozen figures to catch scope changes in dialogue."""
import sqlite3
from datetime import datetime, timezone

import pytest

from app.ai.quick_reads import quick_read
from app.services.live_shop import inspect_shop
from app.services.product_drafts import create_text_product_draft
from test_advisor import chat
from test_quick_reads import NoNetwork


NOW = datetime(2026, 11, 21, 6, 14, tzinfo=timezone.utc)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


@pytest.fixture
def live_shop_data(client, shop_db_path, monkeypatch):
    for module in ('services.chat', 'services.chat_dispatch', 'services.live_shop', 'integrations.management'):
        monkeypatch.setattr(f'app.{module}.datetime', Clock)
    with sqlite3.connect(shop_db_path) as db:
        db.execute('DELETE FROM order_item')
        db.execute('DELETE FROM "order"')
        db.executemany('INSERT INTO "order" VALUES(?,?,?,?)', [
            (1, 120000, 'pending', '2026-11-20 18:00:00'),
            (2, 320000, 'delivered', '2026-11-21 05:00:00'),
            (3, 999000, 'cancelled', '2026-11-21 05:10:00'),
            (4, 200000, 'paid', '2026-11-20 04:00:00'),
            (5, 700000, 'delivered', '2026-11-20 08:00:00'),
            (6, 500000, 'delivered', '2026-11-21 07:00:00'),
            (7, 530000, 'delivered', '2026-11-10 05:00:00'),
        ])
        db.executemany('INSERT INTO order_item VALUES(?,?,?,?,?)', [
            (1, 1, 1, 2, 60000), (2, 2, 2, 3, 100000), (3, 3, 1, 99, 10000),
        ])
    client.app.state.ai_provider = NoNetwork()
    return client


@pytest.mark.parametrize('message', [
    'Ngày hôm nay shop bán được bao nhiêu?',
    'Hôm nay bán được nhiêu rồi?',
    'Hom nay shop chot nhiu roi ban?',
    'Hôm nay có bao nhiêu đơn và tổng bao nhiêu tiền?',
    'Tính đến giờ hôm nay shop bán được bao nhiêu?',
    'Cho mình xem shop nay bán được bao nhiêu',
    'Xin chào, hôm nay shop bán được bao nhiêu?',
    'Cho mình hỏi hôm nay shop đã chốt được nhiêu đơn đến giờ?',
    'Được mấy đơn rồi bạn?',
    'Shop đã bán được bao nhiêu đơn hôm nay?',
])
def test_sales_question_returns_money_and_order_count_without_inference(live_shop_data, message):
    result = chat(live_shop_data, message)
    assert result['provider'] == 'deterministic_parser' and result['fallback_reason'] is None
    assert result['facts']['to_date'] == '2026-11-21'
    assert result['facts']['order_count'] == 2
    assert result['facts']['order_value_vnd'] == 440000
    assert '440.000đ' in result['answer'] and '2 đơn hợp lệ' in result['answer']
    assert result['report']['metrics'][0]['value'] == 440000


def test_sales_followups_keep_period_and_product_scopes_separate(live_shop_data):
    first = chat(live_shop_data, 'Xem đơn #4')
    selected = chat(live_shop_data, 'Mã A001 bao nhiêu tiền vậy?', first['conversation_id'])
    conversation = selected['conversation_id']
    assert selected['facts']['sku'] == 'A001'
    linked = chat(live_shop_data, 'Mẫu đó còn nhiêu?', conversation)
    assert linked['facts']['sku'] == 'A001' and linked['facts']['stock'] == 3
    summary = chat(live_shop_data, 'Ngày hôm nay shop bán được bao nhiêu?', conversation)
    assert 'sku' not in summary['facts'] and summary['facts']['order_value_vnd'] == 440000
    chat(live_shop_data, 'Cảm ơn nha', conversation)
    yesterday = chat(live_shop_data, 'Vậy còn hôm qua thì sao?', conversation)
    assert yesterday['facts']['order_value_vnd'] == 900000 and yesterday['facts']['to_date'] == '2026-11-20'
    seven = chat(live_shop_data, 'Còn bảy ngày qua?', conversation)
    assert seven['facts']['days'] == 7 and 'sku' not in seven['facts']
    comparison = chat(live_shop_data, 'Doanh thu hôm qua so với hôm nay thế nào?', conversation)
    assert comparison['facts']['previous_value_vnd'] == 200000 and comparison['facts']['previous_order_count'] == 1
    assert '240.000đ' in comparison['answer'] and 'Hôm qua cùng giờ' in comparison['answer']


def test_short_conversation_turns_reply_normally_without_repeating_the_brand(live_shop_data):
    first = chat(live_shop_data, 'Chào SellerPilot')
    assert 'ShipCODE' in first['answer']
    conversation = first['conversation_id']
    samples = [
        ('Alo, bạn còn đó không?', 'Mình đây'),
        ('Cảm ơn bạn nhiều nha', 'Không có gì'),
        ('Mình hiểu rồi', 'mình hiểu'),
        ('Hẹn gặp lại', 'Hẹn gặp lại'),
    ]
    for message, expected in samples:
        result = chat(live_shop_data, message, conversation)
        assert expected in result['answer'] and 'ShipCODE' not in result['answer']
        assert result['tool'] is None and not result['suggestions']


def test_item_counts_delivered_value_collected_money_and_backlog_are_distinct(live_shop_data, shop_db_path):
    client = live_shop_data
    sold = chat(client, 'Bán được bao nhiêu cái hôm nay?')
    assert sold['facts']['units_sold'] == 5 and '5 sản phẩm' in sold['answer']
    with sqlite3.connect(shop_db_path) as db:
        db.execute('DELETE FROM order_item WHERE order_id=2')
    partial = chat(client, 'Hôm nay đã bán được bao nhiêu sản phẩm?')
    assert '1/2 đơn hợp lệ' in partial['answer']
    delivered = chat(client, 'Hôm nay đã giao được mấy đơn?')
    assert '1 đơn đã giao' in delivered['answer'] and '320.000đ' in delivered['answer']
    compared = chat(client, 'Hôm nay đã giao mấy đơn so với hôm qua?')
    assert '0 đơn đã giao' in compared['answer'] and '1 đơn đã giao' in compared['answer']
    units_comparison = chat(client, 'Hôm nay bán được bao nhiêu sản phẩm so với hôm qua?')
    assert '1/2 đơn hợp lệ' in units_comparison['answer']
    assert 'Hôm qua cùng giờ có **1 đơn hợp lệ** nhưng thiếu' in units_comparison['answer']
    cancelled = chat(client, 'Hôm nay có bao nhiêu đơn hủy?')
    assert '1 đơn đã hủy' in cancelled['answer']
    collected = chat(client, 'Hôm nay shop đã thu được bao nhiêu tiền?')
    assert 'chưa có số liệu đối soát' in collected['answer'] and '440.000đ' in collected['answer']
    outstanding = chat(client, 'Còn bao nhiêu đơn chờ lấy hàng?')
    assert '1 đơn chờ lấy hàng' in outstanding['answer'] and outstanding['report'] is None
    again = chat(client, 'Bao nhiêu vậy?', outstanding['conversation_id'])
    assert again['answer'] == outstanding['answer']


@pytest.mark.parametrize('message,start,end', [
    ('Tuần trước bán được bao nhiêu?', '2026-11-09', '2026-11-15'),
    ('Tháng trước shop bán được bao nhiêu?', '2026-10-01', '2026-10-31'),
    ('Doanh thu 14 ngày qua', '2026-11-08', '2026-11-21'),
    ('Hôm kia doanh thu thế nào?', '2026-11-19', '2026-11-19'),
    ('Doanh thu 20/11?', '2026-11-20', '2026-11-20'),
    ('Doanh thu ngày 20-11-2026?', '2026-11-20', '2026-11-20'),
])
def test_natural_periods_keep_their_calendar_boundaries(live_shop_data, message, start, end):
    result = chat(live_shop_data, message)
    assert result['facts']['from_date'] == start and result['facts']['to_date'] == end


def test_week_to_date_compares_with_same_span_in_previous_calendar_week(live_shop_data):
    result = chat(live_shop_data, 'Doanh thu tuần này')
    assert result['facts']['previous_value_vnd'] == 530000
    assert result['facts']['from_date'] == '2026-11-16'


def test_known_question_does_not_change_draft_and_live_uses_spoken_scope(live_shop_data):
    client = live_shop_data
    first = chat(client, 'Doanh thu hôm nay')
    conversation = first['conversation_id']
    app = client.app.state
    with app.session_factory() as session:
        draft = create_text_product_draft(session, app.shop_repository, conversation)
        session.flush()
        draft_id = draft.id
        session.commit()
    same = chat(client, 'Ngày hôm nay shop bán được bao nhiêu?', conversation)
    assert same['tool'] == 'get_shop_summary' and not same['product_draft']
    with app.session_factory() as session:
        from app.models.product_draft import ProductDraft
        assert session.get(ProductDraft, draft_id).name is None
        spoken = inspect_shop(session, app.shop_repository, 'Tồn kho của shop',
            'Hôm qua thì sao?', conversation_id=conversation)
    assert spoken['sales_context']['to_date'] == '2026-11-20'
    assert '900.000đ' in spoken['answer']


@pytest.mark.parametrize('message,expected', [
    ('Doanh thu 31/02/2026?', 'không hợp lệ'),
    ('Doanh thu 90 ngày qua?', '1 đến 30 ngày'),
    ('Doanh thu 22/11/2026?', 'chưa diễn ra'),
    ('Doanh thu 7 ngày tới?', 'chưa diễn ra'),
    ('Doanh thu ngày mai?', 'chưa diễn ra'),
])
def test_bad_period_does_not_silently_return_today(live_shop_data, message, expected):
    result = chat(live_shop_data, message)
    assert expected in result['answer'] and not result['report'] and result['tool'] is None


def test_compound_write_or_analysis_do_not_match_a_simple_read():
    for message in ('Ngày hôm nay shop bán được bao nhiêu, đổi giá SKU A001 thành 200k',
                    'Hôm nay bán được bao nhiêu và phân tích vì sao giảm',
                    'Giả sử hôm nay shop bán được bao nhiêu thì đủ hòa vốn?'):
        assert quick_read(message, today=NOW.date()) is None
