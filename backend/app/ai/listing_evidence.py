"""Commercial roles are verified equally in local and browser listing flows."""
import re
from app.ai.fallback import normalize_text
from app.ai.money import affirmed_quote, money_mentions, plain
from app.ai.quantities import quantity_value


def commercial_context(evidence, message, *, stock=False):
    if stock and quantity_value(evidence) == 0 and plain(evidence).strip(' .!?') in {'het hang', 'khong con hang', 'het roi', 'khong con cai nao', 'ton kho bang khong'}:
        return normalize_text(message).strip(' .!?') == normalize_text(evidence).strip(' .!?')
    if not affirmed_quote(evidence, message):
        return False
    text, quote = normalize_text(message), normalize_text(evidence)
    for match in re.finditer(re.escape(quote), text):
        context = plain(text[max(0, match.start() - 70):match.end()])
        markers = re.findall(r'\b(?:gia von|gia nhap|chi phi|phi ship|phi van chuyen|gia cu|gia goc|gia ban|gia|ban|de|chot|kho|con|so luong|ram|dung luong)\b', context)
        if markers and markers[-1] in {'gia von', 'gia nhap', 'chi phi', 'phi ship', 'phi van chuyen', 'gia cu', 'gia goc', 'ram', 'dung luong'}:
            continue
        if stock:
            if re.search(r'\b(?:cai|chiec|san pham|sp|bo|doi|may|xe|trai|qua)\b', plain(quote)) or markers and markers[-1] in {'kho', 'con', 'so luong'}:
                return True
        elif any(item.explicit and item.value is not None for item in money_mentions(quote)) or markers and markers[-1] in {'gia ban', 'gia', 'ban', 'de', 'chot'}:
            return True
    return False
