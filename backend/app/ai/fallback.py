import re
import unicodedata
from datetime import date, timedelta

from app.ai.contracts import ParsedCommand


CHANGE_PRICE_PHRASES = (
    "đổi giá", "doi gia", "cập nhật giá", "cap nhat gia", "sửa giá", "sua gia",
    "điều chỉnh giá", "dieu chinh gia", "set giá", "set gia",
    "giảm giá sku", "giam gia sku", "hạ giá", "ha gia", "tăng giá", "tang gia",
)
LOW_STOCK_PHRASES = (
    "sắp hết", "sap het", "tồn thấp", "ton thap", "gần hết", "gan het",
    "low stock", "hết hàng", "het hang",
)
INVENTORY_PHRASES = (
    "tồn kho", "ton kho", "còn bao nhiêu", "con bao nhieu", "kiểm tra sku",
    "kiem tra sku", "tra sku", "giá sku", "gia sku",
)
SUMMARY_PHRASES = (
    "doanh thu", "bao nhiêu đơn", "bao nhieu don", "đơn chờ", "don cho",
    "tình hình shop", "tinh hinh shop", "tổng quan shop", "tong quan shop",
    "đơn hàng", "don hang", "doanh số", "doanh so", "giá trị đơn", "gia tri don",
)

EXPLICIT_SKU_RE = re.compile(r"\bsku\s*[:#-]?\s*([a-z0-9][a-z0-9._-]{1,99})\b", re.IGNORECASE)
SHORT_SKU_RE = re.compile(r"\b([a-z]{1,12}[-_]?\d{2,})\b", re.IGNORECASE)
LONG_NUMERIC_SKU_RE = re.compile(r"\b(\d{8,30})\b")
PRICE_RE = re.compile(
    r"(?<![\w])(-?\d+(?:[.,]\d+)*)(?:\s*)(tỷ|ty|b|triệu|trieu|tr|k|nghìn|nghin|ngàn|ngan|đ|₫|vnd)?\b",
    re.IGNORECASE,
)


def normalize_text(message: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", message).strip().lower().split())


def parse_fallback(message: str, *, today: date) -> ParsedCommand:
    text = normalize_text(message)
    sku = extract_sku(text)

    # A pricing question is read-only, even when it mentions reducing a price.
    if ('%' in text and any(phrase in text for phrase in CHANGE_PRICE_PHRASES)) or any(phrase in text for phrase in (
        'giá vốn', 'gia von', 'giá nhập', 'gia nhap', 'lợi nhuận', 'loi nhuan',
        'tiền lời', 'tien loi', 'lời bao nhiêu', 'loi bao nhieu', 'lãi', 'lai ',
        'hòa vốn', 'hoa von', 'biên lời', 'bien loi', 'biên lợi', 'bien loi',
        'phí sàn', 'phi san', 'chi phí', 'chi phi', 'định giá', 'dinh gia',
        'chiến lược', 'chien luoc', 'tăng doanh thu', 'tang doanh thu',
        'giữ khách', 'giu khach', 'khách mục tiêu', 'khach muc tieu',
    )) or re.search(r'\b(?:lời|lãi|loi|lai)\b', text) or re.search(r'(?:có nên|co nen|nên|nen).{0,45}(?:giá|gia|bán|ban|giảm|giam|tăng|tang)', text):
        return ParsedCommand(intent='sales_advice', sku=sku)

    if any(phrase in text for phrase in CHANGE_PRICE_PHRASES):
        return ParsedCommand(
            intent="change_price",
            sku=sku,
            new_price_vnd=extract_price(text, sku=sku),
        )

    if any(phrase in text for phrase in ("nên làm gì", "nen lam gi", "tư vấn", "tu van", "viết mô tả", "viet mo ta", "viết bài", "lên kế hoạch", "cải thiện", "ưu tiên", "uu tien", "phân tích", "phan tich")):
        return ParsedCommand(intent="sales_advice", sku=sku)

    search = re.search(r"(?:tìm kiếm|tim kiem|tìm|tim)(?:\s+sản phẩm|\s+san pham)?\s+(.+)", text)
    if search and not sku and not any(phrase in text for phrase in LOW_STOCK_PHRASES):
        return ParsedCommand(intent="product_search", query=search.group(1).strip("?.! ")[:200])

    if any(phrase in text for phrase in LOW_STOCK_PHRASES):
        return ParsedCommand(
            intent="inventory_query",
            inventory_scope="low_stock",
            low_stock_threshold=extract_threshold(text),
        )

    if (sku and "sku" in text) or any(phrase in text for phrase in INVENTORY_PHRASES):
        return ParsedCommand(
            intent="inventory_query",
            sku=sku,
            inventory_scope="single_sku" if sku else "overview",
        )

    if any(phrase in text for phrase in SUMMARY_PHRASES):
        days = 7 if any(p in text for p in ("7 ngày", "7 ngay", "tuần", "tuan")) else 30 if any(p in text for p in ("30 ngày", "30 ngay", "tháng", "thang")) else 1 if any(p in text for p in ("hôm nay", "hom nay")) else None
        return ParsedCommand(intent="shop_summary", day=extract_day(text, today=today), days=days)

    return ParsedCommand(intent="unknown")


def extract_sku(text: str) -> str | None:
    for pattern in (EXPLICIT_SKU_RE, SHORT_SKU_RE, LONG_NUMERIC_SKU_RE):
        match = pattern.search(text)
        if match:
            return match.group(1).upper()
    return None


def extract_price(text: str, *, sku: str | None) -> int | None:
    values: list[int] = []
    if sku:
        text = re.sub(re.escape(sku), "", text, flags=re.IGNORECASE)
    sku_digits = re.sub(r"\D", "", sku or "")
    for match in PRICE_RE.finditer(text):
        raw_value, raw_unit = match.groups()
        digits_only = re.sub(r"\D", "", raw_value)
        if sku_digits and digits_only == sku_digits:
            continue
        value = parse_money(raw_value, raw_unit)
        if value is not None:
            values.append(value)
    return values[-1] if values else None


def parse_money(raw_value: str, raw_unit: str | None) -> int | None:
    unit = (raw_unit or "").lower()
    sign = -1 if raw_value.startswith("-") else 1
    unsigned = raw_value.lstrip("-")
    try:
        if unit in {"tỷ", "ty", "b"}:
            number = float(unsigned.replace(",", "."))
            return sign * int(round(number * 1_000_000_000))
        if unit in {"triệu", "trieu", "tr"}:
            number = float(unsigned.replace(",", "."))
            return sign * int(round(number * 1_000_000))
        if unit in {"k", "nghìn", "nghin", "ngàn", "ngan"}:
            number = float(unsigned.replace(",", "."))
            return sign * int(round(number * 1_000))
        normalized = unsigned.replace(".", "").replace(",", "")
        return sign * int(normalized)
    except ValueError:
        return None


def extract_day(text: str, *, today: date) -> date:
    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        try:
            return date(*(int(part) for part in iso_match.groups()))
        except ValueError:
            pass

    local_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", text)
    if local_match:
        day, month, year = (int(part) for part in local_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            pass

    if "hôm qua" in text or "hom qua" in text:
        return today - timedelta(days=1)
    return today


def extract_threshold(text: str) -> int:
    if "hết hàng" in text or "het hang" in text:
        return 0
    match = re.search(
        r"(?:dưới|duoi|không quá|khong qua|tối đa|toi da|<=?|ngưỡng|nguong)\s*(\d{1,5})",
        text,
    )
    if not match:
        return 5
    return min(int(match.group(1)), 10_000)
