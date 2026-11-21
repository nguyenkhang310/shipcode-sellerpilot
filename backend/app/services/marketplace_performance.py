"""Analyze the same-scope counts a seller copies from marketplace analytics."""
import re

from app.ai.money import plain
from app.ai.quick_reads import normalize_reporting_day_words

_COUNT = r'(?:[0-9]{1,3}(?:[., ][0-9]{3})+|[0-9]{1,12})'
_BUYER = r'(?:khach(?: hang)?|nguoi)'
_FIELDS = {
    'visitors': _BUYER + r' (?:truy cap|ghe shop)',
    'placed': _BUYER + r' (?:da )?dat(?: don| hang)?',
    'paid': _BUYER + r' (?:da )?(?:thanh toan|tra tien)(?: thanh cong)?',
    'paid_value': r'(?:doanh thu|gia tri don) da thanh toan',
}
_INPUTS = 'khách truy cập, khách đặt đơn, khách thanh toán'
REQUEST_COUNTS = f'Lấy {_INPUTS} trong Phân tích bán hàng. Gửi số của cùng sản phẩm (hoặc toàn shop) và hai kỳ bằng nhau.'
STEPS = (
    ('visit_to_place', 'Truy cập → đặt đơn', 'placed', 'visitors'),
    ('place_to_pay', 'Đặt đơn → thanh toán', 'paid', 'placed'),
    ('visit_to_pay', 'Truy cập → thanh toán', 'paid', 'visitors'),
)
EXPERIMENTS = {
    'traffic': ('Đổi ảnh bìa hoặc cụm từ đầu tiêu đề cho đúng nhu cầu tìm kiếm, mỗi lần một thay đổi.', 'khách truy cập'),
    'visit_to_place': ('Mở trang hàng trên điện thoại. Làm rõ một điểm khách cần để mua, như ảnh biến thể hoặc hướng dẫn chọn kích cỡ.', 'tỷ lệ truy cập → đặt đơn'),
    'place_to_pay': ('Thử đặt đến màn thanh toán của đúng biến thể. Kiểm tra tồn, phí giao và điều kiện dùng mã; sửa một trở ngại xác nhận được.', 'tỷ lệ đặt đơn → thanh toán'),
    'basket': ('Thử một combo gồm các món bổ trợ có sẵn hàng. Kiểm tra biên lời sau phí trước khi thử.', 'giá trị đã thanh toán mỗi khách'),
}


def _count_fields(text):
    counts = {}
    for key, label in _FIELDS.items():
        number = rf'(?<![\d.,+\-~])({_COUNT})(?![\d]|[.,][0-9])'
        if key == 'paid_value':
            number += r'\s*(?:vnd|dong|d|₫)(?![a-z])'
        suffix = r'(?!\s*(?:den\b|[-–]\s*\d|[kKmM]\b|nghin\b|trieu\b|%))'
        matches = {
            int(re.sub(r'[., ]', '', matched[1]))
            for pattern in (rf'{number}{suffix}\s+{label}\b', rf'\b{label}\s*(?:[:=]| la )\s*{number}{suffix}')
            for matched in re.finditer(pattern, text)
            if not re.search(r'\b(?:khoang|tam|duoi|hon|gan|tren|toi da|toi thieu)\s*$', text[:matched.start(1)])
        }
        if len(matches) > 1:
            return None
        if matches:
            counts[key] = next(iter(matches))
    return counts


def _ratio(numerator, denominator, factor=100):
    return None if numerator is None or not denominator else numerator / denominator * factor


def _metrics(counts):
    return {
        **{key: _ratio(counts.get(numerator), counts.get(denominator)) for key, _, numerator, denominator in STEPS},
        'traffic': counts.get('visitors'),
        'basket': _ratio(counts.get('paid_value'), counts.get('paid'), factor=1),
    }


