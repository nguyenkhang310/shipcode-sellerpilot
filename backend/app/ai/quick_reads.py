"""Conservative Vietnamese read grammar: normalize, remove politeness, extract slots.

Only whole, unambiguous clauses match. Analysis, hypothetical values, writes and
mixed requests stay with the model. This is rule-based NLP, not a trained model.
"""
import re
from datetime import date, timedelta

from app.ai.contracts import ParsedCommand
from app.ai.money import plain
from app.ai.money import money_mentions

STOCK_NUMBER_WORDS = {
    'khong': 0, 'mot': 1, 'hai': 2, 'ba': 3, 'bon': 4, 'tu': 4,
    'nam': 5, 'sau': 6, 'bay': 7, 'tam': 8, 'chin': 9, 'muoi': 10,
}


def read_text(message):
    text = ' '.join(plain(message).lower().split()).strip(' ?!.,')
    text = re.sub(r'^(?:ban oi[, ]+|sellerpilot oi[, ]+)', '', text)
    text = re.sub(r'^(?:xin chao(?: ban)?|chao ban|alo|hello|hi)[,!.]+\s*', '', text)
    text = re.sub(r'^(?:(?:ban |hay |vui long |lam on )?)(?:giup (?:minh|toi|em) |cho (?:minh|toi|em) )', '', text)
    text = re.sub(r'(?:[, ]+(?:giup (?:minh|toi|em)|dum (?:minh|toi|em)|voi|nhe|nha|a|di|coi|vay))+$', '', text)
    text = re.sub(r'^nay\b', 'hom nay', text)
    return ' '.join(text.split())


def normalize_reporting_day_words(text):
    return re.sub(r'\b(bay|ba muoi) ngay\b', lambda match: '7 ngay' if match[1] == 'bay' else '30 ngay', text)


_PERIOD = re.compile(
    r'\b(?:hom nay|hom qua|hom kia|ngay mai|'
    r'\d{1,3} ngay(?: qua| gan day| vua roi| toi| sau)?|'
    r'tuan (?:nay|truoc|qua|vua roi|toi|sau)|thang (?:nay|truoc|qua|toi|sau)|'
    r'(?:ngay )?(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}-\d{4}|\d{1,2}/\d{1,2}(?:/\d{4})?))\b'
)
_SHOP = r'shop(?: (?:cua )?(?:minh|toi|em)| nay)?'
_SUBJECT = rf'(?:{_SHOP} )?'
_AMOUNT = r'(?:bao nhieu|may|nhieu|nhiu)'
_ORDER_AMOUNT = rf'(?:da )?(?:(?:co|duoc|ban(?: duoc)?|chot(?: duoc)?|ra|nhan(?: duoc)?) )?{_AMOUNT} don(?: hang)?'
_VALUE = rf'(?:(?:tong|tong cong) )?(?:doanh thu|doanh so|gia tri don(?: hang)?)(?: cua shop)?(?: (?:(?:la |duoc )?{_AMOUNT}|the nao|ra sao|sao(?: roi)?))?'
_SELL = r'(?:da )?(?:ban(?: duoc)?|chot(?: duoc)?)'
_SALE_AMOUNT = rf'(?:(?:{_SELL}|tong|tong cong) )?{_AMOUNT} tien|{_SELL} {_AMOUNT}'
_SALES_CLAUSE = rf'(?:{_ORDER_AMOUNT}|{_VALUE}|{_SALE_AMOUNT})'
_SUMMARY = rf'{_SUBJECT}{_SALES_CLAUSE}(?: (?:va |voi )?{_SALES_CLAUSE})?'
_QUANTITY = r'(?:cai|chiec|mon|san pham)'
_COMPARE = re.compile(r'\b(?:so voi|so sanh|chenh lech|hon kem)\b')
_ORDER_STATUSES = {
    'pending': r'(?:cho xac nhan|cho xu ly)',
    'paid': r'(?:cho lay hang|cho gui hang|cho dong goi)',
    'shipped': r'(?:dang giao|dang van chuyen)',
    'delivered': r'(?:da )?giao',
    'cancelled': r'(?:da )?huy',
    'returned': r'(?:da )?hoan(?: hang)?',
}


def sales_text(text):
    text = normalize_reporting_day_words(text)
    text = re.sub(r'\b(?:mot tuan qua|tuan qua|tuan vua roi)\b', '7 ngay qua', text)
    text = re.sub(r'\b(?:ngay )?(?:hom nay|bua nay)\b', 'hom nay', text)
    text = re.sub(r'\b(?:ngay )?(?:hom qua|bua qua)\b', 'hom qua', text)
    text = re.sub(r'\bngay hom kia\b', 'hom kia', text)
    return text


