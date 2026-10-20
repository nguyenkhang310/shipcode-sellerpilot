"""Opt-in live benchmark through the real chat API and a disposable shop.

Run from repo: npm run ai:benchmark. Sends synthetic messages and a drawn image
to the configured providers. Never opens the working shop or publishes products.
Not collected by pytest. Requires the backend dev dependencies.
"""
import asyncio
import base64
import json
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from app.ai.factory import create_provider
from app.core.config import Settings
from app.scripts.check_ai import synthetic_keyboard_png
from test_product_drafts import make_client


async def main():
    settings = Settings()
    if settings.ai_provider != 'gemini':
        print('Benchmark này yêu cầu AI_PROVIDER=gemini; không tự đổi provider hoặc model.')
        return 1
    results, calls = [], Counter()
    async def count_request(request):
        if request.method == 'POST':
            calls[request.url.host] += 1

    with tempfile.TemporaryDirectory(prefix='sellerpilot-ai-benchmark-') as directory:
        fixture, _, _ = make_client(Path(directory))
        app = fixture.app
        async with app.router.lifespan_context(app), create_provider(settings) as provider:
            provider.http.event_hooks['request'].append(count_request)
            app.state.ai_provider = provider
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://qa') as api:
                async def measure(label, message, conversation=None, *, quick=False, listing=False):
                    calls.clear()
                    started = perf_counter()
                    response = await api.post('/api/v1/chat', json={
                        'message': message, 'conversation_id': conversation, 'request_id': str(uuid4())})
                    elapsed = round((perf_counter() - started) * 1000)
                    data = response.json().get('data', {})
                    ok = response.status_code == 200 and data.get('mode') == 'ai' and not data.get('fallback_reason')
                    if quick:
                        ok = ok and not calls and data.get('provider') == 'deterministic_parser'
                    if listing:
                        draft = data.get('product_draft') or {}
                        ok = ok and draft.get('status') == 'ready' and draft.get('price_vnd') == 500000 and draft.get('stock') == 8
                    row = {'case': label, 'ok': ok, 'elapsed_ms': elapsed, 'http_status': response.status_code,
                           'provider': data.get('provider'), 'model': data.get('model'),
                           'fallback_reason': data.get('fallback_reason'), 'inference_calls': dict(calls),
                           'answer_chars': len(data.get('answer', ''))}
                    results.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
                for label, message in [
                    ('greeting', 'chao ban'), ('summary', 'Nay shop sao rồi?'),
                    ('orders', 'Hom nay chot duoc may don?'),
                    ('inventory', 'Bạn ơi, kiểm tra kho giúp mình nhé'),
                    ('sku', 'SKU SEED-PHONE còn mấy cái?'),
                ]:
                    await measure(label, message, quick=True)
                await measure('advice', 'Dựa trên số liệu shop, gợi ý 2 việc cần ưu tiên hôm nay. Trả lời ngắn gọn, không cần kế hoạch dài.')
                await measure('pricing', 'Giá vốn 5 xị, đóng gói 20k mỗi đơn, phí sàn 10%. Nếu bán 1 củ thì còn lời bao nhiêu?')
                upload = await api.post('/api/v1/product-drafts/images-data', json={
                    'images_base64': [base64.b64encode(synthetic_keyboard_png()).decode()]})
                if upload.status_code != 201:
                    raise RuntimeError('Không tạo được ảnh QA; dừng thay vì dùng ảnh của shop.')
                await measure('image_listing', 'Bán sản phẩm trong ảnh giá 5 xị, kho 8 chiếc. Tự viết tên và mô tả theo hình, không bịa thông số.',
                              upload.json()['data']['conversation_id'], listing=True)
    report = {'tested_at': datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).isoformat(),
              'timeout_seconds': settings.gemini_generation_timeout_seconds, 'cases': results}
    output = Path(__file__).resolve().parents[2] / 'docs/evaluations/ai-latency'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('Kết quả:', output / 'results.json', flush=True)
    return 0 if all(row['ok'] for row in results) else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
