"""Whole-message conversational turns; never match inside product instructions."""
import re

from app.ai.quick_reads import read_text


def social_reply(message: str, *, ongoing: bool = False) -> str | None:
    text = read_text(message)
    if re.fullmatch(r'(?:xin )?(?:chao|hello|hi|alo|helo)(?: (?:ban|sellerpilot|tro ly))?', text):
        return ('Mình đây. Bạn đang cần xem phần nào?' if ongoing else
                'Chào bạn, mình là **SellerPilot**, trợ lý bán hàng do **ShipCODE** phát triển. Hôm nay shop cần mình phụ việc gì?')
    if re.fullmatch(r'(?:ban la ai|ban ten gi|sellerpilot la gi|ai (?:la nguoi )?(?:phat trien|tao ra|lam ra) '
                    r'(?:ban|sellerpilot)|(?:ban|sellerpilot) (?:la )?do ai phat trien|(?:ban )?gioi thieu '
                    r'(?:ve )?(?:ban|ban than(?: ban)?|sellerpilot)(?: cho minh)?|sellerpilot cua (?:ai|doi nao|nhom nao))', text):
        return ('Mình là **SellerPilot**, trợ lý bán hàng do **ShipCODE** phát triển. '
                'Mình có thể cùng bạn xem shop đang bán thế nào, xử lý việc còn dang dở và lên kế hoạch cho món bạn muốn đẩy tiếp.')
    if re.fullmatch(r'cam on(?: ban)?(?: (?:nhieu|rat nhieu))?|thanks|thank you', text):
        return 'Không có gì, bạn nhé.'
    if text in {'ok', 'oke', 'okie', 'duoc roi', 'minh hieu roi', 'hieu roi', 'ro roi'}:
        return 'Ừ, mình hiểu rồi.'
    if text in {'tam biet', 'hen gap lai', 'bye', 'goodbye'}:
        return 'Hẹn gặp lại bạn!'
    if text in {'ban oi', 'ban co do khong', 'ban con do khong', 'sellerpilot oi'}:
        return 'Mình đây, bạn nói đi.'
    return None
