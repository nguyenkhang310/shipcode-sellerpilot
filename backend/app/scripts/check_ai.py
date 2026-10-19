"""Verify the selected AI provider through the backend, using synthetic inputs only.

No shop database, real photos or conversation history is read. No seller action
is executed. CLI processes and temporary test workspaces are cleaned up.
"""

import asyncio
import base64
import json
import shutil
import struct
import zlib
from datetime import datetime
from zoneinfo import ZoneInfo
from time import perf_counter

from pydantic import ValidationError

from app.ai.advisor_contracts import AdviceExtraction
from app.ai.contracts import AIProviderError
from app.ai.factory import create_provider, managed_opencode, opencode_version
from app.ai.antigravity import AntigravityClient
from app.ai.opencode import FREE_MODEL
from app.ai.listing_contracts import ListingCopy
from app.core.config import Settings
from app.services.chat import enrich_ai_command


def synthetic_keyboard_png():
    """A small drawn keyboard; never open a user's photo or upload folder."""
    width, height = 384, 200
    pixels = bytearray([245, 245, 245] * width * height)

    def rectangle(left, top, right, bottom, color):
        for y in range(top, bottom):
            start = (y * width + left) * 3
            pixels[start:start + (right - left) * 3] = bytes(color) * (right - left)

    rectangle(15, 27, 369, 175, (35, 40, 48))
    for row in range(4):
        for column in range(13):
            x, y = 24 + column * 26, 36 + row * 26
            rectangle(x, y, x + 21, y + 21, (225, 228, 232))
    rectangle(95, 143, 277, 165, (225, 228, 232))
    for x in (24, 50, 303, 329):
        rectangle(x, 143, x + 21, 165, (225, 228, 232))

    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))

    rows = b''.join(b'\0' + pixels[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))


def parse_json(text):
    # Match the listing service's handling of fenced JSON, without repairing it.
    if text.strip().startswith('```'):
        text = '\n'.join(text.strip().splitlines()[1:-1])
    return json.loads(text)


async def verify(provider):
    if provider.provider == 'opencode':
        model = await provider._free_model()
        if not model.get('capabilities', {}).get('input', {}).get('image'):
            raise ValueError('GLM hiện không khai báo hỗ trợ ảnh; chưa thể xác nhận chức năng đăng hàng từ ảnh.')
        print(f'PASS · {FREE_MODEL}: active, input/output/cache = 0, hỗ trợ ảnh.', flush=True)
    else:
        if not (await provider.check_health()).model_available:
            raise ValueError('Provider chưa sẵn sàng. Với Gemini, kiểm tra key, quyền model và quota; với Antigravity, kiểm tra đăng nhập/quyền CLI.')
        print(f'PASS · {provider.provider} / {provider.model}: model truy cập được.', flush=True)

    today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    change = 'Đổi giá SKU DEMO-KB-001 thành 5 xị'
    result = await provider.classify(change, today=today)
    command = enrich_ai_command(result.command, message=change, today=today, prefer_model_intent=True)
    if (command.intent, command.sku, command.new_price_vnd) != ('change_price', 'DEMO-KB-001', 500000):
        raise ValueError('Phân loại câu đổi giá chưa đúng SKU/giá/ý định.')
    print('PASS · Hiểu yêu cầu đổi giá; chỉ trích tham số, không thực thi.', flush=True)

    answer = await provider.respond('Mình muốn bán phụ kiện cho sinh viên. Gợi ý hai việc bắt đầu, trả lời ngắn nhé.',
        history=[], facts={'synthetic_test_only': True, 'seller_preferences': {'target_audience': 'sinh viên'}})
    if not answer.strip():
        raise ValueError('Hội thoại không có nội dung.')
    print('PASS · Hội thoại tiếng Việt qua agent chat.', flush=True)

    extraction = AdviceExtraction.model_validate_json(await provider.analyze_advice(
        'Giá vốn 5 xị, đóng gói 20k mỗi đơn, phí sàn 10% giá bán. Mình muốn tính thử bán 1 củ.',
        history=[], context={}))
    economics = {item.field: item.value for item in extraction.economics}
    expected = {'unit_cost_vnd': 500000, 'packaging_vnd': 20000, 'fee_percent': 10, 'selling_price_vnd': 1000000}
    if any(economics.get(key) != value for key, value in expected.items()):
        raise ValueError('Đọc bối cảnh tính giá chưa đúng; không dùng kết quả này để tính lời.')
    print('PASS · Phân biệt giá vốn, phí, đóng gói và giá bán.', flush=True)

    message = 'Bán sản phẩm trong ảnh này giá 5 xị, kho còn 8 chiếc. Tự viết tên và mô tả theo đúng hình, không bịa thông số.'
    facts = {
        'synthetic_test_only': True, 'name': None, 'description': None,
        'price_vnd': None, 'stock': None, 'category_id': None, 'category': None,
        'current_message': message, 'copy_instructions': None,
        'allowed_categories': [{'id': 2, 'name': 'Thời Trang Nam'}, {'id': 4, 'name': 'Máy Tính & Laptop'}],
        'response_schema': ListingCopy.model_json_schema(),
    }
    image = {'type': 'file', 'mime': 'image/png',
             'url': 'data:image/png;base64,' + base64.b64encode(synthetic_keyboard_png()).decode('ascii')}
    listing = ListingCopy.model_validate(parse_json(await provider.compose_listing(facts=facts,
        history=[{'role': 'user', 'content': message}], images=[image])))
    if (not listing.name or 'bàn phím' not in listing.name.lower() or not listing.description
            or listing.category_id != 4 or listing.price_vnd != 500000 or listing.stock != 8):
        raise ValueError('Đọc ảnh/soạn bản nháp chưa đúng sản phẩm, ngành hàng, giá hoặc tồn kho.')
    print('PASS · Đọc ảnh bàn phím giả lập, tự soạn tên/mô tả, trích giá và tồn kho.', flush=True)