def sales_period(text, *, today):
    """Take only period phrases present in the seller's words."""
    periods = list(dict.fromkeys(_PERIOD.findall(text)))
    if len(periods) > 1:
        if set(periods) == {'hom nay', 'hom qua'} and _COMPARE.search(text):
            return {'day': today, 'days': 1, 'compare_yesterday': True}
        return {'sales_period_issue': 'multiple_periods'}
    if not periods:
        return {}
    period = periods[0].removeprefix('ngay ')
    if period == 'mai' or period.endswith((' toi', ' sau')):
        return {'sales_period_issue': 'future_period'}
    if period in ('hom nay', 'hom qua', 'hom kia'):
        return {'day': today - timedelta(days=('hom nay', 'hom qua', 'hom kia').index(period)), 'days': 1}
    if period in ('tuan nay', 'tuan truoc', 'thang nay', 'thang truoc', 'thang qua'):
        calendar = 'week' if period.startswith('tuan') else 'month'
        if period.endswith('nay'):
            day = today
        elif calendar == 'week':
            day = today - timedelta(days=today.weekday() + 1)
        else:
            day = today.replace(day=1) - timedelta(days=1)
        return {'day': day, 'calendar_period': calendar}
    if match := re.match(r'(\d+) ngay', period):
        days = int(match[1])
        return {'day': today, 'days': days} if 1 <= days <= 30 else {'sales_period_issue': 'range_limit'}
    try:
        if '-' in period:
            first, middle, last = period.split('-')
            year, month, day = map(int, (first, middle, last) if len(first) == 4 else (last, middle, first))
        else:
            day, month, year = map(int, (period.split('/') + [str(today.year)])[:3])
        return {'day': date(year, month, day), 'days': 1}
    except ValueError:
        return {'sales_period_issue': 'invalid_date'}


def sales_period_followup(text, *, today):
    text = sales_text(text)
    match = re.fullmatch(rf'(?:the |vay )?(?:con )?({_PERIOD.pattern})(?: (?:thi )?(?:sao|the nao|ra sao|roi))?', text)
    return sales_period(match[1], today=today) if match else None


def shop_summary_read(text, *, today):
    text = sales_text(text)
    period = sales_period(text, today=today)
    body = ' '.join(_PERIOD.sub('', text).replace(',', ' ').split())
    # Only strip anchored presentation/reading phrases, never a write or an open-ended question.
    body = re.sub(r'^(?:(?:ve|tao|hien thi|cho xem|xem|lap) )?(?:bieu do|bang thong ke|bao cao truc quan)(?: (?:ve|cua))?\s+', '', body)
    body = re.sub(r'^(?:hoi|xem|kiem tra|cho xem|thong ke|bao cao)(?: giup (?:minh|toi|em))?\s+', '', body)
    body = re.sub(r'^tinh (?:den|toi) (?:gio|luc nay)\s+| (?:ban|ad)$', '', body)
    body = re.sub(r' (?:(?:tinh )?(?:den|toi) gio|roi|chua)$', '', body)
    if period.get('compare_yesterday'):
        body = re.sub(r'\b(?:so voi|so sanh|chenh lech|hon kem|va|voi)\b', ' ', body)
        body = re.sub(r' (?:the nao|ra sao)$', '', ' '.join(body.split()))
    for status, label in _ORDER_STATUSES.items():
        if re.fullmatch(rf'{_SUBJECT}(?:(?:co |con )?{_AMOUNT} don(?: hang)? {label}'
                        rf'|{label} (?:duoc )?{_AMOUNT} don(?: hang)?'
                        rf'|don(?: hang)? {label} (?:co |con )?{_AMOUNT})', body):
            return ParsedCommand(intent='shop_summary', sales_metric=status, **period)
    modes = (
        ('units', rf'{_SUBJECT}{_SELL} {_AMOUNT} {_QUANTITY}'),
        ('collected', rf'{_SUBJECT}(?:da )?(?:thu(?: duoc)?|nhan(?: duoc)?) {_AMOUNT} tien|{_SUBJECT}(?:tien|doanh thu) (?:thuc thu|da thu)(?: {_AMOUNT})?'),
        ('delivered', rf'{_SUBJECT}(?:gia tri|tong tien)(?: cac)? don (?:da )?giao(?:(?: la)? {_AMOUNT})?'),
        (None, _SUMMARY),
        (None, rf'{_SUBJECT}(?:ban hang |ban )?(?:the nao|ra sao|sao(?: roi)?|ban chay khong)'),
        (None, r'(?:tinh hinh|tong quan|so lieu)(?: ban hang)?(?: (?:cua )?shop(?: (?:minh|toi|em))?)?'),
        (None, r'(?:thong ke|bao cao)' if period else r'(?!)'),
    )
    for metric, pattern in modes:
        if re.fullmatch(pattern, body):
            return ParsedCommand(intent='shop_summary', sales_metric=metric,
                                 **(period or {'day': today}))
    return None


