"""Natural-language generation from verified tool facts, without another LLM call.

Read routing uses Vietnamese normalization and complete query clauses; this
renderer handles period, quantities, zero results and confirmed length preference.
No model prediction, random wording or invented business information is involved.
"""
from datetime import date, timedelta
import re

from app.ai.money import plain

ORDER_STATUS_TEXT = {
    'pending': 'chờ xác nhận', 'paid': 'chờ lấy hàng', 'shipped': 'đang giao',
    'delivered': 'đã giao', 'cancelled': 'đã hủy', 'returned': 'đã hoàn',
}


def money(value):
    return f'{int(value):,}'.replace(',', '.') + 'đ'


def summary_reply(facts, *, today: date, concise=False, detailed=False, focused=False):
    end = date.fromisoformat(facts.get('to_date') or facts['date'])
    start = date.fromisoformat(facts.get('from_date') or end.isoformat())
    if calendar := facts.get('calendar_period'):
        word = 'Tuần' if calendar == 'week' else 'Tháng'
        period = f"{word} {'này' if end == today else 'trước'} ({start:%d/%m}–{end:%d/%m})"
    elif start != end:
        period = f"Từ {start:%d/%m} đến {end:%d/%m}"
    else:
        period = 'Hôm nay' if end == today else 'Hôm qua' if end == today - timedelta(days=1) else f'Ngày {end:%d/%m/%Y}'
    count, value = facts['order_count'], facts['order_value_vnd']
    metric = facts.get('sales_metric')
    comparison = facts.get('compare_yesterday')
    if comparison and (not metric or not focused and metric in ('orders', 'order_value')):
        yesterday_count = facts['previous_order_count']
        yesterday_value = facts['previous_value_vnd']
        difference = value - yesterday_value
        movement = ('Giá trị đơn bằng nhau.' if difference == 0 else
                    f"Giá trị đơn hôm nay {'cao' if difference > 0 else 'thấp'} hơn **{money(abs(difference))}**.")
        return (f"**Hôm nay** shop có **{count} đơn hợp lệ**, tổng **{money(value)}**.\n"
                f"**Hôm qua cùng giờ** có **{yesterday_count} đơn hợp lệ**, tổng **{money(yesterday_value)}**.\n\n{movement}")
    if metric == 'collected':
        if comparison:
            return ('Mình chưa có số liệu đối soát tiền thực thu của hai kỳ. '
                    f'Giá trị đơn hôm nay là **{money(value)}**, cùng giờ hôm qua là **{money(facts["previous_value_vnd"])}**.')
        return (f"{period} mình chưa có số liệu đối soát tiền thực thu. "
                f"Giá trị của **{count} đơn hợp lệ** là **{money(value)}**.")
    if metric in ORDER_STATUS_TEXT:
        if 'all_order_status_counts' in facts:
            return f"Hiện shop có **{facts['all_order_status_counts'].get(metric, 0)} đơn {ORDER_STATUS_TEXT[metric]}**."
        amount = facts['order_status_counts'].get(metric, 0)
        answer = (f"Trong các đơn phát sinh kỳ này ({period.lower()}), có **{amount} đơn {ORDER_STATUS_TEXT[metric]}**."
                  if focused else f"{period} có **{amount} đơn {ORDER_STATUS_TEXT[metric]}**.")
        if metric == 'delivered':
            answer += f" Tổng giá trị đơn đã giao là **{money(facts['delivered_value_vnd'])}**."
        if comparison:
            previous_amount = facts['previous_order_status_counts'].get(metric, 0)
            answer += f"\n**Hôm qua cùng giờ** có **{previous_amount} đơn {ORDER_STATUS_TEXT[metric]}**."
            if metric == 'delivered':
                answer += f" Tổng giá trị đơn đã giao là **{money(facts['previous_delivered_value_vnd'])}**."
        return answer
    if metric == 'units':
        answer = units_reply(period, facts['units_sold'], facts['orders_with_item_quantity'], count)
        if comparison:
            answer += '\n' + units_reply('Hôm qua cùng giờ', facts['previous_units_sold'],
                                         facts['previous_orders_with_item_quantity'], facts['previous_order_count'])
        return answer
    if metric in ('delivered_value', 'average_order') or focused and metric in ('orders', 'order_value'):
        previous = None
        if metric == 'orders':
            label, current, previous = 'số đơn hợp lệ', count, facts.get('previous_order_count')
        elif metric == 'order_value':
            label, current = 'tổng giá trị đơn', money(value)
            if comparison:
                previous = money(facts['previous_value_vnd'])
        elif metric == 'delivered_value':
            label, current = 'giá trị đơn đã giao', money(facts['delivered_value_vnd'])
            if comparison:
                previous = money(facts['previous_delivered_value_vnd'])
        else:
            label = 'giá trị trung bình mỗi đơn'
            current = money(facts['average_order_vnd']) if count else None
            if comparison and facts['previous_order_count']:
                previous = money(round(facts['previous_value_vnd'] / facts['previous_order_count']))
        answer = (f'{period}, {label} là **{current}**.' if current is not None
                  else f'{period} chưa có đơn hợp lệ để tính giá trị trung bình.')
        if comparison:
            answer += (f' **Hôm qua cùng giờ**, chỉ số này là **{previous}**.' if previous is not None
                       else ' Hôm qua cùng giờ cũng chưa đủ đơn để tính.' if current is None
                       else ' Hôm qua cùng giờ chưa có đơn hợp lệ để tính.')
        return answer
    if count:
        answer = f"{period} shop có **{count} đơn hợp lệ**, tổng giá trị **{money(value)}**."
    else:
        answer = f"{period} shop chưa có đơn hợp lệ mới. Tổng giá trị đơn là **{money(value)}**."
    if not concise and start != end and count:
        answer += f" Trung bình **{money(facts['average_order_vnd'])}/đơn**."
    if detailed and count:
        if pending := facts.get('order_status_counts', {}).get('pending', facts.get('pending_count', 0)):
            answer += f" Trong số đó có **{pending} đơn** chờ xác nhận."
        answer += ' Số tiền này tính theo giá trị đơn. Phần tiền thực thu cần đối chiếu bảng đối soát.'
    return answer


