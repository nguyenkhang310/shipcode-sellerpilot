"""Conservative Vietnamese read grammar: normalize, remove politeness, extract slots.

Only whole, unambiguous clauses match. Analysis, hypothetical values, writes and
mixed requests stay with the model. This is rule-based NLP, not a trained model.
"""
import re
from datetime import timedelta

from app.ai.contracts import ParsedCommand
from app.ai.money import plain
from app.ai.money import money_mentions


def read_text(message):
    text = ' '.join(plain(message).lower().split()).strip(' ?!.,')
    text = re.sub(r'^(?:ban oi[, ]+|sellerpilot oi[, ]+)', '', text)
    text = re.sub(r'^(?:(?:ban |hay |vui long |lam on )?)(?:giup (?:minh|toi|em) |cho (?:minh|toi|em) )', '', text)
    text = re.sub(r'(?:[, ]+(?:giup (?:minh|toi|em)|dum (?:minh|toi|em)|voi|nhe|nha|a|di|coi|vay))+$', '', text)
    text = re.sub(r'^nay\b', 'hom nay', text)
    return ' '.join(text.split())


def quick_read(message, *, today):
    text = read_text(message)
    period_re = r'\b(?:hom nay|hom qua|(?:7|30) ngay(?: qua| gan day)?|tuan (?:nay|qua|vua roi)|thang (?:nay|qua))\b'
    periods = re.findall(period_re, text)
    if len(set(periods)) > 1:
        return None
    period = periods[0] if periods else None
    calendar = 'week' if period == 'tuan nay' else 'month' if period == 'thang nay' else None
    days = 7 if period and ('7 ' in period or 'tuan' in period) else 30 if period and ('30 ' in period or 'thang' in period) else 1 if period else None
    day = today - timedelta(days=1) if period == 'hom qua' else today
    body = ' '.join(re.sub(period_re, '', text).replace(',', ' ').split())
    body = re.sub(r'^(?:xem|kiem tra|cho xem|thong ke|bao cao)(?: giup (?:minh|toi|em))?\s+', '', body)
    subject = r'(?:shop(?: (?:cua )?(?:minh|toi|em))? )?'
    count = r'(?:(?:co|duoc|ban duoc|chot duoc|nhan duoc) )?(?:bao nhieu|may) don(?: hang)?'
    value = r'(?:(?:tong|tong cong) )?(?:doanh thu|doanh so|gia tri don(?: hang)?)(?: cua shop)?(?: (?:la |duoc )?(?:bao nhieu|may))?'
    clause = rf'(?:{count}|{value})'
    summary = [rf'{subject}{clause}(?: (?:va|voi) {clause})?',
               rf'{subject}(?:ban hang |ban )?(?:the nao|ra sao|sao roi)',
               rf'(?:tinh hinh|tong quan|so lieu)(?: ban hang)?(?: (?:cua )?shop(?: (?:minh|toi|em))?)?',
               r'(?:thong ke|bao cao)' if period else r'(?!)',
               rf'{subject}(?:ban duoc|chot duoc) bao nhieu tien']
    if any(re.fullmatch(pattern, body) for pattern in summary):
        return ParsedCommand(intent='shop_summary', day=day, days=None if calendar else days, calendar_period=calendar)
    # Inventory has no reporting-date slot; do not silently ignore such a filter.
    if periods:
        return None
    inventory = re.sub(r'^(?:xem|kiem tra|cho xem)\s+', '', text)
    if re.fullmatch(rf'(?:ton kho|hang ton(?: kho)?|kho|kho con gi)(?: (?:cua )?shop(?: (?:minh|toi|em))?)?|{subject}con bao nhieu (?:hang|san pham)', inventory):
        return ParsedCommand(intent='inventory_query', inventory_scope='overview')
    item = r'(?:(?:nhung|cac) )?(?:san pham|mat hang|mon|ma|hang)(?: nao)?'
    if re.fullmatch(rf'(?:{subject}(?:co |con )?)?(?:{item} )?(?:sap het|gan het|ton thap|het hang)(?: hang)?(?: khong)?', inventory):
        return ParsedCommand(intent='inventory_query', inventory_scope='low_stock',
                             low_stock_threshold=0 if 'het hang' in inventory and not re.search('sap het|gan het', inventory) else 5)
    low = re.fullmatch(rf'(?:{item} )?(?:con |ton(?: kho)? )?(duoi|khong qua|toi da) (\d{{1,5}})(?: (?:cai|chiec|san pham))?', inventory)
    if low:
        threshold = max(0, int(low[2]) - (1 if low[1] == 'duoi' else 0))
        return ParsedCommand(intent='inventory_query', inventory_scope='low_stock', low_stock_threshold=min(threshold, 10000))
    sku = re.fullmatch(r'(?:(?:sku|ma) ([a-z0-9][a-z0-9._-]{1,99})|([a-z][a-z0-9._-]*\d[a-z0-9._-]*))(?: (?:con|ton(?: kho)?)(?: lai)? (?:bao nhieu|may)(?: (?:hang|san pham|cai|chiec))?| (?:gia|gia ban)(?: (?:la )?bao nhieu)?)', inventory)
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
        text = text[:mention.start] + '_amount_' + text[mention.end:]
    text = re.sub(r'\d+(?:[.,]\d+)?\s*%', '_percent_', text)
    role = r'(?:gia von|gia nhap|von|dong goi|phi san|phi nen tang|tong phi|chi phi khac|quang cao moi don|gia ban)'
    detail = rf'{role}\s*(?:la |[:=] )?(?:_amount_|_percent_)(?: (?:moi|mot) (?:don|san pham))?'
    selling = r'(?:neu )?ban _amount_ (?:thi )?(?:con )?(?:loi|lai|tien loi) bao nhieu'
    question = rf'(?:{selling}|(?:tinh )?(?:loi|lai|tien loi|hoa von) bao nhieu)'
    return bool(re.fullmatch(rf'{detail}(?:[,;. ]+(?:va )?{detail})*[,;. ]+{question}', text))
