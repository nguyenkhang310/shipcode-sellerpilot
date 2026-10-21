"""Natural-language generation from verified tool facts, without another LLM call.

Read routing uses Vietnamese normalization and complete query clauses; this
renderer handles period, quantities, zero results and confirmed length preference.
No model prediction, random wording or invented business information is involved.
"""
from datetime import date, timedelta
import re

from app.ai.money import plain


def money(value):
    return f'{int(value):,}'.replace(',', '.') + 'đ'


def read_reply(result, *, today: date, preferences: dict):
    facts, tool = result['facts'], result['tool']
    style = plain(preferences.get('response_style', ''))
    rejects_brief = bool(re.search(r'\b(?:khong|dung)(?: tra loi)? ngan gon\b', style))
    concise = not rejects_brief and any(word in style for word in
        ('ngan gon', 'suc tich', 'that ngan', 'khong dai dong', 'khong can dai dong'))
    if tool == 'get_shop_summary':
        if facts.get('calendar_period'):
            label = 'Tuần này' if facts['calendar_period'] == 'week' else 'Tháng này'
            period = label + ' (' + date.fromisoformat(facts['from_date']).strftime('%d/%m') + '–' + date.fromisoformat(facts['to_date']).strftime('%d/%m') + ')'
        elif facts.get('days', 1) > 1:
            period = f"Trong {facts['days']} ngày qua"
        else:
            day = date.fromisoformat(str(facts['date']))
            period = 'Hôm nay' if day == today else 'Hôm qua' if day == today - timedelta(days=1) else 'Ngày ' + day.strftime('%d/%m/%Y')
        count, value = facts['order_count'], facts['order_value_vnd']
        answer = (f'{period} shop có **{count} đơn** hợp lệ, tổng giá trị **{money(value)}**.' if count else
                  f'{period} shop chưa có đơn hợp lệ mới. Tổng giá trị đơn hiện là **{money(value)}**.')
        if pending := facts.get('pending_count'):
            answer += f" Còn **{pending} đơn** chờ xác nhận."
        if not concise:
            if facts.get('days', 1) > 1:
                answer += f"\n\nGiá trị trung bình là **{money(facts['average_order_vnd'])}/đơn**; đơn đã giao có tổng giá trị **{money(facts['delivered_value_vnd'])}**."
            answer += '\n\nĐây là giá trị đơn hợp lệ, chưa phải toàn bộ tiền đã thu.'
        return answer
    if tool == 'get_inventory_overview':
        answer = (f"Kho hiện có **{facts['unit_count']:,} sản phẩm** trên **{facts['sku_count']} SKU**. "
                  f"Có **{facts['active_product_count']} sản phẩm** đang bán.").replace(',', '.')
        if not concise:
            answer += (f"\n\n• **{facts['low_stock_count']} SKU** sắp hết, còn 1–5 sản phẩm."
                       f"\n• **{facts['out_of_stock_count']} SKU** đã hết hàng."
                       f"\n• Giá trị hàng theo giá bán hiện tại: **{money(facts['retail_value_vnd'])}**.")
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
            return f'Hiện không có SKU nào còn từ **{threshold} sản phẩm** trở xuống.'
        qualifier = 'Ít nhất ' if len(items) == 50 else ''
        answer = f"{qualifier}**{len(items)} SKU** còn từ **{threshold} sản phẩm** trở xuống:"
        visible = items[:3 if concise else 5]
        for item in visible:
            answer += f"\n\n• **{item['product_name']}** — còn **{item['stock']} sản phẩm**.\n  SKU: {item['sku']}"
        if len(items) > len(visible):
            answer += f"\n\nCòn **{len(items)-len(visible)} SKU** khác trong danh sách."
        return answer
    if tool == 'search_products':
        if not facts['items']:
            if facts.get('min_price_vnd') is not None or facts.get('max_price_vnd') is not None:
                return ('Mình chưa tìm thấy sản phẩm khớp tên và khoảng giá bạn yêu cầu trong shop. '
                        'Điều này không có nghĩa shop không có loại sản phẩm đó; bạn có thể thử khoảng giá khác.')
            return 'Mình chưa tìm thấy sản phẩm phù hợp trong shop. Bạn thử tên ngắn hơn hoặc gửi mã SKU nhé.'
        answer = f"Mình tìm thấy **{facts['total']} sản phẩm** phù hợp trong shop:"
        for item in facts['items'][:3 if concise else 5]:
            answer += f"\n\n• **{item['name']}** — **{money(item['price_vnd'])}**, còn **{item['stock']} sản phẩm**.\n  SKU: {item['sku']}"
        return answer
    return None
