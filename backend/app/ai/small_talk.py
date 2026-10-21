"""Whole-message conversational turns; never match inside product instructions."""
from app.ai.quick_reads import read_text


def social_reply(message: str) -> str | None:
    text = read_text(message)
    if text in {'chao', 'chao ban', 'xin chao', 'xin chao ban', 'hello', 'hi', 'alo', 'helo',
                'ban la ai', 'ban ten gi', 'sellerpilot la gi'}:
        return 'Chào bạn, mình là SellerPilot của ShipCode. Hôm nay bạn muốn mình giúp gì cho shop?'
    if text in {'cam on', 'cam on ban', 'cam on ban nhieu', 'cam on nhieu', 'thanks', 'thank you',
                'ok', 'oke', 'okie', 'duoc roi'}:
        return 'Rất sẵn lòng. Khi cần xem số liệu hoặc xử lý việc tiếp theo cho shop, cứ nhắn mình nhé.'
    return None
