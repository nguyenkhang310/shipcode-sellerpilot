"""Provider lifecycle. OpenCode is a private, managed local child process."""

import asyncio
import json
import logging
import os
import re
import secrets
import shutil
import signal
import socket
import tempfile
from contextlib import AsyncExitStack, asynccontextmanager

import httpx

from app.ai.client import CLASSIFIER_SYSTEM_PROMPT, RESPONSE_SYSTEM_PROMPT, LISTING_SYSTEM_PROMPT, ADVISOR_SYSTEM_PROMPT, OllamaClient
from app.ai.contracts import AIProviderError, ProviderHealth
from app.ai.opencode import OpenCodeClient
from app.ai.antigravity import AntigravityClient
from app.ai.gemini import GeminiClient, GroqBackup

logger = logging.getLogger(__name__)
NO_TOOLS = (
    "\nBạn nhận đầy đủ dữ liệu từ backend trong tin nhắn. "
    "Không dùng bất kỳ công cụ OpenCode nào, không đọc/sửa file, không chạy shell, "
    "không yêu cầu quyền hoặc gọi agent khác. Chỉ trả lời trực tiếp."
)


async def opencode_version(binary):
    """Reject incompatible v2 before trying v1 session/permission endpoints."""
    process = await asyncio.create_subprocess_exec(
        binary, "--version", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout=5)
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
    version = output.decode(errors="replace").strip()
    if process.returncode != 0 or not re.fullmatch(r"1\.\d+\.\d+", version):
        raise RuntimeError(
            "Backend dùng API OpenCode 1.x (đã kiểm chứng 1.18.30). "
            "Cài npm install -g opencode-ai@1.18.30 hoặc đặt OPENCODE_BINARY tới binary 1.x; "
            "OpenCode v2 chưa tương thích."
        )
    return version


def signal_opencode(process, *, force=False):
    if os.name == 'nt':
        process.kill() if force else process.terminate()
    else:
        os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)


class UnavailableOpenCodeProvider:
    """Keep the API usable through deterministic fallback after startup failure."""

    provider = "opencode"
    natural_responses = True
    prefer_model_intent = True

    def __init__(self, model):
        self.model = model

    async def check_health(self):
        return ProviderHealth(availability="unavailable", model_available=False)

    async def classify(self, _message, *, today):
        raise AIProviderError("provider_unavailable")

    async def respond(self, _message, *, history, facts):
        raise AIProviderError("provider_unavailable")


def opencode_config(model):
    full_model = "opencode/" + model
    # V1 injects a "maximum steps reached" assistant prefill on the last step.
    # With steps=1, even the first reply is forced into a premature wrap-up.
    # Two avoids that on the normal first/only generation. Tools still require
    # permission, are never approved, and are rejected by the request watchdog.
    return {
        "model": full_model, "small_model": full_model,
        "enabled_providers": ["opencode"],
        "share": "disabled", "autoupdate": False, "snapshot": False,
        "permission": "ask",
        "agent": {
            "sellerpilot-classifier": {
                "description": "SellerPilot intent classifier", "mode": "primary",
                "model": full_model, "prompt": CLASSIFIER_SYSTEM_PROMPT + NO_TOOLS,
                "permission": "ask", "steps": 2,
            },
            "sellerpilot-chat": {
                "description": "SellerPilot seller conversation", "mode": "primary",
                "model": full_model, "prompt": RESPONSE_SYSTEM_PROMPT + NO_TOOLS,
                "permission": "ask", "steps": 2,
            },
            "sellerpilot-listing": {
                "description": "SellerPilot product copy and image understanding", "mode": "primary",
                "model": full_model, "prompt": LISTING_SYSTEM_PROMPT + NO_TOOLS,
                "permission": "ask", "steps": 2,
            },
            "sellerpilot-advisor": {
                "description": "SellerPilot personal context extraction", "mode": "primary",
                "model": full_model, "prompt": ADVISOR_SYSTEM_PROMPT + NO_TOOLS,
                "permission": "ask", "steps": 2,
            },
        },
    }


