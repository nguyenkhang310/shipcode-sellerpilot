"""Direct Gemini Developer API with optional, explicitly configured Groq backup.

Only inference is sent to providers. Shop reads, calculations, validation and
confirmed writes stay in SellerPilot. No CLI, filesystem tools or API-key URL.
"""
import asyncio
import base64
import binascii
import json
import logging
import re
from contextvars import ContextVar
from datetime import date
from time import monotonic, perf_counter

import httpx
from pydantic import SecretStr, ValidationError

from app.ai.advisor_contracts import AdviceExtraction, AdvicePreparation
from app.ai.client import ADVISOR_SYSTEM_PROMPT, CLASSIFIER_SYSTEM_PROMPT, LISTING_SYSTEM_PROMPT, response_prompt
from app.ai.context import bounded_history
from app.ai.contracts import AIProviderError, ClassificationResult, ModelCommand, ParsedCommand, ProviderHealth
from app.ai.listing_contracts import ListingCopy, listing_validation_context
from app.ai.key_pool import GeminiKeyPool
from app.ai.money import money_hints, plain
from app.ai.text import assistant_text
from app.ai.edit_contracts import ProductEditCopy
from pathlib import Path

logger = logging.getLogger(__name__)
MODEL = 'gemini-3.5-flash-lite'
GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/'
GROQ_URL = 'https://api.groq.com/openai/v1/'
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 18 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
EDIT_SYSTEM_PROMPT=Path(__file__).with_name('prompts').joinpath('edit.md').read_text(encoding='utf-8')


