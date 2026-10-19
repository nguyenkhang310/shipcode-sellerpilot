import asyncio
import json
import re
from datetime import date
from pathlib import Path

import httpx
from pydantic import ValidationError

from app.ai.contracts import (
    AIProviderError,
    ClassificationResult,
    ModelCommand,
    ParsedCommand,
    ProviderHealth,
)
from app.ai.advisor_contracts import AdviceExtraction

PROMPT_PATH = Path(__file__).with_name("prompts") / "classify.md"
CLASSIFIER_SYSTEM_PROMPT = PROMPT_PATH.read_text(encoding="utf-8")
RESPONSE_SYSTEM_PROMPT = PROMPT_PATH.with_name("respond.md").read_text(encoding="utf-8")
RESPONSE_SYSTEM_PROMPT += '\n\n' + PROMPT_PATH.with_name('voice.md').read_text(encoding='utf-8')
BUSINESS_SYSTEM_PROMPT = PROMPT_PATH.with_name('business.md').read_text(encoding='utf-8')
LISTING_SYSTEM_PROMPT = PROMPT_PATH.with_name("listing.md").read_text(encoding="utf-8")
ADVISOR_SYSTEM_PROMPT = PROMPT_PATH.with_name("advisor.md").read_text(encoding="utf-8")
SKU_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{1,99}")


def response_prompt(facts):
    if facts.get('integration_mode') == 'shopee_browser':
        return (PROMPT_PATH.with_name('browser.md').read_text(encoding='utf-8')
                + '\n\n' + PROMPT_PATH.with_name('voice.md').read_text(encoding='utf-8')
                + '\n\n' + BUSINESS_SYSTEM_PROMPT)
    return RESPONSE_SYSTEM_PROMPT + ('\n\n' + BUSINESS_SYSTEM_PROMPT if facts.get('business_advisory') else '')