@asynccontextmanager
async def managed_opencode(settings):
    binary = shutil.which(settings.opencode_binary)
    if not binary:
        raise RuntimeError("Không tìm thấy OpenCode. Cài OpenCode hoặc đặt AI_PROVIDER=ollama.")
    version = await opencode_version(binary)
    # Choose an unused local port; never reuse or stop the user's OpenCode session.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    password = secrets.token_urlsafe(32)
    env = os.environ.copy()
    env.update({
        "OPENCODE_SERVER_USERNAME": "sellerpilot",
        "OPENCODE_SERVER_PASSWORD": password,
        "OPENCODE_CONFIG_CONTENT": json.dumps(opencode_config(settings.opencode_model), ensure_ascii=False),
    })
    with tempfile.TemporaryDirectory(prefix="sellerpilot-opencode-") as workspace:
        process = await asyncio.create_subprocess_exec(
            binary, "serve", "--pure", "--hostname", "127.0.0.1", "--port", str(port),
            cwd=workspace, env=env, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
        )
        try:
            async with httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}", auth=("sellerpilot", password),
                timeout=settings.opencode_generation_timeout_seconds, trust_env=False,
            ) as http:
                async with asyncio.timeout(20):
                    while True:
                        if process.returncode is not None:
                            raise RuntimeError("OpenCode server không khởi động được. Kiểm tra bản cài OpenCode.")
                        try:
                            response = await http.get("/global/health", timeout=1)
                            if response.status_code == 200 and response.json().get("healthy") is True:
                                break
                        except (httpx.HTTPError, ValueError):
                            pass
                        await asyncio.sleep(0.25)
                logger.info("OpenCode %s ready on localhost; model=%s (free only)", version, settings.opencode_model)
                yield OpenCodeClient(http, settings.opencode_model, timeout=settings.opencode_generation_timeout_seconds)
        finally:
            if process.returncode is None:
                try:
                    signal_opencode(process)
                    await asyncio.wait_for(process.wait(), timeout=5)
                except ProcessLookupError:
                    pass
                except TimeoutError:
                    signal_opencode(process, force=True)
                    await process.wait()


@asynccontextmanager
async def create_provider(settings):
    if settings.ai_provider == 'gemini':
        async with httpx.AsyncClient(trust_env=False, follow_redirects=False,
                timeout=httpx.Timeout(settings.gemini_generation_timeout_seconds, connect=5),
                limits=httpx.Limits(max_connections=8, max_keepalive_connections=4)) as http:
            backup = (GroqBackup(http, settings.groq_api_key, settings.groq_model,
                       max_tokens=settings.gemini_max_output_tokens) if settings.groq_fallback_enabled else None)
            credentials = [(settings.gemini_api_key, settings.gemini_project_id),
                (settings.gemini_api_key_2, settings.gemini_project_id_2),
                (settings.gemini_api_key_3, settings.gemini_project_id_3)]
            if not any(key.get_secret_value().strip() for key, _ in credentials):
                logger.warning('Gemini API key missing: add GEMINI_API_KEY to root .env; see docs/GEMINI_API_SETUP.md')
            yield GeminiClient(http, settings.gemini_api_key, settings.gemini_model,
                timeout=settings.gemini_generation_timeout_seconds,
                max_tokens=settings.gemini_max_output_tokens,
                advice_max_tokens=settings.gemini_advice_max_output_tokens,
                backup=backup, credentials=credentials)
    elif settings.ai_provider == "antigravity":
        provider = AntigravityClient(settings.antigravity_binary, settings.antigravity_model,
                                     timeout=settings.antigravity_generation_timeout_seconds)
        try:
            await provider.initialize()
        except AIProviderError as error:
            logger.warning('Antigravity startup unavailable: reason=%s stage=%s', error.reason, error.stage)
        yield provider
    elif settings.ai_provider == "opencode":
        stack = AsyncExitStack()
        try:
            provider = await stack.enter_async_context(managed_opencode(settings))
        except (RuntimeError, OSError, TimeoutError) as error:
            logger.error("OpenCode startup failed: %s; using deterministic fallback", type(error).__name__)
            yield UnavailableOpenCodeProvider(settings.opencode_model)
            return
        try:
            yield provider
        finally:
            await stack.aclose()
    else:
        async with httpx.AsyncClient(
            base_url=settings.ollama_host, timeout=settings.ollama_generation_timeout_seconds,
            trust_env=False,
        ) as http:
            yield OllamaClient(
                http, settings.ollama_model,
                health_timeout_seconds=settings.ollama_health_timeout_seconds,
                generation_timeout_seconds=settings.ollama_generation_timeout_seconds,
                context_length=settings.ollama_context_length,
                max_output_tokens=settings.ollama_max_output_tokens,
                keep_alive=settings.ollama_keep_alive,
            )
