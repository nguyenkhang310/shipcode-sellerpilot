"""Read current seller orders; conversation references never authorize writes."""
import json
import re
from datetime import datetime, timezone

from app.ai.quick_reads import read_text
from app.integrations.order_management import order_detail
from app.integrations.ute_mall import ShopItemNotFoundError
from app.services.seller_voice import money

LABELS = {'pending': 'Chờ xác nhận', 'paid': 'Chờ lấy hàng', 'shipped': 'Đang giao',
          'delivered': 'Đã giao', 'cancelled': 'Đã hủy', 'returned': 'Đã hoàn hàng'}
ID = r'(?:don(?: hang)?\s*(?:so\s*|ma\s*)?#?\s*|#)([1-9]\d{0,9})\b'


def order_reference(message, runs=()):
    text = read_text(message)
    matches = list(re.finditer(ID, text))
    if matches:
        ids = {int(match[1]) for match in matches}
        return next(iter(ids)) if len(ids) == 1 else None
    if not runs:
        return None
    facts = json.loads(runs[-1].facts_json)
    if facts.get('order_lookup', {}).get('missing_id'):
        bare = re.fullmatch(r'#?([1-9]\d{0,9})', text)
        if bare:
            return int(bare[1])
    # Only immediately preceding order turns can supply a reference. Never
    # carry an order selection through a change of topic or use an LLM guess.
    reference = re.fullmatch(r'(?:con )?(?:don (?:do|nay)|no)(?: (?:sao roi|toi dau|the nao))?|(?:con )?(?:ma van don|van don|lich su|buoc tiep theo|roi sao|gio sao)', text)
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
            return {'answer': '\n\n'.join(row['answer'] for row in rows) + '\n\nNhắn mã đơn bạn muốn xem chi tiết.',
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
    answer = f"**Đơn #{id}** hiện **{LABELS.get(order['status'], order['status'])}**, tổng thanh toán **{money(order['total_vnd'])}**."
    if order['tracking_number']:
        answer += f"\n\nVận chuyển: **{order['shipping_carrier']}** · mã **{order['tracking_number']}**."
    else:
        answer += '\n\nĐơn chưa có mã vận đơn.'
    status_event = next((event for event in order['events'] if event['kind'] == 'status'), None)
    if not order['unrecorded_status_change'] and status_event and status_event['to_status'] == order['status']:
        instant = datetime.fromisoformat(status_event['created_at'].replace('Z', '+00:00'))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        answer += '\n\nCập nhật trạng thái lúc **' + instant.astimezone(shop.timezone).strftime('%H:%M %d/%m/%Y') + '**.'
    else:
        answer += '\n\nChưa ghi nhận thời điểm chuyển sang trạng thái này.'
    if show_action:
        answer += '\n\nBạn có thể mở chi tiết ngay bên dưới để xem lịch sử hoặc xử lý đơn.'
    if re.search(r'\b(?:huy|xac nhan|ban giao|hoan tat|sua|doi)\b', read_text(message)):
        answer += ' Thay đổi chỉ được lưu sau khi bạn xem lại và xác nhận trong form.'
    generate = bool(re.search(r'\b(?:tai sao|vi sao|phan tich|de xuat|nen lam gi|can lam gi)\b', read_text(message)))
    return {'answer': answer, '_generate': generate, 'facts': {'order_lookup': context, 'order_action': {'id': id}},
            'tool': 'get_order_tracking', 'tool_arguments': {'id': id}}