def image_parts(images):
    if len(images) > 6:
        raise AIProviderError('invalid_response', stage='image_count')
    parts = []
    for image in images:
        mime, url = image.get('mime'), image.get('url')
        if mime not in ('image/jpeg', 'image/png', 'image/webp') or not isinstance(url, str) or not url.startswith(f'data:{mime};base64,'):
            raise AIProviderError('invalid_response', stage='image_format')
        encoded = url.split(',', 1)[1]
        if len(encoded) > ((MAX_IMAGE_BYTES + 2) // 3) * 4:
            raise AIProviderError('invalid_response', stage='image_size')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise AIProviderError('invalid_response', stage='image_encoding') from error
        valid = (content.startswith(b'\x89PNG\r\n\x1a\n') if mime == 'image/png' else
                 content.startswith(b'\xff\xd8\xff') if mime == 'image/jpeg' else
                 content.startswith(b'RIFF') and content[8:12] == b'WEBP')
        if not valid or not content or len(content) > MAX_IMAGE_BYTES:
            raise AIProviderError('invalid_response', stage='image_content')
        parts.append({'inlineData': {'mimeType': mime, 'data': encoded}})
    return parts


def key_value(key):
    return (key.get_secret_value() if isinstance(key, SecretStr) else key or '').strip()


def groq_strict_schema(schema):
    """Require every declared field, keeping nullable values and validation rules.

    Groq strict decoding requires closed objects and all properties in required.
    Work on a copy so Gemini and local Pydantic contracts remain unchanged.
    """
    def visit(value):
        if isinstance(value, list):
            return [visit(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: visit(item) for key, item in value.items() if key != 'default'}
        if result.get('type') == 'object' and 'properties' in result:
            result['required'] = list(result['properties'])
            result['additionalProperties'] = False
        return result
    return visit(schema)


async def post_json(http, url, headers, body, timeout):
    if len(json.dumps(body, ensure_ascii=False).encode()) > MAX_REQUEST_BYTES:
        raise AIProviderError('invalid_response', stage='request_size')
    try:
        response = await http.post(url, headers=headers, json=body, timeout=timeout, follow_redirects=False)
    except httpx.TimeoutException as error:
        raise AIProviderError('provider_timeout', stage='api_network', retryable=True) from error
    except httpx.HTTPError as error:
        raise AIProviderError('provider_unavailable', stage='api_network', retryable=True) from error
    code = response.status_code
    if code != 200:
        reason = ('provider_rate_limited' if code == 429 else 'model_unavailable' if code == 404 else
                  'provider_rejected' if code in (400, 401, 403) else 'provider_unavailable')
        error = AIProviderError(reason, stage='api_http', retryable=code == 429 or code >= 500)
        error.http_status = code
        if code == 429:
            try:
                error.retry_after_seconds = max(1, min(86400, float(response.headers.get('retry-after', '60'))))
            except ValueError:
                error.retry_after_seconds = 60
        raise error
    try:
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ValueError('response size')
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError('response shape')
        return result
    except (ValueError, TypeError) as error:
        raise AIProviderError('invalid_response', stage='api_envelope') from error


class GroqBackup:
    """One backup attempt; never truncate the gallery to fit a model."""
    provider = 'groq'

    def __init__(self, http, api_key, model='qwen/qwen3.8-27b', *, max_tokens=2048):
        if model not in {'qwen/qwen3.8-27b', 'openai/gpt-oss-120b'}:
            raise ValueError('Unsupported Groq backup model')
        self.http, self._key, self.model = http, key_value(api_key), model
        self.max_tokens, self._cooldown_until = max_tokens, 0.0

    def supports(self, count):
        return bool(self._key) and (count <= 3 if self.model == 'qwen/qwen3.8-27b' else count == 0)

    async def generate(self, system, payload, images, schema, *, timeout, max_tokens=None):
        if not self.supports(len(images)):
            raise AIProviderError('model_unavailable', stage='backup_image_limit')
        if monotonic() < self._cooldown_until:
            raise AIProviderError('provider_rate_limited', stage='backup_cooldown')
        content = [{'type': 'text', 'text': json.dumps(payload, ensure_ascii=False, default=str)}]
        for part in images:
            data = part['inlineData']
            content.append({'type': 'image_url', 'image_url': {'url': f"data:{data['mimeType']};base64,{data['data']}"}})
        body = {'model': self.model, 'messages': [{'role': 'system', 'content': system},
                {'role': 'user', 'content': content}], 'stream': False,
                'max_completion_tokens': max_tokens or self.max_tokens,
                'reasoning_effort': 'none' if self.model.startswith('qwen/') and not schema else 'low'}
        if self.model.startswith('qwen/'):
            body['reasoning_format'] = 'hidden'
        if schema:
            # Structured work needs more care than a short chat. Strict decoding
            # prevents omitted fields; backend evidence checks still apply.
            body['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': 'sellerpilot', 'strict': True, 'schema': groq_strict_schema(schema)}}
        try:
            result = await post_json(self.http, GROQ_URL + 'chat/completions',
                {'Authorization': 'Bearer ' + self._key}, body, timeout)
            choices = result['choices']
            if not isinstance(choices, list) or len(choices) != 1 or choices[0].get('finish_reason') != 'stop':
                raise ValueError('unfinished backup response')
            message = choices[0]['message']
            if message.get('tool_calls') or message.get('function_call'):
                raise AIProviderError('tool_not_allowed', stage='backup_tools')
            text = message['content']
            if not isinstance(text, str) or not text.strip() or len(text) > 16000:
                raise ValueError('backup content')
            return text.strip()
        except AIProviderError as error:
            if error.reason == 'provider_rate_limited':
                self._cooldown_until = monotonic() + getattr(error, 'retry_after_seconds', 60)
            raise
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise AIProviderError('invalid_response', stage='backup_response') from error


class GeminiClient:
    provider = 'gemini'
    natural_responses = True
    prefer_model_intent = True
    prefer_direct_facts = True

    def __init__(self, http, api_key, model=MODEL, *, timeout=45, max_tokens=2048, advice_max_tokens=4096, backup=None, credentials=None, project='', rpm=None):
        if model not in {MODEL, 'gemini-3.8-flash'}:
            raise ValueError('Unsupported Gemini model')
        self.http, self.model = http, model
        self.keys = GeminiKeyPool(credentials if credentials is not None else [(api_key, project)],
                                 rpm=rpm or (15 if model == MODEL else 5))
        self.timeout, self.max_tokens, self.backup = timeout, max_tokens, backup
        self.advice_max_tokens = advice_max_tokens
        self._health = ProviderHealth(availability='unavailable')
        self._health_until = 0.0
        self._response_source = ContextVar('gemini_response_source', default=(self.provider, self.model))

    @property
    def response_provider(self):
        return self._response_source.get()[0]

    @property
    def response_model(self):
        return self._response_source.get()[1]

    async def check_health(self):
        if self.keys.available() is None:
            return ProviderHealth(availability='unavailable')
        if monotonic() < self._health_until:
            return self._health
        try:
            checked = set()
            self._health = ProviderHealth(availability='unavailable')
            while credential := self.keys.available(excluded=checked):
                checked.add(credential.slot)
                response = await self.http.get(GEMINI_URL + self.model,
                    headers={'x-goog-api-key': credential.secret}, timeout=5, follow_redirects=False)
                if response.status_code in (401, 403):
                    self.keys.disable(credential)
                    continue
                data = response.json() if response.status_code == 200 else {}
                ready = (data.get('name') == 'models/' + self.model
                         and 'generateContent' in data.get('supportedGenerationMethods', []))
                self._health = ProviderHealth(availability='available' if ready else 'unavailable', model_available=ready)
                break
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            self._health = ProviderHealth(availability='unavailable')
        self._health_until = monotonic() + 30
        return self._health

    async def classify(self, message: str, *, today: date):
        command = await self._structured(CLASSIFIER_SYSTEM_PROMPT, {
            'today': today.isoformat(), 'current_message': message, 'money_interpretations': money_hints(message)}, ModelCommand)
        try:
            parsed = ParsedCommand.model_validate(command.model_dump())
        except ValidationError as error:
            raise AIProviderError('invalid_response', stage='command_parameters') from error
        return ClassificationResult(command=parsed, provider=self.response_provider, model=self.response_model)

    async def respond(self, message, *, history, facts):
        try:
            async with asyncio.timeout(self.timeout):
                text = await self._generate(response_prompt(facts), {
                    'current_message': message, 'history': bounded_history(history),
                    'shop_facts': facts, 'money_interpretations': money_hints(message)})
                return assistant_text(text)
        except TimeoutError as error:
            raise AIProviderError('provider_timeout', stage='api_deadline') from error

    async def compose_listing(self, *, facts, history, images):
        result = await self._structured(LISTING_SYSTEM_PROMPT, {
            'known_product': facts, 'history': bounded_history(history, turns=12),
            'images_attached': bool(images), 'image_count': len(images)}, ListingCopy,
            images=images, context=listing_validation_context(facts, history))
        return result.model_dump_json()

    async def analyze_advice(self, message, *, history, context):
        result = await self._structured(ADVISOR_SYSTEM_PROMPT, {
            'current_message': message, 'history': bounded_history(history, turns=16),
            'memory': context, 'money_interpretations': money_hints(message)}, AdviceExtraction)
        return result.model_dump_json()

    async def compose_product_edit(self,message,*,history,product):
        text=plain(message)
        rewrite=bool(re.search(r'toi uu|viet lai|soan lai|tu viet|hay hon',text))
        fields=[field for field,pattern in (('name',r'tieu de|ten san pham|doi ten|sua ten'),('description',r'mo ta'))
                if rewrite and re.search(pattern,text)]
        return await self._structured(EDIT_SYSTEM_PROMPT,{
            'current_message':message,'history':bounded_history(history,turns=8),
            'current_product':product,'fields_to_rewrite':fields,'money_interpretations':money_hints(message)},ProductEditCopy,
            context={'rewrite_fields':fields})

    async def prepare_advice(self, message, *, history, context, facts):
        system = (response_prompt(facts) + '\n\nQUY TẮC TRÍCH BỐI CẢNH:\n' + ADVISOR_SYSTEM_PROMPT
            + '\nTrả JSON theo schema: extraction là phần đọc hiểu; answer là văn bản trả lời tiếng Việt dựa '
            'trên shop_facts. Không lồng JSON vào answer. Nếu cần tính lợi nhuận, lưu thông tin mới hoặc tra '
            'sản phẩm cụ thể, để answer=null để backend kiểm tra trước. Không nói đã lưu hay đã thay đổi shop.')
        return await self._structured(system, {'current_message': message,
            'history': bounded_history(history, turns=16), 'memory': context,
            'shop_facts': facts, 'money_interpretations': money_hints(message)}, AdvicePreparation)

    async def _structured(self, system, payload, schema, *, images=None, context=None):
        payload = dict(payload)
        try:
            async with asyncio.timeout(self.timeout):
                for attempt in range(2):
                    text = await self._generate(system, payload, images=images, schema=schema.model_json_schema())
                    fenced = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', text.strip(), re.I)
                    try:
                        return schema.model_validate_json(fenced.group(1) if fenced else text, context=context)
                    except ValidationError as error:
                        if attempt:
                            raise AIProviderError('invalid_response', stage='structured_output') from error
                        payload['format_correction'] = [{'field': '.'.join(map(str, item['loc'])),
                            'type': item['type'], 'rule': item['msg']} for item in error.errors()[:8]]
        except TimeoutError as error:
            raise AIProviderError('provider_timeout', stage='structured_deadline') from error

    async def _generate(self, system, payload, *, images=None, schema=None):
        started = perf_counter()
        parts = image_parts(images or [])
        advice = bool(payload.get('shop_facts', {}).get('business_advisory'))
        output_tokens = self.advice_max_tokens if advice else self.max_tokens
        can_backup = self.backup is not None and self.backup.supports(len(parts))
        try:
            if not self.keys.configured:
                raise AIProviderError('provider_unavailable', stage='api_key_missing')
            try:
                config = {'maxOutputTokens': output_tokens,
                    'thinkingConfig': {'includeThoughts': False,
                        'thinkingLevel': 'MINIMAL' if self.model == MODEL else 'LOW'}}
                if schema:
                    config['responseFormat'] = {'text': {'mimeType': 'APPLICATION_JSON', 'schema': schema}}
                body = {'systemInstruction': {'parts': [{'text': system}]},
                    'contents': [{'role': 'user', 'parts': [{'text': json.dumps(payload, ensure_ascii=False, default=str)}, *parts]}],
                    'generationConfig': config}
                data = await self._gemini_request(body, can_backup=can_backup, started=started)
                if data.get('promptFeedback', {}).get('blockReason'):
                    raise AIProviderError('provider_rejected', stage='api_content_blocked')
                candidates = data.get('candidates')
                if not isinstance(candidates, list) or len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
                    raise AIProviderError('invalid_response', stage='api_unfinished')
                output = candidates[0]['content']['parts']
                if any('functionCall' in part or 'executableCode' in part for part in output):
                    raise AIProviderError('tool_not_allowed', stage='api_tools')
                text = ''.join(part.get('text', '') for part in output if part.get('thought') is not True)
                if not text.strip() or len(text) > 16000:
                    raise AIProviderError('invalid_response', stage='api_content')
                self._response_source.set((self.provider, self.model))
                self._health = ProviderHealth(availability='available', model_available=True)
                self._health_until = monotonic() + 30
                return text.strip()
            except AIProviderError as error:
                self._health = ProviderHealth(availability='unavailable')
                self._health_until = monotonic() + 30
                if not error.retryable or not can_backup:
                    raise
                logger.warning('Gemini using configured Groq backup: reason=%s model=%s images=%s',
                               error.reason, self.backup.model, len(parts))
                remaining = self.timeout - (perf_counter() - started)
                if remaining <= 0:
                    raise
                text = await self.backup.generate(system, payload, parts, schema, timeout=min(20, remaining),
                                                  max_tokens=output_tokens)
                self._response_source.set((self.backup.provider, self.backup.model))
                return text
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise AIProviderError('invalid_response', stage='api_protocol') from error
        finally:
            logger.info('Gemini API timing: model=%s total_ms=%s images=%s', self.model,
                        round((perf_counter() - started) * 1000), len(parts))

    async def _gemini_request(self, body, *, can_backup, started):
        tried = set()
        last_error = None
        while credential := self.keys.available(excluded=tried, reserve=True):
            tried.add(credential.slot)
            remaining = self.timeout - (perf_counter() - started)
            if remaining <= 0:
                raise AIProviderError('provider_timeout', stage='api_deadline', retryable=True)
            try:
                # Extra Gemini credentials are for quota/auth failover. A slow but valid
                # image request cannot safely be replayed with another key, so keep the
                # full request deadline instead of shortening every multi-key call to 15s.
                # Reserve a short window only when a configured backup can handle the call.
                timeout = min(15, remaining) if can_backup else remaining
                return await post_json(self.http, GEMINI_URL + self.model + ':generateContent',
                    {'x-goog-api-key': credential.secret}, body, timeout)
            except AIProviderError as error:
                if error.reason == 'provider_rate_limited':
                    self.keys.rate_limited(credential, getattr(error, 'retry_after_seconds', 60))
                elif error.reason == 'provider_rejected' and error.stage == 'api_http':
                    # Only authentication/authorization errors are key-specific.
                    # A malformed request must not spend requests on every key.
                    if getattr(error, 'http_status', None) not in (401, 403):
                        raise
                    self.keys.disable(credential)
                else:
                    raise
                last_error = error
                logger.warning('Gemini key unavailable: slot=%s reason=%s', credential.slot, error.reason)
        if last_error:
            raise last_error
        if all(credential.disabled for credential in self.keys.credentials):
            raise AIProviderError('provider_rejected', stage='api_keys_rejected')
        raise AIProviderError('provider_rate_limited', stage='api_cooldown', retryable=True)
