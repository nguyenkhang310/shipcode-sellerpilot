"""Use the local OpenCode server; never call its model gateway directly."""

import asyncio
import json
import logging
import re
from contextlib import suppress
from datetime import date

import httpx
from pydantic import ValidationError

from app.ai.contracts import (
    AIProviderError, ClassificationResult, ModelCommand, ParsedCommand, ProviderHealth,
)
from app.ai.advisor_contracts import AdviceExtraction

logger = logging.getLogger(__name__)
FREE_MODEL = "muse-spark-1.3-contributor-free"
SESSION_ID = re.compile(r"^ses_[a-zA-Z0-9_-]+$")


class OpenCodeClient:
    provider = "opencode"
    natural_responses = True
    prefer_model_intent = True

    def __init__(self, http: httpx.AsyncClient, model=FREE_MODEL, *, timeout=90):
        if model != FREE_MODEL:
            raise ValueError("Only the verified free Muse Spark model is allowed.")
        self.http = http
        self.model = model
        self.timeout = timeout
        self._generation_lock = asyncio.Lock()

    async def _free_model(self):
        result = await self.http.get("/provider", timeout=5)
        result.raise_for_status()
        for provider in result.json()["all"]:
            if provider["id"] == "opencode":
                model = provider.get("models", {}).get(self.model)
                if model:
                    cost = model.get("cost", {})
                    cache = cost.get("cache", {})
                    if (model.get("status") == "active"
                            and cost.get("input") == 0 and cost.get("output") == 0
                            and cache.get("read", 0) == 0 and cache.get("write", 0) == 0):
                        return model
        raise AIProviderError("free_model_unavailable")

    async def check_health(self):
        try:
            response = await self.http.get("/global/health", timeout=2)
            response.raise_for_status()
            if response.json().get("healthy") is not True:
                return ProviderHealth(availability="unavailable")
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
            "JSON Schema bắt buộc:\n"
            + json.dumps(ModelCommand.model_json_schema(), ensure_ascii=False)
        )
        answer = await self._ask("sellerpilot-classifier", prompt)
        try:
            parsed = ModelCommand.model_validate_json(answer)
            command = ParsedCommand.model_validate(parsed.model_dump())
        except (ValidationError, ValueError) as error:
            raise AIProviderError("invalid_response") from error
        return ClassificationResult(command=command, provider=self.provider, model=self.model)

    async def respond(self, message: str, *, history: list[dict], facts: dict):
        # Structured JSON preserves data boundaries. No customer/order PII is added here.
        context = {
            "history": [{"role": row["role"], "content": row["content"][:1600]}
                        for row in history[-24:]],
            "shop_facts": facts,
            "current_message": message,
        }
        return await self._ask("sellerpilot-chat", json.dumps(context, ensure_ascii=False, default=str))

    async def compose_listing(self, *, facts: dict, history: list[dict], images: list[dict]):
        # Local uploads are sent as data URLs, never as paths for OpenCode to read.
        model = await self._free_model()
        supports_images = model.get("capabilities", {}).get("input", {}).get("image", False)
        prompt = json.dumps({
            "known_product": facts,
            "history": history[-12:],
            "images_attached": bool(images and supports_images),
        }, ensure_ascii=False)
        return await self._ask("sellerpilot-listing", prompt,
                               files=images if supports_images else None)

    async def analyze_advice(self, message: str, *, history: list[dict], context: dict):
        prompt = json.dumps({'current_message': message, 'history': history[-16:], 'memory': context,
                             'json_schema': AdviceExtraction.model_json_schema()}, ensure_ascii=False)
        return await self._ask('sellerpilot-advisor', prompt)

    @staticmethod
    def _answer(payload):
        info = payload["info"]
        error = info.get("error")
        if error:
            code = error.get("data", {}).get("statusCode")
            raise AIProviderError("provider_rejected" if code in (401, 403, 429) else "provider_unavailable")
        if (info.get("role") != "assistant" or info.get("providerID") != "opencode"
                or info.get("modelID") != FREE_MODEL or info.get("finish") != "stop"
                or not info.get("time", {}).get("completed") or info.get("cost") != 0):
            raise AIProviderError("invalid_response")
        parts = payload["parts"]
        if any(part.get("type") == "tool" for part in parts):
            raise AIProviderError("tool_not_allowed")
        answer = "\n".join(part["text"] for part in parts if part.get("type") == "text").strip()
        if not answer or len(answer) > 12000:
            raise AIProviderError("invalid_response")
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
        session_id = None
        pending = None
        try:
            # Bound queueing + generation, not just the HTTP response wait.
            async with asyncio.timeout(self.timeout):
                async with self._generation_lock:
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
                    return self._answer(response.json())
        except AIProviderError:
            raise
        except (TimeoutError, httpx.TimeoutException) as error:
            raise AIProviderError("provider_timeout") from error
        except httpx.HTTPStatusError as error:
            reason = "provider_rejected" if error.response.status_code in (401, 403, 429) else "provider_unavailable"
            raise AIProviderError(reason) from error
        except httpx.HTTPError as error:
            raise AIProviderError("provider_unavailable") from error
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise AIProviderError("invalid_response") from error
        finally:
            if pending is not None:
                if not pending.done():
                    pending.cancel()
                with suppress(asyncio.CancelledError, httpx.HTTPError):
                    await pending
            if session_id:
                await self._cleanup(session_id)