async def main():
    started = perf_counter()
    try:
        settings = Settings()
    except ValidationError:
        print('FAIL · Cấu hình chưa hợp lệ. Đối chiếu provider/model trong .env.example, root .env và backend/.env.', flush=True)
        return 1
    try:
        if settings.ai_provider == 'gemini':
            if not any(key.get_secret_value().strip() for key in
                       (settings.gemini_api_key, settings.gemini_api_key_2, settings.gemini_api_key_3)):
                print('FAIL · Chưa có GEMINI_API_KEY. Tạo key tại https://aistudio.google.com/apikey rồi điền vào root .env; không gửi key trong chat/Git.', flush=True)
                return 1
            async with create_provider(settings) as provider:
                print(f'Đang kiểm tra Gemini API trực tiếp: {settings.gemini_model}. Chỉ dùng dữ liệu và ảnh tự vẽ.', flush=True)
                await verify(provider)
            print(f'PASS · Gemini API qua kiểm tra trong {perf_counter()-started:.1f}s. Đây là tổng nhiều ca, không phải độ trễ một câu chat.', flush=True)
            return 0
        if settings.ai_provider == 'antigravity':
            provider = AntigravityClient(settings.antigravity_binary, settings.antigravity_model,
                                         timeout=settings.antigravity_generation_timeout_seconds)
            await provider.initialize()
            print('Đang thử chat, hiểu tiền Việt, tư vấn và ảnh tự vẽ qua Antigravity CLI.', flush=True)
            await verify(provider)
            print('Antigravity đã qua kiểm tra. Chạy npm run demo ở thư mục gốc.', flush=True)
            return 0
        if settings.ai_provider != 'opencode':
            raise ValueError('ai:check hỗ trợ AI_PROVIDER=gemini, opencode hoặc antigravity.')
        binary = shutil.which(settings.opencode_binary)
        if not binary:
            raise ValueError('Thiếu OpenCode: npm install -g opencode-ai@1.18.30')
        print(f'OpenCode {await opencode_version(binary)} · model {settings.opencode_model}', flush=True)
        print('Đang thử 4 agent bằng dữ liệu/ảnh tự vẽ. Không đọc hoặc thay đổi shop thật.', flush=True)
        async with managed_opencode(settings) as provider:
            await verify(provider)
        print('GLM sẵn sàng. Chạy npm run demo ở thư mục gốc.', flush=True)
        return 0
    except AIProviderError as error:
        guidance = {
            'free_tier_restricted': 'Gateway trả 403: "OpenCode\'s free tier can only be used from within OpenCode." Model có trong danh sách không đồng nghĩa backend được quyền gọi. Cần quyền/API được provider cho phép hoặc chọn model local; chạy lại không bảo đảm mở khóa. Xem docs/GLM_SETUP.md.',
            'provider_rate_limited': 'Đã đạt hạn mức (429). Kiểm tra hạn mức ở OpenCode Console và thử lại sau.',
            'free_model_unavailable': 'Không thấy GLM Free active với đủ giá 0. Chạy opencode models opencode --refresh --verbose để kiểm tra.',
            'provider_timeout': 'Quá thời gian. Kiểm tra mạng và thử lại; mặc định 90 giây cho mỗi lượt gọi.',
        }
        detail = ('Kiểm tra GEMINI_API_KEY, quyền model và quota trong AI Studio; xem docs/GEMINI_API_SETUP.md.'
                  if settings.ai_provider == 'gemini' else
                  'Kiểm tra agy, đăng nhập và docs/ANTIGRAVITY_SETUP.md; không bật credit hoặc quyền công cụ rộng.'
                  if settings.ai_provider == 'antigravity' else guidance.get(error.reason, 'Kiểm tra kết nối OpenCode; xem docs/GLM_SETUP.md.'))
        print(f'FAIL · {error.reason} ({error.stage or "unknown"}): {detail}', flush=True)
        return 1
    except ValidationError:
        print('FAIL · Phản hồi model chưa khớp schema kiểm thử. Giữ validation; xem hướng dẫn provider trong README.', flush=True)
        return 1
    except (RuntimeError, ValueError, OSError, TimeoutError) as error:
        print(f'FAIL · {error}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
