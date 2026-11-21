"""Isolated browser inference. No shop repository, SQL writes or publication tools."""
import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from time import monotonic

from fastapi import HTTPException
from pydantic import ValidationError

from app.ai.contracts import AIProviderError
from app.ai.fallback import extract_price
from app.ai.gemini import image_parts
from app.ai.listing_contracts import ListingCopy, listing_validation_context
from app.ai.money import money_hints, money_mentions, plain
from app.ai.quick_reads import quick_read
from app.ai.small_talk import social_reply
from app.ai.quantities import quantity_value
from app.ai.listing_evidence import commercial_context
from app.ai.text import conversational_text, reply_format_issue

logger = logging.getLogger(__name__)


def browser_sales_reply(payload, platform, availability):
    today = datetime.now(timezone(timedelta(hours=7))).date()
    command = quick_read(payload.message, today=today)
    if (not command or command.intent != 'shop_summary' or command.sales_metric or
            command.day != today or command.days not in (None, 1) or command.compare_yesterday or command.calendar_period):
        return None
    dashboard = payload.shop_context.dashboard if payload.shop_context else None
    if dashboard:
        metrics = [metric.model_dump() for metric in dashboard.metrics]
    else:
        try:
            snapshot = json.loads(payload.snapshot.text)
        except ValueError:
            snapshot = {}
        metrics = snapshot.get('metrics', []) if isinstance(snapshot, dict) else []
    groups = {'orders': set(), 'sales': set()}
    labels = {'don hang': 'orders', 'orders': 'orders', 'doanh so': 'sales', 'doanh thu': 'sales', 'revenue': 'sales'}
    for row in metrics[:20] if isinstance(metrics, list) else []:
        if not isinstance(row, dict) or not isinstance(row.get('label'), str) or not isinstance(row.get('value'), str):
            continue
        key = labels.get(plain(row['label']).strip())
        value = row['value'].strip()
        if key and re.fullmatch(r'(?:[₫đ]\s*)?\d[\d.,\s]{0,18}(?:[₫đkmb])?', value, re.I):
            groups[key].add(value)
    figures = []
    if len(groups['orders']) == 1:
        figures.append(f'**{next(iter(groups["orders"]))} đơn**')
    if len(groups['sales']) == 1:
        figures.append(f'doanh số **{next(iter(groups["sales"]))}**')
    if figures:
        return (f'Lần đọc gần nhất trên {platform} ghi nhận ' + ' và '.join(figures) +
                '. Mình chưa xác định được kỳ thống kê của các số này.')
    next_step = (availability['hướng_xử_lý'] if availability else
                 'Bạn bấm **Cập nhật** cạnh tên shop để đồng bộ số liệu nhé.')
    return f'Mình chưa đọc được số đơn và doanh số hôm nay từ {platform}. {next_step}'


def browser_availability(context):
    """User-facing readiness; missing observations are never zero stock/sales."""
    labels = {'products': 'tồn kho sản phẩm', 'dashboard': 'doanh số', 'orders': 'danh sách đơn hàng'}
    missing = [label for key, label in labels.items() if getattr(context, key) is None]
    if context.sync_status == 'running':
        next_step = 'Đang đồng bộ dữ liệu. Khi tiến trình kết thúc, bạn có thể hỏi lại; không cần mở thêm tab.'
    else:
        next_step = 'Bấm **Cập nhật** cạnh tên shop để đồng bộ lại một lần; không cần tự mở từng mục.'
    return {'chưa_có_dữ_liệu': missing, 'hướng_xử_lý': next_step}


def browser_answer(answer, context, availability):
    """Catch a provider reverting to the old manual-page workflow or leaking fields.

    Keep normal advice and analysis intact. This is an output guard, not an
    intent router: open conversation still goes to the model with its history.
    """
    if context is None:
        return answer
    prose = ' '.join(answer.split())
    internal = re.search(r'\b(?:null|undefined|shop_context|browser_snapshot|pagination_complete)\b|`products`', prose, re.I)
    manual = re.search(r'(?:bạn|vui lòng|hãy|cần|nhờ).{0,70}(?:mở|chuyển (?:sang|đến)).{0,100}(?:trang|tab|quản lý|kênh người bán)', prose, re.I)
    # Explicit navigation is appropriate when editing a form, but not as a way
    # to answer a read-only stock/sales question with a missing-data excuse.
    missing_excuse = re.search(r'(?:chưa|không).{0,45}(?:dữ liệu|đồng bộ|số liệu|danh sách)', prose, re.I)
    if not internal and not (manual and missing_excuse and availability['chưa_có_dữ_liệu']):
        return answer
    missing = availability['chưa_có_dữ_liệu']
    mentions = {'tồn kho sản phẩm': r'products|tồn kho|sản phẩm|hết hàng',
                'doanh số': r'dashboard|doanh số|doanh thu',
                'danh sách đơn hàng': r'orders|đơn hàng'}
    named = [label for label, pattern in mentions.items() if re.search(pattern, prose, re.I)]
    missing = [label for label in missing if label in named] if named else missing
    if not missing:
        # Do not turn a schema leak or a stale manual instruction into a false
        # missing-data claim when that resource is actually available.
        raise AIProviderError('invalid_response')
    return 'Mình chưa có dữ liệu ' + ', '.join(missing) + ' đã đồng bộ để kết luận chính xác. ' + availability['hướng_xử_lý']


