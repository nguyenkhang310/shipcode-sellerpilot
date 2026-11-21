"""Evidence-led planning briefs for natural replies, with a useful offline plan."""
import re

from app.ai.fallback import extract_sku
from app.ai.money import plain
from app.ai.quick_reads import normalize_reporting_day_words
from app.integrations import management
from app.integrations.business import business_snapshot
from app.integrations.ute_mall import ShopItemNotFoundError
from app.services.conversations import ASK_PRODUCT, has_product_reference
from app.services.marketplace_performance import REQUEST_COUNTS, marketplace_for_plan, render_marketplace_funnel


def planning_request(message, history=()):
    text = normalize_reporting_day_words(plain(message).lower())
    ads = re.search(r'\b(?:tu van quang cao|chien luoc quang cao|ke hoach quang cao|chien dich quang cao|'
                    r'chay (?:ads|quang cao)|ngan sach (?:ads|quang cao)|do (?:hieu qua|roas) quang cao)\b', text)
    mode = ('ad_plan' if ads and not re.search(r'\b(?:gia von|lai bao nhieu|tinh loi)\b', text) else
            'video_script' if re.search(r'kich ban|quay (?:mot |1 )?(?:clip|video)|loi thoai.{0,25}video', text) else
            'business_plan' if re.search(r'ke hoach|len plan|lap plan|lo trinh|chien luoc', text) else
            'performance_analysis' if re.search(
                r'(?:phan tich|toi uu) (?:hieu suat|chuyen doi)|pheu ban hang|ty le (?:khach dat|thanh toan|chuyen doi)', text) else
            'measurement_plan' if re.search(r'cach do|do hieu qua|cach theo doi|don tu tiktok|hieu qua tung video', text) and not re.search(r'kich ban|quay video|lam video', text) else
            'video_script' if re.search(r'tiktok|tik tok|kich ban|quay video|lam video|video ngan|reels|cau mo dau|hook|hieu qua tung video', text) else
            'performance_analysis' if re.search(
                r'phan tich (?:so lieu|shop|kinh doanh|hieu suat|doanh)|tang doanh (?:thu|so)|tang don|ra don|'
                r'ban cham|ban chay|ban tot hon|xep hang san pham|lam sao (?:de )?ban|'
                r'nen (?:bat dau )?ban.{0,40}(?:the nao|ra sao)|'
                r'(?:how to|how (?:can|should) i) sell|increase sales',
                text) else None)
    if mode is None and has_product_reference(message) and re.search(r'\b(?:ban|tiep thi|quang ba)\b', text):
        if re.search(r'lam sao|sao cho|ra sao|the nao', text):
            mode = 'performance_analysis'
    contextual = re.fullmatch(r'(?:vay |roi |hay )?(?:cu the hon|chi tiet hon|di sau hon|lam ro hon|buoc tiep theo)(?: di| nhe| giup minh)?[.!? ]*', text.strip())
    contextual = contextual or (len(text) < 220 and re.search(r'chi quay|lam mot minh|mot nguoi|1 nguoi|khong co thoi gian|do hieu qua|giu chan|it nhap', text))
    if mode is None and contextual:
        for row in reversed(list(history)[-6:]):
            if row.get('role') == 'user':
                previous = planning_request(row.get('content', ''))
                if previous:
                    return {**previous, 'followup': True}
                break
    if mode is None:
        return None
    horizons = list(re.finditer(r'\b(\d{1,2})\s+ngay\b', text))
    # A reporting period such as "7 ngày qua" is not the future plan horizon.
    future = [match for match in horizons if not re.match(r'\s*(?:qua|gan day|vua roi)', text[match.end():])]
    days = int(future[-1][1]) if future else 7
    if 'thang toi' in text:
        days = 30
    detail = mode == 'video_script' and bool(re.search(
        r'\b(?:phan tich tung canh|kich ban(?: tiktok)? (?:day du|chi tiet)|viet chi tiet tung canh)\b', text))
    return {'mode': mode, 'horizon_days': min(90, max(1, days)), 'followup': False,
            **({'detailed_video': detail} if mode == 'video_script' else {})}


