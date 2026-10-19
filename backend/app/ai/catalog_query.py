"""Recognize complete, read-only catalogue questions from the current turn."""
import re
import unicodedata

from app.ai.money import plain, money_mentions


def catalog_lookup(message):
    source = ' '.join(unicodedata.normalize('NFKC', message).lower().split()).strip(' ?.!,')
    text = plain(source)
    original = text
    # These requests need their existing business/write path, not a catalogue read.
    # Preserve accents for ambiguous nouns such as "sữa" versus "sửa".
    if (re.search(r'\b(?:sửa|đổi|xóa|đăng|thêm|tạo|nhập)\b', source)
            or re.search(r'\b(?:sku|doi gia|sua gia|sua san pham|xoa|dang ban|them san pham|tao san pham|gia nhap|gia von|tien loi|loi nhuan|tinh loi|tinh gia|lai|phi san|so sanh|phan tich|tu van|goi y|viet|mo ta|ke hoach|sap het|het hang|ton kho|ton thap|gan het|low stock|doanh thu|doanh so|don hang|bao nhieu don|may don|gia tri don|co the)\b', text)
            or re.search(r'\b(?:hom nay|hom qua|ngay mai|(?:tuan|thang|nam) (?:nay|qua|truoc|toi))\b', text)):
        return None
    recognized = bool(re.search(
        r'^(?:tim(?: kiem)?|xem|liet ke|cho (?:minh|toi|em) (?:xem|tim)|'
        r'(?:shop|kho)(?: (?:minh|toi|co|con|ban))? |con |vay (?:thi |con )?|'
        r'(?:co|ban) .+ (?:khong|ko|k)|.+ (?:co|con) (?:san pham nao|hang|khong|ko|k))', text))
    lower = upper = None
    # Pull price predicates out before extracting the product words. Match the
    # whole amount with the shared money parser (1tr, 500k, 1.000.000đ, ...).
    spans = []
    for match in re.finditer(r'\b(duoi|tren|khong qua|toi da|it nhat|tu|den|toi)\s+', text):
        # Do not turn accented product nouns into comparison operators.
        if source[match.start():match.start() + len(match.group(1))] in {'tủ', 'đèn', 'đen', 'tỏi', 'tối'}:
            continue
        tail = text[match.end():]
        # A range has two independent comparison operands; question words such
        # as "không" must not be read as a zero-valued monetary suffix.
        tail = re.split(r'\s+(?:den|toi|duoi|tren|it nhat|khong qua|khong|ko|va)\b', tail, maxsplit=1)[0]
        amounts = money_mentions(source[match.end():match.end() + len(tail)])
        if not amounts or amounts[0].start != 0 or amounts[0].value is None:
            if match.group(1) in {'tu', 'den', 'toi'}:
                # "tủ lạnh" and "đèn bàn" (also typed without accents) are
                # product names unless an actual amount follows the token.
                continue
            return None
        amount = amounts[0]
        if amount.value < 0 or amount.value > 1_000_000_000:
            return None
        op = match.group(1)
        if op in {'tren', 'it nhat', 'tu'}:
            value = amount.value + (1 if op == 'tren' else 0)
            lower = max(lower, value) if lower is not None else value
        else:
            value = amount.value - (1 if op == 'duoi' else 0)
            upper = min(upper, value) if upper is not None else value
        end = match.end() + amount.end
        currency = re.match(r'\s*(?:dong|vnd|d)\b', text[end:])
        if currency:
            end += currency.end()
        spans.append((match.start(), end))
    if not recognized:
        return None
    for start, end in reversed(spans):
        text = text[:start] + ' ' + text[end:]
    text = ' '.join(text.split())
    address = re.match(r'^(?:bạn|bên bạn)\s+', source)
    if address:
        text = text[address.end():]
    text = re.sub(r'^(?:vay (?:thi|con)\s+|con\s+)', '', text)
    text = re.sub(r'^(?:cho (?:minh|toi|em)\s+)?(?:tim(?: kiem)?|xem|liet ke)\s+', '', text)
    text = re.sub(r'^(?:trong )?(?:shop|kho)(?: (?:cua )?(?:minh|toi))?\s+', '', text)
    text = re.sub(r'^(?:(?:co|con)\s+)?(?:(?:cac|nhung)\s+)?(?:san pham|mat hang|loai|mau|cai)\s+', '', text)
    text = re.sub(r'^(?:co|con)\s+', '', text)
    if re.search(r'\bbán\b', source):
        text = re.sub(r'^ban\s+', '', text)
    text = re.sub(r'\s+(?:co|con)\s+(?:san pham|mau|loai|cai|hang)(?:\s+nao)?\b', ' ', text)
    text = re.sub(r'\s+(?:trong (?:shop|kho)|cua shop)\b', ' ', text)
    text = re.sub(r'(?:\s+(?:co|con|hay|khong|ko|k|nhi|nhe|nao))+$', '', text)
    text = re.sub(r'\s+(?:gia|gia ban)\s*$', '', text)
    text = ' '.join(text.split()).strip(' ?.!,')
    # Reject extra clauses instead of dropping instructions or guessing filters.
    if (not text or len(text) > 100 or len(text.split()) > 12
            or text in {'tim', 'tim kiem', 'xem', 'liet ke', 'sao', 'the nao'}
            or re.fullmatch(r'(?:do|nay|kia|no|nao)(?: (?:thi sao|the nao))?', text)
            or money_mentions(text, include_bare=False)
            or re.match(r'^(?:(?:khoang|tam|hon|gan)\s+)?\d', text)
            or re.search(r'\b(?:va|roi|bao nhieu|duoi|tren|phu hop|nen|ban chay|gia re)\b', text)
            or upper is not None and upper < 0
            or lower is not None and upper is not None and lower > upper):
        return None
    start = original.find(text)
    query = source[start:start + len(text)] if start >= 0 else text
    return {'query': query, 'min_price_vnd': lower, 'max_price_vnd': upper}
