"""Isolated browser inference. No shop repository, SQL writes or publication tools."""
import asyncio
import hashlib
import re
from dataclasses import dataclass
from time import monotonic

from fastapi import HTTPException
from pydantic import ValidationError

from app.ai.contracts import AIProviderError
from app.ai.fallback import extract_price
from app.ai.gemini import image_parts
from app.ai.listing_contracts import ListingCopy, listing_validation_context
from app.ai.money import money_hints
from app.ai.text import assistant_text


async def browser_assist(payload, provider):
    history = [row.model_dump() for row in payload.history]
    facts = {
        'integration_mode': 'shopee_browser',
        'browser_snapshot': payload.snapshot.model_dump(mode='json'),
        'data_scope': 'Only the currently visible page; not a complete shop database.',
        'operations_executed': [],
    }
    if payload.mode == 'chat':
        answer = assistant_text(await provider.respond(payload.message, history=history, facts=facts))
        if not answer or len(answer) > 16000:
            raise AIProviderError('invalid_response')
        return {'answer': answer, 'provider': getattr(provider, 'response_provider', getattr(provider, 'provider', 'gemini')),
                'model': getattr(provider, 'response_model', getattr(provider, 'model', None))}
    images = []
    for value in payload.images:
        if not value.startswith(('data:image/jpeg;base64,', 'data:image/png;base64,', 'data:image/webp;base64,')):
            raise HTTPException(422, detail='Ảnh không hợp lệ.')
        images.append({'mime': value[5:].split(';', 1)[0], 'url': value})
    image_parts(images)  # Validate encoding, signature and size before any provider call.
    known = {**payload.draft.model_dump(), 'current_message': payload.message,
             'allowed_categories': [], 'response_schema': ListingCopy.model_json_schema(),
             'money_interpretations': money_hints(payload.message)}
    raw = await provider.compose_listing(facts=known, history=history, images=images)
    copy = ListingCopy.model_validate_json(raw, context=listing_validation_context(known, history))
    updates = {}
    for field in ('name', 'description'):
        value = getattr(copy, field)
        if value:
            if field == 'name' and re.match(r'^(?:đăng (?:sản phẩm|giúp)|hãy |AI tự viết)', value, re.I):
                continue
            updates[field] = value
    if (copy.price_vnd is not None and copy.price_evidence
            and copy.price_evidence in payload.message
            and extract_price(copy.price_evidence, sku=None) == copy.price_vnd):
        updates['price_vnd'] = copy.price_vnd
    if copy.stock is not None and copy.stock_evidence and copy.stock_evidence in payload.message:
        numbers = re.findall(r'\d+', copy.stock_evidence)
        if numbers == [str(copy.stock)]:
            updates['stock'] = copy.stock
    draft = payload.draft.model_copy(update=updates)
    missing = [field for field in ('name', 'description', 'price_vnd', 'stock') if getattr(draft, field) is None]
    labels = {'name': 'món hàng cần bán', 'description': 'thông tin mô tả', 'price_vnd': 'giá bán', 'stock': 'số lượng tồn kho'}
    answer = copy.clarification or (
        'Mình đã soạn bản nháp. Bạn kiểm tra rồi bấm **Điền vào Shopee**; sản phẩm chưa được đăng.'
        if not missing else 'Mình đã giữ các thông tin đã có. Bạn bổ sung ' + ', '.join(labels[key] for key in missing[:2]) + ' nhé?')
    return {'answer': answer, 'draft': draft.model_dump(), 'missing_fields': missing,
            'provider': getattr(provider, 'response_provider', getattr(provider, 'provider', 'gemini')),
            'model': getattr(provider, 'response_model', getattr(provider, 'model', None))}


@dataclass
class BrowserJob:
    digest: str
    task: asyncio.Task
    created: float


class BrowserRequests:
    """Short HTTP polling avoids MV3's long-fetch service-worker timeout.

    Jobs are inference-only, bounded and expire after ten minutes. Restarting the
    backend loses these jobs; retries never execute shop writes.
    """
    def __init__(self):
        self.jobs = {}

    def key(self, connection_id, request_id):
        return str(connection_id), str(request_id)

    def start(self, payload, provider):
        now = monotonic()
        self.jobs = {key: job for key, job in self.jobs.items() if not job.task.done() or now - job.created < 600}
        key = self.key(payload.connection_id, payload.request_id)
        digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
        if key in self.jobs:
            if self.jobs[key].digest != digest:
                raise HTTPException(409, detail='Mã yêu cầu đã dùng cho nội dung khác.')
            return
        if len(self.jobs) >= 64 or sum(not job.task.done() for job in self.jobs.values()) >= 4:
            raise HTTPException(429, detail='Đang có nhiều yêu cầu AI. Bạn thử lại sau nhé.')

        async def run():
            try:
                async with asyncio.timeout(90):
                    return {'status': 'completed', 'result': await browser_assist(payload, provider)}
            except (AIProviderError, ValidationError, HTTPException, TimeoutError) as error:
                reason = error.reason if isinstance(error, AIProviderError) else 'invalid_response'
                return {'status': 'failed', 'reason': reason,
                        'message': 'Chưa xử lý được bằng AI lúc này. Nội dung và ảnh vẫn được giữ; bạn có thể thử lại.'}
            except asyncio.CancelledError:
                return {'status': 'cancelled'}
            except Exception:
                return {'status': 'failed', 'reason': 'provider_unavailable', 'message': 'Chưa gọi được AI. Bạn thử lại nhé.'}
        self.jobs[key] = BrowserJob(digest, asyncio.create_task(run()), now)

    def status(self, connection_id, request_id):
        job = self.jobs.get(self.key(connection_id, request_id))
        if job is None:
            raise HTTPException(404, detail='Yêu cầu không còn tồn tại; backend có thể đã khởi động lại.')
        if job.task.cancelled():
            return {'status': 'cancelled'}
        return job.task.result() if job.task.done() else {'status': 'running'}

    async def close(self):
        tasks = [job.task for job in self.jobs.values() if not job.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
