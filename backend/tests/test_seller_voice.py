from datetime import date

import pytest

from app.services.seller_voice import read_reply


def summary(count=12, value=2450000, **extra):
    return {'tool':'get_shop_summary','facts':{'date':'2026-10-19',
        'order_count':count,'order_value_vnd':value,'pending_count':3,**extra}}


def test_short_and_model_voice_share_units_and_addressing_without_extra_offer():
    text=read_reply(summary(),today=date(2026,10,19),preferences={})
    assert text.startswith('Hôm nay shop có **12 đơn**')
    assert '**2.450.000đ**' in text and '**3 đơn** chờ xác nhận' in text
    assert 'Bạn có muốn' not in text and 'pending_count' not in text
    assert 'chưa phải toàn bộ tiền đã thu' in text


def test_zero_orders_and_yesterday_do_not_turn_into_predicted_sales():
    text=read_reply(summary(0,0,pending_count=0),today=date(2026,10,20),preferences={})
    assert text.startswith('Hôm qua shop chưa có đơn hợp lệ mới.')
    assert '**0đ**' in text and 'chờ xác nhận' not in text


@pytest.mark.parametrize('style,short', [
    ('trả lời ngắn gọn',True),('không cần dài dòng',True),
    ('đừng trả lời ngắn gọn, hãy giải thích chi tiết',False),
])
def test_response_length_respects_affirmed_style_and_negation(style,short):
    text=read_reply(summary(),today=date(2026,10,19),preferences={'response_style':style})
    assert ('chưa phải toàn bộ tiền đã thu' not in text)==short
    assert '**12 đơn**' in text and '**2.450.000đ**' in text


def test_read_renderer_cannot_replace_a_write_confirmation():
    result={'tool':'create_price_proposal','facts':{'new_price_vnd':500000}}
    assert read_reply(result,today=date(2026,10,19),preferences={}) is None
