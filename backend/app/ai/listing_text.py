"""Shared listing instruction detection for parsing and model validation."""
import re
from app.ai.money import plain

AI_DESCRIPTION_PHRASES = {
    'ai viet', 'viet giup', 'tu viet', 'sellerpilot viet',
}

def _plain(value):
    return ' '.join(plain(value).split())


def _is_generic_product_command(message: str) -> bool:
    text = _plain(message).strip(" .!?")
    if re.search(r'\b(?:dang|dua|tao|them)\b', text) and re.search(
        r'\b(?:san pham nay|mat hang nay|anh nay|cai nay|len san|len shop)\b', text
    ):
        return True
    if re.match(r"^(?:(?:hay|vui long|lam on|ban)\s+)?(?:dang|tao|them|dua)\s+"
                r"(?:san pham|mat hang)\s+(?:nay|do|nay len|tu anh|trong anh)\b", text):
        return True
    return bool(re.fullmatch(
        r"(?:(?:hay|vui long|lam on)\s+)?(?:dang|tao|them|dua)\s+"
        r"(?:san pham|mat hang)(?:\s+(?:nay|moi|tu anh|trong anh))?"
        r"(?:\s+(?:len(?:\s+(?:san|shop))?|vao(?:\s+(?:san|shop))?|"
        r"giup(?:\s+(?:minh|toi|em))?|cho\s+(?:minh|toi|em)|duoc|khong|di|nhe|nha))*",
        text,
    ))


def _wants_ai_description(message: str) -> bool:
    text = _plain(message).strip(" .!?")
    if listing_copy_choice(text) is False:
        return False
    return bool(
        text in {_plain(item) for item in AI_DESCRIPTION_PHRASES}
        or re.search(r'\b(?:tu goi y|goi y (?:cho hay|(?:mot |1 )?(?:tieu de|mo ta|ten)))\b', text)
        or re.search(r'\b(?:suggest|write|improve|polish|rewrite)\b.{0,40}\b(?:title|description)\b', text)
        or re.search(r"\b(?:ai|sellerpilot)\b.{0,25}\b(?:viet|soan|tao)\b", text)
        or re.search(r"\b(?:viet|soan|tao)\b.{0,25}\b(?:mo ta|bang ai)\b", text)
        or re.search(r"\b(?:viet|soan|tao|toi uu|sua|lam dep|cai thien)\b.{0,40}\b(?:caption|tieu de|noi dung|mo ta)\b", text)
        or re.search(r"\btu\s+(?:viet|soan)\b", text)
        or re.search(r'\b(?:viet|soan|lam)\b.{0,12}\blai\b.{0,12}\bban nhap\b', text)
        or re.search(r"\b(?:caption|tieu de|noi dung)\b.{0,35}\b(?:viet|soan|sua|hay hon)\b", text)
        or re.search(r"\b(?:hay|giup)\b.{0,70}\bmo ta(?: san pham)?\b", text)
        or re.search(r"\bdua vao (?:hinh|anh)\b.{0,45}\bmo ta(?: san pham)?\b", text)
    )


def listing_copy_fields(message: str) -> set[str]:
    text = _plain(' '.join(line for line in message.splitlines() if not labelled_copy(line)))
    result = set()
    if re.search(r'\b(?:tieu de|ten san pham|title|product name)\b', text):
        result.add('name')
    if re.search(r'\b(?:mo ta|noi dung|caption|description)\b', text):
        result.add('description')
    return result


def listing_copy_choice(message: str) -> bool | None:
    text = _plain(message).strip(' .,!?:;')
    text = re.sub(r' (?:nhe|nha|di|giup minh|please)$', '', text)
    if re.fullmatch(r'(?:co|duoc|ok(?:e)?|dong y|vang|yes|sure|go ahead)|'
                    r'(?:(?:co|duoc|ok(?:e)?|vang|dong y)[, ]+)?(?:lam dep|viet lai|cai thien|cho hay hon)', text):
        return True
    if re.fullmatch(r'(?:khong(?: con)?(?: can)?[, ]*)?(?:giu (?:nguyen|vay|ban cu)|de vay)|'
                    r'khong(?: (?:can|muon)(?: (?:viet lai|lam dep|cai thien)(?: (?:tieu de|mo ta|ca hai))?)?)?|'
                    r'no(?: thanks)?|keep (?:it|as is)', text):
        return False
    return None


def labelled_copy(message: str) -> bool:
    return bool(re.search(r'(?:^|[\n;,])\s*(?:ten(?: san pham)?|tieu de|mo ta|noi dung|caption|title|description)'
                          r'(?:\s+(?:la|is)\b|\s*[:=])', plain(message)))
