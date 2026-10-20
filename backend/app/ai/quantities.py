"""Strict seller quantity evidence; model guesses never become stock."""
import re
from app.ai.money import NUMBER, _number, plain

COUNT_UNIT = r'(?:sản phẩm|san pham|cái|cai|chiếc|chiec|bộ|bo|đôi|doi|máy|may|xe|sp|trái|trai|quả|qua)'

EMPTY_STOCK_PHRASES = {'het hang', 'khong con hang', 'het roi', 'khong con cai nao', 'ton kho bang khong'}

def quantity_value(text):
    normalized = plain(text).strip(' .!?')
    if normalized in EMPTY_STOCK_PHRASES:
        return 0
    match = re.fullmatch(rf'\s*({NUMBER})(?:\s*{COUNT_UNIT})?\s*', text, re.I)
    if not match:
        return None
    number = match[1]
    if re.search(r'\d', number) and not re.fullmatch(r'\d+|\d{1,3}(?:[.,]\d{3})+', number):
        return None
    words = plain(number).split()
    if words.count('tram') > 1 or words.count('muoi') > 1 or words[:2] == ['khong', 'tram']:
        return None
    try:
        value = _number(number)
    except (ValueError, ArithmeticError):
        return None
    return int(value) if value == value.to_integral_value() and 0 <= value <= 1000000 else None