def attach_business_brief(shop, facts, *, message, history=(), preferences=None):
    request = planning_request(message, history)
    if request is None:
        return None
    funnel = marketplace_for_plan(request, message, history)
    if funnel is not None:
        brief = {**request, 'status': 'proposal_only', 'marketplace_funnel': funnel}
        facts['business_advisory'] = brief
        return brief
    selected = facts.get('selected_product')
    text = plain(message).lower()
    draft = facts.get('draft_context')
    draft_reference = bool(draft and (has_product_reference(message) or 'ban nhap' in text))
    explicit_code = re.search(r'\b(?:sku|ma hang|ma san pham)\s+[a-z0-9._-]+', text)
    if (selected is None or selected.get('found') is False) and not draft_reference and not facts.get('product_reference_missing') and not explicit_code:
        subject_pattern = (r'\bcho (?:san pham (?!nay\b|do\b)|(?=(?:ban phim|chuot|tai nghe|ao|quan|tui|balo|gia do|cap|den)\b))'
                           r'([^,.!?\n]{3,120})')
        named = re.search(subject_pattern, text)
        if not named and request['followup']:
            previous = next((row.get('content', '') for row in reversed(list(history)[-6:]) if row.get('role') == 'user'), '')
            named = re.search(subject_pattern, plain(previous).lower())
        if named:
            query = re.split(r'\s+(?:tren|de|voi|kieu|va viet|trong)\s+', named[1], maxsplit=1)[0].strip()
            if query:
                matches = management.products(shop, query, limit=2)
                if matches['total'] == 1 and matches['items'][0]['sku']:
                    try:
                        selected = facts['selected_product'] = shop.get_item_by_sku(matches['items'][0]['sku'])
                    except ShopItemNotFoundError:
                        facts['planning_product_query'] = query
                else:
                    facts['planning_product_query'] = query
    if selected is None and (request['followup'] or re.search(r'viet them|cach do|do hieu qua|cau mo dau|hook|\bcta\b', plain(message).lower())):
        for row in reversed(list(history)[-6:]):
            if row.get('role') != 'user':
                continue
            sku = extract_sku(row.get('content', '').lower())
            if sku:
                try:
                    selected = shop.get_item_by_sku(sku)
                except ShopItemNotFoundError:
                    selected = {'sku': sku, 'found': False}
                break
    snapshot = facts.get('business_analysis')
    if snapshot is None:
        snapshot = business_snapshot(shop, facts.get('period', {}).get('days', 7),
                                     focus_product_id=(selected or {}).get('product_id'))
        facts['business_analysis'] = snapshot
    if draft_reference and not extract_sku(message.lower()):
        focus = {'product_id': None, 'sku': None, 'name': draft.get('name'),
                 'price_vnd': draft.get('selling_price_vnd'), 'available_stock': draft.get('stock'),
                 'status': 'draft'}
        reason = 'Bản nháp đang soạn mà chủ shop nhắc tới; chưa được đăng, không phải sản phẩm đang bán.'
    elif selected and selected.get('found') is not False:
        focus = {'product_id': selected['product_id'], 'sku': selected['sku'],
                 'name': selected.get('product_name', selected.get('name')),
                 'price_vnd': selected['price_vnd'], 'available_stock': selected['stock'],
                 'status': 'active' if selected.get('is_active', True) else 'inactive',
                 **{key: selected[key] for key in ('variant_title', 'color', 'size') if selected.get(key)}}
        reason = 'Sản phẩm chủ shop đang hỏi; không tự chuyển sang mẫu khác.'
    else:
        explicit_sku = extract_sku(message.lower())
        if explicit_sku or facts.get('product_reference_missing') or facts.get('planning_product_query') or (selected and selected.get('found') is False):
            focus = None
            reason = 'Cần xác minh SKU được yêu cầu; không thay bằng sản phẩm khác.'
        else:
            focus = next(iter(snapshot['promotion_candidates']), None)
            reason = ('Đề xuất thử từ hàng đang bán, kho trên 5; ưu tiên số lượng bán trong kỳ rồi tồn khả dụng. '
                      'Chưa biết biên lời/traffic nên chưa kết luận đây là sản phẩm sinh lời nhất.')
    cur = snapshot['current']
    diagnosis = [
        {'finding': 'period_sales', 'evidence': {'order_count': cur['order_count'], 'order_value_vnd': cur['order_value_vnd'],
                                               'average_order_vnd': cur['average_order_vnd']},
         'meaning': 'Giá trị đơn hợp lệ trong kỳ, không phải tiền thực thu hay lợi nhuận.'},
        {'finding': 'comparison', 'evidence': snapshot['comparison'],
         'meaning': 'So cùng thời lượng; kỳ trước bằng 0 thì phần trăm tăng trưởng là chưa xác định.'},
    ]
    if cur['cancelled_count'] or cur['returned_count']:
        diagnosis.append({'finding': 'order_loss', 'evidence': {key: cur[key] for key in
            ('all_order_count', 'cancelled_count', 'cancelled_rate_percent', 'returned_count', 'returned_rate_percent')},
            'meaning': 'Kiểm tra lý do hủy/hoàn; chưa có bằng chứng quy nguyên nhân cho giá hoặc video.'})
    if snapshot.get('stock_risks'):
        diagnosis.append({'finding':'stock_risk', 'evidence':snapshot['stock_risks'],
                          'meaning':'Ước tính từ lượng bán trong kỳ và tồn hiện tại, không phải dự báo chắc chắn; kiểm tra nhập hàng trước khi kéo đơn.'})
    tasks = facts.get('tasks', {})
    if tasks.get('pending_orders') or tasks.get('packing_orders'):
        diagnosis.append({'finding': 'fulfillment', 'evidence': {key: tasks.get(key, 0) for key in ('pending_orders', 'packing_orders')},
                          'meaning': 'Tồn việc toàn shop; xử lý năng lực giao hàng trước khi tăng kéo đơn.'})
    in_stock = bool(focus and focus.get('status') == 'active' and (focus.get('available_stock') or 0) > 0)
    items = [snapshot.get('requested_product'), *snapshot['period_top_products'], *snapshot['promotion_candidates']]
    focus_data = next((item for item in items if focus and item and focus.get('sku')
        and item.get('sku') == focus['sku'] and item.get('product_id') == focus.get('product_id')), None)
    focus_performance = {key: focus_data[key] for key in ('units_sold', 'previous_units_sold', 'order_count',
        'item_sales_value_vnd', 'order_share_percent', 'stock_cover_days_estimate') if key in focus_data
        } if focus_data and snapshot['attribution']['available'] else None
    if focus_performance:
        diagnosis.append({'finding': 'focus_product_in_period', 'evidence': focus_performance,
                          'meaning': 'Dòng hàng đã đối chiếu theo sản phẩm cha hoặc SKU độc lập, không suy ra doanh số của từng biến thể.'})
    brief = {
        **request, 'status': 'proposal_only', 'diagnosis': diagnosis,
        'focus_product': focus, 'focus_selection_reason': reason,
        'focus_performance': focus_performance,
        'seller_preferences': preferences or facts.get('seller_preferences', {}),
        'commercial_constraints': {'stock_available': in_stock,
            'margin_known': bool(facts.get('pricing_analysis', {}).get('status') == 'calculated') if facts.get('pricing_analysis') else False,
            'ad_budget_vnd': None, 'tiktok_shop_connected': False},
        'deliverables': [
            'Nhận xét số liệu đúng kỳ và lý do chọn ưu tiên.',
            'Việc làm theo ngày/giai đoạn, đầu ra phải hoàn thành, chỉ số xem lại và cách quyết định.',
            'Kịch bản quay theo sản phẩm: câu mở đầu A/B, cảnh quay theo giây, lời thoại, chữ trên màn hình, CTA và caption.',
            'Cách ghi nhận xem → nhấp → đơn, thử một biến mỗi lần; không suy ra đơn TikTok từ tổng đơn Shopee.',
        ],
        'video_production': {
            'format': 'Đề xuất clip dọc 9:16, 20–30 giây; điện thoại, ánh sáng rõ, phụ đề trong vùng không bị nút che.',
            'structure': ['0–3s: cho thấy sản phẩm và vấn đề của người xem; viết 2 câu mở đầu khác nhau.',
                          '3–12s: quay cận món hàng/thao tác thực tế; chỉ nói thông số đã xác minh.',
                          '12–23s: demo tình huống dùng; chưa có kết quả thử thì hướng dẫn quay phép thử, không viết sẵn kết luận.',
                          '23–30s: một lời kêu gọi xem sản phẩm trên Shopee; chỉ nói giỏ TikTok nếu chủ shop xác nhận đã liên kết.'],
            'testing': 'Giữ sản phẩm, thân clip và CTA; chỉ đổi hook A/B. So cùng cửa sổ đo, không chọn video thắng chỉ theo lượt xem hoặc vài đơn.',
            'truthfulness': 'Không tự thêm nhận xét khách, chứng nhận, hiệu năng, chính hãng, bảo hành, giảm giá hay khan hiếm.',
        },
        'measurement': {
            'connected': ['Đơn hợp lệ, giá trị đơn, hủy/hoàn và số lượng bán theo sản phẩm của shop nội bộ.'],
            'manual_fields': ['video_id', 'published_at', 'measurement_window', 'views', 'product_clicks', 'attributed_orders', 'ad_spend_vnd'],
            'definitions': ['Tỷ lệ nhấp = nhấp sản phẩm/lượt xem, khi có đủ hai số cùng kỳ.',
                            'Tỷ lệ chốt sau nhấp = đơn được gán nguồn/nhấp sản phẩm; chưa có nguồn thì không tính.',
                            'Chi phí/đơn = chi quảng cáo/đơn gán nguồn; ROAS = giá trị đơn gán nguồn/chi quảng cáo, không phải lợi nhuận.'],
            'decision': 'Giữ chân kém: sửa mở đầu; xem tốt nhưng ít nhấp: thử demo/CTA; có nhấp ít đơn: kiểm tra trang sản phẩm, giá, giao hàng. Đây là giả thuyết cần đo.',
            'targets': 'Mục tiêu thử nghiệm đề xuất, không phải số thực tế hay cam kết ra đơn; chưa có baseline thì đo trước.',
        },
    }
    brief['shot_list'] = video_shots(focus, in_stock) if focus and focus.get('name') else None
    brief['execution'] = execution_plan(brief, facts)
    if brief['shot_list']:
        brief['video_production']['structure'] = brief['shot_list']['scenes']
    facts['business_advisory'] = brief
    return brief


