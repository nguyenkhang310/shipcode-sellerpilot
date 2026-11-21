"""Present saved, tenant-scoped tool facts without queries or another AI call.

The same projection is used for live chat and history. Reopening a conversation
must not recalculate yesterday's report using today's catalog or orders.
"""
import logging

from pydantic import ValidationError

from app.schemas.chat_report import ChatReport

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    'pending': 'Chờ xác nhận', 'paid': 'Chờ lấy hàng', 'shipped': 'Đang giao',
    'delivered': 'Đã giao', 'cancelled': 'Đã hủy', 'returned': 'Đã hoàn',
}


def _metric(label, value, unit='count', change_percent=None):
    return dict(label=label, value=value, unit=unit, change_percent=change_percent)


def _period(facts):
    start, end = facts.get('from_date'), facts.get('to_date', facts.get('date'))
    if not start or start == end:
        return f"Ngày {end}" if end else 'Số liệu được lưu cùng câu trả lời'
    return f'{start} → {end}'


def _sales(facts):
    metrics = [
        _metric('Giá trị đơn hàng', facts.get('order_value_vnd'), 'vnd', facts.get('change_percent')),
        _metric('Đơn hợp lệ', facts.get('order_count')),
        _metric('Giá trị đã giao', facts.get('delivered_value_vnd'), 'vnd'),
        _metric('Trung bình / đơn', facts.get('average_order_vnd'), 'vnd'),
    ]
    charts = []
    series = facts.get('series', [])
    if series:
        charts.append(dict(kind='line', title='Diễn biến giá trị đơn hàng', unit='vnd',
                           points=[dict(label=p['date'], value=p['value']) for p in series]))
    statuses = facts.get('order_status_counts', facts.get('status_counts', {}))
    if statuses:
        charts.append(dict(kind='bar', title='Trạng thái đơn trong kỳ', unit='count',
                           points=[dict(label=label, value=statuses.get(key, 0))
                                   for key, label in STATUS_LABELS.items()]))
    notes = ['Giá trị đơn hàng loại đơn hủy/hoàn; không đồng nghĩa tiền đã thu hoặc lợi nhuận.']
    if facts.get('includes_partial_today'):
        notes.append('Hôm nay mới tính tới thời điểm cập nhật; so sánh với cùng thời lượng kỳ trước.')
    if facts.get('change_percent') is None:
        notes.append('Chưa có cơ sở kỳ trước để tính tỷ lệ tăng/giảm.')
    return dict(title='Hiệu quả kinh doanh', subtitle=_period(facts),
                as_of=facts.get('updated_at'), timezone=facts.get('timezone'),
                metrics=metrics, charts=charts, notes=notes,
                table=dict(title='Chi tiết giá trị đơn hàng',
                    columns=[dict(label='Thời điểm', unit='text'), dict(label='Giá trị đơn', unit='vnd')],
                    rows=[[p['date'], p['value']] for p in series]) if series else None)


def build_chat_report(tool: str | None, facts: dict) -> dict | None:
    # Old saved facts may predate this contract. An optional visualization must
    # not make an otherwise readable answer/history fail with HTTP 500.
    try:
        return _build_report(tool, facts)
    except (ValidationError, KeyError, TypeError, ValueError):
        logger.warning('Skipped incompatible chat report: tool=%s', tool)
        return None


def _build_report(tool, facts):
    """Closed set of supported tool results; no chart specs from user/model text."""
    if facts.get('business_advisory', {}).get('marketplace_funnel'):
        return None
    if 'all_order_status_counts' in facts:
        return None
    report = None
    if tool == 'get_shop_summary' and 'order_count' in facts:
        report = _sales(facts)
    elif tool == 'get_inventory_overview':
        low, out, total = (facts[key] for key in ('low_stock_count', 'out_of_stock_count', 'sku_count'))
        report = dict(title='Tổng quan tồn kho', subtitle='Tồn khả dụng theo SKU đang bán',
            metrics=[_metric('SKU đang bán', total), _metric('Số lượng trong kho', facts['unit_count']),
                     _metric('Sắp hết hàng', low), _metric('Đã hết hàng', out)],
            charts=[dict(kind='bar', title='Phân bố tồn kho', unit='count', points=[
                dict(label=f"Trên {facts['low_stock_threshold']}", value=max(0, total - low - out)),
                dict(label=f"Còn 1–{facts['low_stock_threshold']}", value=low),
                dict(label='Hết hàng', value=out)])],
            notes=['Tính theo SKU/biến thể hoạt động, không cộng trùng tồn sản phẩm cha.'])
    elif tool == 'get_low_stock':
        items = facts['items'][:50]
        report = dict(title='Hàng cần bổ sung', subtitle=f"Tồn kho không quá {facts['threshold']}",
            metrics=[_metric('SKU trong danh sách', len(items))],
            charts=[dict(kind='bar', title='Tồn kho theo SKU', unit='count',
                         points=[dict(label=item['sku'], value=item['stock']) for item in items[:8]])] if items else [],
            table=dict(title='Chi tiết tồn kho',
                columns=[dict(label='Sản phẩm / SKU', unit='text'), dict(label='Còn', unit='count'),
                         dict(label='Giá bán', unit='vnd')],
                rows=[[item['product_name'] + (f" · {item['variant_title']}" if item.get('variant_title') else '')
                       + '\n' + item['sku'], item['stock'], item['price_vnd']] for item in items]),
            notes=['Danh sách giới hạn 50 SKU; biểu đồ hiển thị tối đa 8 SKU đầu.'] if len(items) >= 50
                  else ['Biểu đồ hiển thị tối đa 8 SKU đầu.'] if len(items) > 8 else [])
    elif tool == 'get_shop_insights' and facts.get('business_advisory', {}).get('mode') in ('video_script', 'measurement_plan'):
        return None
    elif tool == 'get_shop_insights' and facts.get('business_analysis'):
        snapshot = facts['business_analysis']
        current = snapshot['current']
        report = _sales({**current, **snapshot['period'], 'updated_at': snapshot['as_of'],
            'timezone': snapshot['timezone'], 'change_percent': snapshot['comparison']['order_value_change_percent'],
            'series': [dict(date=p['date'], value=p['order_value_vnd']) for p in snapshot['daily_sales']]})
        products = snapshot['period_top_products']
        if products and snapshot['attribution']['available']:
            report['charts'].append(dict(kind='bar', title='Sản lượng bán trong kỳ', unit='count',
                points=[dict(label=p['sku'] or p['name'], value=p['units_sold']) for p in products]))
            report['table'] = dict(title='Sản phẩm bán tốt trong kỳ',
                columns=[dict(label='Sản phẩm / SKU', unit='text'), dict(label='Đã bán', unit='count'),
                         dict(label='Giá trị hàng', unit='vnd')],
                rows=[[p['name'] + ('\n' + p['sku'] if p['sku'] else ''), p['units_sold'], p['item_sales_value_vnd']] for p in products])
            report['notes'].append('Giá trị hàng tính theo giá lúc mua, chưa phân bổ phí vận chuyển/giảm giá cấp đơn.')
        else:
            report['notes'].append('Chưa có dòng hàng đủ dữ kiện để xếp hạng sản phẩm trong kỳ.')
        if snapshot['attribution']['unmatched_current_item_lines']:
            report['notes'].append('Một số dòng hàng chưa khớp danh mục; bảng sản phẩm chưa bao phủ toàn bộ đơn.')
    elif tool == 'get_shop_insights' and facts.get('period'):
        report = _sales(facts['period'])
    return ChatReport.model_validate(report).model_dump(mode='json') if report else None
