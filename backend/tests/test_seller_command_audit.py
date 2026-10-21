"""Common seller wording must resolve slots without inventing writes or values."""
from datetime import date

import pytest

from app.ai.draft_actions import draft_action
from app.ai.quick_reads import quick_read
from app.services.product_edit_chat import local_changes, is_product_edit_request
from test_product_drafts import make_client, OfflineProvider


@pytest.mark.parametrize('message,scope', [
    ('Hôm nay được bao nhiêu đơn vậy?', 'shop_summary'),
    ('Nay có mấy đơn?', 'shop_summary'),
    ('Thống kê hôm nay', 'shop_summary'),
    ('Cho mình xem số liệu hôm qua nhé', 'shop_summary'),
    ('Có món nào sắp hết không?', 'low_stock'),
    ('Hàng nào gần hết?', 'low_stock'),
    ('Mặt hàng nào tồn thấp vậy?', 'low_stock'),
    ('Còn sản phẩm nào hết hàng không?', 'low_stock'),
])
def test_common_read_paraphrases_have_a_complete_direct_route(message, scope):
    result = quick_read(message, today=date(2026, 10, 21))
    assert result is not None
    assert (result.inventory_scope if scope == 'low_stock' else result.intent) == scope
    if 'hết hàng' in message:
        assert result.low_stock_threshold == 0


@pytest.mark.parametrize('message', [
    'Có món nào sắp hết không, đăng thêm giúp mình',
    'Hàng nào gần hết và nên nhập bao nhiêu?',
    'Đừng thống kê hôm nay',
    'Còn hàng không?',  # The product is ambiguous without a selected SKU.
])
def test_incomplete_mixed_negative_and_calendar_requests_are_not_guessed(message):
    assert quick_read(message, today=date(2026, 10, 21)) is None


@pytest.mark.parametrize('day,period,days', [
    (date(2026,10,19),'week',1), (date(2026,10,21),'week',3),
    (date(2026,10,25),'week',7), (date(2026,10,1),'month',1),
    (date(2026,10,31),'month',31),
])
def test_calendar_reads_use_the_start_of_week_or_month_not_rolling_days(tmp_path, day, period, days):
    from app.services.chat import execute_command
    from app.services.seller_voice import read_reply
    from unittest.mock import patch
    client, _, _=make_client(tmp_path)
    word='tuần' if period=='week' else 'tháng'
    command=quick_read('Doanh thu '+word+' này',today=day)
    assert command.calendar_period==period and command.days is None
    with client, client.app.state.session_factory() as session:
        expected={key:value for key,value in {'days':days,'from_date':day.replace(day=day.day-days+1).isoformat(),
            'to_date':day.isoformat(),'order_value_vnd':100000,'order_count':1,'average_order_vnd':100000,
            'delivered_value_vnd':0,'change_percent':None}.items()}
        with patch('app.services.chat.management.dashboard',return_value=expected) as dashboard:
            result=execute_command(session,client.app.state.shop_repository,command)
        assert dashboard.call_args.args[1]==days
        assert dashboard.call_args.kwargs['selected_date']==day
        assert result['facts']['calendar_period']==period
        assert word+' này' in read_reply(result,today=day,preferences={}).lower()


@pytest.mark.parametrize('message,action', [
    ('Khoan đã', 'pause'), ('để lát', 'pause'), ('lưu lại bản nháp', 'pause'),
    ('Hủy nháp', 'cancel'), ('thôi bỏ bản nháp đi', 'cancel'),
    ('Mô tả: Hủy nháp rồi đăng lại', None),
    ('Nếu hủy nháp thì ảnh có mất không?', None),
])
def test_conversational_draft_controls_match_only_the_whole_command(message, action):
    assert draft_action(message) == action


@pytest.mark.parametrize('message,changes', [
    ('Sửa tồn kho SKU SEED-PHONE thành 2.000', {'stock': 2000}),
    ('Cap nhat so luong SKU SEED-PHONE con 0', {'stock': 0}),
    ('sua tieu de SKU SEED-PHONE thanh Dien thoai nho gon', {'name': 'Dien thoai nho gon'}),
    ('Sua mo ta SKU SEED-PHONE thanh "Máy màu đen.\nThông tin do shop cung cấp."', {'description': 'Máy màu đen.\nThông tin do shop cung cấp.'}),
    ('Sửa mô tả SKU SEED-PHONE thành "Hàng đẹp", giá 5 xị, tồn 2.000',
     {'description': 'Hàng đẹp', 'price_vnd': 500000, 'stock': 2000}),
    ('Sửa tiêu đề SKU SEED-PHONE thành Máy màu đen\nGiá bán năm xị\nTồn kho hai mươi',
     {'name': 'Máy màu đen', 'price_vnd': 500000, 'stock': 20}),
])
def test_explicit_edit_slots_preserve_zero_grouped_numbers_and_original_caption(message, changes):
    assert is_product_edit_request(message)
    assert local_changes(message) == changes


@pytest.mark.parametrize('value', ['2.5', '2,5', '-2', '2.00', '2 hoặc 3', '2-3', '1.000.001'])
def test_invalid_stock_is_not_partially_read_as_a_valid_quantity(value):
    assert 'stock' not in local_changes('Sửa tồn kho SKU SEED-PHONE thành ' + value)