def execution_plan(brief, facts):
    focus = brief['focus_product'] or {}
    item = focus.get('name') or 'một SKU còn hàng mà bạn chọn'
    stock = focus.get('available_stock')
    tasks = facts.get('tasks', {})
    pending, packing = tasks.get('pending_orders', 0), tasks.get('packing_orders', 0)
    snapshot = facts['business_analysis']
    current = snapshot['current']
    comparison = snapshot['comparison']
    average_delta = comparison.get('average_order_delta_vnd')
    orders_delta = comparison['order_count_delta']
    experiment = None
    if pending or packing:
        priority = f'Xem {pending} đơn chờ xác nhận và {packing} đơn chờ lấy hàng. Chốt số đơn còn cần xử lý trước khi tăng kéo đơn.'
    elif current['cancelled_count'] or current['returned_count']:
        priority = (f'Mở {current["cancelled_count"]} đơn hủy và {current["returned_count"]} đơn hoàn trong kỳ. '
                    'Ghi lý do từng đơn, rồi xử lý lý do lặp lại nhiều nhất nếu dữ liệu đủ.')
    elif not brief['commercial_constraints']['stock_available']:
        priority = f'Kiểm tra trạng thái đăng và tồn của {item}, rồi xác nhận mẫu đủ điều kiện bán trước khi kéo khách.'
    elif stock is not None and stock <= 5:
        priority = f'{item} còn {stock} chiếc. Chốt khả năng bổ sung tồn và kiểm tra biến thể đang bán trước khi đẩy lượt mua.'
    elif average_delta is not None and average_delta < 0 and orders_delta >= 0:
        priority = 'Số đơn giữ hoặc tăng nhưng giá trị trung bình mỗi đơn giảm. Xem một nhóm sản phẩm thường mua kèm.'
        experiment = (
            f'Chọn một món bổ trợ hợp với {item}; thử gợi ý mua kèm cho đúng biến thể. Tính giá vốn và phí trước khi áp dụng ưu đãi.',
            'So giá trị trung bình mỗi đơn, số đơn hợp lệ và tỷ lệ hủy/hoàn của hai kỳ cùng thời lượng.',
            'Giữ gợi ý mua kèm nếu giá trị mỗi đơn và biên lời tăng, trong khi số đơn không giảm rõ rệt. Thiếu giá vốn thì chưa kết luận có lời.',
        )
    elif orders_delta < 0:
        priority = f'Shop ít hơn {abs(orders_delta)} đơn hợp lệ so với kỳ trước. ' + REQUEST_COUNTS
        experiment = (
            f'Mở trang bán {item} trên điện thoại. Chọn một điểm dễ kiểm tra, như ảnh bìa sai biến thể hoặc bảng kích cỡ thiếu.',
            'So khách truy cập, khách đặt và khách thanh toán của hai kỳ. Dùng đúng một SKU hoặc toàn shop ở cả hai kỳ.',
            'Truy cập giảm thì thử ảnh bìa hoặc tiêu đề. Truy cập giữ mà tỷ lệ đặt giảm thì rà nội dung trang hàng. Chốt từ số từng khâu.',
        )
    else:
        priority = f'Mở trang bán {item} trên điện thoại. Đối chiếu ảnh, giá biến thể và tồn; chụp lại mốc ban đầu.'

    publish = ('Ghi giờ đăng từng bản.' if brief['commercial_constraints']['stock_available']
               else 'Lưu thành bản nháp tới khi mặt hàng sẵn sàng.')
    capture = f'Quay 2 bản cho {item} với cùng cảnh demo và lời kêu gọi hành động. Đổi duy nhất câu mở đầu. {publish}'
    if brief['shot_list']:
        capture += f' Mở 0–3s bằng cảnh thật và câu “{brief["shot_list"]["hooks"][0]}”'
    measure = ('Ghi lượt xem, nhấp và đơn có nguồn của mỗi bản trong cùng cửa sổ đo. '
               'Nếu chưa đo được nhấp hoặc nguồn đơn, thiết lập cách ghi nhận trước khi kết luận.')
    decision = ('Có lượt xem nhưng ít nhấp thì thử lại cảnh demo hoặc lời kêu gọi hành động. '
                'Có nhấp nhưng ít đơn thì đối chiếu giá biến thể, thông tin hàng và phí giao. Mỗi vòng sửa một điểm.')
    if experiment:
        capture, measure, decision = experiment
    days = brief['horizon_days']
    if days == 1:
        stages = [{'day': 'Ngày 1', 'action': f'{priority} {capture} Hẹn đọc số khi đủ cùng cửa sổ đo.'}]
    elif days <= 3:
        stages = [{'day': 'Ngày 1', 'action': priority},
                  {'day': f'Ngày {"2" if days == 2 else "2–3"}', 'action': f'{capture} {measure}'}]
    else:
        edit_day = max(2, days // 2)
        check_day = max(edit_day + 1, days * 3 // 4)
        stages = [{'day': 'Ngày 1', 'action': priority},
                  {'day': 'Ngày 2' if edit_day == 2 else f'Ngày 2–{edit_day}', 'action': capture},
                  {'day': f'Ngày {check_day}' if edit_day + 1 == check_day else f'Ngày {edit_day + 1}–{check_day}', 'action': measure},
                  {'day': f'Ngày {days}' if check_day + 1 == days else f'Ngày {check_day + 1}–{days}', 'action': decision}]
    return {'first_action': priority, 'stages': stages, 'decision': decision}


def video_shots(focus, can_sell):
    name = ' '.join(focus['name'].split())[:100]
    key = plain(name).lower()
    if re.match(r'ban phim\b', key):
        angle, detail, demo = 'nhìn phím trên bàn làm việc', 'quay từ trên xuống, lia dọc một hàng phím', 'gõ một câu ngắn, để mic cạnh bàn để lấy tiếng thật'
        line = 'Bạn nghe thử tiếng gõ của mẫu này nhé.'
    elif re.match(r'(ao|quan|vay|dam|hoodie)\b', key):
        angle, detail, demo = 'xem dáng và bề mặt khi cầm lên', 'đặt mẫu trên mặt phẳng, quay cận cổ, mép hoặc đường may nhìn thấy', 'đưa thước vào khung và quay số đo của đúng mẫu đang cầm'
        line = 'Đây là bề mặt và số đo của đúng mẫu này.'
    elif re.match(r'(tui|balo|ba lo|vi)\b', key):
        angle, detail, demo = 'xem bên trong trước khi chọn', 'đặt sản phẩm trên bàn, mở miệng túi và quay từ trên xuống', 'đặt một vật quen thuộc như sổ tay cạnh túi, thử xếp vào và quay kết quả thật'
        line = 'Mình thử đặt cuốn sổ này vào nhé.'
    elif re.match(r'(chuot|tai nghe|sac|gia do|op|cap|den)\b', key):
        angle, detail, demo = 'nhìn rõ mẫu và các chi tiết thực tế', 'quay cận hai mặt, xoay chậm dưới ánh sáng cạnh cửa sổ', 'đặt cạnh món đồ định dùng cùng và chỉ quay thao tác đã kiểm tra an toàn'
        line = 'Mình xoay hai mặt để bạn dễ đối chiếu.'
    else:
        angle, detail, demo = 'xem kích thước và hình dáng thực tế', 'đặt sản phẩm trên nền trơn, xoay từ trước sang bên cạnh', 'đặt thước hoặc vật quen thuộc cùng mặt phẳng để người xem ước lượng kích thước'
        line = 'Đây là kích thước thực tế khi đặt cạnh thước.'
    variant = focus.get('variant_title') or ' / '.join(str(focus[key]) for key in ('color', 'size') if focus.get(key))
    cta = ('Tìm đúng mẫu trên Shopee để xem giá và lựa chọn.' if can_sell
           else 'Lưu video để xem lại khi shop cập nhật mẫu.')
    return {
        'hooks': [f'Muốn {angle}? Xem ngay đoạn này.', 'Cân nhắc mẫu này? Đây là cảnh quay thật.'],
        'scenes': [
            {'time': '0–3s', 'visual': 'Đưa sản phẩm thật vào giữa khung ngay từ giây đầu.', 'speech': 'Dùng câu mở đầu A hoặc B.', 'overlay': name},
            {'time': '3–10s', 'visual': detail.capitalize() + '.', 'speech': line, 'overlay': variant or 'Cận cảnh mẫu thật'},
            {'time': '10–22s', 'visual': demo.capitalize() + '.', 'speech': 'Bạn xem kết quả ngay trên màn hình nhé.', 'overlay': 'Quay thử trực tiếp'},
            {'time': '22–28s', 'visual': 'Quay chính diện.', 'speech': cta,
             'overlay': 'Xem đúng mẫu trên Shopee' if can_sell else 'Lưu lại để xem sau'},
        ],
        'caption': f'Xem cận {name} trước khi chọn.',
    }


def business_reply_issue(answer, facts, *, message='', seller_context=''):
    brief = facts.get('business_advisory')
    if not brief:
        return None
    text = plain(answer.replace('*', '').replace('`', '')).lower()
    focus = brief.get('focus_product') or {}
    selected = facts.get('selected_product') or {}
    evidence = plain(' '.join(str(value or '') for value in
        (focus.get('name'), selected.get('product_name'), selected.get('description'), seller_context))).lower()
    zero_traffic = r'\b(?:khong|chua) co (?:luot (?:xem|truy cap|nhap)|khach truy cap)|\b0\s+(?:luot (?:xem|truy cap|nhap)|khach truy cap)\b'
    if facts.get('business_analysis') and re.search(zero_traffic, text) and not re.search(zero_traffic, evidence):
        return 'unobserved_traffic'
    for claim in (r'ban phim co', r'(?:phim|go)(?:\s+\w+){0,2}\s+em', r'em ai', r'layout gon', r'thiet ke gon', r'chong nuoc', r'sac nhanh', r'chong on',
                  r'ket noi bluetooth', r'pin \d+ gio', r'bao hanh \d+ thang', r'den rgb', r'den nen'):
        if re.search(claim, text) and not re.search(claim, evidence):
            return 'unsupported_product_feature'
    low_count = facts.get('tasks', {}).get('low_stock_products')
    for match in re.finditer(r'(\d+)\s+(?:san pham|mat hang|mau)(?:\s+\w+){0,3}\s+sap het', text):
        if low_count is not None and int(match[1]) != low_count:
            return 'product_count_vs_stock_units'
    if brief['mode'] == 'measurement_plan':
        if re.search(r'so sanh.{0,65}(?:don hang|don).{0,45}cung ngay', text):
            return 'unattributed_video_orders'
        if re.search(r'van de o|nguyen nhan (?:chinh )?la', text):
            return 'unsupported_marketing_cause'
        for match in re.finditer(r'(?:hook|mo dau|cta|canh demo|loi keu goi).{0,25}chua (?:du )?(?:thu hut|thuyet phuc)', text):
            if not re.search(r'co the|gia thuyet|can kiem tra', text[max(0,match.start()-45):match.start()]):
                return 'unsupported_marketing_cause'
    request = plain(message).lower()
    if brief['mode'] == 'video_script' and brief.get('shot_list'):
        has_timed_scenes = len(re.findall(r'\b\d{1,2}\s*[-–—]\s*\d{1,2}\s*(?:s|giay)?\b', text)) >= 3
        dialogue = 3 if brief.get('detailed_video') else 1
        if (not has_timed_scenes or len(re.findall(r'\bthoai\b', text)) < dialogue
                or not re.search(r'\b(?:chu|overlay)\b', text) or 'caption' not in text):
            return 'incomplete_video_script'
    elif (brief['mode'] == 'video_script' and re.search(r'kich ban', request)
            and re.search(r'loi thoai|loi dan|noi gi', request)):
        if len(re.findall(r'thoai|loi dan|noi:', text)) < 2 or 'caption' not in text:
            return 'incomplete_video_script'
    return None


def business_correction(issue):
    return {
        'unsupported_product_feature': 'Bỏ toàn bộ đặc tính chưa có bằng chứng, kể cả trong hook/caption. Không nói bàn phím cơ, gõ êm, đèn, hiệu năng, bảo hành nếu tên/dữ liệu chủ shop không xác nhận. Chỉ quay mô tả thật và phép thử chưa có kết luận.',
        'product_count_vs_stock_units': 'Số mẫu sắp hết lấy tasks.low_stock_products; số chiếc còn lại của một SKU là available_stock. Không gọi 3 chiếc của một mẫu thành 3 mẫu sắp hết.',
        'unattributed_video_orders': 'Không so tổng đơn shop cùng ngày rồi gán cho video. Chưa có tracking nguồn thì nhấp và đơn có nguồn ghi chưa đo được; hướng dẫn cài cách ghi nhận trước, không giả vờ app đã có UTM/đếm link.',
        'incomplete_video_script': 'Viết hai hook A/B, ba cảnh có mốc giây và thao tác quay thật, ít nhất một dòng Thoại và một dòng Chữ. Thêm CTA và Caption. Giữ dưới 150 từ trừ khi người bán yêu cầu chi tiết từng cảnh.',
        'unsupported_marketing_cause': 'Chưa có dữ liệu traffic/nhấp/nguồn để chẩn đoán nguyên nhân. Viết thành giả thuyết cần thử: có thể, cần kiểm tra, thử A/B; không khẳng định vấn đề ở hook hoặc do giá. Đưa mẫu ghi chép trống và cách xử lý chỉ số chưa đo được.',
        'unobserved_traffic': 'Nói rõ mình chưa có số liệu lượt xem, lượt nhấp hoặc khách truy cập để kết luận. Chỉ số chưa được đo không phải bằng 0. Giữ phần tư vấn sát câu hỏi của người bán.',
    }.get(issue, '')


def complete_business_reply(answer, facts):
    brief = facts.get('business_advisory')
    if brief and brief['mode'] == 'video_script' and not brief.get('detailed_video') and len(answer.split()) > 150:
        return planning_fallback(facts) or answer
    if not brief or not brief.get('execution') or brief['mode'] not in ('business_plan', 'performance_analysis'):
        return answer
    text = plain(answer).lower()
    execution = brief['execution']
    if brief['mode'] == 'performance_analysis':
        has_evidence = bool(re.search(r'\d[\d.,]*\s*(?:don|chiec|%|d(?:ong)?)\b', text))
        if has_evidence and re.search(r'\b(?:do|thu|theo doi|doi chieu)\b', text):
            return answer
        return answer.rstrip() + '\n\n**Việc ưu tiên**\n' + execution['first_action'] + '\n\n' + execution['decision']
    stages = execution['stages']
    if len(re.findall(r'\bngay\s+\d+', text)) >= len(stages) and re.search(r'\b(?:nhap|theo doi|don co nguon|do)\b', text):
        return answer
    steps = '\n'.join(f"• **{stage['day']}** — {stage['action']}" for stage in stages)
    return answer.rstrip() + '\n\n**Lịch triển khai và đo kết quả**\n\n' + steps


def planning_fallback(facts):
    """Still actionable when generation fails; never pretend this is model output."""
    brief = facts.get('business_advisory')
    if not brief:
        return None
    if funnel := brief.get('marketplace_funnel'):
        horizon = brief['horizon_days'] if brief['mode'] == 'business_plan' else None
        return render_marketplace_funnel(funnel, horizon=horizon)
    snapshot = facts['business_analysis']
    cur = snapshot['current']
    period = snapshot['period']
    money = lambda value: f'{value:,}'.replace(',', '.') + 'đ'
    focus = brief['focus_product']
    if focus is None and (facts.get('product_reference_missing') or facts.get('planning_product_query')
                          or (facts.get('selected_product') or {}).get('found') is False):
        return ASK_PRODUCT
    if focus:
        label = focus.get('name') or 'sản phẩm trong bản nháp'
        sku = f"SKU {focus['sku']}, " if focus.get('sku') else ''
        stock = f"kho {focus['available_stock']}" if focus.get('available_stock') is not None else 'chưa chốt tồn'
        product = f"{label} ({sku}{stock})"
    else:
        product = 'một sản phẩm còn hàng mà bạn chọn'
    if brief['mode'] == 'measurement_plan':
        return ('**Đo riêng từng video, chưa quy tổng đơn shop thành đơn TikTok.**\n\n'
                '1. Đặt mã A/B cho hai video, cùng sản phẩm và CTA; chỉ thay câu mở đầu. Chọn cùng cửa sổ đo, ví dụ 3 ngày — đây là lịch thử đề xuất.\n'
                '2. Ghi: mã video → ngày đăng → cửa sổ đo → lượt xem Analytics → nhấp đo được → đơn có nguồn → chi quảng cáo nếu có. Chưa đo nhấp/nguồn thì ghi “chưa đo được”, không ghi 0.\n'
                '3. Nếu cần gán nguồn, thiết lập cách theo dõi link/mã riêng trước hoặc hỏi khách đã xem video nào; phản hồi khách là nguồn tự khai, chưa phải đo tự động. App chưa tích hợp Analytics TikTok.\n'
                '4. Có đủ dữ liệu thì tính nhấp/lượt xem và đơn có nguồn/nhấp. Mẫu số bằng 0 thì chưa tính; không dùng tổng đơn trong ngày thay cho đơn có nguồn.\n'
                '5. Chưa có đơn: kiểm tra đã đo được nhấp chưa; giữ chân kém thì thử hook, có nhấp ít đơn thì kiểm tra trang hàng/giá/giao. Đây là các giả thuyết cần thử, chưa đủ để kết luận nguyên nhân.')
    answer = (f"Từ {period['from_date']} đến {period['to_date']}, shop có **{cur['order_count']} đơn hợp lệ**, "
              f"tổng giá trị **{money(cur['order_value_vnd'])}**. ")
    comparison = snapshot['comparison']
    if comparison['order_value_change_percent'] is not None:
        answer += (f"So với cùng thời lượng kỳ trước, giá trị đơn thay đổi "
                   f"**{comparison['order_value_change_percent']:+g}%** và số đơn thay đổi "
                   f"**{comparison['order_count_delta']:+d}**. ")
        average = comparison.get('average_order_delta_vnd')
        if average:
            answer += f"Giá trị trung bình mỗi đơn {'cao' if average > 0 else 'thấp'} hơn **{money(abs(average))}**. "
    if brief['focus_performance']:
        evidence = brief['focus_performance']
        answer += f"Đã đối chiếu **{evidence['units_sold']} chiếc** của {product} từ **{evidence['order_count']} đơn** trong kỳ."
    answer = answer.strip() + '\n\n'
    if brief['mode'] == 'ad_plan':
        return answer + (
            f"**Chuẩn bị quảng cáo cho {product}**\n\n"
            f"1. {brief['execution']['first_action']} "
            "Tính lãi đóng góp mỗi đơn sau giá vốn, phí, đóng gói và giảm giá. Khoản còn lại là trần chi trên mỗi đơn để hòa vốn. "
            "Hoãn chạy khi chưa tính được lãi hoặc chưa đủ hàng.\n"
            "2. Chạy thử hai mẫu cùng sản phẩm, chỉ đổi câu mở đầu. Chốt ngân sách tối đa và cửa sổ đo trước khi đăng.\n"
            "3. Ghi chi quảng cáo, nhấp, đơn và giá trị đơn có nguồn. Chỉ tăng ngân sách khi số liệu đủ, "
            "chi phí mỗi đơn dưới trần và tồn đủ. ROAS đo giá trị đơn trên chi quảng cáo, cần lãi thực để quyết định."
        )
    if brief['mode'] != 'video_script':
        answer += f"**Kế hoạch {brief['horizon_days']} ngày cho {product}**\n\n"
        answer += '\n'.join(f"• **{stage['day']}** — {stage['action']}" for stage in brief['execution']['stages'])
        answer += "\n\n" + brief['execution']['decision'] + "\n\n"
        if REQUEST_COUNTS not in answer:
            answer += REQUEST_COUNTS + '\n\n'
        return answer.strip()
    shots = brief['shot_list']
    if not shots:
        return answer + 'Bạn muốn quay mặt hàng nào? Gửi tên hoặc SKU để mình viết lời thoại và danh sách cảnh cho đúng mẫu.'
    if not brief.get('detailed_video'):
        _, detail, demo, finish = shots['scenes']
        return (f"**TikTok · {label} · 28 giây · 9:16**\n\n"
                f"**0–3s** Chiếu món thật. Hook A “{shots['hooks'][0]}” Hook B “{shots['hooks'][1]}”\n\n"
                f"**3–10s** {detail['visual']} Chữ “{detail['overlay']}”.\n\n"
                f"**10–22s** {demo['visual']} Thoại “{detail['speech']}”\n\n"
                f"**22–28s** {finish['visual']} “{finish['speech']}”\n\n"
                f"**Caption** {shots['caption']}\n**A/B** Chỉ đổi hook. So nhấp sau 72 giờ.")
    answer = (f"**Kịch bản TikTok cho {product}**\n\n"
               "Quay dọc 9:16. Đặt máy cố định, dùng ánh sáng cửa sổ và giữ phụ đề cách mép dưới.\n\n"
               f"**Hook A** — “{shots['hooks'][0]}”\n"
               f"**Hook B** — “{shots['hooks'][1]}”\n\n")
    answer += '\n\n'.join(f"**{scene['time']}**\nHình — {scene['visual']}\n"
                           f"Thoại — {scene['speech']}\nChữ — {scene['overlay']}" for scene in shots['scenes'])
    answer += (f"\n\n**Caption**\n{shots['caption']}\n\n"
               "**Thử A/B** — Chỉ đổi hook. So lượt xem, lượt nhấp sản phẩm và đơn có nguồn của hai bản "
               "trong cùng cửa sổ đo, ví dụ 72 giờ sau mỗi lần đăng. Chưa gắn nguồn thì để trống cột đơn từ video.")
    return answer