def units_reply(period, units, covered, count):
    if covered == count:
        return f"{period} shop bán được **{units} sản phẩm** từ **{count} đơn hợp lệ**."
    if covered:
        return (f"{period} mình đối chiếu được **{units} sản phẩm từ {covered}/{count} đơn hợp lệ**. "
                'Các đơn còn lại thiếu số lượng dòng hàng.')
    return f"{period} có **{count} đơn hợp lệ** nhưng thiếu số lượng dòng hàng để đếm số sản phẩm đã bán."


def read_reply(result, *, today: date, preferences: dict):
    facts, tool = result['facts'], result['tool']
    style = plain(preferences.get('response_style', ''))
    rejects_brief = bool(re.search(r'\b(?:khong|dung)(?: tra loi)? ngan gon\b', style))
    concise = not rejects_brief and any(word in style for word in
        ('ngan gon', 'suc tich', 'that ngan', 'khong dai dong', 'khong can dai dong'))
    if tool == 'get_shop_summary':
        detailed = rejects_brief or not concise and bool(re.search(r'\b(?:giai thich|tra loi) chi tiet\b', style))
        return summary_reply(facts, today=today, concise=concise, detailed=detailed)
    if tool == 'get_inventory_overview':
        units = f"{facts['unit_count']:,}".replace(',', '.')
        answer = (f"Shop đang bán **{facts['active_product_count']} mặt hàng**, "
                  f"với **{units} sản phẩm** còn trong kho.")
        if not concise:
            low, empty = facts['low_stock_count'], facts['out_of_stock_count']
            issues = ([f'**{low} mã** sắp hết'] if low else []) + ([f'**{empty} mã** đã hết hàng'] if empty else [])
            if issues:
                answer += ' Có ' + ' và '.join(issues) + '.'
        return answer
    if tool == 'get_inventory':
        if facts.get('found') is False:
            return f"Mình chưa tìm thấy mã **{facts['sku']}** trong shop. Bạn kiểm tra lại SKU hoặc gửi tên sản phẩm nhé."
        if 'stock' not in facts or 'product_name' not in facts:
            return None
        stock = facts['stock']
        variant = f" — {facts['variant_title']}" if facts.get('variant_title') else ''
        answer = (f"**{facts['product_name']}**{variant} hiện còn **{stock} sản phẩm**, "
                  f"giá bán **{money(facts['price_vnd'])}**.\n\nSKU: {facts['sku']}")
        if not facts.get('is_active'):
            answer += '\nMẫu này đang ngừng bán.'
        elif stock == 0:
            answer += '\nMẫu này đã hết hàng.'
        elif stock <= 5 and not concise:
            answer += '\nLượng tồn đang thấp; bạn có thể kiểm tra kế hoạch nhập thêm.'
        return answer
    if tool == 'get_low_stock':
        items, threshold = facts['items'], facts['threshold']
        if not items:
            return ('Hiện shop chưa có mã nào hết hàng.' if threshold == 0 else
                    f'Hiện shop chưa có mã nào còn **{threshold} sản phẩm** trở xuống.')
        qualifier = 'Ít nhất ' if len(items) == 50 else ''
        condition = 'đã hết hàng' if threshold == 0 else f'còn **{threshold} sản phẩm** trở xuống'
        answer = f"{qualifier}**{len(items)} mã** {condition}."
        visible = items[:3 if concise else 5]
        for item in visible:
            name = item['product_name'] + (f" · {item['variant_title']}" if item.get('variant_title') else '')
            remaining = f" · còn **{item['stock']} sản phẩm**" if item['stock'] else ' · hết hàng'
            answer += f"\n\n• **{name}**{remaining}\n  SKU: {item['sku']}"
        if len(items) > len(visible):
            answer += f"\n\nCòn **{len(items)-len(visible)} SKU** khác trong danh sách."
        return answer
    if tool == 'search_products':
        if not facts['items']:
            if facts.get('min_price_vnd') is not None or facts.get('max_price_vnd') is not None:
                return ('Mình chưa tìm thấy sản phẩm khớp tên và khoảng giá bạn yêu cầu trong shop. '
                        'Điều này không có nghĩa shop không có loại sản phẩm đó; bạn có thể thử khoảng giá khác.')
            return 'Mình chưa tìm thấy sản phẩm phù hợp trong shop. Bạn thử tên ngắn hơn hoặc gửi mã SKU nhé.'
        answer = f"Mình tìm thấy **{facts['total']} sản phẩm** phù hợp trong shop."
        for item in facts['items'][:3 if concise else 5]:
            answer += f"\n\n• **{item['name']}** — **{money(item['price_vnd'])}**, còn **{item['stock']} sản phẩm**.\n  SKU: {item['sku']}"
        return answer
    return None
