"""Read current seller orders; conversation references never authorize writes."""
import json
import re
from datetime import datetime, timezone

from app.ai.quick_reads import read_text
from app.ai.small_talk import social_reply
from app.integrations.order_management import order_detail
from app.integrations.ute_mall import ShopItemNotFoundError
from app.services.seller_voice import money

LABELS = {'pending': 'Chờ xác nhận', 'paid': 'Chờ lấy hàng', 'shipped': 'Đang giao',
          'delivered': 'Đã giao', 'cancelled': 'Đã hủy', 'returned': 'Đã hoàn hàng'}
ID = r'(?:don(?: hang)?\s*(?:so\s*|ma\s*)?#?\s*|#)([1-9]\d{0,9})\b'
TRACKING = re.compile(r'\b(?:ma van don|ma theo doi|van don|tracking)\b')
ORDER_EDIT = re.compile(r'\b(?:huy|xac nhan|ban giao|hoan tat|sua|doi)\b')


def order_reference(message, runs=()):
    text = read_text(message)
    matches = list(re.finditer(ID, text))
    if matches:
        ids = {int(match[1]) for match in matches}
        return next(iter(ids)) if len(ids) == 1 else None
    last = next((run for run in reversed(runs) if run.tool_name or not social_reply(run.message)), None)
    if not last:
        return None
    facts = json.loads(last.facts_json)
    if facts.get('order_lookup', {}).get('missing_id'):
        bare = re.fullmatch(r'#?([1-9]\d{0,9})', text)
        if bare:
            return int(bare[1])
    # Only immediately preceding order turns can supply a reference. Never
    # carry an order selection through a change of topic or use an LLM guess.
    reference = re.fullmatch(
        r'(?:con |huy |xac nhan |ban giao |hoan tat |sua |doi )?(?:don (?:do|nay)|no)'
        r'(?: (?:sao roi|toi dau(?: roi)?|the nao))?'
        r'|(?:con |xem |tim |co )?(?:ma van don|ma theo doi|van don)(?: (?:cua )?don (?:do|nay))?(?: (?:thi sao|dau|chua|khong))?'
        r'|(?:con |xem )?(?:lich su|buoc tiep theo|roi sao|gio sao)', text)
    if reference:
        return facts.get('order_lookup', {}).get('id')
    return None


def is_order_question(message, runs=()):
    text = read_text(message)
    return bool(re.search(ID, text) or order_reference(message, runs) or re.fullmatch(
        r'(?:con |xem |kiem tra |theo doi )?(?:trang thai don(?: hang)?|lich su don(?: hang)?|ma van don|don hang toi dau)', text))


def order_answer(shop, message, runs=(), *, show_action=True):
    if not is_order_question(message, runs):
        return None
    id = order_reference(message, runs)
    if id is None:
        ids = list(dict.fromkeys(int(match[1]) for match in re.finditer(ID, read_text(message))))
        if len(ids) > 1:
            if len(ids) > 5:
                return {'answer': 'Mình có thể đối chiếu tối đa 5 mã đơn mỗi lượt. Bạn chọn 5 mã cần kiểm tra trước nhé.',
                        'facts': {'order_lookup': {'missing_id': True}}, 'tool': 'get_order_tracking', 'tool_arguments': {}}
            rows = [order_answer(shop, '#' + str(number), show_action=False) for number in ids]
            return {'answer': '\n\n'.join(row['answer'] for row in rows),
                    'facts': {'order_comparison': [row['facts']['order_lookup'] for row in rows]},
                    'tool': 'get_order_tracking', 'tool_arguments': {'ids': ids}}
        return {'answer': 'Bạn muốn xem đơn nào? Gửi mình mã đơn, ví dụ **#123**, mình sẽ kiểm tra trạng thái và lịch sử mới nhất.',
                'facts': {'order_lookup': {'missing_id': True}}, 'tool': 'get_order_tracking', 'tool_arguments': {}}
    try:
        order = order_detail(shop, id)
    except ShopItemNotFoundError:
        return {'answer': f'Mình chưa tìm thấy **đơn #{id}** trong shop đang liên kết. Bạn kiểm tra lại mã đơn nhé.',
                'facts': {'order_lookup': {'id': id, 'found': False}}, 'tool': 'get_order_tracking', 'tool_arguments': {'id': id}}
    # Read-only context excludes buyer address/phone and operation/version IDs.
    context = {key: order[key] for key in ('id', 'status', 'total_vnd', 'shipping_carrier', 'tracking_number', 'events', 'unrecorded_status_change', 'allowed_statuses')}
    context['found'] = True
    text = read_text(message)
    label = f'**Đơn #{id}**'
    status = LABELS.get(order['status'], 'Chưa rõ trạng thái')
    answer = f"{label} · **{status}** · tổng giá trị **{money(order['total_vnd'])}**."
    tracking = order['tracking_number']
    carrier = f" qua **{order['shipping_carrier']}**" if order['shipping_carrier'] else ''
    tracking_answer = (f"{label} gửi{carrier}, mã vận đơn **{tracking}**." if tracking
                       else f"{label} chưa có mã vận đơn.")
    if TRACKING.search(text):
        answer = tracking_answer
    elif tracking and show_action:
        answer += '\n\n' + tracking_answer
    status_event = next((event for event in order['events'] if event['kind'] == 'status'), None)
    if show_action and not TRACKING.search(text) and not order['unrecorded_status_change'] and status_event and status_event['to_status'] == order['status']:
        instant = datetime.fromisoformat(status_event['created_at'].replace('Z', '+00:00'))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        answer += '\n\nCập nhật trạng thái lúc **' + instant.astimezone(shop.timezone).strftime('%H:%M %d/%m/%Y') + '**.'
    elif re.search(r'\b(?:lich su|khi nao|luc nao|may gio)\b', text):
        answer += '\n\nChưa ghi nhận thời điểm chuyển sang trạng thái này.'
    if ORDER_EDIT.match(text):
        answer += '\n\nBạn mở thẻ của đơn bên dưới để xem lại và xác nhận thay đổi nhé.'
    generate = bool(re.search(r'\b(?:tai sao|vi sao|phan tich|de xuat|nen lam gi|can lam gi)\b', text))
    return {'answer': answer, '_generate': generate, 'facts': {'order_lookup': context, 'order_action': {'id': id}},
            'tool': 'get_order_tracking', 'tool_arguments': {'id': id}}