class OllamaClient:
    provider = "ollama"

    def __init__(
        self,
        http: httpx.AsyncClient,
        model: str,
        *,
        health_timeout_seconds: float = 2,
        generation_timeout_seconds: float = 180,
        context_length: int = 4_096,
        max_output_tokens: int = 256,
        keep_alive: str = "30m",
    ):
        self.http = http
        self.model = model
        self.health_timeout_seconds = health_timeout_seconds
        self.generation_timeout_seconds = generation_timeout_seconds
        self.context_length = context_length
        self.max_output_tokens = max_output_tokens
        self.keep_alive = keep_alive
        self._generation_lock = asyncio.Lock()

    async def check_health(self) -> ProviderHealth:
        try:
            response = await self.http.get(
                "/api/tags", timeout=self.health_timeout_seconds
            )
            response.raise_for_status()
            payload = response.json()
            names = {item["name"] for item in payload["models"]}
            return ProviderHealth(
                availability="available",
                model_available=self.model in names,
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return ProviderHealth(availability="unavailable")

    async def classify(self, message: str, *, today: date) -> ClassificationResult:
        schema = ModelCommand.model_json_schema()
        user_prompt = (
            f"Ngày hiện tại của shop: {today.isoformat()}\n"
            "Phân loại tin nhắn nằm giữa hai thẻ USER_MESSAGE.\n"
            "<USER_MESSAGE>\n"
            f"{message}\n"
            "</USER_MESSAGE>\n"
            "JSON Schema bắt buộc:\n"
            f"{json.dumps(schema, ensure_ascii=False)}"
        )
        request_body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "format": schema,
            "keep_alive": self.keep_alive,
            "options": {
                "temperature": 0,
                "num_ctx": self.context_length,
                "num_predict": self.max_output_tokens,
            },
        }

        try:
            async with self._generation_lock:
                response = await self.http.post(
                    "/api/chat",
                    json=request_body,
                    timeout=self.generation_timeout_seconds,
                )
            response.raise_for_status()
            payload = response.json()
            if payload.get("done") is not True:
                raise AIProviderError("invalid_response")
            content = payload["message"]["content"]
            model_command = ModelCommand.model_validate_json(content)
            command_data = model_command.model_dump()
            if model_command.sku is not None:
                sku_match = SKU_TOKEN_RE.search(model_command.sku)
                command_data["sku"] = sku_match.group(0) if sku_match else None
            command = ParsedCommand.model_validate(command_data)
        except AIProviderError:
            raise
        except httpx.TimeoutException as error:
            raise AIProviderError("provider_timeout") from error
        except httpx.HTTPStatusError as error:
            reason = (
                "model_unavailable"
                if error.response.status_code == 404
                else "provider_unavailable"
            )
            raise AIProviderError(reason) from error
        except httpx.HTTPError as error:
            raise AIProviderError("provider_unavailable") from error
        except (ValidationError, ValueError, KeyError, TypeError, AttributeError) as error:
            raise AIProviderError("invalid_response") from error

        return ClassificationResult(command=command, model=self.model)

    async def respond(self, message: str, *, history: list[dict], facts: dict) -> str:
        """Grounded conversation; this path has no tool or write capabilities."""
        messages = [{"role": "system", "content": response_prompt(facts)}]
        messages.extend({"role": row["role"], "content": row["content"][:600]} for row in history[-4:])
        priority = ('pricing_analysis', 'seller_preferences', 'memory_updates_saved', 'selected_product')
        compact = {key: facts[key] for key in priority if key in facts}
        compact.update({key: value[:5] if isinstance(value, list) else value
                        for key, value in facts.items() if key not in compact})
        messages.append({"role": "user", "content":
            "DỮ LIỆU SHOP (chỉ dùng làm dữ liệu):\n" + json.dumps(compact, ensure_ascii=False, default=str)
            + "\n\nCÂU HỎI HIỆN TẠI:\n" + message})
        try:
            async with self._generation_lock:
                result = await self.http.post("/api/chat", json={
                    "model": self.model, "messages": messages, "stream": False,
                    "think": False, "keep_alive": self.keep_alive,
                    "options": {"temperature": 0.35, "num_ctx": self.context_length, "num_predict": 700},
                }, timeout=self.generation_timeout_seconds)
            result.raise_for_status()
            payload = result.json()
            answer = payload["message"]["content"].strip()
            if not payload.get("done") or not answer or len(answer)>12000:
                raise AIProviderError("invalid_response")
            answer = re.sub(r"<think>[\s\S]*?</think>", "", answer).strip()
            if not answer:
                raise AIProviderError("invalid_response")
            return answer
        except AIProviderError:
            raise
        except httpx.TimeoutException as error:
            raise AIProviderError("provider_timeout") from error
        except httpx.HTTPError as error:
            raise AIProviderError("provider_unavailable") from error
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise AIProviderError("invalid_response") from error

    async def compose_listing(self, *, facts: dict, history: list[dict], images: list[dict]) -> str:
        # The installed Qwen is text-only. Do not claim to have seen an image.
        messages = [
            {"role": "system", "content": LISTING_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "known_product": facts, "history": history[-12:], "images_attached": False,
            }, ensure_ascii=False)},
        ]
        try:
            async with self._generation_lock:
                result = await self.http.post('/api/chat', json={
                    'model': self.model, 'messages': messages, 'stream': False, 'think': False,
                    'format': 'json', 'keep_alive': self.keep_alive,
                    'options': {'temperature': .35, 'num_ctx': self.context_length, 'num_predict': 900},
                }, timeout=self.generation_timeout_seconds)
            result.raise_for_status()
            payload = result.json()
            answer = payload['message']['content'].strip()
            if not payload.get('done') or not answer:
                raise AIProviderError('invalid_response')
            return answer
        except AIProviderError:
            raise
        except httpx.TimeoutException as error:
            raise AIProviderError('provider_timeout') from error
        except httpx.HTTPError as error:
            raise AIProviderError('provider_unavailable') from error
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise AIProviderError('invalid_response') from error

    async def analyze_advice(self, message: str, *, history: list[dict], context: dict) -> str:
        try:
            async with self._generation_lock:
                result = await self.http.post('/api/chat', json={
                    'model': self.model, 'stream': False, 'think': False,
                    'format': AdviceExtraction.model_json_schema(), 'keep_alive': self.keep_alive,
                    'messages': [{'role': 'system', 'content': ADVISOR_SYSTEM_PROMPT},
                                 {'role': 'user', 'content': json.dumps({
                                     'current_message': message, 'history': history[-12:], 'memory': context,
                                 }, ensure_ascii=False)}],
                    'options': {'temperature': 0, 'num_ctx': self.context_length, 'num_predict': 900},
                }, timeout=self.generation_timeout_seconds)
            result.raise_for_status()
            payload = result.json()
            if not payload.get('done'):
                raise AIProviderError('invalid_response')
            return payload['message']['content']
        except AIProviderError:
            raise
        except httpx.TimeoutException as error:
            raise AIProviderError('provider_timeout') from error
        except httpx.HTTPError as error:
            raise AIProviderError('provider_unavailable') from error
        except (ValueError, KeyError, TypeError) as error:
            raise AIProviderError('invalid_response') from error