async def browser_assist(payload, provider):
    history = [row.model_dump() for row in payload.history]
    facts = {
        'integration_mode': 'shopee_browser',
        'platform': 'tiktok' if 'tiktok.com' in payload.snapshot.url else 'shopee',
        'browser_snapshot': payload.snapshot.model_dump(mode='json'),
        'data_scope': 'Only the currently visible page; not a complete shop database.',
        'operations_executed': [],
    }
    if payload.shop_context:
        facts['shop_context'] = payload.shop_context.model_dump(mode='json', exclude_none=True)
        facts['data_availability'] = browser_availability(payload.shop_context)
        facts['data_scope'] = ('Account-scoped observations collected automatically across seller pages. '
                               'Use each resource timestamp, pagination completeness, unknown/conflicting counts '
                               'and list scope; neither the current page alone nor a verified Open API shop database.')
    if payload.mode == 'chat':
        platform = 'TikTok Shop' if facts['platform'] == 'tiktok' else 'Shopee'
        answer = (social_reply(payload.message, ongoing=bool(history))
                  or browser_sales_reply(payload, platform, facts.get('data_availability')))
        if answer:
            return {'answer': answer, 'provider': 'deterministic_parser', 'model': None}
        answer = conversational_text(await provider.respond(payload.message, history=history, facts=facts))
        answer = browser_answer(answer, payload.shop_context, facts.get('data_availability'))
        if reply_format_issue(answer) or len(answer) > 16000:
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
             'money_interpretations': money_hints(payload.message), 'image_count': len(images),
             'last_question': history[-1]['content'] if history and history[-1]['role'] == 'assistant' else None}
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
            and extract_price(copy.price_evidence, sku=None) == copy.price_vnd
            and commercial_context(copy.price_evidence, payload.message)):
        updates['price_vnd'] = copy.price_vnd
    elif updates.get('price_vnd') is None:
        prices = {mention.value for mention in money_mentions(payload.message)
                  if mention.value is not None and 1_000 <= mention.value <= 1_000_000_000
                  and commercial_context(mention.text, payload.message)}
        if len(prices) == 1:
            updates['price_vnd'] = prices.pop()

    if copy.stock is not None and copy.stock_evidence and copy.stock_evidence in payload.message:
        if quantity_value(copy.stock_evidence) == copy.stock and commercial_context(copy.stock_evidence, payload.message, stock=True):
            updates['stock'] = copy.stock
    elif updates.get('stock') is None:
        s_match = re.search(r'(?:tồn kho|kho|số lượng|còn)\s*[:=]?\s*(\d+(?:[.,]\d{3})*(?:\s*(?:cái|chiếc|sản phẩm|sp|bộ|đôi))?)\b', payload.message, re.I)
        if s_match:
            s_val = quantity_value(s_match[1])
            if s_val is not None and commercial_context(s_match[1], payload.message, stock=True):
                updates['stock'] = s_val

    draft = payload.draft.model_copy(update=updates)
    missing = [field for field in ('name', 'description', 'price_vnd', 'stock') if getattr(draft, field) is None]
    labels = {'name': 'món hàng cần bán', 'description': 'thông tin mô tả', 'price_vnd': 'giá bán', 'stock': 'số lượng tồn kho'}
    platform = 'TikTok Shop' if 'tiktok.com' in payload.snapshot.url else 'Shopee'
    answer = copy.clarification or (
        f'Mình đã soạn bản nháp. Bạn kiểm tra rồi bấm **Điền vào form** trên {platform}; sản phẩm chưa được đăng.'
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
            except Exception as error:
                logger.warning('Browser inference failed: error_type=%s', type(error).__name__)
                return {'status': 'failed', 'reason': 'provider_unavailable', 'message': 'Chưa gọi được AI. Nội dung vẫn được giữ, bạn thử lại nhé.'}
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