def marketplace_funnel(message):
    text = normalize_reporting_day_words(plain(message).lower())
    sections = re.split(r'\b(?:ky truoc|ky goc)\b', text, maxsplit=1)
    counts = _count_fields(sections[0])
    previous = _count_fields(sections[1]) if len(sections) == 2 else {}
    if not counts and not previous and counts is not None and previous is not None:
        return None
    for period in (counts, previous):
        if period is None or any(period[b] > period[a] for a, b in (
            ('visitors', 'placed'), ('placed', 'paid'), ('visitors', 'paid'),
        ) if a in period and b in period) or (period.get('paid') == 0 and period.get('paid_value', 0) > 0):
            return {'status': 'invalid', 'source': 'seller_input'}
    # A comparison for explicitly different shops/SKUs would mislead.
    subjects = [set(re.findall(r'\bsku\s*[:#]?\s*([a-z0-9][a-z0-9._-]*)', section)) for section in sections]
    if len(sections) == 2:
        platforms = [set(re.findall(r'\b(?:shopee|tiktok)\b', section)) for section in sections]
        entire_shop = [bool(re.search(r'\btoan (?:shop|gian hang)\b', section)) for section in sections]
        if (all(platforms) and platforms[0] != platforms[1]) or (all(subjects) and subjects[0] != subjects[1]) or any(
                subjects[i] and entire_shop[1 - i] for i in range(2)):
            return {'status': 'scope_mismatch', 'source': 'seller_input'}
        current_days = re.search(r'\b(\d{1,2}) ngay(?: qua| gan day| vua roi)\b', sections[0])
        prior_days = re.search(r'\b(\d{1,2}) ngay\b', sections[1])
        if current_days and prior_days and int(current_days[1]) != int(prior_days[1]):
            return {'status': 'period_mismatch', 'source': 'seller_input'}
    current, prior = _metrics(counts), _metrics(previous)
    losses = {}
    for key, denominator in (('traffic', 'visitors'), ('visit_to_place', 'visitors'), ('place_to_pay', 'placed'), ('basket', 'paid')):
        now, before = current[key], prior[key]
        # When samples are sparse, report observed ratios without ranking the drop.
        if now is not None and before and now < before and min(counts.get(denominator, 0), previous.get(denominator, 0)) >= 30:
            losses[key] = (before - now) / before
    priority = max(losses, key=losses.get) if losses else None
    return {'status': 'read', 'source': 'seller_input', 'counts': counts, 'previous': previous,
            'metrics': current, 'baseline': prior, 'priority': priority}


def marketplace_for_plan(plan, message, history):
    if not plan or plan['mode'] not in ('business_plan', 'performance_analysis'):
        return None
    current = marketplace_funnel(message)
    if current is not None or not plan['followup']:
        return current
    previous = next((row.get('content', '') for row in reversed(list(history)[-6:]) if row.get('role') == 'user'), '')
    return marketplace_funnel(previous)


def render_marketplace_funnel(funnel, *, horizon=None):
    if funnel['status'] != 'read':
        reason = {
            'scope_mismatch': 'Hai kỳ đang khác phạm vi sàn, SKU hoặc gian hàng.',
            'period_mismatch': 'Hai kỳ đang có số ngày khác nhau.',
        }.get(funnel['status'], 'Các số đang trùng nhãn hoặc chưa khớp thứ tự truy cập, đặt đơn và thanh toán.')
        return reason + ' ' + REQUEST_COUNTS
    def percent(value):
        return f'{value:.2f}'.rstrip('0').rstrip('.').replace('.', ',') + '%'

    def number(value):
        return f'{round(value):,}'.replace(',', '.')

    metrics, baseline = funnel['metrics'], funnel['baseline']
    lines = []
    if metrics['traffic'] is not None:
        comparison = f' · kỳ trước {number(baseline["traffic"])}' if baseline['traffic'] is not None else ''
        lines.append(f'• **Khách truy cập** — {number(metrics["traffic"])}{comparison}')
    for key, label, numerator, denominator in STEPS:
        value = metrics[key]
        if value is None:
            continue
        current = f'{percent(value)} ({number(funnel["counts"][numerator])}/{number(funnel["counts"][denominator])} khách)'
        comparison = f' · kỳ trước {percent(baseline[key])}' if baseline[key] is not None else ''
        lines.append(f'• **{label}** — {current}{comparison}')
    if metrics['basket'] is not None:
        amount = number(metrics['basket']) + ' ₫/khách'
        comparison = f' · kỳ trước {number(baseline["basket"])} ₫/khách' if baseline['basket'] is not None else ''
        lines.append(f'• **Giá trị đã thanh toán mỗi khách** — {amount}{comparison}')
    priority = funnel['priority']
    if priority:
        action, kpi = EXPERIMENTS[priority]
        decision = ('So hai kỳ cùng độ dài và phạm vi. Giữ thử nghiệm nếu chỉ số cải thiện '
                    'và tỷ lệ hủy/hoàn vẫn ổn.')
        if horizon and horizon > 1:
            step = (f'**Kế hoạch {horizon} ngày**\n'
                    f'• Ngày 1 — Ghi mốc {kpi}. {action}\n'
                    f'• Ngày {"2" if horizon == 2 else f"2–{horizon}"} — Theo dõi cùng chỉ số. '
                    f'Đọc kết quả khi đủ cùng cửa sổ đo. {decision}')
        else:
            step = f'**Việc thử trước** — Ghi mốc {kpi}. {action} {decision}'
    else:
        has_pairs = all(metric in funnel[period] for period in ('counts', 'previous') for metric in ('visitors', 'placed', 'paid'))
        step = ('Chưa đủ căn cứ để chọn khâu cần sửa. ' + REQUEST_COUNTS if not has_pairs
                else 'Theo dõi thêm cùng phạm vi trước khi đổi. Giữ một thay đổi mỗi vòng để đọc được tác động.')
    headline = '**Phễu bán hàng từ số bạn cung cấp**'
    return '\n\n'.join(filter(None, (headline, '\n'.join(lines), step)))