def quick_read(message, *, today):
    text = read_text(message)
    text = re.sub(r'[.?!;]\s*(?:ban )?(?:cho (?:minh|toi|em) xem|ve|xem|hien thi) '
                  r'(?:bieu do|bang so lieu|bao cao truc quan)$', '', text)
    if summary := shop_summary_read(text, today=today):
        return summary
    # Inventory has no reporting-date slot; do not silently ignore such a filter.
    if _PERIOD.search(sales_text(text)):
        return None
    inventory = re.sub(r'^(?:xem|kiem tra|cho xem|liet ke)\s+', '', text)
    if re.fullmatch(rf'(?:ton kho|hang ton(?: kho)?|kho|kho con gi)(?: (?:cua )?shop(?: (?:minh|toi|em))?)?'
                    rf'|(?:{_SHOP}|{_SUBJECT}(?:kho|ton kho)) con {_AMOUNT}(?: (?:hang|san pham))?', inventory):
        return ParsedCommand(intent='inventory_query', inventory_scope='overview')
    item = r'(?:(?:nhung|cac) )?(?:san pham|mat hang|mon|ma|hang)(?: nao)?'
    if re.fullmatch(rf'{_SUBJECT}(?:co |con )?(?:{item} )?(?:sap het|gan het|ton thap|het hang)(?: hang)?(?: khong)?', inventory):
        return ParsedCommand(intent='inventory_query', inventory_scope='low_stock',
                             low_stock_threshold=0 if 'het hang' in inventory and not re.search('sap het|gan het', inventory) else 5)
    threshold = r'\d{1,5}|' + '|'.join(STOCK_NUMBER_WORDS)
    low = re.fullmatch(
        rf'(?:{item} )?(?:con |ton(?: kho)? |(?:sap het|gan het|ton thap)(?: hang)? )?'
        rf'(duoi|khong qua|toi da) ({threshold})(?: (?:cai|chiec|san pham))?', inventory)
    if low:
        limit = int(low[2]) if low[2].isdecimal() else STOCK_NUMBER_WORDS[low[2]]
        limit = max(0, limit - (1 if low[1] == 'duoi' else 0))
        return ParsedCommand(intent='inventory_query', inventory_scope='low_stock', low_stock_threshold=min(limit, 10000))
    sku_stock = rf'(?:con|ton(?: kho)?)(?: lai)? {_AMOUNT}(?: (?:hang|san pham|cai|chiec))?'
    sku_price = rf'(?:gia|gia ban)(?: (?:la )?(?:{_AMOUNT}(?: tien)?|sao|the nao))?'
    sku = re.fullmatch(
        rf'(?:(?:sku|ma) ([a-z0-9][a-z0-9._-]{{1,99}})|([a-z][a-z0-9._-]*\d[a-z0-9._-]*))'
        rf' (?:{sku_stock}(?: va {sku_price})?|{sku_price}|{_AMOUNT} tien)', inventory)
    if sku:
        code = sku[1] or sku[2]
        if code not in {'nay', 'do'}:
            return ParsedCommand(intent='inventory_query', sku=code.upper(), inventory_scope='single_sku')
    return None


def simple_pricing_read(message):
    """Only a complete labelled-cost question may use exact local wording.

    Extraction/evidence validation and Decimal arithmetic run before this.
    Strategy, multiple scenarios, negotiation and open questions do not match.
    """
    text = read_text(message)
    for mention in reversed(money_mentions(text, include_bare=False)):
        if mention.value is None or not 0 <= mention.value <= 1_000_000_000:
            return False
        text = text[:mention.start] + '_amount_' + text[mention.end:]
    text = re.sub(r'\d+(?:[.,]\d+)?\s*%', '_percent_', text)
    role = r'(?:gia von|gia nhap|von|dong goi|chi phi khac|quang cao moi don|gia ban)'
    detail = rf'(?:{role}\s*(?:la |[:=] )?_amount_|(?:phi san|phi nen tang|tong phi)\s*(?:la |[:=] )?_percent_)(?: (?:moi|mot) (?:don|san pham))?'
    selling = r'(?:neu )?ban _amount_ (?:thi )?(?:con )?(?:loi|lai|tien loi) bao nhieu'
    question = rf'(?:{selling}|(?:tinh )?(?:loi|lai|tien loi|hoa von) bao nhieu)'
    return bool(re.fullmatch(rf'{detail}(?:[,;. ]+(?:va )?{detail})*[,;. ]+{question}', text))
