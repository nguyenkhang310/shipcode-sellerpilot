"""Evidence-led planning briefs for natural replies, with a useful offline plan."""
import re

from app.ai.fallback import extract_sku
from app.ai.money import plain
from app.integrations.business import business_snapshot
from app.integrations.ute_mall import ShopItemNotFoundError


def planning_request(message, history=()):
    text = plain(message).lower()
    mode = ('business_plan' if re.search(r'ke hoach|len plan|lap plan|lo trinh|chien luoc', text) else
            'measurement_plan' if re.search(r'cach do|do hieu qua|cach theo doi|don tu tiktok|hieu qua tung video', text) and not re.search(r'kich ban|quay video|lam video', text) else
            'video_script' if re.search(r'tiktok|tik tok|kich ban|quay video|lam video|video ngan|reels|cau mo dau|hook|hieu qua tung video', text) else
            'performance_analysis' if re.search(r'phan tich (?:so lieu|shop|kinh doanh|hieu suat|doanh)|tang doanh thu|tang don|ra don|ban cham', text) else None)
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
    return {'mode': mode, 'horizon_days': min(90, max(1, days)), 'followup': False}


def attach_business_brief(shop, facts, *, message, history=(), preferences=None):
    request = planning_request(message, history)
    if request is None:
        return None
    snapshot = facts.get('business_analysis')
    if snapshot is None:
        snapshot = business_snapshot(shop, facts.get('period', {}).get('days', 7))
        facts['business_analysis'] = snapshot
    selected = facts.get('selected_product')
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
    draft = facts.get('draft_context')
    draft_reference = bool(draft and re.search(r'san pham nay|mau nay|ban nhap|mon nay|hang nay', plain(message).lower()))
    if draft_reference and not extract_sku(message.lower()):
        focus = {'product_id': None, 'sku': None, 'name': draft.get('name'),
                 'price_vnd': draft.get('selling_price_vnd'), 'available_stock': draft.get('stock'),
                 'status': 'draft'}
        reason = 'Bản nháp đang soạn mà chủ shop nhắc tới; chưa được đăng, không phải sản phẩm đang bán.'
    elif selected and selected.get('found') is not False:
        focus = {'product_id': selected['product_id'], 'sku': selected['sku'],
                 'name': selected.get('product_name', selected.get('name')),
                 'price_vnd': selected['price_vnd'], 'available_stock': selected['stock'],
                 'status': 'active' if selected.get('is_active', True) else 'inactive'}
        reason = 'Sản phẩm chủ shop đang hỏi; không tự chuyển sang mẫu khác.'
    else:
        explicit_sku = extract_sku(message.lower())
        if explicit_sku or (selected and selected.get('found') is False):
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
    if focus is not None:
        in_stock = (focus.get('available_stock') or 0) > 0
    else:
        in_stock = False
    brief = {
        **request, 'status': 'proposal_only', 'diagnosis': diagnosis,
        'focus_product': focus, 'focus_selection_reason': reason,
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
            'connected': ['Đơn hợp lệ, giá trị đơn, hủy/hoàn và số lượng bán theo sản phẩm từ Shopee.'],
            'manual_fields': ['video_id', 'published_at', 'measurement_window', 'views', 'product_clicks', 'attributed_orders', 'ad_spend_vnd'],
            'definitions': ['Tỷ lệ nhấp = nhấp sản phẩm/lượt xem, khi có đủ hai số cùng kỳ.',
                            'Tỷ lệ chốt sau nhấp = đơn được gán nguồn/nhấp sản phẩm; chưa có nguồn thì không tính.',
                            'Chi phí/đơn = chi quảng cáo/đơn gán nguồn; ROAS = giá trị đơn gán nguồn/chi quảng cáo, không phải lợi nhuận.'],
            'decision': 'Giữ chân kém: sửa mở đầu; xem tốt nhưng ít nhấp: thử demo/CTA; có nhấp ít đơn: kiểm tra trang sản phẩm, giá, giao hàng. Đây là giả thuyết cần đo.',
            'targets': 'Mục tiêu thử nghiệm đề xuất, không phải số thực tế hay cam kết ra đơn; chưa có baseline thì đo trước.',
        },
    }
    facts['business_advisory'] = brief
    return brief


def business_reply_issue(answer, facts, *, message='', seller_context=''):
    brief = facts.get('business_advisory')
    if not brief:
        return None
    text = plain(answer.replace('*', '').replace('`', '')).lower()
    focus = brief.get('focus_product') or {}
    selected = facts.get('selected_product') or {}
    evidence = plain(' '.join(str(value or '') for value in
        (focus.get('name'), selected.get('product_name'), selected.get('description'), seller_context))).lower()
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
    if (brief['mode'] == 'video_script' and re.search(r'kich ban', request)
            and re.search(r'loi thoai|loi dan|noi gi', request)):
        if len(re.findall(r'thoai|loi dan|noi:', text)) < 2 or 'caption' not in text:
            return 'incomplete_video_script'
    return None


