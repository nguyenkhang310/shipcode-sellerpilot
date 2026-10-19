"""Use the local OpenCode server; never call its model gateway directly."""

import asyncio
import json
import logging
import re
from contextlib import suppress
from datetime import date
from time import monotonic

import httpx
from pydantic import ValidationError

from app.ai.contracts import (
    AIProviderError, ClassificationResult, ModelCommand, ParsedCommand, ProviderHealth,
)
from app.ai.advisor_contracts import AdviceExtraction
from app.ai.listing_contracts import ListingCopy, listing_validation_context
from app.ai.context import bounded_history
from app.ai.money import money_hints

logger = logging.getLogger(__name__)
FREE_MODEL = "glm-5.3-flash-free"
ACCESS_RECHECK_SECONDS = 60
SESSION_ID = re.compile(r"^ses_[a-zA-Z0-9_-]+$")


class OpenCodeClient:
    provider = "opencode"
    natural_responses = True
    prefer_model_intent = True

    def __init__(self, http: httpx.AsyncClient, model=FREE_MODEL, *, timeout=90):
        if model != FREE_MODEL:
            raise ValueError(f"Only opencode/{FREE_MODEL} is allowed; paid fallback is disabled.")
        self.http = http
        self.model = model
        self.timeout = timeout
        self._generation_lock = asyncio.Lock()
        self._access_restricted = False
        self._access_retry_at = 0.0

    def _check_access(self):
        if self._access_restricted and monotonic() < self._access_retry_at:
            raise AIProviderError("free_tier_restricted", stage="access_cooldown")

    async def _free_model(self):
        result = await self.http.get("/provider", timeout=5)
        result.raise_for_status()
        for provider in result.json()["all"]:
            if provider["id"] == "opencode":
                model = provider.get("models", {}).get(self.model)
                if model:
                    cost = model.get("cost", {})
                    cache = cost.get("cache", {})
                    prices = (cost.get("input"), cost.get("output"),
                              cache.get("read"), cache.get("write"))
                    if (model.get("status") == "active"
                            and all(type(price) in (int, float) and price == 0 for price in prices)):
                        return model
        raise AIProviderError("free_model_unavailable")

    async def check_health(self):
        try:
            response = await self.http.get("/global/health", timeout=2)
            response.raise_for_status()
            if response.json().get("healthy") is not True:
                return ProviderHealth(availability="unavailable")
            # A listed free model is not proof of inference access. A known
            # gateway denial stays degraded until a real generation succeeds.
            if self._access_restricted:
                return ProviderHealth(availability="available", model_available=False)
            try:
                await self._free_model()
            except AIProviderError:
                return ProviderHealth(availability="available", model_available=False)
            return ProviderHealth(availability="available", model_available=True)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
            return ProviderHealth(availability="unavailable")

    async def classify(self, message: str, *, today: date):
        prompt = (
            f"Ngày hiện tại của shop: {today.isoformat()}\n"
            f"<USER_MESSAGE>\n{message}\n</USER_MESSAGE>\n"
            + "Quy đổi tiền từ lời người bán (không phải dữ liệu giá mặc định):\n"
            + json.dumps(money_hints(message), ensure_ascii=False) + '\n'
            + "JSON Schema bắt buộc:\n"
            + json.dumps(ModelCommand.model_json_schema(), ensure_ascii=False)
        )
        parsed = await self._structured("sellerpilot-classifier", prompt, ModelCommand)
        try:
            command = ParsedCommand.model_validate(parsed.model_dump())
        except ValidationError as error:
            raise AIProviderError('invalid_response', stage='command_parameters') from error
        return ClassificationResult(command=command, provider=self.provider, model=self.model)

    async def respond(self, message: str, *, history: list[dict], facts: dict):
        # Structured JSON preserves data boundaries. No customer/order PII is added here.
        context = {
            "history": bounded_history(history),
            "shop_facts": facts,
            "current_message": message,
            "money_interpretations": money_hints(message),
        }
        return await self._ask("sellerpilot-chat", json.dumps(context, ensure_ascii=False, default=str))

    async def compose_listing(self, *, facts: dict, history: list[dict], images: list[dict]):
        # Local uploads are sent as data URLs, never as paths for OpenCode to read.
        self._check_access()
        model = await self._free_model()
        supports_images = model.get("capabilities", {}).get("input", {}).get("image", False)
        prompt = json.dumps({
            "known_product": facts,
            "history": bounded_history(history, turns=12),
            "images_attached": bool(images and supports_images),
        }, ensure_ascii=False)
        parsed = await self._structured("sellerpilot-listing", prompt, ListingCopy,
                                        files=images if supports_images else None,
                                        validation_context=listing_validation_context(facts, history))
        return parsed.model_dump_json()

    async def analyze_advice(self, message: str, *, history: list[dict], context: dict):
        prompt = json.dumps({'current_message': message, 'history': bounded_history(history, turns=16), 'memory': context,
                             'money_interpretations': money_hints(message),
                             'json_schema': AdviceExtraction.model_json_schema()}, ensure_ascii=False)
        parsed = await self._structured('sellerpilot-advisor', prompt, AdviceExtraction)
        return parsed.model_dump_json()

    async def _structured(self, agent, prompt, schema, *, files=None, validation_context=None):
        """One format correction within the same total deadline, never a shop write."""
        try:
            async with asyncio.timeout(self.timeout):
                for attempt in range(2):
                    answer = await self._ask(agent, prompt, files=files)
                    fenced = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', answer.strip(), re.I | re.S)
                    try:
                        return schema.model_validate_json(fenced.group(1) if fenced else answer, context=validation_context)
                    except ValidationError as error:
                        if attempt:
                            raise AIProviderError('invalid_response', stage='structured_output') from error
                        # Field paths/error codes only: do not repeat or log the
                        # invalid response, seller text, image URLs or secrets.
                        issues = [{'field': '.'.join(map(str, item['loc'])), 'type': item['type'], 'rule': item['msg']}
                                  for item in error.errors()[:8]]
                        logger.warning('OpenCode structured format correction: agent=%s', agent)
                        prompt += '\nFORMAT_CORRECTION: ' + json.dumps({
                            'issues': issues, 'required_schema': schema.model_json_schema(),
                            'instruction': 'Trả một JSON instance đúng schema, không trả JSON Schema, không Markdown. Không tạo dữ kiện còn thiếu. Bỏ mọi tuyên bố mới/nguyên tem/chính hãng/bảo hành chưa có lời chủ shop xác nhận; vẫn tự soạn nội dung từ dữ kiện còn lại.',
                        }, ensure_ascii=False)
        except TimeoutError as error:
            raise AIProviderError('provider_timeout', stage='structured_deadline') from error

    @staticmethod
    def _rejection_reason(status, message=""):
        if status == 429:
            return "provider_rate_limited"
        if status == 403 and ("FreeTierError" in message or "free tier" in message.lower()):
            return "free_tier_restricted"
        return "provider_rejected" if status in (401, 403) else "provider_unavailable"

    @staticmethod
    def _answer(payload):
        info = payload["info"]
        error = info.get("error")
        if error:
            code = error.get("data", {}).get("statusCode")
            raise AIProviderError(OpenCodeClient._rejection_reason(code, str(error.get("data", {}).get("message", ""))),
                stage='model_gateway', retryable=code in (500, 502, 503, 504))
        # Model identity and zero cost are mandatory even when retrying. Never
        # accept a paid/wrong model or a tool result as an ordinary chat reply.
        if (info.get("role") != "assistant" or info.get("providerID") != "opencode"
                or info.get("modelID") != FREE_MODEL or isinstance(info.get('cost'), bool)
                or info.get("cost") != 0):
            raise AIProviderError("invalid_response", stage='model_identity_or_cost')
        parts = payload["parts"]
        if any(part.get("type") == "tool" for part in parts):
            raise AIProviderError("tool_not_allowed", stage='tool_result')
        if info.get("finish") != "stop" or not info.get("time", {}).get("completed"):
            logger.warning('OpenCode incomplete reply: finish=%s', info.get('finish'))
            raise AIProviderError("invalid_response", stage='incomplete_reply', retryable=True)
        answer = "\n".join(part["text"] for part in parts if part.get("type") == "text").strip()
        if not answer or len(answer) > 12000:
            raise AIProviderError("invalid_response", stage='empty_or_oversized_reply', retryable=True)
        return answer

    async def _cleanup(self, session_id):
        # Abort also clears a pending permission. Never approve OpenCode tools.
        for method, path in (("POST", f"/session/{session_id}/abort"),
                             ("DELETE", f"/session/{session_id}")):
            with suppress(httpx.HTTPError):
                response = await self.http.request(method, path, timeout=2)
                if response.status_code >= 400:
                    logger.warning("OpenCode session cleanup failed (%s)", response.status_code)

    async def _ask(self, agent: str, prompt: str, *, files: list[dict] | None = None):
        self._check_access()
        try:
            # One bounded retry for transient gateway failures or incomplete
            # generations. Each attempt has its own session and cleanup. These
            # agents cannot perform shop writes, so this never repeats an action.
            async with asyncio.timeout(self.timeout):
                for attempt in range(2):
                    try:
                        return await self._ask_once(agent, prompt, files=files)
                    except AIProviderError as error:
                        logger.warning('OpenCode generation rejected: agent=%s reason=%s stage=%s attempt=%s',
                                       agent, error.reason, error.stage or 'unknown', attempt + 1)
                        if attempt or not error.retryable:
                            raise
                        await asyncio.sleep(0.25)
        except TimeoutError as error:
            raise AIProviderError('provider_timeout', stage='generation_deadline') from error

    async def _ask_once(self, agent: str, prompt: str, *, files: list[dict] | None = None):
        session_id = None
        pending = None
        try:
            # Bound queueing + generation, not just the HTTP response wait.
            async with asyncio.timeout(self.timeout):
                async with self._generation_lock:
                    self._check_access()
                    await self._free_model()
                    created = await self.http.post("/session", json={
                        "title": "SellerPilot", "agent": agent,
                        "model": {"providerID": "opencode", "id": self.model},
                        "permission": [{"permission": "*", "pattern": "*", "action": "ask"}],
                    }, timeout=5)
                    created.raise_for_status()
                    candidate = created.json()["id"]
                    if not isinstance(candidate, str) or not SESSION_ID.fullmatch(candidate):
                        raise AIProviderError("invalid_response")
                    session_id = candidate
                    pending = asyncio.create_task(self.http.post(f"/session/{session_id}/message", json={
                        "model": {"providerID": "opencode", "modelID": self.model},
                        "agent": agent, "parts": [{"type": "text", "text": prompt}, *(files or [])],
                    }, timeout=self.timeout))
                    while not pending.done():
                        await asyncio.wait({pending}, timeout=0.4)
                        if pending.done():
                            break
                        permissions = await self.http.get("/permission", timeout=2)
                        permissions.raise_for_status()
                        if any(row.get("sessionID") == session_id for row in permissions.json()):
                            raise AIProviderError("tool_not_allowed")
                    response = await pending
                    response.raise_for_status()
                    answer = self._answer(response.json())
                    self._access_restricted = False
                    self._access_retry_at = 0.0
                    return answer
        except AIProviderError as error:
            if error.reason == "free_tier_restricted" and error.stage != "access_cooldown":
                self._access_restricted = True
                self._access_retry_at = monotonic() + ACCESS_RECHECK_SECONDS
            raise
        except (TimeoutError, httpx.TimeoutException) as error:
            raise AIProviderError("provider_timeout", stage='http_deadline') from error
        except httpx.HTTPStatusError as error:
            reason = self._rejection_reason(error.response.status_code, error.response.text)
            if reason == "free_tier_restricted":
                self._access_restricted = True
                self._access_retry_at = monotonic() + ACCESS_RECHECK_SECONDS
            raise AIProviderError(reason, stage='http_status',
                retryable=error.response.status_code in (500, 502, 503, 504)) from error
        except httpx.HTTPError as error:
            raise AIProviderError("provider_unavailable", stage='http_connection', retryable=True) from error
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise AIProviderError("invalid_response", stage='response_envelope', retryable=True) from error
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                with suppress(asyncio.CancelledError, httpx.HTTPError):
                    await pending
            if session_id:
                await self._cleanup(session_id)
