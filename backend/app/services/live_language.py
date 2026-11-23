"""Language hints and transcript handling for Gemini Live."""
import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ai.money import plain


class LivePreferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    language: Literal['vi', 'en'] = 'vi'
    voice: Literal['male', 'female'] | None = None


GEMINI_VOICES = {
    'vi': {'male': 'Iapetus', 'female': 'Erinome'},
    'en': {'male': 'Puck', 'female': 'Kore'},
}
LIVE_GREETINGS = {
    'vi': (
        'Chào chủ shop! Hôm nay bạn muốn mình giúp việc gì?',
        'Mình đây! Bạn muốn bắt đầu từ việc nào của shop hôm nay?',
        'Chào bạn! Hôm nay bạn muốn xem số liệu hay xử lý việc khác cho shop?',
        'Chào chủ shop! Bạn cứ nói việc cần làm, mình bắt đầu ngay.',
        'Chào bạn! Có việc gì của shop bạn muốn mình giúp trước không?',
    ),
    'en': (
        'Hi there! What can I help you with today?',
        'Hey! Where would you like to start with your shop today?',
        'Hi! Want to check your shop’s numbers or tackle something else?',
        'Hello! Tell me what’s on your list for the shop today.',
        'Good to hear from you! What should we work on first?',
    ),
}
COMMON_TERMS = ('SellerPilot', 'UTech Official', 'Shopee', 'TikTok Shop', 'SKU', 'SPX', 'Viettel Post')
VIETNAMESE_TERMS = ('năm xị', 'hai củ rưỡi', 'giá bán', 'tồn kho', 'mã vận đơn', 'xác nhận đăng',
                    'tiêu đề là', 'giữ nguyên tiêu đề', 'viết lại mô tả', 'bản nháp', 'biểu đồ',
                    'hàng sắp hết', 'tổng giá trị đơn hàng', 'kế hoạch bảy ngày', 'bảy ngày tới',
                    'bao nhiêu đơn hàng', 'hôm nay', 'bảy ngày qua', 'ba mươi ngày qua',
                    'doanh thu', 'đơn chờ lấy hàng', 'đơn hoàn', 'đơn hủy', 'giao thành công',
                    'mã phân loại', 'giá vốn', 'phí sàn', 'lợi nhuận',
                    'sản phẩm này', 'sản phẩm vừa đăng', 'tăng doanh số', 'xóa sản phẩm', 'xác nhận xóa sản phẩm')
ENGLISH_TERMS = ('order value', 'low stock', 'tracking number', 'confirm publish', 'confirm product update',
                 'confirm order update', 'Vietnamese dong')


def transcription_config(language, product_name=None):
    terms = ENGLISH_TERMS if language == 'en' else VIETNAMESE_TERMS
    vocabulary = [*COMMON_TERMS, *terms]
    if product_name:
        name = ' '.join(product_name.split())
        if 2 <= len(name) <= 80 and name not in vocabulary:
            vocabulary.append(name)
    return {'languageCodes': ['en-US' if language == 'en' else 'vi-VN'], 'customVocabulary': vocabulary}


def merge_transcript(previous, text, *, final=False):
    if not previous:
        return text
    candidate, current = text.strip(), previous.strip()
    if candidate == current:
        return previous
    if candidate.startswith(current) and candidate[len(current):len(current) + 1] in ' ,.!?;:\n' and (
        not text[0].isspace() or ' ' in current or final
    ):
        return text
    before, incoming = current.split(), candidate.split()
    if len(incoming) >= 2 and len(incoming) < len(before) and not text[0].isspace():
        if [plain(word).casefold() for word in incoming] == [plain(word).casefold() for word in before[:len(incoming)]]:
            return previous
    if final and len(before) >= 4 and len(incoming) >= len(before) - 1:
        shared = sum(a.strip('.,?!').casefold() == b.strip('.,?!').casefold() for a, b in zip(before, incoming))
        if [word.casefold() for word in before[:2]] == [word.casefold() for word in incoming[:2]] and shared >= len(before) * .6:
            return text
    # Some providers resend the tail of a phrase in the next segment.
    for size in range(min(len(before), len(incoming), 12), 1, -1):
        if [word.casefold() for word in before[-size:]] == [word.casefold() for word in incoming[:size]]:
            parts = candidate.split(maxsplit=size)
            return current + (' ' + parts[size] if len(parts) > size else '')
    # The provider also streams sub-word pieces, including partial words.
    return previous + text


