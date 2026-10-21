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
    return bool(
        text in {_plain(item) for item in AI_DESCRIPTION_PHRASES}
        or re.search(r"\b(?:ai|sellerpilot)\b.{0,25}\b(?:viet|soan|tao)\b", text)
        or re.search(r"\b(?:viet|soan|tao)\b.{0,25}\b(?:mo ta|bang ai)\b", text)
        or re.search(r"\b(?:viet|soan|tao|toi uu|sua)\b.{0,40}\b(?:caption|tieu de|noi dung)\b", text)
        or re.search(r"\btu\s+(?:viet|soan)\b", text)
        or re.search(r'\b(?:viet|soan|lam)\b.{0,12}\blai\b.{0,12}\bban nhap\b', text)
        or re.search(r"\b(?:caption|tieu de|noi dung)\b.{0,35}\b(?:viet|soan|sua|hay hon)\b", text)
        or re.search(r"\b(?:hay|giup)\b.{0,70}\bmo ta(?: san pham)?\b", text)
        or re.search(r"\bdua vao (?:hinh|anh)\b.{0,45}\bmo ta(?: san pham)?\b", text)
    )
