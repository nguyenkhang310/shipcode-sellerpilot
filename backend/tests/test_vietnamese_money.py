from datetime import date

import pytest

from app.ai.money import money_mentions, money_hints, single_money
from app.ai.fallback import extract_price, parse_fallback
from app.ai.advisor_contracts import EconomicsUpdate
from app.services.advisor import _grounded_number


@pytest.mark.parametrize('phrase,value', [
    ('5 xị', 500000), ('5xi', 500000), ('năm xị', 500000), ('nam xi', 500000),
    ('2 củ', 2000000), ('hai củ rưỡi', 2500000), ('2 cu ruoi', 2500000),
    ('1 triệu rưỡi', 1500000), ('triệu rưỡi', 1500000), ('nửa củ', 500000),
    ('1tr2', 1200000), ('1tr200k', 1200000), ('1 triệu 200 nghìn', 1200000),
    ('một triệu hai trăm nghìn', 1200000), ('hai trăm ba mươi lăm nghìn', 235000),
    ('1.200.000đ', 1200000), ('1.200k', 1200000), ('1,2 triệu', 1200000),
    ('2k5', 2500), ('0đ', 0), ('-5 xị', -500000), ('5 chục nghìn', 50000),
    ('5 trăm ngàn', 500000), ('50 ngàn', 50000), ('0.001k', 1),
])
def test_shared_money_grammar(phrase, value):
    assert single_money(phrase) == value
    assert extract_price(phrase, sku=None) == value


@pytest.mark.parametrize('phrase', ['5 rưỡi', '5 chục', '5 lít', '500–600k', '5 xị hoặc 6 xị', '20.5đ', '1tr50'])
def test_ambiguous_or_fractional_currency_never_becomes_a_fixed_price(phrase):
    assert single_money(phrase) is None
    assert extract_price(phrase, sku=None) is None
    assert any(item['needs_clarification'] for item in money_hints(phrase))


def test_price_change_does_not_take_stock_or_model_number_as_the_price():
    message = 'Đổi giá SKU KB87 từ 1 củ xuống 5 xị, còn 20 cái'
    command = parse_fallback(message, today=date(2026, 10, 18))
    assert command.sku == 'KB87' and command.new_price_vnd == 500000
    assert extract_price('bán 5 xị, tồn 20 cái', sku=None) == 500000
    assert extract_price('để 500k hoặc 600k', sku=None) is None


def test_currency_hints_preserve_original_quote_and_do_not_convert_vegetables():
    assert money_hints('giá bán NĂM XỊ') == [{'quote': 'NĂM XỊ', 'value_vnd': 500000, 'needs_clarification': False}]
    assert money_hints('một củ hành, 2 củ tỏi') == []
    assert len(money_mentions('1 triệu 200 nghìn')) == 1


def test_cost_evidence_uses_the_same_units_and_requires_a_single_value():
    message = 'Giá vốn 5 xị, bán 1 củ.'
    assert _grounded_number(EconomicsUpdate(field='unit_cost_vnd', value=500000, evidence='Giá vốn 5 xị'), message)
    assert not _grounded_number(EconomicsUpdate(field='unit_cost_vnd', value=50000, evidence='Giá vốn 5 xị'), message)
    assert not _grounded_number(EconomicsUpdate(field='unit_cost_vnd', value=500000, evidence=message), message)


@pytest.mark.parametrize('phrase,value', [('2 củ 5',2500000),('1 triệu 200',1200000),
    ('một triệu hai trăm',1200000),('1 triệu 50',None)])
def test_spaced_money_tails_are_not_silently_truncated(phrase,value):
    assert single_money(phrase) == value


def test_quantity_after_a_currency_unit_is_not_a_money_fraction():
    assert extract_price('giá 1 triệu 20 cái',sku=None) == 1000000


def test_negated_money_and_cancelled_price_change_are_not_actions():
    from app.ai.money import affirmed_quote
    assert not affirmed_quote('5 xị','Không phải 5 xị mà là 6 xị')
    assert affirmed_quote('6 xị','Không phải 5 xị mà là 6 xị')
    assert not _grounded_number(EconomicsUpdate(field='unit_cost_vnd',value=500000,evidence='5 xị'),'Giá vốn không phải 5 xị')
    assert parse_fallback('Đừng đổi giá SKU A001 thành 5 xị',today=date(2026,10,18)).intent == 'unknown'
