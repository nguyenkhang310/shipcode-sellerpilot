"""Vietnamese monetary expressions shared by intent, listings and cost evidence.

Keep the seller's original wording and spans. Monetary units are interpreted
deterministically; product/price/cost roles still come from context, not numbers.
Ambiguous expressions have no value instead of being guessed by the model.
"""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


def plain(text):
    text = unicodedata.normalize('NFKD', text.lower().replace('đ', 'd'))
    return ''.join(char for char in text if not unicodedata.combining(char))


WORD_VALUES = {'khong': 0, 'mot': 1, 'hai': 2, 'ba': 3, 'bon': 4, 'tu': 4,
               'nam': 5, 'lam': 5, 'sau': 6, 'bay': 7, 'tam': 8, 'chin': 9}
WORDS = r'(?:không|khong|một|mot|mốt|bốn|bon|tư|tu|hai|ba|năm|nam|lăm|lam|sáu|sau|bảy|bay|tám|tam|chín|chin|mười|muoi|mươi|trăm|tram|linh|lẻ|le)'
NUMBER = rf'(?:-?\d+(?:[.,]\d+)*|nửa|nua|{WORDS}(?:\s+{WORDS})*)'
UNIT = r'(?:trăm\s+(?:nghìn|ngàn)|tram\s+(?:nghin|ngan)|chục\s+(?:nghìn|ngàn)|chuc\s+(?:nghin|ngan)|triệu|trieu|nghìn|nghin|ngàn|ngan|đồng|dong|tỷ|tỉ|ty|ti|củ|cu|xị|xi|vnd|vnđ|tr|k|đ|₫)'
EXPLICIT = re.compile(rf'(?<!\w)(?P<number>{NUMBER})\s*(?P<unit>{UNIT})(?![^\W\d_]|_)', re.I)
LOWER_UNIT = re.compile(rf'\s*(?P<number>{NUMBER})\s*(?P<unit>{UNIT})(?![^\W\d_]|_)', re.I)
HALF = re.compile(r'\s+(?:rưỡi|ruoi)\b', re.I)
SHORT = re.compile(r'\d{1,3}(?![\w.,])')
SPACE_TAIL = re.compile(rf'\s+(?P<number>{NUMBER})(?!\w)', re.I)
IMPLICIT_HALF = re.compile(rf'(?<!\w)(?P<unit>{UNIT})\s+(?:rưỡi|ruoi)\b', re.I)
BARE = re.compile(r'(?<![\w.,])-?\d+(?:[.,]\d+)*(?![\w.,])')
AMBIGUOUS = re.compile(rf'(?<!\w)(?:{NUMBER})\s+(?:lít|lit|chai|chục|chuc|trăm|tram|rưỡi|ruoi)\b', re.I)
RANGE = re.compile(rf'(?<!\w){NUMBER}\s*(?:{UNIT})?\s*(?:[-–~]|đến|den|tới|toi|hoặc|hoac|hay)\s*{NUMBER}\s*(?:{UNIT})?', re.I)
FACTORS = {'ty': 10**9, 'ti': 10**9, 'trieu': 10**6, 'tr': 10**6, 'cu': 10**6,
           'xi': 100000, 'k': 1000, 'nghin': 1000, 'ngan': 1000,
           'tram nghin': 100000, 'tram ngan': 100000, 'chuc nghin': 10000, 'chuc ngan': 10000,
           'dong': 1, 'd': 1, '₫': 1, 'vnd': 1}


@dataclass(frozen=True)
class MoneyMention:
    start: int
    end: int
    text: str
    value: int | None
    explicit: bool
    colloquial: bool = False
    factor: int = 1


def _number(text):
    normalized = plain(text).strip()
    if normalized == 'nua':
        return Decimal('.5')
    if re.fullmatch(r'-?\d+(?:[.,]\d+)*', normalized):
        unsigned = normalized.lstrip('-')
        if not unsigned.startswith('0') and re.fullmatch(r'\d{1,3}(?:[.,]\d{3})+', unsigned):
            return Decimal(normalized.replace('.', '').replace(',', ''))
        return Decimal(normalized.replace(',', '.'))
    total, current = 0, None
    for word in normalized.split():
        if word in WORD_VALUES:
            if current is not None:
                raise ValueError('Ambiguous consecutive number words')
            current = WORD_VALUES[word]
        elif word == 'tram':
            total += (current or 1) * 100
            current = None
        elif word == 'muoi':
            total += (current or 1) * 10
            current = None
        elif word in {'linh', 'le'}:
            continue
        else:
            raise ValueError('Unsupported number')
    total += current or 0
    return Decimal(total)


def _integer(amount):
    return int(amount) if amount.is_finite() and amount == amount.to_integral_value() and abs(amount) <= 10**15 else None


