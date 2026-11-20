"""Language hints and transcript handling for Gemini Live."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ai.money import plain


class LivePreferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    language: Literal['vi', 'en'] = 'vi'
    voice: Literal['male', 'female'] | None = None


GEMINI_VOICES = {'male': 'Puck', 'female': 'Kore'}
COMMON_TERMS = ('SellerPilot', 'UTech Official', 'Shopee', 'TikTok Shop', 'SKU', 'SPX', 'Viettel Post')
VIETNAMESE_TERMS = ('năm xị', 'hai củ rưỡi', 'giá bán', 'tồn kho', 'mã vận đơn', 'xác nhận đăng',
                    'tiêu đề', 'mô tả', 'bản nháp', 'biểu đồ', 'hàng sắp hết', 'tổng giá trị đơn hàng',
                    'bao nhiêu đơn hàng', 'hôm nay', 'bảy ngày qua', 'ba mươi ngày qua',
                    'sản phẩm này', 'sản phẩm vừa đăng', 'tăng doanh số')
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