def test_no_accent_multi_field_edit_creates_one_preview_without_writing_shop(tmp_path):
    import sqlite3
    client, path, _ = make_client(tmp_path)
    with client:
        client.app.state.ai_provider = OfflineProvider()
        result = client.post('/api/v1/chat', json={'message':
            'sua tieu de SKU SEED-PHONE thanh Dien thoai nho gon\nmo ta: Máy màu đen.\ngia ban: 5 xi\nton kho: 2.000'})
        assert result.status_code == 200, result.text
        data = result.json()['data']
        assert data['product_edit_proposal'] and data['fallback_reason'] is None
        changes = {item['field']: item['after'] for item in data['product_edit_proposal']['changes']}
        assert changes == {'name': 'Dien thoai nho gon', 'description': 'Máy màu đen.', 'price_vnd': 500000, 'stock': 2000}
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT name,price,stock FROM product WHERE id=1').fetchone() == ('Điện thoại mẫu', 1000000, 8)


@pytest.mark.parametrize('message', ['Thôi không sửa nữa', 'Hủy yêu cầu sửa', 'Đừng sửa tiêu đề SKU SEED-PHONE thành Máy màu đen'])
def test_cancelling_a_target_clarification_never_creates_an_edit_preview(tmp_path, message):
    client, _, _ = make_client(tmp_path)
    with client:
        first = client.post('/api/v1/chat', json={'message': 'Sửa tiêu đề thành Máy màu đen'}).json()['data']
        assert first['facts']['missing_fields'] == ['sku']
        result = client.post('/api/v1/chat', json={'message': message, 'conversation_id': first['conversation_id']})
        assert result.status_code == 200, result.text
        data = result.json()['data']
        assert data['product_edit_proposal'] is None
        assert not data['facts'].get('pending_edit_message')


@pytest.mark.parametrize('reply', ['2.000', 'ton: 2.000'])
def test_short_stock_reply_resolves_only_the_field_being_asked(tmp_path, reply):
    client, _, _ = make_client(tmp_path)
    with client:
        first=client.post('/api/v1/chat',json={'message':'Sửa tồn kho SKU SEED-PHONE thành 2 hoặc 3'}).json()['data']
        assert first['facts']['missing_fields']==['stock']
        result=client.post('/api/v1/chat',json={'message':reply,'conversation_id':first['conversation_id']}).json()['data']
        assert result['product_edit_proposal'] is not None
        assert {item['field']:item['after'] for item in result['product_edit_proposal']['changes']}=={'stock':2000}


@pytest.mark.parametrize('period,dates,expected', [
    ('week',['2026-10-18 12:00:00','2026-10-19 12:00:00','2026-10-20 12:00:00'],2),
    ('month',['2026-09-30 12:00:00','2026-10-01 12:00:00','2026-10-20 12:00:00'],2),
])
def test_calendar_boundaries_exclude_previous_week_or_month_orders(tmp_path, period, dates, expected):
    import sqlite3
    from datetime import datetime, timezone
    from unittest.mock import patch
    from app.services.chat import execute_command
    client,path,_=make_client(tmp_path)
    with sqlite3.connect(path) as db:
        for index,created in enumerate(dates):
            db.execute('INSERT INTO "order" VALUES(?,1,100000,?,?)',(index+1,'pending',created))
    command=quick_read('Doanh thu '+('tuần' if period=='week' else 'tháng')+' này',today=date(2026,10,21))
    with client,client.app.state.session_factory() as session:
        with patch('app.integrations.management.datetime',wraps=datetime) as clock:
            clock.now.return_value=datetime(2026,10,21,8,tzinfo=timezone.utc)
            result=execute_command(session,client.app.state.shop_repository,command)
        assert result['facts']['order_count']==expected
        assert result['facts']['order_value_vnd']==expected*100000
        assert result['facts']['from_date']==('2026-10-19' if period=='week' else '2026-10-01')


@pytest.mark.parametrize('message',['Hôm nay được bao nhiêu đơn vậy?','Có món nào sắp hết không?','Doanh thu tuần này','Doanh thu tháng này'])
def test_everyday_reads_skip_external_inference_and_do_not_change_an_active_draft(tmp_path,message):
    from test_quick_reads import NoNetwork
    from test_product_drafts import CopyProvider
    from app.models.product_draft import ProductDraft
    client,_,_=make_client(tmp_path)
    with client:
        client.app.state.ai_provider=CopyProvider()
        first=client.post('/api/v1/chat',json={'message':'Đăng sản phẩm mới'}).json()['data']
        client.app.state.ai_provider=NoNetwork()
        result=client.post('/api/v1/chat',json={'message':message,'conversation_id':first['conversation_id']})
        assert result.status_code==200,result.text
        data=result.json()['data']
        assert data['provider']=='deterministic_parser' and data['fallback_reason'] is None
        assert data['product_draft'] is None
        with client.app.state.session_factory() as session:
            draft=session.get(ProductDraft,first['product_draft']['id'])
            assert draft.name is None and draft.price_vnd is None and draft.stock is None