def money_mentions(text, *, include_bare=True):
    result = []
    for match in EXPLICIT.finditer(text):
        if result and match.start() < result[-1].end:
            continue
        # "một củ hành" is a vegetable, not a million dong.
        unit = plain(match['unit'])
        if unit == 'cu' and re.match(r'\s+(?:hành|hạnh|tỏi|gừng|khoai|cải|nghệ)\b', text[match.end():], re.I):
            continue
        factor = FACTORS[unit]
        end = match.end()
        half = HALF.match(text, end)
        short = SHORT.match(text, end) if factor >= 1000 else None
        try:
            number = _number(match['number'])
            amount = number * factor
            if half:
                amount += (Decimal('.5') * factor) * (-1 if number < 0 else 1)
                end = half.end()
            elif short:
                # Two suffix digits ("1tr50") have competing conventions.
                # Ask for a full amount rather than silently selecting a scale.
                amount = Decimal('NaN') if len(short[0]) == 2 else amount + (Decimal(short[0]) * factor / (10**len(short[0]))) * (-1 if number < 0 else 1)
                end = short.end()
            lower = LOWER_UNIT.match(text, end)
            last_factor = factor
            while lower and FACTORS[plain(lower['unit'])] < last_factor:
                child_factor = FACTORS[plain(lower['unit'])]
                child_number = _number(lower['number'])
                if child_number < 0 or child_number * child_factor >= last_factor:
                    break
                amount += child_number * child_factor * (-1 if number < 0 else 1)
                end, last_factor = lower.end(), child_factor
                lower = LOWER_UNIT.match(text, end)
            tail = SPACE_TAIL.match(text, end) if factor >= 1000 and last_factor == factor and not half and not short else None
            if tail and not re.match(r'\s*(?:cái|chiếc|sản phẩm|sp|máy|đơn|lần|ngày|tháng|năm|%)\b', text[tail.end():], re.I):
                raw_tail = tail['number']
                tail_value = _number(raw_tail)
                if re.fullmatch(r'\d|\d{3}', raw_tail):
                    amount += tail_value * factor / (10 if len(raw_tail) == 1 else 1000) * (-1 if number < 0 else 1)
                elif not re.search(r'\d', raw_tail) and re.search(r'\b(?:tram|muoi)\b', plain(raw_tail)) and tail_value < 1000:
                    amount += tail_value * factor / 1000 * (-1 if number < 0 else 1)
                else:
                    amount = Decimal('NaN')
                end = tail.end()
            value = _integer(amount)
        except (ValueError, InvalidOperation):
            value = None
        colloquial = unit in {'xi', 'cu'} or bool(half or short) or end != match.end() or not re.search(r'\d', match['number'])
        result.append(MoneyMention(match.start(), end, text[match.start():end], value, True, colloquial, factor))

    def occupied(start, end):
        return any(start < item.end and end > item.start for item in result)

    for match in IMPLICIT_HALF.finditer(text):
        if not occupied(match.start(), match.end()):
            factor = FACTORS[plain(match['unit'])]
            result.append(MoneyMention(match.start(), match.end(), match[0], _integer(Decimal('1.5') * factor), True, True, factor))
    result.sort(key=lambda item: item.start)
    combined = []
    for item in result:
        if (combined and item.value is not None and combined[-1].value is not None
                and item.factor < combined[-1].factor and item.value < combined[-1].factor
                and re.fullmatch(r'\s*(?:(?:và|va|lẻ|le)\s+)?', text[combined[-1].end:item.start])):
            previous = combined.pop()
            combined.append(MoneyMention(previous.start, item.end, text[previous.start:item.end],
                previous.value + item.value, True, True, item.factor))
        else:
            combined.append(item)
    result = combined
    for match in AMBIGUOUS.finditer(text):
        if not occupied(match.start(), match.end()):
            result.append(MoneyMention(match.start(), match.end(), match[0], None, True, True))
    for match in RANGE.finditer(text):
        if any(item.explicit and item.start < match.end() and item.end > match.start() for item in result):
            result = [item for item in result if not (item.start < match.end() and item.end > match.start())]
            result.append(MoneyMention(match.start(), match.end(), match[0], None, True, True))
    if include_bare:
        for match in BARE.finditer(text):
            if not occupied(match.start(), match.end()):
                try:
                    value = _integer(_number(match[0]))
                except (ValueError, InvalidOperation):
                    value = None
                result.append(MoneyMention(match.start(), match.end(), match[0], value, False))
    return sorted(result, key=lambda item: item.start)


def single_money(text):
    mentions = money_mentions(text)
    if len(mentions) != 1 or re.search(r'\d\s*%|(?:đến|tới|hoặc|hay)\s+\d|\d\s*[-–~]\s*\d', text, re.I):
        return None
    return mentions[0].value


def affirmed_quote(quote, message):
    quote = unicodedata.normalize('NFKC', quote).lower().strip()
    source = unicodedata.normalize('NFKC', message).lower()
    amounts = money_mentions(quote)
    offset = amounts[0].start if amounts else 0
    for match in re.finditer(re.escape(quote), source):
        prefix = source[max(0, match.start() + offset - 45):match.start() + offset]
        if not re.search(r'\b(?:không|khong|ko|đừng|dung|chưa|chua)(?:\s+(?:phải|phai|bán|ban|lấy|lay|chốt|chot|để|de|giá|gia|vốn|von)){0,4}\s*$', prefix):
            return True
    return False


def money_hints(text):
    return [{'quote': item.text, 'value_vnd': item.value,
             'needs_clarification': item.value is None,
             **({'negated': True} if not affirmed_quote(item.text, text) else {})}
            for item in money_mentions(text, include_bare=False)]