def unclear_vietnamese(text):
    words = re.findall(r'[a-z]+|\d+', plain(text).lower())
    if len(words) < 6 or not any(len(word) <= 1 for word in words):
        return False
    if any(word in {'ao', 'quan', 'giay', 'hang', 'gia', 'ban', 'san', 'ton', 'kho', 'don',
                    'cho', 'cua', 'voi', 'la', 'nay', 'gi', 'khong', 'shop', 'shopee', 'sku', 'xac', 'anh', 'hinh'}
           or word.isdigit() for word in words):
        return False
    return sum(len(word) <= 2 for word in words) / len(words) >= .62


REPEAT_QUESTION = 'Mình nghe chưa rõ. Bạn nói lại chậm hơn một chút nhé.'


def repeat_question(language):
    return 'I didn’t catch that. Could you say that again?' if language == 'en' else REPEAT_QUESTION


def incomplete_shop_phrase(text):
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', plain(text)).split()) in {'san pham', 'product', 'products'}


def listing_opening(message):
    text = ' '.join(re.sub(r'[^a-z0-9]+', ' ', plain(message)).split())
    return bool(re.fullmatch(
        r'(?:(?:minh|toi|em|anh|chi) )?(?:(?:muon|can|hay|giup (?:minh|toi|em|anh|chi)) )?'
        r'(?:dang(?: ban)?|them) (?:mot )?(?:san pham|mon hang)(?: moi)?(?: len (?:shop|cua hang))?'
        r'(?: giup (?:minh|toi|em|anh|chi))?(?: nhe| nha| voi)?'
        r'|(?:(?:i (?:want|need)|i would like|i d like) to |(?:can|could) you |please )?'
        r'(?:list|post|add|upload) (?:a |one |my )?(?:new )?(?:product|item)(?: please)?',
        text,
    ))


def spoken_listing_name(message, *, expecting_title=False):
    """Keep the seller's words, distinguishing a dictated title from a product cue."""
    source = unicodedata.normalize('NFC', message).strip()
    text = plain(source)
    exact = re.match(r'^(?:cho |dat |giu )?(?:tieu de|ten san pham|ten)(?: (?:chinh xac|nguyen van))?(?: la| thanh)?\s*[:=,]?\s+', text)
    cue = re.match(r'^(?:(?:minh|toi|em) (?:muon )?)?(?:(?:cai|mon|san pham) nay |day |nay )?'
                   r'(?:(?:dang ban|dang) (?:giup minh )?|(?:la )?ban |la )(?:(?:mot|1) (?:chiec )?|chiec )?', text)
    if not (exact or cue or expecting_title) or '?' in source:
        return None
    offset = (exact or cue).end() if exact or cue else 0
    quoted = re.match(r'^(?:"([^"\n]+)"|“([^”\n]+)”)', source[offset:])
    name = ((quoted[1] or quoted[2]) if quoted else re.split(
        r'[,;\n]\s*(?=(?:giá|tồn|còn|mô tả|ngành)\b)|\s+(?=(?:giá bán|tồn kho|còn \d)\b)',
        source[offset:], maxsplit=1, flags=re.I)[0].strip().removesuffix('.').strip(' ;'))
    if (not 2 <= len(name) <= 120 or '\n' in name
            or re.fullmatch(r'(?:san pham|mon hang|cai nay|do|day|tieu de|ten|ban nhap)', plain(name))
            or re.match(r'^(?:gia|ton|con \d|mo ta|nganh|\d+|ok|dong y|khong|duoc|hay|co the|huy|xac nhan|cam on)\b', plain(name))):
        return None
    return name, bool(exact or expecting_title and not cue)


def copy_choice(message):
    text = ' '.join(plain(message).strip(' .,!?').replace(',', ' ').split())
    text = re.sub(r' (?:nhe|nha|di|giup minh)$', '', text)
    if re.fullmatch(r'(?:minh |toi )?(?:(?:khong )?giu(?: nguyen)?(?: (?:ten|tieu de)(?: cu)?)?|khong(?: can| lam dep| viet lai)?|giu vay|de vay)', text):
        return 'keep'
    if re.fullmatch(r'(?:minh |toi )?(?:co|duoc|ok(?:e)?|dong y|lam dep(?: (?:ca hai|tieu de|tieu de va mo ta))?|(?:viet|soan) (?:lai|dep hon|lai cho dep)(?: ca hai)?)', text):
        return 'polish'
    return None