def business_correction(issue):
    return {
        'unsupported_product_feature': 'Bỏ toàn bộ đặc tính chưa có bằng chứng, kể cả trong hook/caption. Không nói bàn phím cơ, gõ êm, đèn, hiệu năng, bảo hành nếu tên/dữ liệu chủ shop không xác nhận. Chỉ quay mô tả thật và phép thử chưa có kết luận.',
        'product_count_vs_stock_units': 'Số mẫu sắp hết lấy tasks.low_stock_products; số chiếc còn lại của một SKU là available_stock. Không gọi 3 chiếc của một mẫu thành 3 mẫu sắp hết.',
        'unattributed_video_orders': 'Không so tổng đơn shop cùng ngày rồi gán cho video. Chưa có tracking nguồn thì nhấp và đơn có nguồn ghi chưa đo được; hướng dẫn cài cách ghi nhận trước, không giả vờ app đã có UTM/đếm link.',
        'incomplete_video_script': 'Viết kịch bản quay đầy đủ: 2 hook A/B, mỗi cảnh có mốc giây, hình ảnh, nhãn Thoại: với câu nói cụ thể và Chữ: trên màn hình, CTA và Caption. Không thay lời thoại bằng mô tả thao tác.',
        'unsupported_marketing_cause': 'Chưa có dữ liệu traffic/nhấp/nguồn để chẩn đoán nguyên nhân. Viết thành giả thuyết cần thử: có thể, cần kiểm tra, thử A/B; không khẳng định vấn đề ở hook hoặc do giá. Đưa mẫu ghi chép trống và cách xử lý chỉ số chưa đo được.',
    }.get(issue, '')


def planning_fallback(facts):
    """Still actionable when generation fails; never pretend this is model output."""
    brief = facts.get('business_advisory')
    if not brief:
        return None
    snapshot = facts['business_analysis']
    cur = snapshot['current']
    period = snapshot['period']
    money = lambda value: f'{value:,}'.replace(',', '.') + 'đ'
    focus = brief['focus_product']
    if focus:
        label = focus.get('name') or 'sản phẩm trong bản nháp'
        sku = f"SKU {focus['sku']}, " if focus.get('sku') else ''
        stock = f"kho {focus['available_stock']}" if focus.get('available_stock') is not None else 'chưa chốt tồn'
        product = f"**{label}** ({sku}{stock})"
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
              f"giá trị **{money(cur['order_value_vnd'])}**. Đây là khung thử nghiệm, chưa phải dự báo doanh số.\n\n")
    if brief['mode'] != 'video_script':
        answer += (f"**Kế hoạch {brief['horizon_days']} ngày**\n"
                   f"• Đầu kỳ: xử lý đơn chờ, chọn {product}; kiểm tra trang hàng, giá vốn và khả năng giao.\n"
                   "• Giữa kỳ: quay hai phiên bản cùng một video, chỉ đổi câu mở đầu; đăng và ghi số liệu từng video theo cùng cửa sổ đo.\n"
                   "• Cuối kỳ: so lượt xem, nhấp sản phẩm và đơn có nguồn; sửa đúng khâu yếu rồi thử lại. Chưa có giá vốn thì chưa chốt giảm giá/chạy ads.\n\n")
    answer += (f"**Video thử cho {product}**\n"
               '• 0–3s: đưa sản phẩm vào khung. Mở A: “Bạn đang cân nhắc món này? Xem cận trước nhé.”; B: “Món này dùng thế nào? Mình quay thử cho bạn xem.”\n'
               '• 3–12s: quay cận chi tiết nhìn thấy; lời thoại mô tả đúng chi tiết đã kiểm tra.\n'
               '• 12–23s: quay một thao tác sử dụng thực tế, chưa đo thì không tuyên bố hiệu năng.\n'
               '• 23–30s: “Xem thông tin và giá hiện tại trên gian hàng Shopee.” Quay dọc, phụ đề rõ, tránh vùng nút giao diện.\n\n'
               '**Đo kết quả:** ghi lượt xem, nhấp và đơn có nguồn từng video. App chưa liên kết số liệu TikTok; không lấy tổng đơn shop làm đơn từ video. '
               'Không đủ dữ liệu thì tiếp tục đo, không khẳng định video chắc chắn ra đơn.')
    return answer
