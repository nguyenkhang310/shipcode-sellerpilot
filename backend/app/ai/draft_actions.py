"""Whole-turn draft controls; captions and hypothetical instructions never match."""
import re

from app.ai.quick_reads import read_text


def draft_action(message: str) -> str | None:
    text = read_text(message)
    text = re.sub(r'^(?:(?:minh|toi|em)\s+)?(?:muon\s+)?', '', text)
    if re.fullmatch(r'(?:huy(?: dang| ban nhap| san pham)?(?: nay)?|bo ban nhap(?: nay)?|'
                    r'(?:thoi )?khong dang(?: san pham(?: nay)?)? nua|dung dang(?: san pham(?: nay)?)? nua)', text):
        return 'cancel'
    if re.fullmatch(r'(?:de sau|de lat(?: lam tiep)?|tam dung|luu ban nhap|khoan dang|chua dang|dung dang voi)', text):
        return 'pause'
    return None
